/** patch-o06-note.js — O06 追认型兑现：事件段在文本顺序上早于神谕原文出现（那刻夏 L3 发现） */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const p = path.join(ROOT, 'tools/build-oracle-fulfillment-v2.js');
let s = fs.readFileSync(p, 'utf8');
if (!s.includes('SEQUENCE_NOTES')) {
  s = s.replace('const EVENT_SEGMENTS_EXTRA = {', `const SEQUENCE_NOTES = {
  O06: '追认型：v2 把 3.2|争辩|2（segment_index 269）标为兑现，但神谕原句出现在 3.2|学者|4（segment_index 315）——兑现事件在文本顺序上早于神谕被说出；「至纯粹」在瑟希斯说出原句前已出现两次（丹恒概括、那刻夏自述），O06 是被追认的神谕，不是被预告的神谕（那刻夏 L3 发现）。',
};

const EVENT_SEGMENTS_EXTRA = {`);
}
if (!s.includes('sequence_note:')) {
  s = s.replace(
    '    event_segments: eventSegments,',
    '    event_segments: eventSegments,\n    sequence_note: SEQUENCE_NOTES[o.oracle_id] || \'\','
  );
}
fs.writeFileSync(p, s, 'utf8');
require(p);
const J = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/config/oracle-fulfillment.v2.json'), 'utf8'));
const o6 = J.oracles.find((o) => o.oracle_id === 'O06');
console.log('O06 sequence_note =', (o6.sequence_note || '').slice(0, 80));
