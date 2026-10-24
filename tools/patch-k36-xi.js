/**
 * patch-k36-xi.js — 按设定修正 K36/E30 口径：
 * 「记忆的花」= 昔涟自身（记忆形态），所以是昔涟为最初的种子/桃子讲水晶花寓言，并改写结局。
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const jp = (p) => path.join(ROOT, p);

// 1) knife-scenes.json
const K = JSON.parse(fs.readFileSync(jp('data/config/knife-scenes.json'), 'utf8'));
const k = K.scenes.find((s) => s.id === 'K36');
if (k) {
  k.position = '3.7 魔女的孤诣课题：三千万世讲述的最后一段寓言——昔涟（记忆形态，原文说话人标注为「记忆的花」，按设定即昔涟自身）为最初的种子/桃子讲述「水晶花寓言」，并改写故事的结局';
  k.why = '「无瑕的水晶花」正是昔涟与德谬歌自己的隐喻：越纯粹越封闭、越无「心」也无「爱」；昔涟以「我的审美」改写结局，把「破碎/收梢」解释成「向命运发起抗争，以破碎书写故事的结局」——这是她把 O13 的「收梢于花开时」翻译成「爱」的预演，也是她讲给最初的种子/桃子的告白。';
  k.speaker_note = '说话人「记忆的花」在语料中已归一为 昔涟(form=记忆形态)；本场景按「昔涟本人讲述」理解。';
  if (Array.isArray(k.address_change)) k.address_change = ['昔涟（记忆形态）→ 桃子（最初的种子）：讲故事者与听者', '故事内：小妖精 → 无瑕的水晶花'];
  else if (typeof k.address_change === 'string') k.address_change = '昔涟（记忆形态）→ 桃子（最初的种子）：讲故事者与听者；故事内：小妖精 → 无瑕的水晶花';
}
fs.writeFileSync(jp('data/config/knife-scenes.json'), JSON.stringify(K, null, 2), 'utf8');

// 2) key-events.json
const E = JSON.parse(fs.readFileSync(jp('data/config/key-events.json'), 'utf8'));
const evs = E.events || E.key_events || [];
const e30 = evs.find((x) => x.id === 'E30');
if (e30) {
  e30.event_name = '「水晶花寓言」：昔涟为最初的种子讲述「无瑕即无爱，破碎才生出心与爱」';
  e30.meaning_before = '「无瑕」的水晶花＝纯粹的理想之美；小妖精日复一日守着它，想弄清它的「心」该有多美。';
  e30.meaning_after = '昔涟（记忆形态）为最初的种子/桃子讲述并改写结局：无瑕的水晶花因封闭自己而既没有「心」也不懂「爱」；跌落碎裂不是意外，而是「向命运发起抗争，以破碎书写故事的结局」——破碎之后它才终于有了「心」、学会了「爱」；昔涟的「收梢」由此被解释为生命与爱的开始。';
  e30.speaker_note = '原文说话人标注「记忆的花」，语料归一为 昔涟(form=记忆形态)；按设定即昔涟本人。';
}
fs.writeFileSync(jp('data/config/key-events.json'), JSON.stringify(E, null, 2), 'utf8');

// 3) 两个报告 md 的口径替换
const fixes = [
  ['「记忆的花」（桃子/德谬歌的记忆形态）为昔涟讲故事，昔涟改写结局', '昔涟（记忆形态，原文标注「记忆的花」）为最初的种子/桃子讲水晶花寓言，并改写结局'],
  ['「记忆的花」（桃子/德谬歌的记忆形态，正在学习「会讲故事才是昔涟」）→ 讲给昔涟；昔涟以「我的审美」改写结局', '昔涟（记忆形态，原文标注「记忆的花」）→ 讲给最初的种子/桃子；昔涟以「我的审美」改写结局'],
  ['「记忆的花」（桃子/德谬歌的记忆形态，正学着「会讲故事才是昔涟」）为昔涟讲故事；昔涟是听者与改写者', '昔涟（记忆形态，原文标注「记忆的花」）为最初的种子/桃子讲故事，并改写结局'],
];
for (const rel of ['data/reports/knife-scenes.md', 'data/reports/key-events.md']) {
  const p = jp(rel);
  let t = fs.readFileSync(p, 'utf8');
  let n = 0;
  for (const [a, b] of fixes) {
    if (t.includes(a)) { t = t.split(a).join(b); n++; }
  }
  fs.writeFileSync(p, t, 'utf8');
  console.log(rel, '替换段落数:', n);
}
console.log('K36 role=', k && k.role, '| E30 name=', e30 && e30.event_name);
