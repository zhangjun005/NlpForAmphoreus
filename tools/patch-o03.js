/** patch-o03.js — 万敌 L3 结论：O03 兑现段 = 主线 3.3|黎明|11 + 记忆线 3.4|点燃|11；
 * 3.1|王座|8（K04）无 O03 文本/死亡事件，降为「主题前置段」。
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

const fp = path.join(ROOT, 'tools/build-oracle-fulfillment-v2.js');
let s = fs.readFileSync(fp, 'utf8');
if (!s.includes("O03: [\n")) {
  s = s.replace(
    'const EVENT_SEGMENTS_EXTRA = {',
    "const EVENT_SEGMENTS_EXTRA = {\n  O03: [\n    { segment_id: '3.3|黎明啊，执耀于全世之终|11', role: '兑现', note: '主线：#15174 旁白「从身后刺入第十节胸椎」+ #15175/#15180 临终（万敌 L3）' },\n    { segment_id: '3.4|英雄啊，点燃那最初的骄阳|11', role: '兑现', note: '记忆线（K05）：#17283 白厄预告、#17294 O03 结局宣告、#17319–17323 临终（万敌 L3）' },\n  ],"
  );
  fs.writeFileSync(fp, s, 'utf8');
  console.log('O03 event_segments 已锁定（主线+记忆线）');
}
require(fp);

// 更新 open questions
const oqp = path.join(ROOT, 'data/config/l3-open-questions.json');
const oq = JSON.parse(fs.readFileSync(oqp, 'utf8'));
const ids = new Set(oq.items.map((x) => x.id));
if (!ids.has('L3-OQ11')) {
  oq.items.push({
    id: 'L3-OQ11', char: '万敌',
    issue: 'O03 兑现段：v2 proposed=3.1|王座|8（K04）无 O03 文本、无死亡事件；实际兑现出现两次（主线 3.3|黎明|11 #15174、记忆线 3.4|点燃|11 #17294）',
    decision: 'event_segments 锁定两段兑现；3.1|王座|8 降为「主题前置段」（万敌 L3）', status: 'resolved',
  });
  oq.items.push({
    id: 'L3-OQ12', char: '万敌',
    issue: 'O03 是否「跨轮回稳定」的命定：两代白厄各执行一次「背后刺入第十节胸椎」',
    decision: '报告写成「他把刀递给杀死自己的人」——命定是被角色交出的，不是被偷袭的', status: 'open',
  });
  fs.writeFileSync(oqp, JSON.stringify(oq, null, 2), 'utf8');
  console.log('open questions 增补 2 条，共', oq.items.length);
}
