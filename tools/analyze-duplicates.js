/**
 * analyze-duplicates.js — 只读分析：重复台词到底是哪来的
 * 输入 data/corpus/amphoreus.final.jsonl
 * 分为两类：
 *   类 A「同任务内重复」= dedupe 的 is_duplicate（任务+kind+speaker+text 相同）
 *   类 B「跨任务重复」= 同 speaker + 同 text 出现在 2 个以上任务页（这才是"轮回/口头禅"候选）
 */
const fs = require('fs');
const path = require('path');

const R = fs.readFileSync(path.join(__dirname, '..', 'data/corpus/amphoreus.final.jsonl'), 'utf8')
  .trim().split('\n').map(JSON.parse);

// ---------- 类 A：同任务内重复 ----------
const groups = new Map();
for (const r of R) {
  const k = [r.task, r.speaker, r.text].join('\u0001');
  if (!groups.has(k)) groups.set(k, []);
  groups.get(k).push(r);
}
const dupGroups = [...groups.values()].filter((g) => g.length > 1);
const dupRecords = dupGroups.reduce((s, g) => s + g.length - 1, 0);

const cls = {};
for (const g of dupGroups) {
  const kinds = new Set(g.map((r) => r.kind));
  const steps = new Set(g.map((r) => r.step_idx));
  const ids = g.map((r) => r.id).sort((a, b) => a - b);
  const adjacent = ids.some((v, i) => i > 0 && v - ids[i - 1] === 1);
  let c;
  if ([...kinds].some((k) => k === 'option' || k === 'sms_option')) c = '含选项(分支转录)';
  else if (steps.size > 1) c = '跨步骤重复';
  else if (adjacent) c = '同步骤相邻重复';
  else c = '同步骤非相邻重复';
  cls[c] = (cls[c] || 0) + 1;
}

// ---------- 类 B：跨任务重复 ----------
const cross = new Map();
for (const r of R) {
  if (!r.speaker || !r.text || r.text.length < 4) continue;
  const k = [r.speaker, r.text].join('\u0001');
  if (!cross.has(k)) cross.set(k, []);
  cross.get(k).push(r);
}
const crossGroups = [...cross.values()].filter((g) => new Set(g.map((r) => r.task)).size > 1);
const crossByVer = crossGroups.filter((g) => new Set(g.map((r) => r.version)).size > 1);

// ---------- 输出 ----------
console.log('总记录 =', R.length);
console.log('\n## 类 A：同任务内重复（is_duplicate 口径）');
console.log('重复组 =', dupGroups.length, ' 冗余记录 =', dupRecords);
console.log('分类 =', JSON.stringify(cls, null, 0));

console.log('\n### 类 A 最大的 12 组');
dupGroups.sort((a, b) => b.length - a.length);
for (const g of dupGroups.slice(0, 12)) {
  const r0 = g[0];
  const ids = g.map((r) => r.id);
  const steps = [...new Set(g.map((r) => r.step_title))];
  const kinds = [...new Set(g.map((r) => r.kind))];
  console.log(`- x${g.length} [${r0.version}#${r0.series_no}] ${r0.task} | speaker=${r0.speaker || '(空)'} | kind=${kinds.join('/')}`);
  console.log(`  text="${r0.text.slice(0, 40)}"`);
  console.log(`  ids=${ids.slice(0, 8).join(',')}${ids.length > 8 ? '...' : ''} | 涉及步骤数=${steps.length} | 步骤=${steps.slice(0, 3).map((s) => s.slice(0, 12)).join(' / ')}`);
}

console.log('\n## 类 B：跨任务重复（同 speaker+同 text 出现在 ≥2 个任务页）');
console.log('组 =', crossGroups.length, ' 其中跨版本 =', crossByVer.length);
const crossSorted = crossGroups.sort((a, b) => b.length - a.length);
console.log('\n### 类 B 最大的 15 组');
for (const g of crossSorted.slice(0, 15)) {
  const tasks = [...new Set(g.map((r) => r.task))];
  const vers = [...new Set(g.map((r) => r.version))];
  console.log(`- x${g.length} speaker=${g[0].speaker} 版本=${vers.join(',')} 任务数=${tasks.length}`);
  console.log(`  text="${g[0].text.slice(0, 46)}"`);
  console.log(`  任务=${tasks.slice(0, 3).map((t) => t.slice(0, 10)).join(' / ')}`);
}

// 类 B 里"分版本重复"的样例（才是轮回候选）
console.log('\n### 类 B 中「跨版本」样例（轮回/回忆候选，前 10 组）');
for (const g of crossByVer.sort((a, b) => b.length - a.length).slice(0, 10)) {
  const pairs = g.map((r) => `${r.version}:${r.task.slice(0, 8)}`).slice(0, 4);
  console.log(`- x${g.length} ${g[0].speaker}: "${g[0].text.slice(0, 36)}" | ${pairs.join(' , ')}`);
}
