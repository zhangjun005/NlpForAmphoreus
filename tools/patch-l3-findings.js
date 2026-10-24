/** patch-l3-findings.js — 修正 L3 发现的两处下游口径
 * 1) oracles.jsonl 的 O02：补 source_lines（雅努斯 #7939 / 欧洛尼斯 #7744 的散文原话 → 缇宝提炼成箴言）
 * 2) outline-annotator.md 的「明天见」时间线与次数（23 条唯一记录；首现不是 #6876）
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

// ---- 1) build-oracles.js: O02 增加 source_lines ----
const bo = path.join(ROOT, 'tools/build-oracles.js');
let t = fs.readFileSync(bo, 'utf8');
const o02old = "{ id: 'O02', holder: '缇宝', titan: '雅努斯（门径）', text: '汝将碎作千片，凋零在他乡的土壤。', keywords: ['碎作千片', '凋零', '他乡'] }";
const o02new = "{ id: 'O02', holder: '缇宝', titan: '雅努斯（门径）', text: '汝将碎作千片，凋零在他乡的土壤。', keywords: ['碎作千片', '凋零', '他乡'], source_lines: [{ record_id: 7939, speaker: '雅努斯', text: '指引世人者，灵魂必遭歧路分离，碎作千片化身，如琉璃掷地……' }, { record_id: 7744, speaker: '欧洛尼斯', text: '若散播预言，只会引发灾难。那灾难…足以将你撕成千片。' }], source_note: 'O02 的「原文」是缇宝从泰坦散文化宣判（#7939/#7744）中提炼成的十二字箴言；提炼动作本身未被任何配置记录（缇宝 L3 发现）' }";
if (t.includes(o02old)) {
  t = t.replace(o02old, o02new);
  fs.writeFileSync(bo, t, 'utf8');
  console.log('build-oracles.js: O02 source_lines 已补');
} else {
  console.log('未匹配 O02 行，需手动检查');
}
require(bo);

// ---- 2) outline 修正 ----
const op = path.join(ROOT, 'docs/report/outline-annotator.md');
let o = fs.readFileSync(op, 'utf8');
const oldLine = '  - 收束预告：3.7 结尾缇宝说「明天见」、白厄说「明天见，乘以一千」（`#25778`、`#25779`），「明天见」从 3.1 妈妈临终的一句话（`#6876`）变成全篇的预言。';
const newLine = '  - 收束预告：3.7 结尾缇里西庇俄丝（=缇宝）说「明天见」、白厄说「明天见，乘以一千」（`#25778`、`#25779`）。「明天见」的全库唯一记录数为 **23 条**（按 context 块统计会出现 25 的重复计数，勿用）；首现是 3.0 白厄对半神说「我明白了。那么，明天见」（`#4211`），缇宝系首现是对商人的客套话（`#5259`），**不是 #6876**；#6876 是母亲（莫忒丝）对缇宝说的那一句，随后被缇宝改写成「世上最伟大的预言」（`#8077`）。';
if (o.includes(oldLine)) {
  o = o.replace(oldLine, newLine);
  fs.writeFileSync(op, o, 'utf8');
  console.log('outline: 明天见口径已修正');
} else {
  console.log('outline 行未匹配，需手动修正');
}
