/**
 * v3：修正 v2 的两个问题
 *  - 章节切分：之前只认 ==二级==，而流程步骤是 ===三级===，导致整页被当成 1 节（step 全丢）
 *    → 改为逐行扫描标题，同时记录 chapter(二级) 与 step(三级及以下)
 *  - 剧情链：前置/后续 字段是 "*[[标题]]"，带前缀星号导致标题不匹配，链只串到 1 页
 *    → 清洗掉 * 与多余链接后再建链
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
// 用于链接型字段（前置/后续）：直接取第一个 [[...]] 目标
// 注意：不能按中文逗号切——任务标题本身大量含「，」
function cleanLink(s) {
  const raw = String(s || '');
  const m = raw.match(/\[\[([^\]|]+)/);
  if (m) return m[1].trim();
  return cleanInline(raw).replace(/^\*+\s*/, '').split('\n')[0].trim();
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

const HEADING = /^(={2,6})\s*([^=\n]+?)\s*\1\s*$/;

function parseQuest(title, wtRaw) {
  const meta = {};
  const mT = wtRaw.match(/\{\{任务\n([\s\S]*?)\n\}\}/);
  if (mT) Object.assign(meta, parseTemplateParams(mT[1]));

  // 关键：把 {{任务}} 元数据模板整块剥掉再扫描正文
  // 否则模板里「任务流程=*xxx」的清单会被当成旁白混进语料
  let wt = wtRaw;
  if (mT) wt = wt.replace(mT[0], '');
  wt = wt.replace(/\{\{系列任务[\s\S]*?\n\}\}/g, '');

  const lines = wt.split(/\r?\n/);
  const mask = extraMask(lines);
  const recs = [];
  let chapter = '';
  let curScene = '';
  let stepTitle = '';
  let stepIdx = 0;

  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) { i++; continue; }

    const hm = line.match(HEADING);
    if (hm) {
      const level = hm[1].length;
      const text = cleanInline(hm[2]);
      if (level <= 2) { chapter = text; stepTitle = text; stepIdx++; }
      else { stepTitle = text; stepIdx++; }
      i++; continue;
    }

    const push = (r) => recs.push({ ...r, chapter, step_idx: stepIdx, step_title: stepTitle, extra: mask[i] });

    const mDesc = line.match(/\{\{任务描述\|([^|]*)\|?([^}]*)\}\}/);
    if (mDesc) { push({ kind: 'narration', speaker: '', text: cleanInline(mDesc[1]), location: cleanInline(mDesc[2]) }); i++; continue; }

    // {{角色对话|左|角色|文本|台词}} —— 气泡式对白（带场景名）
    if (line.startsWith('{{角色对话')) {
      let block = line;
      let depth = (block.match(/\{\{/g) || []).length - (block.match(/\}\}/g) || []).length;
      while (depth > 0 && i + 1 < lines.length) { i++; block += '\n' + lines[i]; depth = (block.match(/\{\{/g) || []).length - (block.match(/\}\}/g) || []).length; }
      const inner = block.replace(/^\{\{角色对话\s*/, '').replace(/\}\}\s*$/, '');
      const parts = inner.replace(/^\|/, '').split('|').map((s) => s.trim());
      const kindTag = parts[0];
      if (kindTag === '模板开始') { curScene = cleanInline(parts[1] || ''); }
      else if (kindTag === '模板结束') { curScene = ''; }
      else if (['左', '右', '中'].includes(kindTag) && parts[1]) {
        // 格式: 方向 | 角色名 | 类型(文本/图片) | 台词
        const type = parts[2];
        const txt = cleanInline(parts.slice(3).join('|'));
        if (txt && (type === undefined || type === '文本')) push({ kind: 'dialogue', speaker: cleanInline(parts[1]), text: txt, scene: curScene });
      }
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
        if (txt) recs.push({ kind: 'option', speaker: '开拓者', text: txt, chapter, step_idx: stepIdx, step_title: stepTitle, extra: mask[startLine] });
      }
      const innerRe = /\*\s*([^*：:{}\n]{1,16}?)\s*[：:]\s*([^\n*{}]+)/g;
      while ((m = innerRe.exec(block))) {
        const spk = cleanInline(m[1]), txt = cleanInline(m[2]);
        if (spk && txt) recs.push({ kind: 'dialogue', speaker: spk, text: txt, chapter, step_idx: stepIdx, step_title: stepTitle, extra: mask[startLine] });
      }
      i++; continue;
    }

    const mD = line.match(/^\*\s*([^*：:（(\[{|\n]{1,16}?)\s*[：:]\s*(.+)$/);
    if (mD) {
      const spk = cleanInline(mD[1]), txt = cleanInline(mD[2]);
      if (spk && txt && spk.length <= 12 && !/[，。！？、]/.test(spk)) { push({ kind: 'dialogue', speaker: spk, text: txt }); i++; continue; }
    }
    if (line.startsWith('*') && line.length > 2) {
      const t = cleanInline(line.replace(/^\*+\s*/, ''));
      if (t) push({ kind: 'narration', speaker: '', text: t });
    }
    i++;
  }

  return {
    meta: {
      task: title,
      version: cleanInline(meta['所属版本'] || ''),
      series: cleanInline(meta['系列任务'] || ''),
      series_no: cleanInline(meta['任务编号'] || ''),
      prev: cleanLink(meta['前置任务'] || ''),
      next: cleanLink(meta['后续任务'] || ''),
      cast: cleanInline(meta['出场人物'] || ''),
      region: cleanInline(meta['任务地区'] || ''),
    },
    records: recs,
  };
}

(async () => {
  const files = fs.readdirSync(CACHE).filter((f) => f.endsWith('.txt'));
  const parsed = new Map();
  for (const f of files) {
    const title = decodeURIComponent(f.replace(/\.txt$/, ''));
    parsed.set(title, parseQuest(title, fs.readFileSync(path.join(CACHE, f), 'utf8')));
  }
  const all = [...parsed.entries()];
  const tasks = all.filter(([, p]) => p.meta.series_no && p.meta.version);
  const skipped = all.filter(([, p]) => !(p.meta.series_no && p.meta.version)).map(([t]) => t);
  console.log(`缓存页=${all.length}  有效任务页=${tasks.length}  跳过(系列汇总页)=${skipped.length}`);

  const byTitle = new Map(tasks.map(([t, p]) => [t, p]));
  const nextOf = new Map(), prevOf = new Map();
  for (const [t, p] of tasks) {
    if (p.meta.next && byTitle.has(p.meta.next)) nextOf.set(t, p.meta.next);
    if (p.meta.prev && byTitle.has(p.meta.prev)) prevOf.set(t, p.meta.prev);
  }
  console.log(`前置/后续链边=${nextOf.size}  有前置的页=${prevOf.size}/${tasks.length}`);

  // 拓扑排序：边 = 前置→后续；同层用 (版本, 任务编号) 兜底排序
  const key = (t) => {
    const m = byTitle.get(t).meta;
    return [parseFloat(m.version) || 0, parseInt(m.series_no, 10) || 0, t];
  };
  const cmp = (a, b) => {
    const A = key(a), B = key(b);
    return A[0] - B[0] || A[1] - B[1] || String(A[2]).localeCompare(String(B[2]));
  };
  const indeg = new Map(tasks.map(([t]) => [t, 0]));
  const outEdges = new Map(tasks.map(([t]) => [t, []]));
  for (const [t, n] of nextOf) { outEdges.get(t).push(n); indeg.set(n, (indeg.get(n) || 0) + 1); }
  let ready = tasks.map(([t]) => t).filter((t) => indeg.get(t) === 0).sort(cmp);
  console.log(`入度为 0 的起点=${ready.length}: ${ready.join(' / ')}`);
  const finalOrder = [];
  while (ready.length) {
    const t = ready.shift();
    finalOrder.push(t);
    for (const n of outEdges.get(t)) {
      indeg.set(n, indeg.get(n) - 1);
      if (indeg.get(n) === 0) { ready.push(n); ready.sort(cmp); }
    }
  }
  if (finalOrder.length !== tasks.length) {
    const rest = tasks.map(([t]) => t).filter((t) => !finalOrder.includes(t)).sort(cmp);
    console.log(`⚠ 有环/未覆盖 ${rest.length} 页，按(版本,编号)追加: ${rest.join(' / ')}`);
    finalOrder.push(...rest);
  }
  // 链一致性检查
  const pos = new Map(finalOrder.map((t, i) => [t, i]));
  const violations = [...nextOf.entries()].filter(([a, b]) => pos.get(b) <= pos.get(a));
  console.log(`链一致性违例=${violations.length}` + (violations.length ? ': ' + violations.map(([a, b]) => `${a}→${b}`).join('; ') : ' ✓'));

  const records = [], metas = [];
  let globalIdx = 0;
  finalOrder.forEach((t, oi) => {
    const p = byTitle.get(t);
    metas.push({ ...p.meta, order: oi + 1 });
    let n = 0;
    for (const r of p.records) {
      if (!r.text) continue;
      records.push({ id: ++globalIdx, order: oi + 1, task: t, version: p.meta.version, series: p.meta.series, series_no: p.meta.series_no, idx: ++n, ...r });
    }
  });

  fs.writeFileSync(path.join(OUT, 'amphoreus.jsonl'), records.map((r) => JSON.stringify(r)).join('\n'), 'utf8');
  fs.writeFileSync(path.join(OUT, 'quest-order.json'), JSON.stringify(metas, null, 2), 'utf8');
  fs.writeFileSync(
    path.join(OUT, 'amphoreus.lines.txt'),
    records.map((r) => `[${r.version}#${r.series_no}] ${r.task} | ${r.step_title} | ${r.speaker || '【旁白】'}: ${r.text}`).join('\n'),
    'utf8'
  );

  // 校验
  console.log('\n== 校验 ==');
  console.log('任务顺序版本: ' + [...new Set(metas.map((m) => m.version))].join(' → '));
  console.log('版本单调: ' + (metas.every((m, i) => i === 0 || +m.version >= +metas[i - 1].version) ? '✓' : '✗'));
  const stepDist = {};
  records.forEach((r) => (stepDist[r.step_idx] = (stepDist[r.step_idx] || 0) + 1));
  const stepVals = Object.keys(stepDist).map(Number).sort((a, b) => a - b);
  console.log(`step_idx 取值范围=${stepVals[0]}..${stepVals[stepVals.length - 1]}（共 ${stepVals.length} 个不同值）`);
  console.log(`step_idx>1 的记录=${records.filter((r) => r.step_idx > 1).length}/${records.length}`);
  const titles = [...new Set(records.map((r) => r.step_title))].filter((t) => t);
  console.log(`不同 step_title=${titles.length}  例: ${titles.slice(15, 19).join(' / ')}`);
  console.log(`extra=true: ${records.filter((r) => r.extra).length} 条`);
  console.log(`带 location: ${records.filter((r) => r.location).length} 条`);

  console.log('\n== 结果 ==');
  const kind = {}; records.forEach((r) => (kind[r.kind] = (kind[r.kind] || 0) + 1));
  console.log(`任务页=${metas.length}  记录=${records.length}  字数=${records.reduce((s, r) => s + r.text.length, 0)}`);
  console.log('类型=' + JSON.stringify(kind));
  const perVer = {}; records.forEach((r) => (perVer[r.version] = (perVer[r.version] || 0) + 1));
  console.log('各版本: ' + Object.entries(perVer).map(([v, c]) => `${v}:${c}`).join('  '));
  console.log('\n顺序核对（每版前 2 页）:');
  metas.forEach((m, i) => {
    if (i === 0 || m.version !== metas[i - 1].version) console.log(`  ${i + 1}. [${m.version} #${m.series_no}] ${m.task}  — ${m.series}`);
    else if (metas[i - 1].version === m.version && metas[i - 2] && metas[i - 2].version !== m.version) console.log(`  ${i + 1}. [${m.version} #${m.series_no}] ${m.task}`);
  });
})();
