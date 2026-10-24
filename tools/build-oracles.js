/**
 * build-oracles.js — 建 13 条神谕表 + 四份词表（神谕/母题/称呼/歌谣）
 * 输入: data/corpus/amphoreus.final.jsonl、data/corpus/segments.jsonl、data/corpus/ruby-pairs.jsonl、data/config/speaker-alias.v3.json
 * 输出:
 *   data/corpus/oracles.jsonl        神谕表（含引用 occurrence、注音隐喻、候选兑现场景）
 *   data/config/vocab-oracle.json    神谕词表
 *   data/config/vocab-motif.json     母题词表
 *   data/config/vocab-address.json   称呼词表
 *   data/config/vocab-ballad.json    歌谣词表
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const rd = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const R = rd('data/corpus/amphoreus.final.jsonl').trim().split('\n').map(JSON.parse);
const SEG = rd('data/corpus/segments.jsonl').trim().split('\n').map(JSON.parse);
const ruby = rd('data/corpus/ruby-pairs.jsonl').trim().split('\n').map(JSON.parse);
const alias = JSON.parse(rd('data/config/speaker-alias.v3.json'));

const norm = (s) => (s || '').replace(/[「」『』"“”\s…\.。！？、，；：—\-【】（）()]/g, '');

// 13 条神谕（12 黄金裔，遐蝶两条：缇宁解读版 + 玻吕茜亚版）
const ORACLES = [
  { id: 'O01', holder: '阿格莱雅', titan: '墨涅塔（浪漫）', text: '汝将最后一次沐浴，在温热耀眼的黄金中。', keywords: ['沐浴', '黄金'] },
  { id: 'O02', holder: '缇宝', titan: '雅努斯（门径）', text: '汝将碎作千片，凋零在他乡的土壤。', keywords: ['碎作千片', '凋零', '他乡'], source_lines: [{ record_id: 7939, speaker: '雅努斯', text: '指引世人者，灵魂必遭歧路分离，碎作千片化身，如琉璃掷地……' }, { record_id: 7744, speaker: '欧洛尼斯', text: '若散播预言，只会引发灾难。那灾难…足以将你撕成千片。' }], source_note: 'O02 的「原文」是缇宝从泰坦散文化宣判（#7939/#7744）中提炼成的十二字箴言；提炼动作本身未被任何配置记录（缇宝 L3 发现）' },
  { id: 'O03', holder: '万敌', titan: '尼卡多利（纷争）', text: '终有一日，汝将背后负创而死。', keywords: ['背后负创', '负创'] },
  { id: 'O04', holder: '遐蝶', titan: '塞纳托斯（死亡）', text: '花海尽头，生者的魂灵将温暖汝之指尖；相拥之后，便是永恒的离别。', keywords: ['花海', '指尖', '永恒的离别'] },
  { id: 'O05', holder: '玻吕茜亚', titan: '塞纳托斯（死亡）', note: '双子（遐蝶/玻吕茜亚）共有神谕；塞纳托斯神权只能由一人执掌', text: '汝将凋零，令逝者自残余中发芽，一同死去的火新生。', keywords: ['凋零', '发芽', '火新生'] },
  { id: 'O06', holder: '那刻夏', titan: '瑟希斯（理性）', text: '汝将超越至纯粹之终极，回归腐败苦黑。', keywords: ['纯粹', '终极', '腐败', '苦黑'] },
  { id: 'O07', holder: '风堇', titan: '艾格勒（天空）', text: '在彩虹桥的尽头，天空之子将缝补晨昏。', keywords: ['彩虹桥', '天空之子', '缝补晨昏'] },
  { id: 'O08', holder: '赛飞儿', titan: '扎格列斯（诡计）', text: '汝将与贪婪同行，亦将亡于分文。', keywords: ['贪婪', '分文'] },
  { id: 'O09', holder: '白厄', titan: '刻法勒（负世）', text: '汝将肩负骄阳，直至灰白的黎明显著。', keywords: ['骄阳', '灰白的黎明'] },
  { id: 'O10', holder: '海瑟音', titan: '法吉娜（海洋）', text: '汝将长眠于涛声中，于天地境界之海完成征服。', keywords: ['涛声', '天地境界之海', '征服'] },
  { id: 'O11', holder: '刻律德菈', titan: '塔兰顿（律法）', text: '汝将于天地境界之海完成征服，长眠于涛声中。', keywords: ['天地境界之海', '涛声'] },
  { id: 'O12', holder: '荒笛', titan: '吉奥里亚（大地）', text: '汝将自掘坟墓，焚毁于叛逆的熔炉。', keywords: ['自掘坟墓', '叛逆', '熔炉'] },
  { id: 'O13', holder: '昔涟', titan: '德谬歌（创世）', text: '汝将收梢于花开时，一如终结诞下起始。', keywords: ['收梢', '花开', '终结', '起始'] },
];

// 注音：表面词→所指（只取有意义的对，排除神名→神职的常规对照表）
const nameSet = new Set(Object.keys(alias.canonical));
for (const v of Object.values(alias.canonical)) for (const t of v.titles || []) nameSet.add(t);
const rubyPairs = ruby.filter((r) => r.display !== r.gloss);

const segs = SEG.filter((s) => s.has_dialogue && !s.low_content);
const out = [];

for (const o of ORACLES) {
  const no = norm(o.text);
  // 神谕的"可匹配片段"：整句 + 按标点切出的部分（支持半句引用，如「花海尽头…」只引前半句）
  const frags = [o.text, ...o.text.split(/[；;，,、]/)]
    .map(norm)
    .filter((s) => s.length >= 8);

  // 引用 occurrence：记录文本包含任一可匹配片段
  const occ = R.filter((r) => {
    const nr = norm(r.text);
    return frags.some((f) => nr.includes(f));
  })
    .map((r) => ({
      id: r.id, version: r.version, task: r.task, step_idx: r.step_idx, step_title: r.step_title,
      speaker: r.canonical_speaker || r.speaker || '旁白',
      form: r.form || null,
      repeat_kind: r.repeat_kind,
      text: r.text,
    }))
    .sort((a, b) => a.id - b.id);

  // 注音隐喻：display（≥2 字）出现在神谕文本中即可；单字「汝」按语义特例处理（只对白厄预言 O09 有意义）
  const metaphors = rubyPairs
    .filter((p) => p.display.length >= 2 && o.text.includes(p.display))
    .map((p) => ({ display: p.display, gloss: p.gloss, page: p.page }))
    .filter((v, i, arr) => arr.findIndex((x) => x.display === v.display && x.gloss === v.gloss) === i);
  if (o.id === 'O09' && !metaphors.some((m) => m.display === '汝')) {
    metaphors.unshift({ display: '汝', gloss: '白厄', page: '（白厄预言原文注音）' });
  }

  // 候选兑现步骤：关键词命中数（作为人工标注的提示，不作为结论）
  const scored = segs
    .map((s) => {
      const txt = s.text_all || '';
      let score = 0;
      const hits = [];
      for (const k of o.keywords) if (txt.includes(k)) { score += 2; hits.push(k); }
      for (const m of metaphors) if (txt.includes(m.gloss)) { score += 1; hits.push(m.gloss); }
      return { segment_id: s.segment_id, version: s.version, task: s.task, step_title: s.step_title, score, hits };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 8);

  out.push({
    oracle_id: o.id,
    text: o.text,
    holder: o.holder,
    titan: o.titan,
    keywords: o.keywords,
    tokens_for_recall: [...new Set([...o.keywords, ...metaphors.map((m) => m.display), ...metaphors.map((m) => m.gloss)])],
    metaphors,
    occurrences: occ,
    first_appearance: occ.length ? { version: occ[0].version, task: occ[0].task, id: occ[0].id } : null,
    fulfillment_candidates: scored,
    ...(o.source_lines ? { source_lines: o.source_lines } : {}),
    ...(o.source_note ? { source_note: o.source_note } : {}),
    fulfillment: '',        // 人工填写：task / step_idx / segment_id
    fulfillment_type: '',   // 人工填写：字面 / 反转 / 错位
    note: '',
  });
}

fs.writeFileSync(path.join(ROOT, 'data/corpus/oracles.jsonl'), out.map((o) => JSON.stringify(o)).join('\n'), 'utf8');

// ---------------- 四份词表 ----------------
const oracleTerms = [...new Set(out.flatMap((o) => o.tokens_for_recall))];
fs.writeFileSync(path.join(ROOT, 'data/config/vocab-oracle.json'), JSON.stringify({
  note: '神谕词表：关键词 + 注音隐喻表面词 + 注音所指',
  by_oracle: Object.fromEntries(out.map((o) => [o.oracle_id, o.tokens_for_recall])),
  terms: oracleTerms,
}, null, 2), 'utf8');

const motifTerms = [
  '逐火是不断失却的旅途', '明天见', '不要回头', '灰白的黎明', '长夜', '一页永恒',
  '记忆的种子', '记忆的幼芽', '记忆的花', '记忆的花蕾', '涟漪', '德谬歌', '迷路迷境',
  '无漏净子', '金枝', '火种', '创世涡心', '黎明机器', '再创世', '永劫回归', '盗火行者',
  '空白的愿望', '另一位作者', '哀丽秘榭', '太阳', '烈阳', '新页', '故事的下一页',
];
fs.writeFileSync(path.join(ROOT, 'data/config/vocab-motif.json'), JSON.stringify({
  note: '母题词表（人工维护，用于 semantic_recall：字面不同但语义回收）',
  terms: motifTerms,
}, null, 2), 'utf8');

// 称呼词表：来自 address_scan_index 全部称呼 + 神谕/正式敬语
const addrTerms = [...new Set([...Object.keys(alias.address_scan_index || {}),
  '阁下', '大人', '陛下', '凯撒', '吾师', '老师', '救世主', '伙伴', '搭档', '主爵',
  '王储', '殿下', '半神', '黄金裔', '无名客', '异乡人', '旅人', '小家伙'])];
fs.writeFileSync(path.join(ROOT, 'data/config/vocab-address.json'), JSON.stringify({
  note: '称呼词表：address_scan_index 全部称呼 + 敬语/身份称呼',
  terms: addrTerms,
  by_target: alias.address_scan_index || {},
}, null, 2), 'utf8');

// 歌谣词表：人工列 + 从语料里搜到的歌谣相关记录 id
const balladHits = R.filter((r) => /歌谣|童谣|谣曲|迷路迷境|小妖精/.test(r.text || ''));
const balladTerms = [...new Set(['歌谣', '童谣', '谣曲', '迷路迷境', '小妖精', '风中的歌谣',
  '于是便有了我、你，编织言语和歌谣', '新页'])];
fs.writeFileSync(path.join(ROOT, 'data/config/vocab-ballad.json'), JSON.stringify({
  note: '歌谣词表（人工）：用于识别歌谣/童谣类文本的引用与回收',
  terms: balladTerms,
  corpus_hits: balladHits.slice(0, 40).map((r) => ({ id: r.id, version: r.version, speaker: r.canonical_speaker || r.speaker, text: r.text })),
  corpus_hit_count: balladHits.length,
}, null, 2), 'utf8');

// ---------------- 统计 ----------------
console.log('=== 神谕表 ===');
for (const o of out) {
  console.log(`${o.oracle_id} ${o.holder}(${o.titan}) 引用=${o.occurrences.length} 隐喻=${o.metaphors.length} 候选=${o.fulfillment_candidates.length} | ${o.text.slice(0, 30)}`);
}
console.log('\n引用总数 =', out.reduce((s, o) => s + o.occurrences.length, 0));
console.log('有注音隐喻的神谕 =', out.filter((o) => o.metaphors.length).length);
console.log('词表: oracle=' + oracleTerms.length + ' motif=' + motifTerms.length + ' address=' + addrTerms.length + ' ballad=' + balladTerms.length);
console.log('歌谣相关记录 =', balladHits.length);
console.log('\n注音隐喻样例:');
for (const o of out) if (o.metaphors.length) console.log('  ' + o.oracle_id + ': ' + o.metaphors.map((m) => `${m.display}→${m.gloss}`).join(' ; '));
