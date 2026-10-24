/** patch-o06-lock.js — 锁定 O06 兑现事件段（K14 争辩|2 为兑现；追认注记保留） */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const p = path.join(ROOT, 'tools/build-oracle-fulfillment-v2.js');
let s = fs.readFileSync(p, 'utf8');
if (!s.includes("O06: [\n")) {
  s = s.replace(
    'const EVENT_SEGMENTS_EXTRA = {',
    "const EVENT_SEGMENTS_EXTRA = {\n  O06: [\n    { segment_id: '3.2|争辩啊，代长矛分庭抗礼|2', role: '兑现', note: '自我处刑/交出理性火种；文本顺序早于神谕原句出现（见 sequence_note）' },\n  ],"
  );
  fs.writeFileSync(p, s, 'utf8');
  console.log('O06 event_segments 已锁定');
}
require(p);
const J = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/config/oracle-fulfillment.v2.json'), 'utf8'));
const o6 = J.oracles.find((o) => o.oracle_id === 'O06');
console.log('O06 event_segments =', JSON.stringify(o6.event_segments));
console.log('O06 sequence_note 前 60 =', (o6.sequence_note || '').slice(0, 60));
