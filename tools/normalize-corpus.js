#!/usr/bin/env node
/**
 * normalize-corpus.js — 翁法罗斯主线语料 v2：说话人归一 + 文本清洗
 *
 * 输入（只读）：
 *   data/corpus/amphoreus.jsonl        v1 语料（24,206 条）
 *   data/config/speaker-alias.json     角色称呼/别名/形态归一表
 *   docs/speaker-aliases.md            人工调研的称呼集合（仅作背景，不参与计算）
 *
 * 输出（只写这 3 个文件）：
 *   data/corpus/amphoreus.v2.jsonl     原字段 + canonical_speaker / form / text_clean / view
 *   data/corpus/amphoreus.v2.lines.txt 人读版（格式同 v1，说话人用规范名、文本用 text_clean）
 *   docs/corpus-pipeline.md            处理规则 + 统计 + 变更示例（本脚本自动生成，数字与运行结果同步）
 *
 * 绝不修改 v1 语料、data/raw/、data/config/。发现配置缺漏只在 stdout 与文档中给建议，不改配置。
 *
 * 用法：node tools/normalize-corpus.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const F = {
  input: path.join(ROOT, 'data', 'corpus', 'amphoreus.jsonl'),
  config: path.join(ROOT, 'data', 'config', 'speaker-alias.json'),
  outJsonl: path.join(ROOT, 'data', 'corpus', 'amphoreus.v2.jsonl'),
  outLines: path.join(ROOT, 'data', 'corpus', 'amphoreus.v2.lines.txt'),
  doc: path.join(ROOT, 'docs', 'corpus-pipeline.md'),
};

// ---- 安全护栏：输入文件绝不可能被输出路径覆盖 ----
const READONLY = [F.input, F.config].map((p) => path.resolve(p));
for (const key of ['outJsonl', 'outLines', 'doc']) {
  const out = path.resolve(F[key]);
  if (READONLY.includes(out)) throw new Error(`输出路径与只读输入相同，拒绝运行: ${out}`);
}

const cfg = JSON.parse(fs.readFileSync(F.config, 'utf8'));

// ============================================================
// 一、说话人归一
// ============================================================
const canonicalDefs = cfg.canonical || {};
const literalMap = cfg.speaker_literal_map || {};
const formMap = cfg.form_map || {};
const titlePatterns = (cfg.title_prefix_patterns || []).map((p) => new RegExp(p));
const nonSpeakerLabels = new Set(cfg.non_speaker_labels || []);
const memeTerms = new Set((cfg.meme_terms && cfg.meme_terms.terms) || []);

// 优先级 2 的索引：speaker_aliases → canonical（只保留第一个声明者，防重复登记歧义）
const aliasIndex = new Map();
const canonicalForms = new Map(); // canonical → Set(forms)，用于判断命中的别名是不是"形态"
for (const [canonical, def] of Object.entries(canonicalDefs)) {
  for (const a of def.speaker_aliases || []) if (!aliasIndex.has(a)) aliasIndex.set(a, canonical);
  canonicalForms.set(canonical, new Set(def.forms || []));
}

/**
 * 生成候选写法：原始 → 按 title_prefix_patterns 剥前缀 → 去成对引号 → 去尾部括号注音。
 * 每个候选都按 1→2→3→4 的优先级（literal → alias → form_map → canonical 键）重试。
 * 说明：canonical 键本身作为最末级"隐式 alias"兜底，便于覆盖「断锋爵」拉比努斯 这类
 *       只登记了 titles、没登记 speaker_aliases 的 NPC；form_map 优先于它，因此
 *       长夜月 仍会先命中 form_map 归到 三月七，不会误归到 canonical["长夜月"]。
 */
function speakerVariants(raw) {
  const out = [];
  const seen = new Set();
  const push = (v, how) => {
    if (!v || seen.has(v)) return;
    seen.add(v);
    out.push({ v, how });
  };
  push(raw, '原文');
  for (const re of titlePatterns) push(raw.replace(re, '').trim(), `剥前缀 ${re.source}`);
  push(raw.replace(/^[「『]([\s\S]*)[」』]$/, '$1').trim(), '去成对引号');
  push(raw.replace(/[（(][^（()）]*[)）]\s*$/, '').trim(), '去尾部括号注音');
  // 剥前缀 + 去引号的组合（例如「X」Y 之外还套了一层括号）
  for (const re of titlePatterns) {
    const s = raw.replace(re, '').trim();
    if (s !== raw) {
      push(s.replace(/^[「『]([\s\S]*)[」』]$/, '$1').trim(), `剥前缀+去引号 ${re.source}`);
      push(s.replace(/[（(][^（()）]*[)）]\s*$/, '').trim(), `剥前缀+去括号 ${re.source}`);
    }
  }
  return out;
}

function formOf(canonical, written) {
  const forms = canonicalForms.get(canonical);
  if (forms && forms.has(written)) return written;
  if (formMap[written] === canonical) return written;
  return null;
}

/**
 * @returns {{canonical: string|null, form: string|null, rule: string}}
 */
