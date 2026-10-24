/** patch-krypudela-findings.js — 刻律德菈 L3 的口径修正
 * 1) f14 图注补：刻律德菈曲线 best_other=O08(0.721)，O10 仅词面；SBERT 看不到镜像对
 * 2) open-questions 增补：救城的将领归属、best_other 口径统一
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

// 1) figure-captions.md f14 段补口径
const cp = path.join(ROOT, 'docs/report/figure-captions.md');
let t = fs.readFileSync(cp, 'utf8');
const anchor = '**局限**：① 步骤级、同段混用（O11 引用与兑现都在 `囚人|15`）；② 两条曲线**不存在「交错」**；③ 相似度不能替代人工判读的兑现判定。';
const add = anchor + '\n\n**补注（刻律德菈 L3 核验）**：镜像对只能在词面层成立——刻律德菈本人曲线的 `best_other` 是 **O08（0.721 @ order 46）**，不是 O10（TF-IDF 下 O10 仅 8/31 步出现、SBERT 下仅 1/31）；海瑟音曲线里「own=O10、最相似其他=O11（0.698）」是海瑟音的数据，不能转述成刻律德菈的。因此 f14 图注不能写「两条曲线几乎相等所以是镜像对」，只能写「词袋相同导致 TF-IDF 逐点重合；镜像关系由引用（#20228/#20229）与兑现方式（#20339/#19814）读出，SBERT 读不到」。';
if (t.includes(anchor) && !t.includes('补注（刻律德菈 L3 核验）')) {
  t = t.replace(anchor, add);
  fs.writeFileSync(cp, t, 'utf8');
  console.log('f14 图注已补口径');
}

// 2) open questions
const oqp = path.join(ROOT, 'data/config/l3-open-questions.json');
const oq = JSON.parse(fs.readFileSync(oqp, 'utf8'));
const ids = new Set(oq.items.map((x) => x.id));
if (!ids.has('L3-OQ13')) {
  oq.items.push({ id: 'L3-OQ13', char: '刻律德菈', issue: '3.5|初日|2 有 6 条「救城的将领」实为她（#17891/#17892/#17894/#17896/#17897/#17900，#17896 与 #20265 逐字相同），但语料标 generic_npc 未计入 296', decision: '统计按 296，报告注明归属缺口；若采纳则为 302、首次开口前移 #17891', status: 'open' });
  oq.items.push({ id: 'L3-OQ14', char: '刻律德菈/海瑟音', issue: '曲线 best_other 口径不统一：刻律德菈 best_other=O08(0.721)，O10 仅词面；海瑟音 own=O10、best_other=O11(0.698)', decision: 'f14/第 3 章统一写「镜像对=词面+引用+兑现读出，SBERT 不可见」，不写成两条曲线相似', status: 'resolved' });
  oq.items.push({ id: 'L3-OQ15', char: '刻律德菈', issue: '「深读覆盖 32.3%」是步骤并集口径（刀场景∪关键事件∪标注 10/31），纯刀场景 7/31=22.6%；她在 A 组台词总量与步数均末位、87% 集中在 3.5', decision: '报告表述为「时间上极端集中」，不写「密度低」或「逐条读过 32.3%」', status: 'resolved' });
  fs.writeFileSync(oqp, JSON.stringify(oq, null, 2), 'utf8');
  console.log('open questions 增补 3 条，共', oq.items.length);
}
