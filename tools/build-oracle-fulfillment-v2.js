/**
 * build-oracle-fulfillment-v2.js
 * A1：把神谕兑现拆成「吟诵段 recitation」与「事件段 event」
 * 输入：data/corpus/oracles.jsonl、data/config/oracle-fulfillment.filled.json、data/config/knife-scenes.json
 * 输出：data/config/oracle-fulfillment.v2.json（候选）、data/reports/oracle-fulfillment-v2-review.md（13 行供人工确认）
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const rd = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const ORACLES = rd('data/corpus/oracles.jsonl').trim().split('\n').map(JSON.parse);
const FILLED = JSON.parse(rd('data/config/oracle-fulfillment.filled.json'));
const KNIFE = JSON.parse(rd('data/config/knife-scenes.json'));
const filledById = Object.fromEntries((FILLED.oracles || []).map((o) => [o.oracle_id, o]));


// ===== 人工修正（2026-10-24，依据用户裁定）=====
// event_segments 支持多段：{segment_id, role: '兑现'|'意义转折', note}
const SEQUENCE_NOTES = {
  O06: '追认型：v2 把 3.2|争辩|2（segment_index 269）标为兑现，但神谕原句出现在 3.2|学者|4（segment_index 315）——兑现事件在文本顺序上早于神谕被说出；「至纯粹」在瑟希斯说出原句前已出现两次（丹恒概括、那刻夏自述），O06 是被追认的神谕，不是被预告的神谕（那刻夏 L3 发现）。',
};

const EVENT_SEGMENTS_EXTRA = {
  O06: [
    { segment_id: '3.2|争辩啊，代长矛分庭抗礼|2', role: '兑现', note: '自我处刑/交出理性火种；文本顺序早于神谕原句出现（见 sequence_note）' },
  ],
  O05: [
    { segment_id: '3.2|断梦啊，从夙世捎来启迪|1', role: '意义转折', note: '双子抉择：我和姐姐必须有一人牺牲' },
    { segment_id: '3.2|摇船啊，请载我横渡冥流|19', role: '兑现', note: '塞纳托斯形态宣言：命中注定的时刻再次到来' },
  ],
  O13: [
    { segment_id: '3.4|英雄啊，兑现那染血的冀望|7', role: '意义转折', note: '「为这个我们深爱的世界，写下不同以往的结局」——收梢的预演/写作行为' },
    { segment_id: '3.7|魔女的孤诣课题|21', role: '兑现', note: '收梢于花开时；德谬歌诞生（含水晶花寓言的改写）' },
  ],
};
// O05 双子共有：候选人工指定
const EVENT_CANDIDATE_EXTRA = {
  O05: ['3.2|断梦啊，从夙世捎来启迪|1', '3.2|断梦啊，从夙世捎来启迪|2', '3.2|摇船啊，请载我横渡冥流|19'],
};

const segOf = (occ) => `${occ.version}|${occ.task}|${occ.step_idx}`;
const out = [];
const rows = [];

for (const o of ORACLES) {
  const f = filledById[o.oracle_id] || {};
  const recitation = [...new Set((o.occurrences || []).map(segOf))].filter(Boolean);
  // 事件段候选：刀子系统里 角色=holder 或 oracles 提到本 id 的场景
  const scenes = (KNIFE.scenes || []).filter((s) => {
    if (s.role === o.holder) return true;
    return typeof s.oracles === 'string' && s.oracles.includes(o.oracle_id);
  });
  const candidates = scenes
    .map((s) => ({
      scene_id: s.id,
      title: s.title,
      segment_ids: s.segment_ids || [],
      intensity: s.intensity,
      types: s.type || [],
      why: s.why || '',
    }))
    .filter((c) => c.segment_ids.length && c.segment_ids.some((id) => !recitation.includes(id)));
  const proposed = candidates.length ? candidates[0].segment_ids.find((id) => !recitation.includes(id)) : null;
  const extraSegments = EVENT_SEGMENTS_EXTRA[o.oracle_id] || [];
  const extraCandidates = EVENT_CANDIDATE_EXTRA[o.oracle_id] || [];
  const eventSegments = extraSegments.length
    ? extraSegments
    : (proposed ? [{ segment_id: proposed, role: '兑现', note: '' }] : []);

  out.push({
    oracle_id: o.oracle_id,
    text: o.text,
    holder: o.holder,
    titan: o.titan,
    recitation_segments: recitation,
    current_filled_fulfillment: f.fulfillment_segment || '',
    current_filled_type: f.fulfillment_type || '',
    event_candidates: candidates,
    proposed_event_segment: proposed || '',
    event_segments: eventSegments,
    sequence_note: SEQUENCE_NOTES[o.oracle_id] || '',
    manual_event_candidate_segments: extraCandidates,
    proposed_event_scene: candidates.length ? candidates[0].scene_id : '',
    confirm_event_segment: '',   // 人工确认后填写
    confirm_type: '',            // 字面/反转/错位（人工确认）
    note: candidates.length ? '' : '刀子系统未找到对应 event 候选，需人工指定',
  });

  rows.push({
    id: o.oracle_id, holder: o.holder, text: o.text,
    recitationN: recitation.length,
    films: candidates.map((c) => `${c.scene_id}:${c.segment_ids.join(',')}`),
    current: f.fulfillment_segment || '—',
    proposed: proposed || '—',
    type: f.fulfillment_type || '—',
  });
}

fs.writeFileSync(path.join(ROOT, 'data/config/oracle-fulfillment.v2.json'), JSON.stringify({
  note: 'A1 修订：recitation_segments=出现原文/吟诵的步骤；event_candidates=刀子系统给出的兑现事件段候选；confirm_* 待人工确认',
  generated_by: 'tools/build-oracle-fulfillment-v2.js',
  oracles: out,
}, null, 2), 'utf8');

// 复核表
const md = [];
md.push('# 神谕兑现拆分复核表（A1）');
md.push('');
md.push('> 用法：在「确认 event_segment」「确认类型」两列填上你的判断；可直接改 `data/config/oracle-fulfillment.v2.json` 的 `confirm_event_segment` / `confirm_type`。');
md.push('> 说明：`recitation_segments` 是出现神谕原文/吟诵的步骤（可多个）；`event_candidates` 来自 35 个刀子场景（按角色/神谕关联）。');
md.push('> 目的：修复检索实验——v1 的 gold 多数是吟诵步，拆开后用 event 段做 gold 才能公平比较方法。');
md.push('');
md.push('| 神谕 | 持有者 | 吟诵段数 | 事件段候选（场景:segment_id） | 现 gold | 确认 event_segment | 确认类型 |');
md.push('|---|---|---|---|---|---|---|');
for (const r of rows) {
  md.push(`| ${r.id} | ${r.holder} | ${r.recitationN} | ${r.films.length ? r.films.join('<br>') : '（无）'} | ${r.current} |  |  |`);
}
md.push('');
md.push('## 待你确认的 13 行');
md.push('');
for (const r of rows) {
  md.push(`### ${r.id} · ${r.holder}`);
  md.push('');
  md.push(`**神谕**：${r.text}`);
  md.push(`**吟诵段**（${r.recitationN}）：${out.find((x) => x.oracle_id === r.id).recitation_segments.join(' / ')}`);
  md.push(`**事件段候选**：`);
  if (!r.films.length) md.push('- （刀子系统无候选，需人工指定 segment_id）');
  for (const c of out.find((x) => x.oracle_id === r.id).event_candidates) {
    md.push(`- ${c.scene_id}｜${c.title}｜${c.segment_ids.join(',')}｜强度 ${c.intensity}｜${c.types.join('/')}`);
  }
  md.push(`**现 gold（v1，可能仍是吟诵步）**：${r.current}`);
  md.push('');
}
fs.mkdirSync(path.join(ROOT, 'data/reports'), { recursive: true });
fs.writeFileSync(path.join(ROOT, 'data/reports/oracle-fulfillment-v2-review.md'), md.join('\n'), 'utf8');

console.log('oracle-fulfillment.v2.json 已生成：');
for (const r of rows) console.log(`  ${r.id} ${r.holder}: 吟诵段 ${r.recitationN}，事件候选 ${r.films.length}，现 gold=${r.current}，建议=${r.proposed}`);
