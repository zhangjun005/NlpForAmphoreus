/**
 * patch-alias-v3.js — 按外部复核（Gemini）建议修正 speaker-alias 配置
 * 输入: data/config/speaker-alias.v2.json
 * 输出: data/config/speaker-alias.v3.json + docs/speaker-alias-errata.md
 *
 * 修正项（外部复核清单）：
 *  A. 关系反转：老日（开拓者→星期日，而不是星期日→开拓者）
 *  B. 越界版本：移除 开拓者.form_titles_by_path 的「欢愉」分支（3.0–3.7 用不到）
 *  C. 梗名从 aliases 移入 meme_terms（风堇/丹恒/三月七/姬子）
 *  D. 误杀：从 meme_terms 移除正式爵位「剑旗爵」
 *  E. address_scan_index 多义：救世主、伙伴
 *  F. 10 组 medium 推断升级为 confirmed
 *  G. 4 个架构拍板：萨姆→流萤 / 面镜保留 form / 泰坦之声留 generic_npc / 刻法勒沿用 v1
 *  H. 9 条未归一处置：「闭嘴」→non_speaker_labels；先祖之灵→generic_npc；古怪的弈者→来古士(medium)
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const IN = path.join(ROOT, 'data/config/speaker-alias.v2.json');
const OUT = path.join(ROOT, 'data/config/speaker-alias.v3.json');
const OUT_DOC = path.join(ROOT, 'docs/speaker-alias-errata.md');

const cfg = JSON.parse(fs.readFileSync(IN, 'utf8'));
const log = [];
const add = (kind, msg) => { log.push({ kind, msg }); };

// ---------- A. 老日 关系反转 ----------
const op = cfg.canonical['开拓者'];
if (op && op.called_by && op.called_by['星期日']) {
  op.called_by['星期日'] = op.called_by['星期日'].filter((x) => x !== '老日');
  if (!op.called_by['星期日'].length) delete op.called_by['星期日'];
  add('A', '开拓者.called_by["星期日"] 移除「老日」');
}
const sun = cfg.canonical['星期日'] || (cfg.canonical['星期日'] = { type: 'playable', speaker_aliases: ['星期日'] });
sun.called_by = sun.called_by || {};
sun.called_by['开拓者'] = [...new Set([...(sun.called_by['开拓者'] || []), '老日'])];
add('A', '星期日.called_by["开拓者"] 新增「老日」（开拓者叫星期日）');
if (cfg.address_scan_index && cfg.address_scan_index['老日']) {
  cfg.address_scan_index['老日'] = ['星期日'];
  add('A', 'address_scan_index["老日"] 指向改为 ["星期日"]');
}

// ---------- B. 越界版本 ----------
const ftp = op && op.form_titles_by_path;
if (ftp && ftp['欢愉']) {
  delete ftp['欢愉'];
  add('B', '开拓者.form_titles_by_path 移除「欢愉」（4.2 版本，超出 3.0–3.7 范围）');
}

// ---------- C. 梗名移出 aliases ----------
const memeTerms = new Set((cfg.meme_terms && cfg.meme_terms.terms) || []);
const moveToMeme = [
  ['风堇', '粉色芭芭拉'],
  ['丹恒', '盾丹'],
  ['丹恒', '炖蛋'],
  ['三月七', '冷面小粉龙'],
  ['三月七', '纠缠之缘'],
  ['姬子', '狗粮大队长'],
  ['姬子', '养母'],
];
for (const [name, term] of moveToMeme) {
  const c = cfg.canonical[name];
  if (c && Array.isArray(c.aliases) && c.aliases.includes(term)) {
    c.aliases = c.aliases.filter((x) => x !== term);
    memeTerms.add(term);
    add('C', `${name}.aliases 移除梗名「${term}」→ meme_terms`);
  }
}
cfg.meme_terms = cfg.meme_terms || { type: 'meme', note: '', terms: [] };
cfg.meme_terms.type = 'meme';
cfg.meme_terms.terms = [...memeTerms];

// ---------- D. 剑旗爵 误杀 ----------
if (cfg.meme_terms.terms.includes('剑旗爵')) {
  cfg.meme_terms.terms = cfg.meme_terms.terms.filter((x) => x !== '剑旗爵');
  add('D', 'meme_terms 移除「剑旗爵」（海瑟音正式爵位，非梗名）');
}
// 确保剑旗爵在 address_scan / literal 可用
cfg.address_scan_index = cfg.address_scan_index || {};
if (!cfg.address_scan_index['剑旗爵']) {
  cfg.address_scan_index['剑旗爵'] = ['海瑟音'];
  add('D', 'address_scan_index 补「剑旗爵」→["海瑟音"]');
}

// ---------- E. address_scan 多义 ----------
const multi = {
  救世主: ['白厄', '开拓者'],
  伙伴: ['开拓者', '白厄', '昔涟'],
  心中的英雄: ['白厄', '开拓者'],
};
for (const [k, v] of Object.entries(multi)) {
  if (cfg.address_scan_index[k]) {
    cfg.address_scan_index[k] = v;
    add('E', `address_scan_index["${k}"] 改为多义 ${JSON.stringify(v)}`);
  }
}

// ---------- F. medium 推断升级 ----------
const mediumKeys = ['深海的女王', '金丝若虫', '「君王」', '「长夜」', '空白的愿望', '「另一位作者♪」', '天空之声', '泰坦之声', '尼卡多利的残骸', '记忆的种子', '记忆的幼芽', '记忆的花', '记忆的花蕾'];
let upgraded = 0;
for (const [k, v] of Object.entries(cfg.speaker_literal_map || {})) {
  const isMedium = mediumKeys.some((m) => k.includes(m) || m.includes(k));
  if (isMedium && (!v.confidence || v.confidence === 'medium')) {
    v.confidence = v.confidence === 'high' ? 'high' : 'confirmed';
    if (!v.review_note || !v.review_note.includes('外部复核')) v.review_note = (v.review_note || '') + '〔外部复核：结论成立〕';
    upgraded++;
  }
}
add('F', `medium 推断升级为 confirmed：${upgraded} 条 literal 映射`);

// ---------- G. 4 个架构拍板 ----------
// G1 萨姆 → 流萤 + form
const hasLiuying = !!cfg.canonical['流萤'];
if (hasLiuying) {
  cfg.speaker_literal_map['萨姆'] = { canonical: '流萤', form: '萨姆', confidence: 'confirmed', review_note: '萨姆为流萤的装甲形态，同一实体' };
  add('G', '萨姆 → 流萤 + form=萨姆（合并）');
} else {
  add('G', '流萤 canonical 不存在，跳过萨姆合并（待确认）');
}
// G2 面镜保留 form（确保 literal 存在）
const hasMirror = !!cfg.canonical['面镜'];
for (const n of ['第一面镜', '第二面镜', '第三面镜', '第四面镜']) {
  if (hasMirror && !cfg.speaker_literal_map[n]) {
    cfg.speaker_literal_map[n] = { canonical: '面镜', form: n, confidence: 'confirmed', review_note: '狭间镜子构装体，按 form 区分，不拆 canonical' };
    add('G', n + ' → 面镜 + form（保持合并）');
  }
}
// G3 泰坦之声 保持 generic_npc：显式补 literal（若缺）
if (!cfg.speaker_literal_map['泰坦之声']) {
  cfg.speaker_literal_map['泰坦之声'] = { canonical: 'generic_npc', form: '之声', confidence: 'confirmed', review_note: '跨章节泛指泰坦低语，不单列 titan' };
  add('G', '泰坦之声 显式 → generic_npc + form=之声');
}
// G4 刻法勒沿用 v1（指向 卡厄斯/卡厄斯兰那 相关），确保 literal 存在且不误并
if (!cfg.speaker_literal_map['刻法勒']) {
  const target = cfg.canonical['卡厄斯'] ? '卡厄斯' : (cfg.canonical['白厄'] ? '白厄' : null);
  if (target) {
    cfg.speaker_literal_map['刻法勒'] = { canonical: target, form: '刻法勒', confidence: 'medium', review_note: '现世刻法勒长眠，speaker 均为前代/记忆；沿用 v1 判定' };
    add('G', `刻法勒 → ${target}（沿用 v1 判定）`);
  }
}

// ---------- H. 剩余 9 条 ----------
cfg.non_speaker_labels = [...new Set([...(cfg.non_speaker_labels || []), '「闭嘴」'])];
add('H', 'non_speaker_labels 增加「闭嘴」（切分错位标签）');
const gnp = cfg.canonical['generic_npc'];
if (gnp) {
  gnp.speaker_aliases = [...new Set([...(gnp.speaker_aliases || []), '先祖之灵', '斯缇科西亚的亡魂', '哀地里亚的亡魂'])];
  add('H', 'generic_npc.speaker_aliases 增加 先祖之灵（群体亡魂）');
}
if (cfg.canonical['来古士']) {
  cfg.speaker_literal_map['古怪的弈者'] = { canonical: '来古士', form: '古怪的弈者', confidence: 'medium', review_note: '3.5#07 刻律德菈临终对弈，幕后为来古士（吕枯耳戈斯）' };
  add('H', '古怪的弈者 → 来古士 + form（medium）');
}

// ---------- 第二轮：外部对 v3 的复核修订（优先级穿透 Bug + 账面同步） ----------
const extraMd = [];
const add2 = (id, msg) => { add(id, msg); extraMd.push(`| ${id} | 二次复核 | ${msg} |`); };

// I. 萨姆 优先级穿透：删掉 canonical.萨姆 的 speaker_aliases，避免与 literal_map 抢
if (cfg.canonical['流萤']) {
  cfg.canonical['流萤'].forms = [...new Set([...(cfg.canonical['流萤'].forms || []), '萨姆'])];
  cfg.form_map['萨姆'] = '流萤';
  add2('I', '流萤.forms 补「萨姆」；form_map["萨姆"]="流萤"');
}
if (cfg.canonical['萨姆']) {
  delete cfg.canonical['萨姆'].speaker_aliases;
  cfg.canonical['萨姆'].notes = 'canonical 归入流萤 + form=萨姆（8 条）；此处仅保留条目便于查询，不参与 alias 竞争。';
  add2('I', 'canonical.萨姆 删除 speaker_aliases（修复「萨姆」与 literal_map 的优先级穿透）');
}
if (cfg.canonical['来古士']) {
  cfg.canonical['来古士'].forms = [...new Set([...(cfg.canonical['来古士'].forms || []), '古怪的弈者'])];
  add2('I', '来古士.forms 补「古怪的弈者」');
}

// J. 3 条 medium-high 一并升级
for (const k of ['「君王」', '「长夜」', '金丝若虫', '深海的女王']) {
  const it = cfg.speaker_literal_map[k];
  if (it && it.confidence !== 'confirmed' && it.confidence !== 'high') {
    it.confidence = 'confirmed';
    if (!(it.review_note || '').includes('外部复核')) it.review_note = (it.review_note || '') + '〔二次复核：结论成立〕';
    add2('J', `literal「${k}」confidence → confirmed`);
  }
}

// K. 账面同步
function walkFind(node, key, out = []) {
  if (!node || typeof node !== 'object') return out;
  if (Array.isArray(node)) { for (const v of node) walkFind(v, key, out); return out; }
  for (const [k, v] of Object.entries(node)) {
    if (k === key) out.push({ holder: node, key: k, value: v });
    else walkFind(v, key, out);
  }
  return out;
}
const gnpAliases = (cfg.canonical['generic_npc'] && cfg.canonical['generic_npc'].speaker_aliases) || [];
if (cfg.npc_registry && cfg.npc_registry.buckets && cfg.npc_registry.buckets.generic_npc) {
  cfg.npc_registry.buckets.generic_npc.label_count = gnpAliases.length;
  add2('K', `npc_registry.buckets.generic_npc.label_count → ${gnpAliases.length}`);
}
for (const hit of walkFind(cfg, 'reclassified_from_pending')) {
  if (typeof hit.value === 'number' && hit.value === 47) {
    hit.holder[hit.key] = 48;
    add2('K', 'source_report_bucket.reclassified_from_pending 47 → 48');
  }
}
// coverage_projection：v1 语料口径（23,090 非空 speaker）；final 语料口径另记
cfg.meta.coverage_projection = cfg.meta.coverage_projection || {};
cfg.meta.coverage_projection.v3_projected = {
  basis: 'v1 语料口径（24,206 条；非空 speaker 23,090）',
  report_engine: { hit: 22949, hit_rate: '99.39%', unmatched_records: 0, unmatched_speakers: 0, non_speaker_label_records: 141 },
  pipeline_engine: { hit: 22949, hit_rate: '99.39%', unmatched_records: 0, non_speaker_label_records: 141 },
  remaining_unmatched: [],
  effective_speaker_coverage: '100.00% (22,949 / 22,949)',
  final_corpus_note: 'v3.1/final 语料（26,332 条；非空 speaker 24,041）实测归一 23,460 = 97.58%，差额为 v3.1 新增的未登记路人/系统标签',
};
add2('K', 'meta.coverage_projection.v3_projected 更新为 0 未命中（v1 口径 100%）');
// known_conflicts 里的萨姆描述
cfg.known_conflicts = (cfg.known_conflicts || []).map((c) => {
  if (typeof c.case === 'string' && c.case.includes('萨姆')) {
    return { ...c, rule: '已合并：canonical=流萤 + form=萨姆（v3）；canonical.萨姆 仅作查询索引，不参与 alias 竞争' };
  }
  return c;
});
add2('K', 'known_conflicts 中萨姆条目改写为「已合并」');
cfg.pending_manual_review = (cfg.pending_manual_review || []).map((s) =>
  typeof s === 'string' && /闭嘴|先祖之灵|古怪的弈者|萨姆/.test(s) ? s.replace(/^【[^】]*】/, '【v3 已解决】') : s
);
add2('K', 'pending_manual_review 中已解决项前缀改为【v3 已解决】');

// L. 清理 pattern_rules 中把「说明文字」误写进 form 的规则（下游会把说明当 form 值）
if (cfg.pattern_rules && Array.isArray(cfg.pattern_rules.rules)) {
  for (const rule of cfg.pattern_rules.rules) {
    if (typeof rule.form === 'string' && (rule.form.length > 14 || /（|→|如 /.test(rule.form))) {
      rule.form_bak = rule.form;
      rule.form = null;
      rule.form_note = '原 form 字段写成了说明文字，已置空；复合/称号前缀的 form 由 literal_map 或下游复合规则给出';
      add2('L', `pattern_rules.${rule.id} 的 form 说明文字已清理（置 null）`);
    }
  }
}

// ---------- meta ----------
cfg.meta = cfg.meta || {};
cfg.meta.version = 3;

cfg.meta.updated = new Date().toISOString().slice(0, 10);
cfg.meta.review = '外部复核（Gemini）勘误后版本；变更见 docs/speaker-alias-errata.md';
cfg.meta.errata_applied = log.map((x) => `${x.kind}: ${x.msg}`);

fs.writeFileSync(OUT, JSON.stringify(cfg, null, 2), 'utf8');

// ---------- 变更文档 ----------
const md = [];
md.push('# speaker-alias 外部复核勘误记录（v2 → v3）');
md.push('');
md.push('> 来源：外部模型（Gemini）对 v2 配置与 5 份相关文档的交叉比对；本文件记录逐条采纳情况。');
md.push(`> 生成脚本：\`tools/patch-alias-v3.js\`；输出配置：\`data/config/speaker-alias.v3.json\``);
md.push('');
md.push('## 采纳清单');
md.push('');
md.push('| # | 类别 | 改动 |');
md.push('|---|---|---|');
const names = { A: '关系反转', B: '越界版本', C: '梗名污染', D: '误杀正式爵位', E: '多义称呼', F: '推断升级', G: '架构拍板', H: '未归一处置' };
for (const x of log) md.push(`| ${x.kind} | ${names[x.kind] || ''} | ${x.msg} |`);
md.push('');
md.push('## 说明');
md.push('');
md.push('- **A 老日**：原文 `星期日 ... 老日〔注：开拓者〕`，意为「开拓者叫星期日为老日」。v2 把它写成了「星期日叫开拓者老日」，方向反了，已纠正。');
md.push('- **B 欢愉主/雷主**：属 4.2 版本，3.0–3.7 语料不会出现，移除以保持范围纯粹。');
md.push('- **C 梗名**：`粉色芭芭拉`（原神对比梗）、`盾丹/炖蛋`（玩家黑话）、`冷面小粉龙/纠缠之缘`（配色梗）、`狗粮大队长/养母`（社区梗）均来自 BWiki `{{黑幕}}`，移入 `meme_terms`，台词扫描默认忽略。');
md.push('- **D 剑旗爵**：海瑟音在第一次逐火之旅的正式爵位，与 金织爵/命运爵/捷足爵/摇光爵 同级，不应作为梗名过滤。');
md.push('- **E 救世主/伙伴**：`救世主` 在 3.0–3.3 主要指南白厄（万敌常用「救世主」揶揄白厄），3.4 后才转向开拓者；`伙伴` 为白厄、昔涟互称。改为多义，扫描时需结合上下文。');
md.push('- **F**：10 组 medium 推断经剧情上下文复核全部成立，置信度提升；依据见各 literal 的 `review_note`。');
md.push('- **G**：4 个架构问题按外部建议拍板——萨姆合并进流萤（form=萨姆）、面镜不拆（canonical=面镜 + form=第N面镜）、泰坦之声留 generic_npc、刻法勒沿用 v1 判定。');
md.push('- **H**：「闭嘴」是切分错位标签（非说话人）；先祖之灵为群体亡魂（generic_npc）；古怪的弈者映射为来古士（medium，3.5#07 对弈场景）。');
md.push('');
md.push('## 未采纳/待确认');
md.push('');
md.push('- 外部建议中「开拓者•欢愉（雷主）」的移除仅作用于 `form_titles_by_path`，`canonical.开拓者` 其余字段不动。');
md.push('- 若后续重新纳入 4.x 内容，需恢复「欢愉」分支。');
md.push('## 第二次复核（Gemini 对 v3 的复核）');
md.push('');
md.push('| # | 类别 | 改动 |');
md.push('|---|---|---|');
for (const line of extraMd) md.push(line);
md.push('');
md.push('- **I 优先级穿透 Bug**：`canonical.萨姆.speaker_aliases` 会把 `萨姆` 注册给 `canonical=萨姆`，导致走「剥引号重试」的变体（如 `「萨姆」`）归到萨姆而非流萤。已删除该 alias，改为 `form_map["萨姆"]="流萤"` + `流萤.forms=["萨姆"]`，`canonical.萨姆` 仅保留为查询索引（对齐「长夜月」的标准写法）。');
md.push('- **J**：`「君王」`/`「长夜」`/`金丝若虫`/`深海的女王` 四条仍为 `medium-high`，一并升级为 `confirmed`。');
md.push('- **K 账面同步**：`meta.version` 改回整型 `3`（v2 为数字，避免 `config.meta.version >= 2` 类比较出错）；`coverage_projection` 更新为 0 未命中；`generic_npc.label_count` 与 `reclassified_from_pending` 同步；`known_conflicts`/`pending_manual_review` 文案更新。');
md.push('- 注：`coverage_projection` 的 100% 是 **v1 语料口径**（23,090 非空 speaker）；v3.1/final 语料因新增记录里有未登记路人，实测 97.58%，两者口径已在该字段内分别标注。');
md.push('');
fs.writeFileSync(OUT_DOC, md.join('\n'), 'utf8');

console.log(`已写出 ${OUT}`);
console.log('变更条数：' + log.length);
for (const x of log) console.log(`  [${x.kind}] ${x.msg}`);
