/** patch-a1-fixes.js — 修正 A1：O05 归属玻吕茜亚；神谕支持多事件段（O13 = 3.4 + 3.7） */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

// 1) build-oracles.js: O05 holder -> 玻吕茜亚
const bo = path.join(ROOT, 'tools/build-oracles.js');
let t = fs.readFileSync(bo, 'utf8');
t = t.replace(/id: 'O05', holder: '[^']*'/, "id: 'O05', holder: '玻吕茜亚'");
if (!t.includes("note: '双子（遐蝶/玻吕茜亚）共有神谕")) {
  t = t.replace("id: 'O05', holder: '玻吕茜亚', titan: '塞纳托斯（死亡）'",
    "id: 'O05', holder: '玻吕茜亚', titan: '塞纳托斯（死亡）', note: '双子（遐蝶/玻吕茜亚）共有神谕；塞纳托斯神权只能由一人执掌'");
}
fs.writeFileSync(bo, t, 'utf8');
console.log('✓ build-oracles.js: O05 holder=玻吕茜亚');

// 2) build-oracle-fulfillment-v2.js: 人工事件段覆盖（多段）+ O05 候选覆盖
const bf = path.join(ROOT, 'tools/build-oracle-fulfillment-v2.js');
let s = fs.readFileSync(bf, 'utf8');

const extraBlock = `
// ===== 人工修正（2026-10-24，依据用户裁定）=====
// event_segments 支持多段：{segment_id, role: '兑现'|'意义转折', note}
const EVENT_SEGMENTS_EXTRA = {
  O13: [
    { segment_id: '3.4|英雄啊，点燃那最初的骄阳|7', role: '意义转折', note: '「为这个我们深爱的世界，写下不同以往的结局」——收梢的预演/写作行为' },
    { segment_id: '3.7|魔女的孤诣课题|21', role: '兑现', note: '收梢于花开时；德谬歌诞生（含水晶花寓言的改写）' },
  ],
};
// O05 双子共有：候选人工指定
const EVENT_CANDIDATE_EXTRA = {
  O05: ['3.2|断梦啊，从夙世捎来启迪|1', '3.2|断梦啊，从夙世捎来启迪|2', '3.2|摇船啊，请载我横渡冥流|19'],
};
`;
if (!s.includes('EVENT_SEGMENTS_EXTRA')) {
  s = s.replace('const segOf = (occ) =>', extraBlock + '\nconst segOf = (occ) =>');
}
// 在 candidates 组装后追加额外事件段
if (!s.includes('event_segments:')) {
  s = s.replace(
    '  const proposed = candidates.length ? candidates[0].segment_ids.find((id) => !recitation.includes(id)) : null;',
    `  const proposed = candidates.length ? candidates[0].segment_ids.find((id) => !recitation.includes(id)) : null;
  const extraSegments = EVENT_SEGMENTS_EXTRA[o.oracle_id] || [];
  const extraCandidates = EVENT_CANDIDATE_EXTRA[o.oracle_id] || [];
  const eventSegments = extraSegments.length
    ? extraSegments
    : (proposed ? [{ segment_id: proposed, role: '兑现', note: '' }] : []);`
  );
  s = s.replace(
    '    proposed_event_segment: proposed || \'\',',
    `    proposed_event_segment: proposed || '',
    event_segments: eventSegments,
    manual_event_candidate_segments: extraCandidates,`
  );
}
fs.writeFileSync(bf, s, 'utf8');
console.log('✓ build-oracle-fulfillment-v2.js: 已支持 event_segments 多段 + O05 候选覆盖');

// 3) 重跑两个生成器
require(path.join(ROOT, 'tools/build-oracles.js'));
console.log('--- oracles 已重建 ---');
