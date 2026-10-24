/** patch-a1-fixes2.js — 给 O05 配置多事件段并重跑 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const p = path.join(ROOT, 'tools/build-oracle-fulfillment-v2.js');
let s = fs.readFileSync(p, 'utf8');
if (!s.includes("O05: [\n    { segment_id: '3.2|断梦啊")) {
  s = s.replace(
    'const EVENT_SEGMENTS_EXTRA = {',
    `const EVENT_SEGMENTS_EXTRA = {
  O05: [
    { segment_id: '3.2|断梦啊，从夙世捎来启迪|1', role: '意义转折', note: '双子抉择：我和姐姐必须有一人牺牲' },
    { segment_id: '3.2|摇船啊，请载我横渡冥流|19', role: '兑现', note: '塞纳托斯形态宣言：命中注定的时刻再次到来' },
  ],`
  );
  fs.writeFileSync(p, s, 'utf8');
  console.log('已写入 O05 多事件段');
}
require(p);
const J = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/config/oracle-fulfillment.v2.json'), 'utf8'));
for (const o of J.oracles) {
  if (['O04', 'O05', 'O13'].includes(o.oracle_id)) {
    console.log(o.oracle_id, o.holder, JSON.stringify(o.event_segments));
  }
}
