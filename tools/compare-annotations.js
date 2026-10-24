/**
 * compare-annotations.js — 计算两套独立标注的一致性（A2）
 * 输入：data/config/annotation-labels.json（annotator）、data/config/annotation-labels.independent.json（独立盲标）
 * 输出：data/config/annotation-agreement.json、data/reports/annotation-agreement.md
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const rd = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));

const A = rd('data/config/annotation-labels.json').samples;
const B = rd('data/config/annotation-labels.independent.json').samples;
const mapB = new Map(B.map((x) => [x.segment_id, x]));
const pairs = A.map((a) => ({ a, b: mapB.get(a.segment_id) })).filter((p) => p.b);
const N = pairs.length;

// 等级完全一致
const exact = pairs.filter((p) => p.a.significance === p.b.significance).length;
// 相邻一致（差 ≤1）
const adjacent = pairs.filter((p) => Math.abs(p.a.significance - p.b.significance) <= 1).length;
// 二次加权 kappa
const K = 4;
const conf = Array.from({ length: K }, () => Array(K).fill(0));
for (const p of pairs) conf[p.a.significance][p.b.significance]++;
const obs = pairs.reduce((s, p) => s + (p.a.significance === p.b.significance ? 1 : 0), 0) / N;
const rowSum = conf.map((r) => r.reduce((s, v) => s + v, 0));
const colSum = conf[0].map((_, j) => conf.reduce((s, r) => s + r[j], 0));
const exp = rowSum.reduce((s, rv, i) => s + rv * colSum[i], 0) / (N * N);
// 未加权 kappa（Cohen）
const kappaUnweighted = (obs - exp) / (1 - exp);
// 加权 kappa：κ = 1 - (观测加权分歧 / 期望加权分歧)
const wq = (i, j) => ((i - j) * (i - j)) / ((K - 1) * (K - 1));
const wl = (i, j) => Math.abs(i - j) / (K - 1);
const weighted = (w) => {
  const obsD = pairs.reduce((s, p) => s + w(p.a.significance, p.b.significance), 0) / N;
  let expD = 0;
  for (let i = 0; i < K; i++) for (let j = 0; j < K; j++) expD += w(i, j) * rowSum[i] * colSum[j] / (N * N);
  return expD === 0 ? 1 : 1 - obsD / expD;
};
const kappaLinear = weighted(wl);
const kappaQuadratic = weighted(wq);

// 类型一致
const jac = (x, y) => {
  const X = new Set(x || []), Y = new Set(y || []);
  const inter = [...X].filter((v) => Y.has(v)).length;
  const uni = new Set([...X, ...Y]).size;
  return uni ? inter / uni : 1;
};
const typeExact = pairs.filter((p) => {
  const X = [...new Set((p.a.types || []).slice().sort())].join(',');
  const Y = [...new Set((p.b.types || []).slice().sort())].join(',');
  return X === Y;
}).length;
const jacMean = pairs.reduce((s, p) => s + jac(p.a.types, p.b.types), 0) / N;

// 分歧清单
const disagreements = pairs
  .filter((p) => p.a.significance !== p.b.significance)
  .map((p) => ({
    segment_id: p.a.segment_id,
    annotator_level: p.a.significance,
    independent_level: p.b.significance,
    diff: p.b.significance - p.a.significance,
    annotator_types: p.a.types,
    independent_types: p.b.types,
    annotator_note: p.a.note,
    independent_before: p.b.before_state,
    independent_after: p.b.after_state,
    independent_why: p.b.why_not_lower,
    independent_confidence: p.b.confidence,
  }))
  .sort((x, y) => Math.abs(y.diff) - Math.abs(x.diff));

const out = {
  note: 'A2 独立双标注一致性：annotator（读剧情 agent，task-8）vs independent-subagent（盲标，未读既有标签）',
  n_samples: N,
  level_exact_agreement: { count: exact, rate: +(exact / N).toFixed(4) },
  level_adjacent_agreement: { count: adjacent, rate: +(adjacent / N).toFixed(4) },
  kappa_linear: +kappaLinear.toFixed(4),
  kappa_quadratic: +kappaQuadratic.toFixed(4),
  confusion: conf,
  type_set_exact: { count: typeExact, rate: +(typeExact / N).toFixed(4) },
  type_jaccard_mean: +jacMean.toFixed(4),
  distribution: {
    annotator: A.reduce((m, x) => ((m[x.significance] = (m[x.significance] || 0) + 1), m), {}),
    independent: B.reduce((m, x) => ((m[x.significance] = (m[x.significance] || 0) + 1), m), {}),
  },
  n_disagreements: disagreements.length,
  disagreements,
};
fs.writeFileSync(path.join(ROOT, 'data/config/annotation-agreement.json'), JSON.stringify(out, null, 2), 'utf8');

// 报告
const md = [];
md.push('# 独立双标注一致性（A2）');
md.push('');
md.push('> annotator = 读剧情的 agent（task-8，曾阅读全剧情并做过 74 条标注）；independent-subagent = 盲标（只看 segment_id 与原文，未读既有标签/A-B 分数）。');
md.push('> 两套标签均按「三问机械化规则」重新定位：0 普通 / 1 局部 / 2 持续状态变化 / 3 不可逆或重释前文。');
md.push('');
md.push('## 总览');
md.push('');
md.push('| 指标 | 数值 |');
md.push('|---|---|');
md.push(`| 样本 | ${N} |`);
md.push(`| 等级完全一致 | ${exact}/${N} = **${(exact / N * 100).toFixed(1)}%** |`);
md.push(`| 等级相差≤1 | ${adjacent}/${N} = ${(adjacent / N * 100).toFixed(1)}% |`);
md.push(`| 未加权 kappa（Cohen） | ${kappaUnweighted.toFixed(3)} |`);
md.push(`| 线性加权 kappa | ${kappaLinear.toFixed(3)} |`);
md.push(`| 二次加权 kappa | **${kappaQuadratic.toFixed(3)}** |`);
md.push(`| 类型集合完全一致 | ${typeExact}/${N} = ${(typeExact / N * 100).toFixed(1)}% |`);
md.push(`| 类型 Jaccard 均值 | ${jacMean.toFixed(3)} |`);
md.push(`| 等级分布（annotator） | ${JSON.stringify(out.distribution.annotator)} |`);
md.push(`| 等级分布（independent） | ${JSON.stringify(out.distribution.independent)} |`);
md.push('');
md.push('## 混淆矩阵（行=annotator，列=independent）');
md.push('');
md.push('| | 0 | 1 | 2 | 3 |');
md.push('|---|---|---|---|---|');
conf.forEach((r, i) => md.push(`| **${i}** | ${r.join(' | ')} |`));
md.push('');
md.push('## 分歧清单（按等级差排序）');
md.push('');
md.push('| segment_id | annotator | independent | 差 | annotator 依据 | independent 的 before→after |');
md.push('|---|---|---|---|---|---|');
for (const d of disagreements) {
  md.push(`| \`${d.segment_id}\` | ${d.annotator_level} | ${d.independent_level} | ${d.diff > 0 ? '+' : ''}${d.diff} | ${(d.annotator_note || '').replace(/\|/g, '\\|').slice(0, 60)} | ${(d.independent_before || '').replace(/\|/g, '\\|').slice(0, 30)} → ${(d.independent_after || '').replace(/\|/g, '\\|').slice(0, 40)} |`);
}
md.push('');
md.push('## 怎么用这批数据');
md.push('');
md.push('1. 报告里把两套标注都写成「**LLM 辅助标注**」，本文件是**重复标注稳定性/一致性**证据，不是准确率；');
md.push('2. 分歧样本即人工复核优先集（见上表）；用户只需裁定这些 + 等级 3 + A/B 关键差异；');
md.push('3. 主结果仍用 annotator 标签（任务 8 已复核定稿），independent 标签用于敏感性分析（换一套标签看结论是否稳定）。');
fs.writeFileSync(path.join(ROOT, 'data/reports/annotation-agreement.md'), md.join('\n'), 'utf8');

console.log(`一致性：等级完全 ${exact}/${N} (${(exact / N * 100).toFixed(1)}%)，相差≤1 ${adjacent}/${N}，二次加权 kappa ${kappaQuadratic.toFixed(3)}，类型集合 ${typeExact}/${N}，Jaccard ${jacMean.toFixed(3)}，分歧 ${disagreements.length}`);
console.log('分歧（前 8 条）:');
disagreements.slice(0, 8).forEach((d) => console.log(`  ${d.segment_id}  ${d.annotator_level} vs ${d.independent_level} (${d.diff > 0 ? '+' : ''}${d.diff})`));
