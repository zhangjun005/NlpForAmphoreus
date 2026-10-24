/**
 * build-annotation-materials.js
 * 产出两份人工标注材料：
 *   1) data/reports/annotation-sample.md       40–80 个步骤的分层抽样名单（含待填列）
 *      data/config/annotation-sample.json      机器可读版本（labels 留空）
 *   2) data/reports/oracle-fulfillment-review.md  13 条神谕的兑现候选表（人工判定）
 *      data/config/oracle-fulfillment.json     机器可读模板（fulfillment/type 留空）
 *
 * 抽样为确定性（按 segment_id 排序 + 等距抽取），无随机，保证可复现。
 * 口径见 docs/实验口径与评测方案.md §11.5（分层抽样）。
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const rd = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const SEG = rd('data/corpus/segments.jsonl').trim().split('\n').map(JSON.parse);
const ORACLES = rd('data/corpus/oracles.jsonl').trim().split('\n').map(JSON.parse);

const eligible = SEG.filter((s) => s.has_dialogue && !s.low_content && s.n_main > 0);

// ---------- 分层定义 ----------
const KNOWN_IDENTITY = ['3.7|魔女的孤诣课题|21']; // 昔涟诞生（已知案例，必须进标注集）

const pickStratified = (arr, quota) => {
  const a = arr.slice().sort((x, y) => x.segment_id.localeCompare(y.segment_id));
  if (a.length <= quota) return a;
  const stride = a.length / quota;
  const out = [];
  for (let i = 0; i < quota; i++) out.push(a[Math.floor(i * stride)]);
  return out;
};

const used = new Set();
const layers = [];
const addLayer = (name, desc, pool, quota) => {
  const cand = pool.filter((s) => !used.has(s.segment_id));
  const chosen = pickStratified(cand, quota);
  chosen.forEach((s) => used.add(s.segment_id));
  layers.push({ name, desc, pool: cand.length, chosen });
};

const hasOracle = (s) => (s.semantic_recall_oracle_count || 0) >= 1;
const hasMotif = (s) => (s.semantic_recall_motif_count || 0) >= 3;

// 先抽"特殊层"，再抽长度层，避免被普通片段占满
addLayer('L5 神谕相关', '命中神谕词表（兑现/引用候选）', eligible.filter(hasOracle), 12);
addLayer('L6 母题/记忆回收', '母题词表命中≥3 或已知身份揭示段（含昔涟诞生）',
  eligible.filter((s) => hasMotif(s) || KNOWN_IDENTITY.includes(s.segment_id)), 10);
addLayer('L4 长步骤(>30句)', '检查基线是否偏爱长步骤', eligible.filter((s) => s.n_dialogue > 30), 8);
addLayer('L3 中长(11–30句)', '主体之一', eligible.filter((s) => s.n_dialogue >= 11 && s.n_dialogue <= 30), 12);
addLayer('L2 中等(4–10句)', '主体之二', eligible.filter((s) => s.n_dialogue >= 4 && s.n_dialogue <= 10), 12);
addLayer('L1 短步骤(1–3句)', '检查基线是否偏爱短句', eligible.filter((s) => s.n_dialogue >= 1 && s.n_dialogue <= 3), 10);
addLayer('L7 普通推进(负样本)', '无神谕/母题命中且停顿比例低',
  eligible.filter((s) => !hasOracle(s) && !hasMotif(s) && (s.semantic_recall_count || 0) === 0 && s.pause_ratio <= 0.2), 10);

const total = layers.reduce((n, l) => n + l.chosen.length, 0);

// ---------- 输出：标注名单 ----------
const jsonSample = {
  note: '叙事显著性标注样本（分层抽样，确定性等距选取）；labels 留空待人工填写',
  protocol: 'docs/实验口径与评测方案.md §6 与 §11.5',
  labels_schema: {
    significance: '0 普通推进 / 1 局部信息或关系变化 / 2 叙事状态明显变化 / 3 重大转折或前文意义被重新解释',
    types: ['identity', 'memory', 'prophecy', 'relationship', 'world', 'sacrifice', 'motif'],
  },
  total,
  layers: layers.map((l) => ({ name: l.name, desc: l.desc, pool_size: l.pool, sampled: l.chosen.length })),
  samples: layers.flatMap((l) =>
    l.chosen.map((s) => ({
      segment_id: s.segment_id,
      layer: l.name,
      version: s.version,
      task: s.task,
      step_idx: s.step_idx,
      step_title: s.step_title,
      n_dialogue: s.n_dialogue,
      n_narration: s.n_narration,
      char_len: s.char_len,
      speakers: (s.speakers || []).slice(0, 6),
      signals: {
        oracle: s.semantic_recall_oracle_count || 0,
        motif: s.semantic_recall_motif_count || 0,
        structure: s.structure_count || 0,
        pause_ratio: s.pause_ratio || 0,
      },
      significance: null,
      types: [],
      note: '',
    }))
  ),
};
fs.mkdirSync(path.join(ROOT, 'data/reports'), { recursive: true });
fs.writeFileSync(path.join(ROOT, 'data/config/annotation-sample.json'), JSON.stringify(jsonSample, null, 2), 'utf8');

const mdSample = [];
mdSample.push('# 叙事显著性标注样本（分层抽样）');
mdSample.push('');
mdSample.push(`> 共 **${total}** 个步骤实例（来自 ${eligible.length} 个合格候选）。`);
mdSample.push('> 标注单位：**步骤实例**（`segment_id = version|task|step_idx`）；文本内容请对照 `data/corpus/amphoreus.final.lines.txt` 或直接查 jsonl 的 `main_records`。');
mdSample.push('> 等级：0 普通推进 / 1 局部信息或关系变化 / 2 叙事状态明显变化 / 3 重大转折或前文意义被重新解释。');
mdSample.push('> 类型（可多选）：identity 身份揭示 / memory 记忆 / prophecy 神谕兑现 / relationship 关系 / world 世界规则 / sacrifice 牺牲告别 / motif 母题回收。');
mdSample.push('');
mdSample.push('## 分层与配额');
mdSample.push('');
mdSample.push('| 层 | 说明 | 候选池 | 抽取 |');
mdSample.push('|---|---|---|---|');
layers.forEach((l) => mdSample.push(`| ${l.name} | ${l.desc} | ${l.pool} | ${l.chosen.length} |`));
mdSample.push('');
layers.forEach((l) => {
  mdSample.push(`## ${l.name}（${l.chosen.length} 个）`);
  mdSample.push('');
  mdSample.push('| # | segment_id | 版本 | 任务 | 步骤 | 对话/旁白 | 字数 | 信号(神谕/母题/结构/停顿) | 等级 | 类型 | 备注 |');
  mdSample.push('|---|---|---|---|---|---|---|---|---|---|---|');
  l.chosen.forEach((s, i) => {
    mdSample.push(
      `| ${i + 1} | \`${s.segment_id}\` | ${s.version} | ${s.task} | ${s.step_title} | ${s.n_dialogue}/${s.n_narration} | ${s.char_len} | ` +
      `${s.semantic_recall_oracle_count || 0}/${s.semantic_recall_motif_count || 0}/${s.structure_count || 0}/${s.pause_ratio || 0} |  |  |  |`
    );
  });
  mdSample.push('');
});
fs.writeFileSync(path.join(ROOT, 'data/reports/annotation-sample.md'), mdSample.join('\n'), 'utf8');

// ---------- 输出：神谕兑现候选表 ----------
const jsonOracle = {
  note: '神谕兑现表模板：fulfillment / fulfillment_type / evidence 待人工填写；candidates 为关键词候选（非结论）',
  fulfillment_type_schema: ['字面', '反转', '错位'],
  oracles: ORACLES.map((o) => ({
    oracle_id: o.oracle_id,
    text: o.text,
    holder: o.holder,
    titan: o.titan,
    metaphors: o.metaphors,
    occurrence_count: o.occurrences.length,
    occurrences: o.occurrences.map((x) => ({ id: x.id, version: x.version, task: x.task, step_title: x.step_title, speaker: x.speaker })),
    candidates: o.fulfillment_candidates,
    fulfillment_segment: '',
    fulfillment_type: '',
    evidence: '',
  })),
};
fs.writeFileSync(path.join(ROOT, 'data/config/oracle-fulfillment.json'), JSON.stringify(jsonOracle, null, 2), 'utf8');

const mdO = [];
mdO.push('# 神谕兑现候选表（人工判定）');
mdO.push('');
mdO.push('> 用法：在每条的「候选」里挑一个（或自己填 segment_id），填 `fulfillment_segment`、`fulfillment_type`（字面/反转/错位）、一句 `evidence`。');
mdO.push('> 候选是按关键词命中算的**提示**，不是结论；同一条神谕的兑现也可能不在候选里（尤其隐喻型）。');
mdO.push('> 机器可读版本：`data/config/oracle-fulfillment.json`。');
mdO.push('');
for (const o of ORACLES) {
  mdO.push(`## ${o.oracle_id} · ${o.holder}（${o.titan}）`);
  mdO.push('');
  mdO.push(`**神谕**：${o.text}`);
  if (o.metaphors.length) mdO.push(`**注音隐喻**：${o.metaphors.map((m) => `${m.display}→${m.gloss}`).join('；')}`);
  mdO.push(`**引用次数**：${o.occurrences.length}（首次：${o.first_appearance ? `${o.first_appearance.version} ${o.first_appearance.task}` : '未找到'}）`);
  mdO.push('');
  mdO.push('| 候选 segment_id | 版本 | 任务 | 步骤 | 命中词 | 分数 |');
  mdO.push('|---|---|---|---|---|---|');
  o.fulfillment_candidates.forEach((c) => {
    mdO.push(`| \`${c.segment_id}\` | ${c.version} | ${c.task} | ${c.step_title} | ${c.hits.join('、')} | ${c.score} |`);
  });
  mdO.push('');
  mdO.push('判定：fulfillment_segment = ________ ；fulfillment_type = ______ ；evidence = ________');
  mdO.push('');
}
fs.writeFileSync(path.join(ROOT, 'data/reports/oracle-fulfillment-review.md'), mdO.join('\n'), 'utf8');

// ---------- 打印 ----------
console.log(`标注样本：${total} 个（${layers.length} 层）`);
layers.forEach((l) => console.log(`  ${l.name}: 池 ${l.pool} → 抽 ${l.chosen.length}`));
const byVer = {};
jsonSample.samples.forEach((s) => (byVer[s.version] = (byVer[s.version] || 0) + 1));
console.log('  版本分布:', JSON.stringify(byVer));
console.log(`神谕兑现表：${ORACLES.length} 条，候选合计 ${ORACLES.reduce((n, o) => n + o.fulfillment_candidates.length, 0)}`);
console.log('输出：data/reports/annotation-sample.md / oracle-fulfillment-review.md；配置：data/config/annotation-sample.json / oracle-fulfillment.json');
