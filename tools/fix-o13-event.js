/** fix-o13-event.js — 修正 O13「意义转折」事件段：应为 3.4|英雄啊，兑现那染血的冀望|7（#15510 所在段） */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const p = path.join(ROOT, 'tools/build-oracle-fulfillment-v2.js');
let s = fs.readFileSync(p, 'utf8');
s = s.replace(
  "segment_id: '3.4|英雄啊，点燃那最初的骄阳|7'",
  "segment_id: '3.4|英雄啊，兑现那染血的冀望|7'"
);
fs.writeFileSync(p, s, 'utf8');
console.log('已修正 O13 意义转折段 -> 3.4|英雄啊，兑现那染血的冀望|7');
require(p);
const J = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/config/oracle-fulfillment.v2.json'), 'utf8'));
const o13 = J.oracles.find((o) => o.oracle_id === 'O13');
console.log('O13 event_segments =', JSON.stringify(o13.event_segments));
