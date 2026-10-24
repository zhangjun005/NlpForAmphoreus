/** patch-l3-final.js — 最后两个 L3（三月七/丹恒）带来的数据修正与归档
 * A. 语料就地修正（final.jsonl，gitignored；脚本可复现）：
 *    A1) 13 条 speaker=长夜月 的记录 canonical_speaker 改为 三月七（form=长夜月）
 *    A2) #24334 抓取混入「防止你忘记原文：揭开记忆的帷幕」→ text/text_clean 清理为「揭开记忆的被褥——」
 * B. knife-scenes：
 *    B1) K22 注记「丹恒与荒笛共有场景」；B2) K33 扩展尾段「重逢|3」#22726–#22738
 * C. oracle-fulfillment.v2：O12 加 type_note（字面为主，另有反转读法）
 * D. 导出《昔涟》歌词块 data/config/song-lyrics.json（供后续歌词查询用）
 * E. l3-open-questions 增补/更新
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const jp = (p) => path.join(ROOT, p);

// A1 + A2：语料就地修正
const lines = fs.readFileSync(jp('data/corpus/amphoreus.final.jsonl'), 'utf8').trim().split('\n');
let fixedLong = 0, fixedClean = 0;
const out = lines.map((ln) => {
  const r = JSON.parse(ln);
  if (r.canonical_speaker === '长夜月') {
    r.canonical_speaker = '三月七';
    r.form = '长夜月';
    fixedLong++;
  }
  if (r.id === 24334) {
    r.text = '「揭开记忆的被褥——」';
    r.text_clean = '「揭开记忆的被褥——」';
    r.corpus_fix_note = '原记录混入抓取注释「防止你忘记原文：揭开记忆的帷幕」，已清理（三月七 L3 发现）';
    fixedClean++;
  }
  return JSON.stringify(r);
});
fs.writeFileSync(jp('data/corpus/amphoreus.final.jsonl'), out.join('\n') + '\n', 'utf8');
console.log('语料修正：长夜月→三月七', fixedLong, '条；#24334 清理', fixedClean, '条');

// B：knife-scenes
const kp = jp('data/config/knife-scenes.json');
const K = JSON.parse(fs.readFileSync(kp, 'utf8'));
const k22 = (K.scenes || []).find((x) => x.id === 'K22');
if (k22) {
  k22.scene_note = '丹恒与荒笛共有场景：承接大地火种、现场说话最多的是丹恒（丹恒 L3 发现）；role/group 仍按 NPC 注记口径，但报告须写「K22 为丹恒与荒笛共有」。';
}
const k33 = (K.scenes || []).find((x) => x.id === 'K33');
if (k33) {
  k33.range_note = '原 ranges 只到 #22681；长夜月真正的告别在下一段 3.6|重逢|3（#22726–#22738，「让『无漏净子』这个名字，从你脑海中褪去吧」「『忘却』会守望你的来路，如长夜般隐秘，永远安宁♭」），引用/统计时须并入（三月七 L3 发现）。';
  k33.extended_record_span = [22726, 22738];
  k33.extended_segment_ids = ['3.6|重逢啊，笑泪相拥|3'];
}
fs.writeFileSync(kp, JSON.stringify(K, null, 2), 'utf8');
console.log('K22/K33 注记已补');

// C：O12 type_note
const fp = jp('tools/build-oracle-fulfillment-v2.js');
if (!fs.readFileSync(fp, 'utf8').includes('O12')) {
  let s = fs.readFileSync(fp, 'utf8');
  s = s.replace('const SEQUENCE_NOTES = {', `const TYPE_NOTES = {
  O12: 'v2 记「字面」；丹恒 L3 认为原句在承接后被改写为「以身为舟／荒龙腾飞」（#21679–#21700），按「词语保留、价值反转」口径也可读作「反转」。报告保留「字面」统计，另注明反转读法。',
};

const SEQUENCE_NOTES = {`);
  s = s.replace('    sequence_note: SEQUENCE_NOTES[o.oracle_id] || \'\',', '    sequence_note: SEQUENCE_NOTES[o.oracle_id] || \'\',\n    type_note: TYPE_NOTES[o.oracle_id] || \'\',');
  fs.writeFileSync(fp, s, 'utf8');
  console.log('O12 type_note 生成器已改');
}
// 直接补进现有 JSON（避免重复 require 影响）
const vp = jp('data/config/oracle-fulfillment.v2.json');
const V = JSON.parse(fs.readFileSync(vp, 'utf8'));
const o12 = (V.oracles || []).find((o) => o.oracle_id === 'O12');
if (o12) {
  o12.type_note = 'v2 记「字面」；丹恒 L3 认为原句在承接后被改写为「以身为舟／荒龙腾飞」（#21679–#21700），按「词语保留、价值反转」口径也可读作「反转」。报告保留「字面」统计，另注明反转读法。';
  fs.writeFileSync(vp, JSON.stringify(V, null, 2), 'utf8');
  console.log('O12 type_note 已写入');
}

// D：歌词导出（昔涟《如我所书》歌词块 #26218–#26241）
const recs = out.map((l) => JSON.parse(l));
const lyricRecs = recs.filter((r) => r.id >= 26218 && r.id <= 26241);
fs.writeFileSync(jp('data/config/song-lyrics.json'), JSON.stringify({
  note: '游戏内《如我所书》插曲歌词块（3.7|落英|11，旁白唱词），可用于歌词向量查询对照（用户计划）',
  segment: '3.7|落英啊，残芳纷飞留归|11',
  records: lyricRecs.map((r) => ({ id: r.id, text: r.text })),
  full_text: lyricRecs.map((r) => r.text).join('\n'),
}, null, 2), 'utf8');
console.log('歌词导出条数 =', lyricRecs.length);

// E：open questions
const oqp = jp('data/config/l3-open-questions.json');
const oq = JSON.parse(fs.readFileSync(oqp, 'utf8'));
const ids = new Set(oq.items.map((x) => x.id));
const add = (item) => { if (!ids.has(item.id)) { oq.items.push(item); ids.add(item.id); } };
add({ id: 'L3-OQ16', char: '三月七', issue: '13 条 speaker=长夜月 的记录 canonical 为「长夜月」而非三月七（v3 归一缺口）；全库 ♭ 14 条 100% 属长夜月', decision: '已就地修正为 canonical=三月七/form=长夜月（13 条）；统计口径 664 条 +13 = 677（报告注明）', status: 'resolved' });
add({ id: 'L3-OQ17', char: '丹恒', issue: 'K22 role/group 记「荒笛/NPC」，但场景中说话最多、承接大地火种的是丹恒', decision: 'K22 加 scene_note「丹恒与荒笛共有」；报告写共有场景，不把丹恒唯一一次承接神权算给 NPC', status: 'resolved' });
add({ id: 'L3-OQ18', char: '丹恒', issue: 'O12 兑现类型：v2 记字面，L3 认为价值反转（以身为舟/荒龙腾飞）', decision: '统计保留字面，加 type_note 注明反转读法', status: 'resolved' });
add({ id: 'L3-OQ19', char: '全员', issue: '《如我所书》结尾 #26119–#26122 列出 14 个名字，但 #26176 说「十三位英雄」；14 名 = 11 黄金裔 + 三月七 + 丹恒 + 开拓者', decision: '「十三英雄」= 11 黄金裔 + 三月七 + 丹恒；开拓者不在英雄名单（只在 14 个被写下的名字里）——与报告 11+3 口径一致', status: 'resolved' });
add({ id: 'L3-OQ20', char: '三月七', issue: '#24334 抓取混入「防止你忘记原文：揭开记忆的帷幕」；#26218–#26241 是《如我所书》歌词块', decision: '#24334 已清理；歌词单独导出 data/config/song-lyrics.json', status: 'resolved' });
add({ id: 'L3-OQ21', char: '三月七', issue: '她的深读覆盖统计 6/53 是旧口径；3.0/3.4/3.5 的 14 步 144 条本次已补读', decision: '报告用「L3 已补读」口径，不再引用 6/53', status: 'resolved' });
fs.writeFileSync(oqp, JSON.stringify(oq, null, 2), 'utf8');
console.log('open questions 总条数 =', oq.items.length);
