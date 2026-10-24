/**
 * build-segments.js — 生成「步骤实例」表（实验口径见 docs/实验口径与评测方案.md）
 * 输入: data/corpus/amphoreus.final.jsonl
 * 输出: data/corpus/segments.jsonl + 统计打印
 *
 * 单位: segment_id = version|task|step_idx
 * 原则: 只标记不过滤/不删除（过滤交给后续实验按标记选择）
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const IN = path.join(ROOT, 'data/corpus/amphoreus.final.jsonl');
const OUT = path.join(ROOT, 'data/corpus/segments.jsonl');

const R = fs.readFileSync(IN, 'utf8').trim().split('\n').map(JSON.parse);

// 词表（semantic_recall：字面不同但语义回收的线索）
const loadTerms = (p) => {
  try { return JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8')).terms || []; }
  catch { return []; }
};
const VOCABS = {
  oracle: loadTerms('data/config/vocab-oracle.json'),
  motif: loadTerms('data/config/vocab-motif.json'),
  address: loadTerms('data/config/vocab-address.json'),
  ballad: loadTerms('data/config/vocab-ballad.json'),
};

// 系统/操作类文本启发式（旁白的操作提示、战斗动作、地图指引等）
const SYSTEM_LIKE = /^(击杀|击败|获得|收集|调查|前往|离开|开启|关闭|进入|返回|点击|选择|与.{1,10}(对话|交谈)|打开|使用|放置|护送|跟随|解救|阻止|击败|清除|回到|走到|靠近|查看|阅读|拾取|完成)/;

const segMap = new Map();
for (const r of R) {
  const sid = [r.version, r.task, r.step_idx].join('|');
  if (!segMap.has(sid)) {
    segMap.set(sid, {
      segment_id: sid,
      version: r.version,
      order: r.order,
      task: r.task,
      series_no: r.series_no,
      step_idx: r.step_idx,
      step_title: r.step_title,
      inferred: !!r.step_title_inferred,
      records: [],
    });
  }
  segMap.get(sid).records.push(r);
}

const segs = [];
for (const s of segMap.values()) {
  const recs = s.records;
  const main = recs.filter((r) => r.view === 'main');
  const dia = main.filter((r) => r.kind === 'dialogue');
  const nar = main.filter((r) => r.kind === 'narration');
  const opt = recs.filter((r) => r.kind === 'option');
  const sms = recs.filter((r) => r.kind === 'sms' || r.kind === 'sms_option');
  const join = (arr) => arr.map((r) => r.text_clean || r.text || '').filter(Boolean).join('');
  const textDialogue = join(dia);
  const textNarration = join(nar);
  const textAll = join([...dia, ...nar]);
  const speakers = [...new Set(main.map((r) => r.canonical_speaker).filter((x) => x && x !== 'generic_npc' && x !== '旁白'))];
  const cntKind = (k) => main.filter((r) => r.repeat_kind === k).length;
  const nMain = main.length || 1;

  const systemLike = nar.filter((r) => SYSTEM_LIKE.test((r.text_clean || '').trim())).length;
  const lowContent = textDialogue.length < 20 && dia.length <= 1;

  // 步骤内 main 记录，按剧情顺序（id 升序），供滑窗/说话人/视角计算使用
  const mainRecords = main
    .slice()
    .sort((a, b) => a.id - b.id)
    .map((r) => ({
      id: r.id,
      kind: r.kind,
      speaker: (r.canonical_speaker && r.canonical_speaker !== 'generic_npc') ? (r.form ? `${r.canonical_speaker}(${r.form})` : r.canonical_speaker) : (r.speaker || '旁白'),
      text: r.text_clean || r.text || '',
    }));

  // 滑窗口径：20 条记录、步长 10；记录数 < 20 时整步一个窗口并标记
  const nRecWindow = mainRecords.length;
  const shortForWindow = nRecWindow < 20;
  const nWindows = shortForWindow ? 1 : Math.floor((nRecWindow - 20) / 10) + 1;

  // semantic_recall：词表匹配（与 surface_repetition 分开）
  const segText = textAll;
  const hit = (arr, minLen) => arr.filter((t) => t.length >= minLen && segText.includes(t));
  const srOracle = hit(VOCABS.oracle, 3);
  const srMotif = hit(VOCABS.motif, 3);
  const srAddress = hit(VOCABS.address, 2);
  const srBallad = hit(VOCABS.ballad, 3);
  const srAll = [...new Set([...srOracle, ...srMotif, ...srAddress, ...srBallad])];

  segs.push({
    segment_id: s.segment_id,
    version: s.version,
    order: s.order,
    task: s.task,
    series_no: s.series_no,
    step_idx: s.step_idx,
    step_title: s.step_title,
    inferred: s.inferred,
    n_records: recs.length,
    n_main: main.length,
    n_dialogue: dia.length,
    n_narration: nar.length,
    n_option: opt.length,
    n_sms: sms.length,
    n_extra: recs.length - main.length,
    char_len: textAll.length,
    char_len_dialogue: textDialogue.length,
    text_dialogue: textDialogue,
    text_narration: textNarration,
    text_all: textAll,
    speakers,
    has_option: opt.length > 0,
    has_dialogue: dia.length > 0,
    system_only: dia.length === 0 && nar.length > 0 && systemLike === nar.length,
    system_like_ratio: nar.length ? +(systemLike / nar.length).toFixed(3) : 0,
    low_content: lowContent,
    pause_ratio: +(cntKind('pause') / nMain).toFixed(3),
    motif_count: cntKind('motif'),
    ritual_count: cntKind('ritual'),
    structure_count: cntKind('structure'),
    translation_count: cntKind('translation'),
    // 重复功能分两层：surface_repetition（repeat_kind）+ semantic_recall（词表匹配）
    surface_repetition_count: main.filter((r) => ['motif', 'catchphrase', 'structure', 'ritual', 'translation'].includes(r.repeat_kind)).length,
    semantic_recall_oracle_count: srOracle.length,
    semantic_recall_motif_count: srMotif.length,
    semantic_recall_address_count: srAddress.length,
    semantic_recall_ballad_count: srBallad.length,
    semantic_recall_count: srAll.length,
    semantic_recall_terms: srAll.slice(0, 20),
    // 滑窗结构（语义突变特征待实现，这里先给出窗口信息）
    main_records: mainRecords,
    n_records_window: nRecWindow,
    short_for_window: shortForWindow,
    n_windows: nWindows,
    semantic_shift_top20_mean: null,
    semantic_shift_p90: null,
    semantic_shift_max: null,
    option_texts: opt.map((r) => r.text_clean || r.text),
  });
}

segs.sort((a, b) => a.order - b.order || a.step_idx - b.step_idx);
fs.writeFileSync(OUT, segs.map((s) => JSON.stringify(s)).join('\n'), 'utf8');

// ---------------- 统计 ----------------
const cnt = (f) => segs.reduce((a, s) => { const k = f(s); a[k] = (a[k] || 0) + 1; return a; }, {});
const eligible = segs.filter((s) => s.n_main > 0 && !s.low_content && s.has_dialogue);
const pct = (a, b) => (b ? ((a / b) * 100).toFixed(2) : '0.00');
const lens = eligible.map((s) => s.char_len).sort((a, b) => a - b);
const q = (p) => lens[Math.floor(lens.length * p)] || 0;

console.log('=== 步骤实例表 ===');
console.log(`步骤实例总数 = ${segs.length}`);
console.log(`按版本: ${JSON.stringify(cnt((s) => s.version))}`);
console.log(`有对白的 = ${segs.filter((s) => s.has_dialogue).length}`);
console.log(`含选项的 = ${segs.filter((s) => s.has_option).length}`);
console.log(`inferred=true = ${segs.filter((s) => s.inferred).length} (${pct(segs.filter((s) => s.inferred).length, segs.length)}%)`);
console.log(`system_only = ${segs.filter((s) => s.system_only).length}`);
console.log(`low_content = ${segs.filter((s) => s.low_content).length}`);
console.log(`\n合格候选池（n_main>0 且 非low_content 且 有对白）= ${eligible.length} (${pct(eligible.length, segs.length)}%)`);
console.log(`  版本分布: ${JSON.stringify(cnt.call(null, (s) => s.version))}`);
const eVer = {};
eligible.forEach((s) => (eVer[s.version] = (eVer[s.version] || 0) + 1));
console.log(`  合格池版本分布: ${JSON.stringify(eVer)}`);
console.log(`  长度 P50/P90/P99/max = ${q(0.5)} / ${q(0.9)} / ${q(0.99)} / ${lens[lens.length - 1] || 0}`);
const sizes = eligible.map((s) => (s.n_dialogue <= 3 ? '1-3句' : s.n_dialogue <= 10 ? '4-10句' : s.n_dialogue <= 30 ? '11-30句' : '>30句'));
console.log(`  规模分布: ${JSON.stringify(sizes.reduce((a, k) => ((a[k] = (a[k] || 0) + 1), a), {}))}`);
console.log(`\n重复功能合计（合格池）: pause=${eligible.reduce((a, s) => a + Math.round(s.pause_ratio * s.n_main), 0)} motif=${eligible.reduce((a, s) => a + s.motif_count, 0)} ritual=${eligible.reduce((a, s) => a + s.ritual_count, 0)} structure=${eligible.reduce((a, s) => a + s.structure_count, 0)} translation=${eligible.reduce((a, s) => a + s.translation_count, 0)}`);
console.log(`\n合格池最长 3 个步骤:`);
eligible.sort((a, b) => b.char_len - a.char_len).slice(0, 3).forEach((s) => console.log(`  ${s.segment_id} | ${s.step_title.slice(0, 24)} | ${s.char_len} 字 / ${s.n_dialogue} 句`));
console.log(`\n输出: ${OUT}`);
