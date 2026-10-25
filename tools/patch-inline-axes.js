/** patch-inline-axes.js — ch4/ch5 的图注改为"每张图旁边标轴" */
const fs = require('fs');
const path = require('path');
const p = path.join(__dirname, '..', 'frontend/docs/13-章节正文.md');
let t = fs.readFileSync(p, 'utf8');

const a1 = '**图与数据**：`f14`、`f10`（横轴角色、纵轴出场步骤/覆盖率）、`oracle_sim__阿格莱雅/赛飞儿.csv`；`L3 海瑟音/刻律德菈/阿格莱雅/赛飞儿/开拓者/三月七/丹恒`。';
const b1 = [
  '**图与数据**：',
  '- `f14` 镜像曲线：**横轴**=全局步序；**纵轴**=与 O10/O11 的余弦相似度；**读法**=两条线是否重合。',
  '- `f10` 覆盖率图：**横轴**=角色（A 组 11 + B 组 3）；**纵轴**=出场步骤数 / 被精读覆盖的步骤数；**读法**=看谁台词多但被读得少。',
  '- 数据：`oracle_sim__阿格莱雅/赛飞儿.csv`（横轴步序、纵轴余弦相似度）；`L3` 七份。',
].join('\n');

const a2 = '**图与数据**：`f4`、`f12`、`f13`、`f15`；`data/config/key-events.json`；`data/config/motif-query-mingtianjian.json`（明天见）、`data/config/motif-query-zaijianmian.json`（再见面）；`L3` 14 份。';
const b2 = [
  '**图与数据**：',
  '- `f4` 引用台账：**横轴**=剧情顺序；**纵轴**=引用阶段（原文出现/他人解释/本人引用/结局宣告/改写）；**读法**=看"说话权"如何移动。',
  '- `f12` 明天见时间线：**横轴**=版本 3.0–3.7；**纵轴**=出现次数；**读法**=看母题从哪来、到哪去。',
  '- `f13` 水晶花曲线：**横轴**=全局步序；**纵轴**=与 K36 原文的余弦相似度；**读法**=词频加权与语义向量两条线是否同步。',
  '- `f15` 检索对比：**横轴**=检索方法；**纵轴**=MRR（越高越好）；**读法**=v3 组普遍低。',
  '- 数据：`data/config/key-events.json`；`data/config/motif-query-mingtianjian.json`（明天见）、`motif-query-zaijianmian.json`（再见面）；`L3` 14 份。',
].join('\n');

let n = 0;
if (t.includes(a1)) { t = t.replace(a1, b1); n++; }
if (t.includes(a2)) { t = t.replace(a2, b2); n++; }
fs.writeFileSync(p, t, 'utf8');
console.log('替换完成:', n, '处');
