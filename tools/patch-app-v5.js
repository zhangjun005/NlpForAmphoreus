const fs = require('fs');
const path = require('path');
const p = path.join(__dirname, '..', 'frontend/src/App.jsx');
let t = fs.readFileSync(p, 'utf8');
t = t.replace("title: '承受命定的人：沉默、递刀与追认'", "title: '与命定交手的人：沉默、递刀与追认'");
const i = t.indexOf('ch04: {');
const j = t.indexOf('ch05: {');
if (i > 0 && j > i) {
  let seg = t.slice(i, j);
  seg = seg.replace("src: '/figures/f14_mirror_pair_O10_O11.png'", "src: '/figures/f4_citation_stage.png'");
  seg = seg.replace("title: 'f14 镜像曲线（对偶组）'", "title: 'f4 引用台账（对偶与长线）'");
  seg = seg.replace("axes: '横轴：全局步序；纵轴：与 O10/O11 的余弦相似度。'", "axes: '横轴：剧情顺序；纵轴：引用阶段（原文出现/他人解释/本人引用/结局宣告/改写）。'");
  seg = seg.replace("judge: '两条线分离大 = 能区分两条镜像命定（好）；重合 = 分不开（坏）。'", "judge: '阶段从「原文出现/他人解释」移到「本人引用/结局宣告」= 接管完成（好）；停在他人/旁白 = 没接管。'");
  seg = seg.replace("conclusion: '词频加权逐点重合，语义向量平均差 0.005、最大 0.018 → 两种表示都分不开，归属只能靠引用与兑现判。'", "conclusion: '本人引用 19/34、结局宣告 8 条，末次引用时本人 8/13——方向对，但只是弱趋势。'");
  t = t.slice(0, i) + seg + t.slice(j);
}
t = t.replace('丹恒 1,541 条含 89 条「丹枫」。', '丹恒 1,541 条含 89 条「丹枫」，3.6 承接大地火种（荒笛 → 丹恒）。');
fs.writeFileSync(p, t, 'utf8');
console.log('App.jsx 收尾修改完成');