function resolveSpeaker(raw) {
  const speaker = typeof raw === 'string' ? raw : '';
  if (speaker === '') return { canonical: null, form: null, rule: 'empty' };
  if (nonSpeakerLabels.has(speaker)) return { canonical: null, form: null, rule: 'non_speaker_label' };
  if (memeTerms.has(speaker)) return { canonical: null, form: null, rule: 'meme_term' }; // 梗名不参与归一
  for (const { v, how } of speakerVariants(speaker)) {
    if (Object.prototype.hasOwnProperty.call(literalMap, v)) {
      const hit = literalMap[v];
      return { canonical: hit.canonical || null, form: hit.form ?? null, rule: `1 speaker_literal_map / ${how}` };
    }
    if (aliasIndex.has(v)) {
      const canonical = aliasIndex.get(v);
      return { canonical, form: formOf(canonical, v), rule: `2 speaker_alias / ${how}` };
    }
    if (Object.prototype.hasOwnProperty.call(formMap, v)) {
      return { canonical: formMap[v], form: v, rule: `5 form_map / ${how}` };
    }
    if (Object.prototype.hasOwnProperty.call(canonicalDefs, v)) {
      return { canonical: v, form: null, rule: `4b canonical 键兜底 / ${how}` };
    }
  }
  return { canonical: null, form: null, rule: '6 未命中' };
}

// ============================================================
// 二、文本清洗与 kind 修正
// ============================================================
const HS = /他\/她/g;
const WHOLE_STAR = /^[*＊]([^*＊]+)[*＊]$/;
// 整句 *...* 里一旦出现这些标点，说明是有语义的对白/独白（如赛飞儿演戏的整段台词），不能当舞台指示
const DIALOGUE_PUNCT = /[，。！？…、；：,.!?;:「」『』（）()“”"'"]/;
// 3.6#07 长夜月的「他/她们俩」：按任务要求不做性别替换
const isHeSheException = (rec) =>
  rec && rec.version === '3.6' && String(rec.series_no) === '07' && /长夜月/.test(rec.speaker || '');

function cleanText(rec) {
  const rawText = typeof rec.text === 'string' ? rec.text : '';
  const trimmed = rawText.trim();
  const changes = [];
  const starInfo = { stageDirection: false, wholeStarDialogue: false, starRemoved: 0 };
  let t = rawText;

  // 2.1 模板残留：先删成对 {{...}}，再删被截断的 {{...（v1 解析器在跨行模板处截断）
  let before = t;
  t = t.replace(/\{\{[^{}]*\}\}/g, '');
  t = t.replace(/\{\{[\s\S]*$/, '');
  t = t.replace(/\}\}/g, '').replace(/\{\{/g, '');
  if (t !== before) changes.push('template_residue');

  // 2.2 <br> 等 HTML 残留
  before = t;
  t = t.replace(/<br\s*\/?>/gi, '');
  if (t !== before) changes.push('html_br');

  // 2.3 [[链接]] 残留：保留显示文本，只去标记
  before = t;
  t = t.replace(/\[\[([^\]|]*)\|([^\]]*)\]\]/g, '$2').replace(/\[\[([^\]]*)\]\]/g, '$1');
  t = t.replace(/\[\[|\]\]/g, '');
  if (t !== before) changes.push('wiki_link');

  // 2.4 他/她 → 开拓者（3.6#07 长夜月的「他/她们俩」保留）
  before = t;
  let heSheCount = 0;
  let keptException = 0;
  const exception = isHeSheException(rec);
  t = t.replace(HS, (m, offset, s) => {
    if (exception && s.startsWith('他/她们俩', offset)) {
      keptException++;
      return m;
    }
    heSheCount++;
    return '开拓者';
  });
  if (t !== before) changes.push('he_she');

  // 2.5 *强调* / *舞台指示*
  //     整句被一对 * 包住且不含标点 → 舞台指示（拟声/动作描述）→ kind 改 narration，去星号
  //     其余（行内 *我们*、整段带标点的演戏台词等）→ 只去星号，保留台词
  const isWholeStar = WHOLE_STAR.test(trimmed) && !DIALOGUE_PUNCT.test(trimmed);
  let kind = rec.kind;
  before = t;
  if (isWholeStar) {
    starInfo.stageDirection = true;
    kind = 'narration';
    const n = (t.match(/[*＊]/g) || []).length;
    starInfo.starRemoved = n;
    t = t.replace(/[*＊]/g, '');
    changes.push('stage_direction');
  } else if (/[*＊]/.test(t)) {
    if (WHOLE_STAR.test(trimmed)) starInfo.wholeStarDialogue = true; // 整句*…*但含标点 → 按台词保留
    const n = (t.match(/[*＊]/g) || []).length;
    starInfo.starRemoved = n;
    t = t.replace(/[*＊]/g, '');
    changes.push('emphasis_star');
  }

  const text = t.trim();
  return { text, kind, changes, heSheCount, keptException, starInfo, hadText: rawText !== '' };
}

