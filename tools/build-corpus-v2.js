/**
 * v2：按真实剧情顺序重建语料
 * 修的三件事：
 *  1. 顺序 —— 之前按 SMW 返回的字母序抓，语料是"书、争、仇、公…"；现在按 前置任务/后续任务 链 + (版本, 任务编号) 排序
 *  2. step —— 之前所有记录都被写成「步骤1」（闭包变量 bug），现在每节标题单独记录 step_title/step_idx
 *  3. 附加 —— 记录 location（任务描述里的地点）、extra（是否在 {{折叠}} 额外对话里）
 */
const fs = require('fs');
const path = require('path');

const RAW = path.join(__dirname, '..', 'data', 'raw');
const OUT = path.join(__dirname, '..', 'data', 'corpus');
const CACHE = path.join(RAW, 'wt-cache');

function cleanInline(s) {
  let t = String(s || '');
  for (let i = 0; i < 6; i++) {
    const before = t;
    t = t.replace(/\{\{([^{}]*?)\}\}/g, (m, inner) => {
      const parts = inner.split('|');
      const name = parts[0].trim();
      if (['颜色', '注音', '黑幕', '文本样式', 'ruby'].includes(name)) return parts[parts.length - 1];
      if (['图标', '道具', '物品', '技能', 'PAGENAME'].includes(name)) return '';
      return parts.slice(1).filter((p) => p && !/^[a-zA-Z]+=/.test(p)).pop() || '';
    });
    if (t === before) break;
  }
  t = t.replace(/\[\[([^\]|]*)\|([^\]]*)\]\]/g, '$2').replace(/\[\[([^\]]*)\]\]/g, '$1');
  t = t.replace(/<[^>]+>/g, '').replace(/'''?/g, '');
  return t.trim();
}

function parseTemplateParams(body) {
  const out = {};
  let depth = 0, key = null, buf = '';
  for (const ch of body) {
    if (ch === '{') depth++;
    if (ch === '}') depth--;
    if (ch === '|' && depth === 0) {
      if (key !== null) out[key] = buf.trim();
      key = ''; buf = '';
      continue;
    }
    if (ch === '=' && depth === 0 && key === '' && buf.trim()) { key = buf.trim(); buf = ''; continue; }
    buf += ch;
  }
  if (key) out[key] = buf.trim();
  return out;
}

// 折叠块内的行标记（用于区分"额外对话"和主线）
function extraMask(lines) {
  const mask = new Array(lines.length).fill(false);
  const stack = [];
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    for (let ci = 0; ci < line.length - 1; ci++) {
      if (line[ci] === '{' && line[ci + 1] === '{') { stack.push(line.slice(ci + 2, ci + 4) === '折叠'); ci++; continue; }
      if (line[ci] === '}' && line[ci + 1] === '}') { stack.pop(); ci++; continue; }
    }
    mask[li] = stack.some(Boolean);
  }
  return mask;
}

function parseQuest(title, wt) {
  const meta = {};
  const mT = wt.match(/\{\{任务\n([\s\S]*?)\n\}\}/);
  if (mT) Object.assign(meta, parseTemplateParams(mT[1]));

  const recs = [];
  const parts = wt.split(/^==\s*([^=\n]+?)\s*==\s*$/m);
  const sections = [];
  if (parts.length > 2) for (let i = 1; i < parts.length; i += 2) sections.push({ head: parts[i].trim(), body: parts[i + 1] || '' });
  else sections.push({ head: '', body: wt });

  sections.forEach((sec, si) => {
    const lines = sec.body.split(/\r?\n/);
    const mask = extraMask(lines);
    const stepIdx = si + 1;
    const stepTitle = sec.head.replace(/^\d+[.、]\s*/, '').trim();
    const push = (r) => recs.push({ ...r, step_idx: stepIdx, step_title: stepTitle });

    let i = 0;
    while (i < lines.length) {
      const line = lines[i].trim();
      if (!line) { i++; continue; }

      const mDesc = line.match(/\{\{任务描述\|([^|]*)\|?([^}]*)\}\}/);
      if (mDesc) {
        push({ kind: 'narration', speaker: '', text: cleanInline(mDesc[1]), location: cleanInline(mDesc[2]), extra: mask[i] });
        i++; continue;
      }

      if (line.startsWith('{{剧情选项')) {
        let block = line, depth = (line.match(/\{\{/g) || []).length - (line.match(/\}\}/g) || []).length;
        const startLine = i;
        while (depth > 0 && i + 1 < lines.length) { i++; block += '\n' + lines[i]; depth = (block.match(/\{\{/g) || []).length - (block.match(/\}\}/g) || []).length; }
        const optRe = /\|\s*选项\d+\s*=\s*([^\n|]*)/g;
        let m;
        while ((m = optRe.exec(block))) {
          const txt = cleanInline(m[1]);
          if (txt) push({ kind: 'option', speaker: '开拓者', text: txt, extra: mask[startLine] });
        }
        const innerRe = /\*\s*([^*：:{}\n]{1,16}?)\s*[：:]\s*([^\n*{}]+)/g;
        while ((m = innerRe.exec(block))) {
          const spk = cleanInline(m[1]), txt = cleanInline(m[2]);
          if (spk && txt) push({ kind: 'dialogue', speaker: spk, text: txt, extra: mask[startLine] });
        }
        i++; continue;
      }

      const mD = line.match(/^\*\s*([^*：:（(\[{|\n]{1,16}?)\s*[：:]\s*(.+)$/);
      if (mD) {
        const spk = cleanInline(mD[1]), txt = cleanInline(mD[2]);
        if (spk && txt && spk.length <= 12 && !/[，。！？、]/.test(spk)) {
          push({ kind: 'dialogue', speaker: spk, text: txt, extra: mask[i] });
          i++; continue;
        }
      }
      if (line.startsWith('*') && line.length > 2) {
        const t = cleanInline(line.replace(/^\*+\s*/, ''));
        if (t) push({ kind: 'narration', speaker: '', text: t, extra: mask[i] });
      }
      i++;
    }
  });

  return {
    meta: {
      task: title,
      version: cleanInline(meta['所属版本'] || ''),
      series: cleanInline(meta['系列任务'] || ''),
      series_no: cleanInline(meta['任务编号'] || ''),
      prev: cleanInline(meta['前置任务'] || ''),
      next: cleanInline(meta['后续任务'] || ''),
      cast: cleanInline(meta['出场人物'] || ''),
      region: cleanInline(meta['任务地区'] || ''),
    },
    records: recs,
  };
}

(async () => {
  // 1) 读全部缓存页
  const files = fs.readdirSync(CACHE).filter((f) => f.endsWith('.txt'));
  const parsed = new Map();
  for (const f of files) {
    const title = decodeURIComponent(f.replace(/\.txt$/, ''));
    parsed.set(title, parseQuest(title, fs.readFileSync(path.join(CACHE, f), 'utf8')));
  }
  const all = [...parsed.entries()];

  // 2) 只保留真正的任务页（有任务编号；排除系列汇总页）
  const tasks = all.filter(([, p]) => p.meta.series_no && p.meta.version);
  const skipped = all.filter(([, p]) => !(p.meta.series_no && p.meta.version)).map(([t]) => t);
  console.log(`缓存页=${all.length}  有效任务页=${tasks.length}  跳过(系列汇总页)=${skipped.length}`);
  if (skipped.length) console.log('  跳过: ' + skipped.join(' / '));

  // 3) 用 前置/后续 串成剧情链
  const byTitle = new Map(tasks.map(([t, p]) => [t, p]));
  const nextOf = new Map();
  const prevOf = new Map();
  for (const [t, p] of tasks) {
    if (p.meta.next) nextOf.set(t, p.meta.next);
    if (p.meta.prev) prevOf.set(t, p.meta.prev);
  }
  const heads = tasks.filter(([t]) => !prevOf.has(t)).map(([t]) => t);
  console.log(`链头(无前置)=${heads.length}: ${heads.join(' / ')}`);

  const order = [];
  const visited = new Set();
  let cur = heads[0];
  while (cur && byTitle.has(cur) && !visited.has(cur)) {
    order.push(cur); visited.add(cur);
    cur = nextOf.get(cur);
  }
  const chainOk = order.length === tasks.length;
  console.log(`链覆盖=${order.length}/${tasks.length} ${chainOk ? '✓ 单链完整' : '✗ 有断裂，将按(版本,编号)兜底'}`);

  let finalOrder = order;
  if (!chainOk) {
    const rest = tasks.map(([t]) => t).filter((t) => !visited.has(t));
    rest.sort((a, b) => {
      const A = byTitle.get(a).meta, B = byTitle.get(b).meta;
      return A.version.localeCompare(B.version, undefined, { numeric: true }) || A.series_no.localeCompare(B.series_no, undefined, { numeric: true });
    });
    finalOrder = [...order, ...rest];
  }

  // 4) 按剧情顺序输出语料
  const records = [];
  const metas = [];
  let globalIdx = 0;
  for (const t of finalOrder) {
    const p = byTitle.get(t);
    metas.push(p.meta);
    let n = 0;
    for (const r of p.records) {
      if (!r.text) continue;
      records.push({ id: ++globalIdx, order: finalOrder.indexOf(t) + 1, ...p.meta, idx: ++n, ...r });
    }
  }

  fs.writeFileSync(path.join(OUT, 'amphoreus.jsonl'), records.map((r) => JSON.stringify(r)).join('\n'), 'utf8');
  fs.writeFileSync(path.join(OUT, 'quest-order.json'), JSON.stringify(metas, null, 2), 'utf8');
  fs.writeFileSync(
    path.join(OUT, 'amphoreus.lines.txt'),
    records.map((r) => `[${r.version}#${r.series_no}] ${r.task} | ${r.step_title} | ${r.speaker || '【旁白】'}: ${r.text}`).join('\n'),
    'utf8'
  );

  // 5) 校验 + 统计
  console.log('\n== 校验 ==');
  const vers = [...new Set(metas.map((m) => m.version))];
  console.log('任务页版本顺序: ' + vers.join(' → '));
  const mono = metas.every((m, i) => i === 0 || +m.version >= +metas[i - 1].version);
  console.log('版本单调递增: ' + (mono ? '✓' : '✗'));
  const steps = records.filter((r) => r.step_idx > 1).length;
  console.log(`step_title 生效: 非"步骤1"的记录=${steps} / ${records.length}`);
  console.log(`额外对话标记 extra=true: ${records.filter((r) => r.extra).length} 条`);
  console.log(`带 location 的旁白: ${records.filter((r) => r.location).length} 条`);

  console.log('\n== 结果 ==');
  const kind = {};
  records.forEach((r) => (kind[r.kind] = (kind[r.kind] || 0) + 1));
  console.log(`任务页=${metas.length}  记录=${records.length}  字数=${records.reduce((s, r) => s + r.text.length, 0)}`);
  console.log('类型=' + JSON.stringify(kind));
  const perVer = {};
  records.forEach((r) => (perVer[r.version] = (perVer[r.version] || 0) + 1));
  console.log('各版本记录数: ' + Object.entries(perVer).map(([v, c]) => `${v}:${c}`).join('  '));
  console.log('\n前 8 页顺序:');
  metas.slice(0, 8).forEach((m, i) => console.log(`  ${i + 1}. [${m.version} #${m.series_no}] ${m.task}  (${m.series})`));
})();
