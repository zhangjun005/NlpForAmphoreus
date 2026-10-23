/**
 * BWiki 剧情语料抓取 + 解析
 * 输入: data/raw/amphoreus-quest-index.json (74 个翁法罗斯开拓任务页)
 * 输出: data/corpus/amphoreus.jsonl  每行一条: {task, series, version, step, idx, speaker, text, kind}
 *       data/corpus/amphoreus.lines.txt  便于人工抽查的 "任务|步骤|角色:台词"
 * 数据源: https://wiki.biligame.com/sr (MediaWiki API, prop=wikitext)
 */
const fs = require('fs');
const path = require('path');

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0';
const RAW = path.join(__dirname, '..', 'data', 'raw');
const OUT = path.join(__dirname, '..', 'data', 'corpus');
const CACHE = path.join(RAW, 'wt-cache');
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(CACHE, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function apiWikitext(title) {
  const cf = path.join(CACHE, encodeURIComponent(title) + '.txt');
  if (fs.existsSync(cf)) return fs.readFileSync(cf, 'utf8');
  const u =
    'https://wiki.biligame.com/sr/api.php?action=parse&format=json&formatversion=2&prop=wikitext&page=' +
    encodeURIComponent(title);
  for (let attempt = 0; attempt < 3; attempt++) {
    const r = await fetch(u, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(40000) });
    const j = await r.json();
    if (j.error) {
      if (j.error.code === 'missingtitle') return null;
      await sleep(800 * (attempt + 1));
      continue;
    }
    fs.writeFileSync(cf, j.parse.wikitext, 'utf8');
    return j.parse.wikitext;
  }
  return null;
}