// ============================================================
// 三、主流程
// ============================================================
const stats = {
  total: 0,
  badLines: [],
  blankLines: 0,
  rules: new Map(), // 归一规则命中条数
  canonical: new Map(), // canonical → 条数
  forms: new Map(), // form → 条数
  formNull: 0,
  emptySpeaker: 0,
  hit: 0,
  clean: new Map(), // 类别 → 条数
  cleanExamples: new Map(), // 类别 → 示例 [{id, rule, before, after}]
  cleanChanged: 0,
  cleanEmpty: [],
  starRemoved: 0,
  heSheRecords: 0,
  heSheOccurrences: 0,
  heSheExceptionKept: 0,
  stage: [],
  wholeStarDialogue: [],
  kindBefore: new Map(),
  kindAfter: new Map(),
  view: new Map(),
  extraTrue: 0,
  unmatchedSpeakers: new Map(), // speaker → {n, kinds}
};

function bump(map, key, n = 1) {
  map.set(key, (map.get(key) || 0) + n);
}

function addExample(cat, rec, rule, before, after) {
  if (!stats.cleanExamples.has(cat)) stats.cleanExamples.set(cat, []);
  const arr = stats.cleanExamples.get(cat);
  if (arr.length < 4) arr.push({ id: rec.id, rule, before, after });
}

const rawInput = fs.readFileSync(F.input, 'utf8');
const inputLines = rawInput.split(/\r?\n/);
const records = [];
for (let i = 0; i < inputLines.length; i++) {
  const line = inputLines[i];
  if (!line.trim()) {
    stats.blankLines++;
    continue;
  }
  try {
    records.push(JSON.parse(line));
  } catch (e) {
    stats.badLines.push({ line: i + 1, error: e.message, preview: line.slice(0, 120) });
  }
}
stats.total = records.length;

const outRecords = records.map((rec) => {
  const norm = resolveSpeaker(rec.speaker);
  const cleaned = cleanText(rec);

  bump(stats.kindBefore, rec.kind);
  bump(stats.kindAfter, cleaned.kind);
  bump(stats.view, rec.extra === true ? 'extra' : 'main');
  if (rec.extra === true) stats.extraTrue++;

  // ------- 归一统计 -------
  bump(stats.rules, norm.rule.startsWith('1 ') ? '1 speaker_literal_map'
    : norm.rule.startsWith('2 ') ? '2 speaker_alias'
    : norm.rule.startsWith('5 ') ? '5 form_map'
    : norm.rule.startsWith('4b') ? '4b canonical 键兜底'
    : norm.rule === 'non_speaker_label' ? 'non_speaker_label'
    : norm.rule === 'meme_term' ? 'meme_term'
    : norm.rule === 'empty' ? 'empty speaker'
    : '6 未命中');
  if (norm.canonical) {
    stats.hit++;
    bump(stats.canonical, norm.canonical);
    if (norm.form) bump(stats.forms, norm.form);
    else stats.formNull++;
  } else if ((rec.speaker || '') === '') {
    stats.emptySpeaker++;
  } else {
    const cur = stats.unmatchedSpeakers.get(rec.speaker) || { n: 0, kinds: new Map() };
    cur.n++;
    bump(cur.kinds, rec.kind);
    stats.unmatchedSpeakers.set(rec.speaker, cur);
  }

  // ------- 清洗统计 -------
  if (cleaned.changes.length) {
    stats.cleanChanged++;
    for (const cat of cleaned.changes) {
      bump(stats.clean, cat);
      addExample(cat, rec, norm.canonical || '(null)', rec.text, cleaned.text);
    }
  }
  if (cleaned.text === '' && cleaned.hadText) stats.cleanEmpty.push({ id: rec.id, version: rec.version, series_no: rec.series_no, kind: rec.kind, speaker: rec.speaker, before: rec.text });
  stats.starRemoved += cleaned.starInfo.starRemoved;
  if (cleaned.starInfo.stageDirection) {
    stats.stage.push({ id: rec.id, version: rec.version, series_no: rec.series_no, task: rec.task, speaker: rec.speaker, before: rec.text, after: cleaned.text });
  }
  if (cleaned.starInfo.wholeStarDialogue) stats.wholeStarDialogue.push(rec.id);
  if (cleaned.heSheCount) {
    stats.heSheRecords++;
    stats.heSheOccurrences += cleaned.heSheCount;
  }
  if (cleaned.keptException) stats.heSheExceptionKept += cleaned.keptException;

  return {
    ...rec,
    canonical_speaker: norm.canonical,
    form: norm.form,
    text_clean: cleaned.text,
    view: rec.extra === true ? 'extra' : 'main',
    // kind 可能被修正为 narration（舞台指示），其余字段原样保留
    kind: cleaned.kind,
  };
});

// ============================================================
// 四、写出
// ============================================================
fs.writeFileSync(F.outJsonl, outRecords.map((r) => JSON.stringify(r)).join('\n'), 'utf8');

const lineText = (r) => r.text_clean || r.text; // 9 条清洗后为空（原文只剩截断模板）→ 回退显示原文
fs.writeFileSync(
  F.outLines,
  outRecords
    .map((r) => {
      const who = r.canonical_speaker || r.speaker || '【旁白】';
      return `[${r.version}#${r.series_no}] ${r.task} | ${r.step_title} | ${who}: ${lineText(r)}`;
    })
    .join('\n'),
  'utf8'
);

// ============================================================
// 五、统计输出
// ============================================================
const pct = (a, b) => (b ? ((a / b) * 100).toFixed(2) + '%' : '0.00%');
const sortMap = (m) => [...m.entries()].sort((a, b) => b[1] - a[1]);
const nonEmptySpeakers = stats.total - stats.emptySpeaker;
const unmatchedSpeakersSorted = [...stats.unmatchedSpeakers.entries()].sort((a, b) => b[1].n - a[1].n);
const unmatchedRecords = stats.total - stats.emptySpeaker - stats.hit;

const lines = [];
const P = (s = '') => {
  lines.push(s);
  console.log(s);
};

P('==============================================');
P(' 翁法罗斯语料 v2：说话人归一 + 文本清洗');
P('==============================================');
P(`输入: data/corpus/amphoreus.jsonl`);
P(`输出: data/corpus/amphoreus.v2.jsonl / amphoreus.v2.lines.txt / docs/corpus-pipeline.md`);
P('');
P('== 基本 ==');
P(`总记录数: ${stats.total}   （坏行=${stats.badLines.length}，空行=${stats.blankLines}）`);
if (stats.badLines.length) stats.badLines.forEach((b) => P(`  ✗ 第 ${b.line} 行: ${b.error} | ${b.preview}`));
P(`记录类型: ${sortMap(stats.kindBefore).map(([k, v]) => `${k}:${v}`).join('  ')} → 清洗后 ${sortMap(stats.kindAfter).map(([k, v]) => `${k}:${v}`).join('  ')}`);
P(`view 字段: ${sortMap(stats.view).map(([k, v]) => `${k}:${v}`).join('  ')}   （extra=true 校验: ${stats.extraTrue}）`);
P('');
P('== 说话人归一 ==');
const nullTotal = stats.total - stats.hit;
P(`非空 speaker 记录: ${nonEmptySpeakers} 条`);
P(`命中 canonical: ${stats.hit} 条，命中率 ${pct(stats.hit, nonEmptySpeakers)}（占全部记录 ${pct(stats.hit, stats.total)}）`);
P(`canonical=null: ${nullTotal} 条（= 旁白等空 speaker ${stats.emptySpeaker} 条 + 非空但未匹配 ${unmatchedRecords} 条）`);
P(`form 非空: ${[...stats.forms.values()].reduce((s, n) => s + n, 0)} 条；form=null: ${stats.formNull} 条`);
P('归一规则分布:');
for (const [k, v] of sortMap(stats.rules)) P(`  ${k}: ${v}`);
P('');
P(`form 分布 Top20:`);
for (const [k, v] of sortMap(stats.forms).slice(0, 20)) P(`  ${String(v).padStart(5)}  ${k}`);
P('');
P(`Top 未匹配说话人（共 ${stats.unmatchedSpeakers.size} 个写法 / ${unmatchedRecords} 条）:`);
for (const [s, o] of unmatchedSpeakersSorted.slice(0, 15)) P(`  ${String(o.n).padStart(5)}  ${s}`);
P('');
P('配置缺漏建议（未修改 data/config/，完整 8 条见 docs/corpus-pipeline.md §5）:');
P('  1) true_name 已登记却未进 speaker_aliases: 海列屈拉→海瑟音(58) / 雅辛缇娅·雅辛忒丝→风堇(46) / 赛法利娅→赛飞儿(11) / 阿那克萨戈拉斯→那刻夏(8) / 迈德漠斯→万敌(6)');
P('  2) 泰坦作说话人未登记 canonical: 瑟希斯(157) / 欧洛尼斯(60) / 塞纳托斯(53) / 雅努斯(11)');
P('  3) 后缀模式未覆盖: X之声(来古士之声 136) / X的记忆·记忆中的X(约 100) / 的投影(26) / 称号前缀(先王欧利庞 24、元老凯妮斯 15)');
P('  4) 复合标签未拆: 永夜之帷，三月七(8) / 开拓者&昔涟(6) / 毁灭的容器，卡厄斯兰那(6)');
P('  5) 翁法罗斯常规 NPC 未登记: 巴特鲁斯(138) / 克拉特鲁斯(116) / 凯妮斯(121) / 哈托努斯(78) / 露奈比斯·索拉比斯(146) 等');
P('  6) 客串角色未登记: 卡芙卡(79) / 景元(28) / 流萤(26) / 银狼(17) / 阮•梅(18) 等');
P('  7) 墨涅塔的幻影 归到 canonical=墨涅塔，但 canonical 无墨涅塔条目');
P('');
P('== 清洗 ==');
const cleanLabels = {
  template_residue: '模板残留 {{...}}/}} 清理',
  html_br: '<br> 等 HTML 残留清理',
  wiki_link: '[[...]] 链接残留清理',
  he_she: '他/她 → 开拓者',
  emphasis_star: '行内 *强调* 去星号',
  stage_direction: '整句 *舞台指示* → kind=narration',
};
for (const [k, label] of Object.entries(cleanLabels)) P(`  ${label}: ${stats.clean.get(k) || 0} 条`);
P(`  累计被清洗的记录: ${stats.cleanChanged} 条（${pct(stats.cleanChanged, stats.total)}）`);
P(`  他/她 替换: ${stats.heSheRecords} 条记录 / ${stats.heSheOccurrences} 处；保留例外(他/她们俩): ${stats.heSheExceptionKept} 处`);
P(`  去掉 * 标记总数: ${stats.starRemoved} 个`);
P(`  整句 *...* 但含标点、保留为台词: ${stats.wholeStarDialogue.length} 条`);
P(`  清洗后为空: ${stats.cleanEmpty.length} 条` + (stats.cleanEmpty.length ? `  例: ${stats.cleanEmpty.slice(0, 5).map((x) => '#' + x.id + ' ' + JSON.stringify(x.before)).join(' | ')}` : ''));
P('');
P('舞台指示 → narration 清单:');
for (const s of stats.stage) P(`  #${s.id} [${s.version}#${s.series_no}] ${s.speaker}: ${JSON.stringify(s.before)} → ${JSON.stringify(s.after)}`);
P('');
P('== 输出校验 ==');
const outCount = outRecords.length;
const edgeOk = outCount === stats.total;
P(`  v2 行数=${outCount}，与输入一致: ${edgeOk ? '✓' : '✗'}`);
const kindSum = [...stats.kindAfter.values()].reduce((s, n) => s + n, 0);
P(`  kind 总数=${kindSum}，与记录数一致: ${kindSum === stats.total ? '✓' : '✗'}`);
const viewSum = [...stats.view.values()].reduce((s, n) => s + n, 0);
P(`  view 总数=${viewSum}，与记录数一致: ${viewSum === stats.total ? '✓' : '✗'}`);
const nullWithSpeaker = outRecords.filter((r) => !r.canonical_speaker && (r.speaker || '') !== '').length;
P(`  canonical=null 且 speaker 非空=${nullWithSpeaker}（= 未命中 ${unmatchedRecords}）: ${nullWithSpeaker === unmatchedRecords ? '✓' : '✗'}`);