// ---- 模板/标记清理 ----
function cleanInline(s) {
  let t = s;
  // {{颜色|x|Y}} / {{注音|A|B}} / {{黑幕|Y}} 等：取最后一个纯文本参数
  for (let i = 0; i < 6; i++) {
    const before = t;
    t = t.replace(/\{\{([^{}]*?)\}\}/g, (m, inner) => {
      const parts = inner.split('|');
      const name = parts[0].trim();
      if (['颜色', '注音', '黑幕', '文本样式', 'ruby'].includes(name)) return parts[parts.length - 1];
      if (['图标', '道具', '物品', '技能'].includes(name)) return '';
      if (name.startsWith('#') || name === '!' ) return '';
      return parts.slice(1).filter((p) => p && !/^[a-zA-Z]+=/.test(p)).pop() || '';
    });
    if (t === before) break;
  }
  t = t.replace(/\[\[([^\]|]*)\|([^\]]*)\]\]/g, '$2').replace(/\[\[([^\]]*)\]\]/g, '$1');
  t = t.replace(/<[^>]+>/g, '');
  t = t.replace(/'''?/g, '');
  return t.trim();
}

const SPEAKER_RE = /^\*\s*([^*：:（(\[{|\n]{1,16}?)\s*[：:]\s*(.+)$/;

function parseTemplateParams(body) {
  // 极简 1 层参数解析：|key=value（value 可含嵌套模板）
  const out = {};
  let depth = 0, cur = '', key = null, buf = '';
  for (const ch of body) {
    if (ch === '{') depth++;
    if (ch === '}') depth--;
    if (ch === '|' && depth === 0) {
      if (key === null) { cur = ''; } else { out[key] = buf.trim(); }
      key = ''; buf = '';
      continue;
    }
    if (ch === '=' && depth === 0 && key === '' && buf.trim()) { key = buf.trim(); buf = ''; continue; }
    buf += ch;
  }
  if (key) out[key] = buf.trim();
  return out;
}

function parseQuest(title, wt) {
  // 1) 任务模板元数据
  const meta = {};
  const mT = wt.match(/\{\{任务\n([\s\S]*?)\n\}\}/);
  if (mT) Object.assign(meta, parseTemplateParams(mT[1]));

  const recs = [];
  // 2) 按 == 章节切分（只切二级标题）
  const parts = wt.split(/^==\s*([^=\n]+?)\s*==\s*$/m);
  // parts[0] 为模板区，之后交替 [标题, 内容]
  let stepIdx = 0;
  const sections = [];
  if (parts.length > 2) {
    for (let i = 1; i < parts.length; i += 2) sections.push({ head: parts[i].trim(), body: parts[i + 1] || '' });
  } else {
    sections.push({ head: '', body: wt });
  }

  for (const sec of sections) {
    stepIdx++;
    const lines = sec.body.split(/\r?\n/);
    let i = 0;
    let branchDepth = 0;
    while (i < lines.length) {
      const raw = lines[i];
      const line = raw.trim();
      if (!line) { i++; continue; }

      // 任务描述 / 场景旁白
      const mDesc = line.match(/\{\{任务描述\|([^|]*)\|?([^}]*)\}\}/);
      if (mDesc) {
        recs.push({ kind: 'narration', speaker: '', text: cleanInline(mDesc[1]) });
        i++; continue;
      }

      // 剧情选项块
      if (line.startsWith('{{剧情选项')) {
        branchDepth++;
        // 收集该块内所有 |选项N= / |剧情N=（可能跨行、含嵌套）
        let block = line, depth = (line.match(/\{\{/g) || []).length - (line.match(/\}\}/g) || []).length;
        while (depth > 0 && i + 1 < lines.length) { i++; block += '\n' + lines[i]; depth = (block.match(/\{\{/g) || []).length - (block.match(/\}\}/g) || []).length; }
        const optRe = /\|\s*选项\d+\s*=\s*([^\n|]*)/g;
        let m;
        while ((m = optRe.exec(block))) {
          const txt = cleanInline(m[1]);
          if (txt) recs.push({ kind: 'option', speaker: '开拓者', text: txt, branch: branchDepth });
        }
        // 选项内部的分支台词：以 *角色： 形式内联
        const innerRe = /\*\s*([^*：:{}\n]{1,16}?)\s*[：:]\s*([^\n*{}]+)/g;
        while ((m = innerRe.exec(block))) {
          const spk = cleanInline(m[1]), txt = cleanInline(m[2]);
          if (spk && txt) recs.push({ kind: 'dialogue', speaker: spk, text: txt, branch: branchDepth });
        }
        i++; continue;
      }

      // 常规台词行
      const mD = line.match(SPEAKER_RE);
      if (mD) {
        const spk = cleanInline(mD[1]);
        const txt = cleanInline(mD[2]);
        if (spk && txt && spk.length <= 12 && !/[，。！？、]/.test(spk)) {
          recs.push({ kind: 'dialogue', speaker: spk, text: txt, branch: branchDepth });
          i++; continue;
        }
      }
      // 无归属旁白行（*开头或以…… 开头）
      if (line.startsWith('*') && line.length > 2) {
        const t = cleanInline(line.replace(/^\*+\s*/, ''));
        if (t) recs.push({ kind: 'narration', speaker: '', text: t });
      }
      i++;
    }
  }

  const series = cleanInline(meta['系列任务'] || '');
  const version = cleanInline(meta['所属版本'] || '');
  const out = [];
  let n = 0;
  for (const r of recs) {
    if (!r.text || r.text.length < 1) continue;
    out.push({
      task: title,
      series,
      version,
      step: r.kind === 'option' ? `选项` : `步骤${stepIdx}`,
      idx: ++n,
      ...r,
    });
  }
  return { meta, records: out };
}

(async () => {
  const index = JSON.parse(fs.readFileSync(path.join(RAW, 'amphoreus-quest-index.json'), 'utf8'));
  const titles = index.map((r) => r.任务);
  console.log(`待抓任务页=${titles.length}`);

  const all = [];
  const metaAll = [];
  for (let k = 0; k < titles.length; k++) {
    const title = titles[k];
    let wt;
    try { wt = await apiWikitext(title); } catch (e) { console.log(`  !! ${title} 抓取异常 ${e.message}`); continue; }
    if (!wt) { console.log(`  !! ${title} 页面不存在`); continue; }
    const { meta, records } = parseQuest(title, wt);
    all.push(...records);
    metaAll.push({ task: title, ...meta });
    process.stdout.write(`\r  ${k + 1}/${titles.length}  ${title}  (${records.length} 条)            `);
    await sleep(180);
  }
  console.log('');

  fs.writeFileSync(path.join(OUT, 'amphoreus.jsonl'), all.map((r) => JSON.stringify(r)).join('\n'), 'utf8');
  fs.writeFileSync(path.join(OUT, 'quest-meta.json'), JSON.stringify(metaAll, null, 2), 'utf8');
  fs.writeFileSync(
    path.join(OUT, 'amphoreus.lines.txt'),
    all.map((r) => `${r.task}\t步骤${r.step}\t${r.speaker ? r.speaker : '【旁白】'}: ${r.text}`).join('\n'),
    'utf8'
  );

  // 统计
  const byKind = {};
  const bySpeaker = {};
  for (const r of all) {
    byKind[r.kind] = (byKind[r.kind] || 0) + 1;
    if (r.speaker) bySpeaker[r.speaker] = (bySpeaker[r.speaker] || 0) + 1;
  }
  const totalChars = all.reduce((s, r) => s + r.text.length, 0);
  console.log(`\n== 结果 ==`);
  console.log(`任务页=${metaAll.length}  记录=${all.length}  纯台词字数=${totalChars}`);
  console.log(`类型分布=${JSON.stringify(byKind)}`);
  const top = Object.entries(bySpeaker).sort((a, b) => b[1] - a[1]).slice(0, 25);
  console.log(`不同说话人=${Object.keys(bySpeaker).length}`);
  console.log('说话人 Top25:');
  top.forEach(([s, c]) => console.log(`   ${s}\t${c}`));
})();