// ============================================================
// 六、生成 docs/corpus-pipeline.md
// ============================================================
const docLines = [];
const D = (s = '') => docLines.push(s);
const fmtExamples = (cat) => {
  const ex = stats.cleanExamples.get(cat) || [];
  if (!ex.length) return '- （本次运行无此类改动）';
  return ex.map((e) => `- \`#${e.id}\` → canonical=${e.rule}\n  - 原文：\`${JSON.stringify(e.before)}\`\n  - 清洗：\`${JSON.stringify(e.after)}\``).join('\n');
};

D('# 语料管线 v2：说话人归一 + 清洗');
D();
D('> 本文档由 `tools/normalize-corpus.js` 运行时自动生成，统计数字与当次运行结果严格一致。');
D('> 生成命令：`node tools/normalize-corpus.js`（只读 v1 语料与配置，只写 v2 产物与本文件）。');
D();
D('## 1. 概览');
D();
D('| 项 | 值 |');
D('|---|---|');
D(`| 输入 | \`data/corpus/amphoreus.jsonl\`（v1） |`);
D(`| 输出 | \`data/corpus/amphoreus.v2.jsonl\`、\`data/corpus/amphoreus.v2.lines.txt\`、本文件 |`);
D(`| 记录数 | ${stats.total}（坏行 ${stats.badLines.length}，空行 ${stats.blankLines}） |`);
D(`| 记录类型 | 清洗前 ${sortMap(stats.kindBefore).map(([k, v]) => `${k}:${v}`).join(' / ')} → 清洗后 ${sortMap(stats.kindAfter).map(([k, v]) => `${k}:${v}`).join(' / ')} |`);
D(`| view | ${sortMap(stats.view).map(([k, v]) => `${k}:${v}`).join(' / ')}（extra=true 校验：${stats.extraTrue} 条 → extra） |`);
D();
D('**v2 新增字段**（v1 所有字段原样保留，`text` 原文不做任何改写，`speaker` 保留原标签）：');
D();
D('| 字段 | 类型 | 说明 |');
D('|---|---|---|');
D('| `canonical_speaker` | str \\| null | 归一后的规范角色名；未命中为 `null`（不猜） |');
D('| `form` | str \\| null | 形态/变体名（迷迷、长夜月、缇安…）；纯粹规范名命中时为 `null` |');
D('| `text_clean` | str | 清洗后的正文（去掉 `*强调*`、`{{...}}`、`[[...]]`、`<br>`，`他/她`→`开拓者`）；**`text` 原文保持不动** |');
D('| `view` | str | `main` \\| `extra`（`extra=true` → `extra`，1,459 条；不物理拆文件） |');
D();
D('### 人读版 `amphoreus.v2.lines.txt`');
D();
D('格式与 v1 完全一致，仅两处按 v2 语义取值：');
D();
D('- 说话人：优先输出 `canonical_speaker`，未命中时回退 `speaker` 原文，旁白用 `【旁白】`；');
D('- 正文：输出 `text_clean`（若清洗后为空则回退原文，共 ' + stats.cleanEmpty.length + ' 条，见 §3.7）。');
D();
D('便于 `grep "^.*| 昔涟:"` 直接按规范名检索。行数 = 记录数，不增删行。');
D();
D('## 2. 说话人归一规则');
D();
D('严格按 `data/config/speaker-alias.json` 的 `normalization_order` 执行：');
D();
D('| 优先级 | 规则 | 实现 |');
D('|---|---|---|');
D('| 1 | `speaker_literal_map` 精确命中 | 直接取 `canonical` + `form`（form 可为描述性标签，如「记忆/幻象形态」） |');
D('| 2 | `canonical.speaker_aliases` 精确命中 | 取该角色的 canonical；`form` 仅当命中串本身就是已登记形态（`forms`/`form_map`）时填写 |');
D('| 3 | 按 `title_prefix_patterns` 剥前缀后重试 1–2 | 如 `「阳雷骑士」塞涅俄丝` → `塞涅俄丝` |');
D('| 4 | 剥成对 `「」『』`、去尾部括号注音后重试 | 如 `「遐蝶」` → `遐蝶`、`「丹恒」` → `丹恒` |');
D('| 5 | `form_map` 命中 | `canonical` + `form` = 该写法（如 `长夜月` → 三月七 + form=长夜月） |');
D('| 6 | 仍未命中 | `canonical=null`，保留原 `speaker`，进人工确认清单（`pending_manual_review`） |');
D();
D('补充约定（实现细节，均为"不猜"原则的延伸）：');
D();
D('- **候选写法 × 优先级**：先对原始写法跑 1→2→5，再对"剥前缀/去引号/去括号"的写法跑同一顺序，即优先级高于写法宽容度。');
D('- **canonical 键兜底（位于 form_map 之后）**：`「断锋爵」拉比努斯` 这类 NPC 在配置里只有 `titles`、没有 `speaker_aliases`，剥前缀后精确等于 canonical 键才归一，不做任何模式推断。`form_map` 在它之前生效，因此 `长夜月` 仍归 `三月七 + form=长夜月`（遵守 known_conflicts），不会落到 `canonical["长夜月"]` 这条查询用条目。');
D('- **`non_speaker_labels`**（旁白/？？？/遥远的男声/留言石板/神性的回响…）一律 `canonical=null`。');
D('- **`meme_terms`**（梗名/奇美拉名/网名）不参与归一，命中即 null。');
D('- **known_conflicts 全部遵守**：卡厄斯=前世黄金裔（≠卡厄斯兰那/白厄）、铁墓≠白厄、长夜月→三月七、缇安/缇宁→缇宝、迷迷→昔涟、黑塔人偶/大黑塔→黑塔。本脚本不在此之外新增任何合并。');
D('- **未命中不猜**：`canonical=null` 的条目 `speaker` 原文完整保留；未匹配清单见 §2.3 与 §5。');
D();
D('### 2.1 归一统计');
D();
D(`- 非空 \`speaker\` 记录：${nonEmptySpeakers} 条`);
D(`- 命中 canonical：**${stats.hit} 条，命中率 ${pct(stats.hit, nonEmptySpeakers)}**（占全部记录 ${pct(stats.hit, stats.total)}）`);
D(`- \`canonical=null\`：${stats.total - stats.hit} 条（= 旁白等空 speaker ${stats.emptySpeaker} 条 + 非空但未匹配 ${unmatchedRecords} 条）`);
D(`- \`form\` 非空：${[...stats.forms.values()].reduce((s, n) => s + n, 0)} 条；\`form=null\`：${stats.formNull} 条`);
D();
D('| 归一规则 | 命中记录数 |');
D('|---|---|');
for (const [k, v] of sortMap(stats.rules)) D(`| ${k} | ${v} |`);
D();
D('### 2.2 form 分布 Top20');
D();
D('| # | form | 记录数 |');
D('|---|---|---|');
sortMap(stats.forms).slice(0, 20).forEach(([k, v], i) => D(`| ${i + 1} | ${k} | ${v} |`));
D();
D('规范角色名分布 Top20（供参考）：');
D();
D('| # | canonical_speaker | 记录数 |');
D('|---|---|---|');
sortMap(stats.canonical).slice(0, 20).forEach(([k, v], i) => D(`| ${i + 1} | ${k} | ${v} |`));
D();
D('### 2.3 未匹配说话人');
D();
D(`共 ${stats.unmatchedSpeakers.size} 个写法 / ${unmatchedRecords} 条记录。Top 15：`);
D();
D('| # | speaker 原文 | 记录数 |');
D('|---|---|---|');
unmatchedSpeakersSorted.slice(0, 15).forEach(([s, o], i) => D(`| ${i + 1} | ${s} | ${o.n} |`));
D();
D('## 3. 清洗规则与计数');
D();
D('`text` 原文**永不改写**；所有清洗结果只写入 `text_clean`（唯一例外是 §3.6 的 `kind` 修正，见下）。');
D();
D(`累计被清洗的记录：**${stats.cleanChanged} 条**（${pct(stats.cleanChanged, stats.total)}）。`);
D();
D('| 类别 | 说明 | 条数 |');
D('|---|---|---|');
for (const [k, label] of Object.entries(cleanLabels)) D(`| \`${k}\` | ${label} | ${stats.clean.get(k) || 0} |`);
D();
D('### 3.1 模板残留 `{{...}}`');
D();
D('先删成对 `{{...}}`，再删被 parser 截断的 `{{...`（v1 在跨行模板处截断，如 `我{{黑幕` → `我`）。');
D();
D(fmtExamples('template_residue'));
D();
D('### 3.2 HTML 标签 `<br>`');
D();
D('删除 `<br>` / `<br/>` / `<br />`。本次语料中为 0 条（防御性规则，保留以应对重抓）。');
D();
D('### 3.3 wiki 链接残留 `[[...]]`');
D();
D('`[[目标|显示]]` → `显示`，`[[目标]]` → `目标`，残留标记删除。本次语料中为 0 条。');
D();
D('### 3.4 `他/她` → `开拓者`');
D();
D(`BWiki 为兼容双主角写作的性别占位符。本次替换 **${stats.heSheRecords} 条记录 / ${stats.heSheOccurrences} 处**。`);
D();
D(`**唯一例外**：3.6#07「长夜月」的单句台词里的「他/她们俩」保留不替换（指代对象仍待人工确认），本次保留 ${stats.heSheExceptionKept} 处。`);
D();
D(fmtExamples('he_she'));
D();
D('### 3.5 行内 `*强调*` 去星号');
D();
D('如 `*我们*`（缇宝指代其分身群体）只去星号、保留词义。本次去星号共 ' + stats.starRemoved + ' 个。');
D();
D(fmtExamples('emphasis_star'));
D();
D('### 3.6 整句 `*...*` 舞台指示 → `kind=narration`');
D();
D('判定条件：整句被**一对** `*` 包住，且**不含任何对话标点**（`，。！？…、；：` 及引号/括号）。');
D('满足则视为拟声/动作描述（如 `*泰坦悲伤的低鸣*`、`*低吼*`），去星号后将 `kind` 由 `dialogue` 改为 `narration`，`speaker` 原文保留（不丢信息，v1 文件仍是原始类型）。');
D();
D(`共 ${stats.stage.length} 条：`);
D();
D('| id | 版本#编号 | speaker | 原文 → 清洗后 |');
D('|---|---|---|---|');
for (const s of stats.stage) D(`| ${s.id} | ${s.version}#${s.series_no} | ${s.speaker} | \`${s.before}\` → \`${s.after}\` |`);
D();
D(`另有 ${stats.wholeStarDialogue.length} 条「整句被 * 包住但含对话标点」，是角色**演戏/模仿**时的整段台词（如 3.3#07 赛飞儿、\`「赛白厄」\`），按台词保留、只去星号，未改 kind。`);
D();
D('### 3.7 清洗后为空的记录');
D();
if (!stats.cleanEmpty.length) D('本次无。');
else {
  D(`共 ${stats.cleanEmpty.length} 条：原文只剩被截断的模板（如 \`{{颜色\`），语义在 v1 解析阶段已丢失。`);
  D();
  D('| id | 版本#编号 | kind | speaker | text 原文 |');
  D('|---|---|---|---|---|');
  for (const s of stats.cleanEmpty) D(`| ${s.id} | ${s.version}#${s.series_no} | ${s.kind} | ${s.speaker} | \`${JSON.stringify(s.before)}\` |`);
}
D();
D('## 4. `view` 字段');
D();
D(`不物理拆文件，只加 ` + '`view`' + ` 标记：\`extra=true\`（\`{{折叠}}\` 块内的可选对话）→ \`extra\`，其余 → \`main\`。`);
D(`本次：${sortMap(stats.view).map(([k, v]) => `\`${k}\` ${v} 条`).join('，')}。`);
D();
D('## 5. 配置缺漏建议（未修改配置，仅记录；`canonical=null` 的条目保持 null）');
D();
D('以下按"证据强度"排序，供人工确认后再决定是否扩 `speaker-alias.json`：');
D();
D('1. **`true_name` 已登记但未进 `speaker_aliases`**（命中率提升空间最大、证据最硬）：语料里出现了角色真名写法，如 `海列屈拉`（海瑟音 true_name，58 条）、`雅辛缇娅`/`雅辛忒丝`（风堇 Hyacinthia，46 条）、`赛法利娅`（赛飞儿 Cifera，11 条）、`阿那克萨戈拉斯`（那刻夏，8 条）、`迈德漠斯`（万敌 Mydeimos，6 条）。建议把这些真名补进对应角色的 `speaker_aliases`。');
D('2. **泰坦本身作为说话人未登记**：`瑟希斯`（157）、`欧洛尼斯`（60）、`塞纳托斯`（53）、`雅努斯`（11）等只在 `titan_canonical` 里作为"称号→黄金裔"存在，没有 canonical 条目。建议新增泰坦 canonical（或明确"泰坦之声归到泰坦而非黄金裔"）。');
D('3. **后缀/前缀模式未覆盖**：`来古士之声`（136，可考虑 `^(.+)之声$` → canonical + form=…之声）、`记忆中的X`（`记忆中的赛飞儿` 24、`记忆中的缇宝` 22、`记忆中的阿格莱雅` 15、`记忆中的万敌` 14、`记忆中的昔涟` 11…）、`X的记忆`（`海瑟音的记忆` 23）、`黑塔的投影`（16）、`螺丝咕姆的投影`（10）；NPC 称号前缀 `先王欧利庞`（24）、`元老凯妮斯`（15）。前 5 个模式与既有 `literal_map` 里「记忆中的那刻夏」「来古士的记忆」是同一族，建议补成通用规则或逐条补表。');
D('4. **复合说话人标签**（对应 data/README 已知问题 #10/#11）：`永夜之帷，三月七`（8）、`开拓者&昔涟`（6）、`毁灭的容器，卡厄斯兰那`（6）。建议加一条"复合标签拆分"规则（拆成主体角色 + 保留 form）。');
D('5. **明显的翁法罗斯常规 NPC**（建议整批进 `canonical` 或统一 `generic_npc`）：`「贼灵」巴特鲁斯`/`巴特鲁斯`（138）、`克拉特鲁斯`（116）、`凯妮斯`/`元老凯妮斯`（121）、`哈托努斯`（78）、`温柔的母亲`（78）、`露奈比斯`/`索拉比斯`（146，塞涅俄丝的双翼，已有 aliases 但没进 speaker_aliases）、`第四面镜`（71）、`达米亚诺斯`（47）、`阿蒙内特`（75）、`吉奥刻勒斯`（20）、`权杖δ-me13`（69，3.6 权杖 AI）等。');
D('6. **非翁法罗斯的客串角色**：`卡芙卡`（79）、`景元`（28）、`流萤`（26）、`银狼`（17）、`砂金`（15）、`刃`（14）、`波提欧`（14）、`符玄`（13）、`翡翠`（13）、`飞霄`（12）、`布洛妮娅`（11）、`镜流`（9）、`花火`（9）、`阮•梅`（18）、`爻光`（8）…配置的 canonical 只覆盖翁法罗斯主线角色，建议单独建"客串角色"小节。');
D('7. **`canonical_speaker` 可能指向未登记角色**：`speaker_literal_map` 把 `墨涅塔的幻影` 归到 `墨涅塔`，但 `canonical` 里没有 `墨涅塔` 条目（只是泰坦）。建议补登记，或把该映射改为"泰坦"分类。');
D('8. **风格一致的检查项**：`海瑟音` 的 literal 形态写了「记忆/幻象形态」，而同类「记忆中的X」写「记忆形态」，`form` 取值口径建议统一。');
D();
D('## 6. 复现');
D();
D('```bash');
D('# 只读 v1 语料 + 配置；只写 data/corpus/amphoreus.v2.* 与 docs/corpus-pipeline.md');
D('node tools/normalize-corpus.js');
D('```');
D();
D('校验要点：v2 行数与 v1 一致（' + stats.total + '）；`extra=true` → `view=extra`（' + stats.extraTrue + '）；`kind` 总数守恒；`text` 字段与 v1 逐字节一致；`speaker` 原文保留；`canonical=null` 不猜。');
D();
D('## 7. 已知遗留（v2 未处理，留给后续）');
D();
D('- data/README 已知问题 #10：`kind=narration` 里内嵌说话人的写法（`永夜之帷，三月七：「…」`、`博识尊[黑塔]：「…」`）未二次拆分；');
D('- 已知问题 #11/#12：复合标签（`「赛白厄」` 已按 literal 归一，但 `开拓者&昔涟` 等仍未拆）；');
D('- 分支选项仍按文档顺序并列（v1 遗留，非本管线范围）；');
D('- `text_clean` 未做简繁/标点规范化（保持原作）。');
D('- `step_title` 未清洗：全篇有 1 个步骤标题含 `他/她`（`找到开拓者并带他/她回家`，影响 43 条记录的 `step_title` 字段）。按任务要求只清洗 `text`，`step_title` 原文保留；如需统一，可对 `step_title` 复用同一 `他/她` 规则。');

fs.writeFileSync(F.doc, docLines.join('\n') + '\n', 'utf8');

P('');
P(`已写出: data/corpus/amphoreus.v2.jsonl / data/corpus/amphoreus.v2.lines.txt / docs/corpus-pipeline.md`);
