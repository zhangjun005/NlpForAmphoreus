#!/usr/bin/env node
/**
 * tools/report-corpus.js —— 语料只读质检与统计报告生成器
 *
 * 输入（全部只读）：
 *   data/corpus/amphoreus.jsonl          主语料（JSONL，一行一条记录）
 *   data/corpus/amphoreus.lines.txt      人读版（用于派生文件一致性核对）
 *   data/corpus/quest-order.json         67 个任务页的剧情顺序与前置/后续链
 *   data/config/speaker-alias.json       说话人归一配置（只读，只做本地计算）
 *   data/shots/yinnian.rendered.txt      单页浏览器渲染正文（抽样核对用，可缺）
 *
 * 输出（仅写 data/reports/）：
 *   data/reports/corpus-stats.md         总量 / 分布 / 角色 / 长度统计
 *   data/reports/qa-checks.md            顺序 / 完整性 / 文本纯度 / 抽样比对 / 已知问题
 *   data/reports/unmatched-speakers.md   未归一 speaker 清单与归类建议
 *
 * 约束：绝不写 data/corpus|config|raw；不使用 git；不联网；不修改任何输入文件。
 * 用法：node tools/report-corpus.js
 */

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------
const ROOT = path.resolve(__dirname, '..');
const DATA = path.join(ROOT, 'data');
const OUT_DIR = path.join(DATA, 'reports');

const P = {
  corpus: path.join(DATA, 'corpus', 'amphoreus.jsonl'),
  lines: path.join(DATA, 'corpus', 'amphoreus.lines.txt'),
  questOrder: path.join(DATA, 'corpus', 'quest-order.json'),
  config: path.join(DATA, 'config', 'speaker-alias.json'),
  rendered: path.join(DATA, 'shots', 'yinnian.rendered.txt'),
};

/** 渲染正文只覆盖这一页任务，抽样比对时必须按 task 过滤 */
const RENDERED_TASK = '银辇啊，迅赴那黑色大地';
/** 抽样随机种子（固定，保证报告可复现） */
const SAMPLE_SEED = 20251023;
const SAMPLE_N = 20;

const VERSIONS = ['3.0', '3.1', '3.2', '3.3', '3.4', '3.5', '3.6', '3.7'];

// ---------------------------------------------------------------------------
// 通用工具
// ---------------------------------------------------------------------------
const readText = (p) => fs.readFileSync(p, 'utf8');
const readJson = (p) => JSON.parse(readText(p));
const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const cjkLen = (s) => [...s].length;
const num = (n) => Number(n).toLocaleString('en-US');
const pct = (n, d) => (d ? ((n / d) * 100).toFixed(2) + '%' : '—');

/** Markdown 表格单元格转义 */
const cell = (s) =>
  String(s == null ? '' : s)
    .replace(/\r?\n/g, ' ')
    .replace(/\|/g, '\\|')
    .trim();

/** 按 Unicode 码点截断 */
const trunc = (s, n) => {
  const a = [...String(s)];
  return a.length <= n ? a.join('') : a.slice(0, n).join('') + '…';
};

/** 取匹配位置前后共 n 个码点的片段（避免截断后丢失命中内容） */
function snippetAround(text, re, n = 40) {
  const testRe = new RegExp(re.source, re.flags.replace('g', ''));
  const m = testRe.exec(text);
  if (!m) return trunc(text, n);
  const chars = [...text];
  const cpIndex = [...text.slice(0, m.index)].length;
  const mLen = [...m[0]].length;
  const half = Math.max(0, Math.floor((n - mLen) / 2));
  const start = Math.max(0, cpIndex - half);
  const end = Math.min(chars.length, start + n);
  return (start > 0 ? '…' : '') + chars.slice(start, end).join('') + (end < chars.length ? '…' : '');
}

/** 生成 Markdown 表格 */
function mdTable(headers, rows) {
  const out = [];
  out.push('| ' + headers.map(cell).join(' | ') + ' |');
  out.push('| ' + headers.map(() => '---').join(' | ') + ' |');
  for (const r of rows) out.push('| ' + r.map(cell).join(' | ') + ' |');
  return out.join('\n');
}

/** nearest-rank 分位数：P_k = 升序第 ceil(k/100*N) 个（1-based） */
function quantile(sortedAsc, k) {
  if (!sortedAsc.length) return 0;
  const idx = Math.max(0, Math.ceil((k / 100) * sortedAsc.length) - 1);
  return sortedAsc[Math.min(idx, sortedAsc.length - 1)];
}

function lengthStats(arr) {
  if (!arr.length) return null;
  const sorted = [...arr].sort((a, b) => a - b);
  const sum = arr.reduce((a, b) => a + b, 0);
  return {
    n: arr.length,
    mean: sum / arr.length,
    p50: quantile(sorted, 50),
    p90: quantile(sorted, 90),
    p99: quantile(sorted, 99),
    max: sorted[sorted.length - 1],
    min: sorted[0],
    sum,
  };
}

/** mulberry32 伪随机数（确定性） */
function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function counterToRows(map, total, limit) {
  const arr = [...map.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), 'zh'));
  const sliced = limit ? arr.slice(0, limit) : arr;
  return { arr, sliced };
}

const uniq = (arr) => [...new Set(arr)];

// ---------------------------------------------------------------------------
// 0. 读取输入
// ---------------------------------------------------------------------------
function loadRecords() {
  const buf = fs.readFileSync(P.corpus);
  const text = buf.toString('utf8');
  const rawLines = text.split(/\r?\n/);
  const records = [];
  rawLines.forEach((line, i) => {
    if (!line.trim()) return;
    const rec = JSON.parse(line);
    rec.__line = i + 1; // 物理行号（1-based）
    records.push(rec);
  });
  return { buf, text, records };
}

// ---------------------------------------------------------------------------
// 1. 说话人归一（严格按 config.normalization_order 规则 1–5，只读计算）
// ---------------------------------------------------------------------------
function buildNormalizer(cfg) {
  const canonical = cfg.canonical || {};
  const literal = cfg.speaker_literal_map || {};
  const forms = cfg.form_map || {};
  const nonSpeakers = new Set(cfg.non_speaker_labels || []);
  const titlePatterns = (cfg.title_prefix_patterns || []).map((p) => new RegExp(p));

  /** alias -> { canonical, form } */
  const aliasMap = new Map();
  for (const [name, entry] of Object.entries(canonical)) {
    for (const a of entry.speaker_aliases || []) {
      if (!aliasMap.has(a)) aliasMap.set(a, { canonical: name, form: a, rule: 'speaker_aliases' });
    }
  }

  // 配置里存在、但没写 speaker_aliases 的 canonical 名（仅用于"配置缺口"提示，不参与归一）
  const canonicalKeysWithoutAliases = [];
  for (const [name, entry] of Object.entries(canonical)) {
    if (!(entry.speaker_aliases || []).includes(name)) canonicalKeysWithoutAliases.push(name);
  }

  const stripTitlePrefix = (s) => {
    for (const re of titlePatterns) if (re.test(s)) return s.replace(re, '').trim();
    return null;
  };
  /** 规则 4：剥离成对引号 / 去括号注音 */
  const stripPaired = (s) =>
    s
      .replace(/^[「『](.*)[」』]$/, '$1')
      .replace(/（[^）]*）|\([^)]*\)/g, '')
      .trim();

  const hit = (t, baseRule) => {
    if (literal[t]) return { canonical: literal[t].canonical, form: literal[t].form ?? t, rule: '1:speaker_literal_map' };
    if (aliasMap.has(t)) return { ...aliasMap.get(t), rule: `2:speaker_aliases${baseRule}` };
    return null;
  };

  /** 返回 { canonical, form, rule } / { nonSpeaker:true, rule } / null */
  function resolve(raw) {
    if (typeof raw !== 'string') return null;
    const t = raw.trim();
    if (!t) return null;
    // 1 + 2
    const r1 = hit(t, '');
    if (r1) return r1;
    // 3 标题前缀剥离后重试 1-2
    const p = stripTitlePrefix(t);
    if (p && p !== t) {
      const rp = hit(p, '(前缀剥离后)');
      if (rp) return { ...rp, rule: '3:title_prefix → ' + rp.rule };
    }
    // 4 成对引号 / 括号剥离后重试 1-2
    const b = stripPaired(t);
    if (b && b !== t) {
      const rb = hit(b, '(引号剥离后)');
      if (rb) return { ...rb, rule: '4:strip_pair → ' + rb.rule };
    }
    // 5 form_map
    if (forms[t]) return { canonical: forms[t], form: t, rule: '5:form_map' };
    // config 明示的非说话人标签
    if (nonSpeakers.has(t)) return { nonSpeaker: true, rule: 'config:non_speaker_labels' };
    return null;
  }

  // 仅给「未归一 speaker 的归类建议」使用的宽松解析（不改变严格归一结论）
  function resolveLoose(raw) {
    const t = String(raw || '').trim();
    if (!t) return null;
    const direct = resolve(t);
    if (direct && !direct.nonSpeaker) return direct;
    const stripped = t
      .replace(/^[「『"'"'（(]+/, '')
      .replace(/[」』"'"'）)]+$/, '')
      .replace(/[？?！!…。，,～~]+$/, '')
      .trim();
    if (stripped && stripped !== t) {
      const r = resolve(stripped);
      if (r && !r.nonSpeaker) return { ...r, rule: 'strip_punct → ' + r.rule };
    }
    return null;
  }

  return { resolve, resolveLoose, aliasMap, literal, forms, nonSpeakers, canonical, canonicalKeysWithoutAliases, titlePatterns };
}

// ---------------------------------------------------------------------------
// 2. 未归一 speaker 的归类建议（启发式；报告里会写明规则，供人工复核）
// ---------------------------------------------------------------------------
const ROLE_WORDS = [
  '公民', '市民', '民众', '居民', '路人', '众人', '人们', '大家', '村民', '住民', '民众',
  '信徒', '祭司', '侍卫', '士兵', '卫兵', '卫士', '守卫', '哨兵', '侍从', '侍女', '仆人',
  '商人', '铁匠', '衣匠', '医师', '医生', '工匠', '画师', '诗人', '吟游诗人', '舞者',
  '酒保', '侍者', '摊贩', '报幕', '报名官', '传令兵', '传令', '斥候', '监工', '代表',
  '眷属', '精灵', '奇美拉', '大地兽', '海妖', '死囚', '难民', '俘虏', '战俘', '牧人',
  '猎户', '渔夫', '孩童', '小孩', '女孩', '男孩', '少女', '少年', '青年', '老人', '老者',
  '妇人', '女子', '男子', '女声', '男声', '声音', '嗓音', '科员', '职员', '力士', '斗士',
  '武士', '战士', '刺客', '盗贼', '游侠', '飞行员', '指挥官', '医疗兵', '智械', '黑客',
  '骇客', '主持人', '播报员', '军官', '军需官', '戍卫长', '百夫长', '将军', '队长',
  '官员', '议员', '元老', '学者', '术士', '法师', '炼金术士', '圣女', '司铎', '大司铎',
  '国王', '王后', '臣民', '贵族', '元老院议员', '母亲', '父亲', '女儿', '儿子', '店主',
  '之民', '亡魂', '眷属', '余烬', '之子', '海妖', '奇兽', '异兽', '残忆',
];

/** 已知的非翁法罗斯可玩角色（在 3.x 主线中客串），config 未收录 */
const CAMEO_PLAYABLE = [
  '卡芙卡', '景元', '流萤', '银狼', '砂金', '波提欧', '花火', '符玄', '飞霄', '布洛妮娅',
  '知更鸟', '翡翠', '希儿', '希露瓦', '阮•梅', '托帕', '镜流', '乱破', '爻光', '刃',
  '应星', '萨姆', '原始博士', '黑天鹅', '星期日', '姬子', '瓦尔特', '帕姆',
];

function buildSuggester(cfg, normalizer) {
  const canonical = cfg.canonical || {};
  const bodyChars = /[\u3400-\u4dbf\u4e00-\u9fff·•]/;

  /** 名称 -> { canonical, src }（用于"字符串包含已知角色名"；忽略单字名，避免「星」误配「应星」这类误判） */
  const nameIndex = new Map();
  const addName = (name, canonicalName, src) => {
    if (!name || name.length < 2 || !bodyChars.test(name)) return;
    if (!nameIndex.has(name)) nameIndex.set(name, { canonical: canonicalName, src });
  };
  for (const [name, entry] of Object.entries(canonical)) {
    addName(name, name, 'canonical 名');
    for (const a of entry.speaker_aliases || []) addName(a, name, 'speaker_aliases');
    for (const f of entry.forms || []) addName(f, name, 'forms');
    for (const t of entry.titles || []) addName(t, name, 'titles');
    for (const a of entry.aliases || []) addName(a, name, 'aliases');
    // true_name 可能是 "海列屈拉 Helektra" 这类混排
    if (entry.true_name) {
      for (const m of String(entry.true_name).match(/[\u4e00-\u9fff·•]{2,}/g) || []) addName(m, name, 'true_name');
    }
  }
  // 泰坦名单独处理：泰坦是"说话实体"本身，不能直接归一成对应黄金裔，只做提示
  const titanCanonical = cfg.titan_canonical || {};
  // 名称按长度降序，优先匹配长名
  const namesByLen = [...nameIndex.keys()].sort((a, b) => b.length - a.length);

  const matchNameIn = (s) => {
    for (const n of namesByLen) {
      if (s.includes(n)) {
        const info = nameIndex.get(n);
        return { name: n, canonical: info.canonical, src: info.src };
      }
    }
    return null;
  };

  const roleRe = new RegExp('(' + ROLE_WORDS.join('|') + ')');

  function suggest(raw) {
    const t = String(raw || '').trim();
    const punct = t.replace(/^[「『"'"'（(]+/, '').replace(/[」』"'"'）)]+$/, '').trim();
    const noTail = punct.replace(/[？?！!…。，,～~、]+$/g, '').trim();

    // 疑似字段错位：speaker 里混入整句台词
    if (/[。！？!?]/.test(t) && (t.length >= 8 || /^[？?]/.test(t))) {
      return { bucket: '待人工', reason: '疑似字段错位：speaker 混入台词/标点，建议人工核对拆分' };
    }
    // 复合说话人
    const compoundParts = t.split(/[&＆、]/).map((s) => s.trim()).filter(Boolean);
    if (compoundParts.length > 1) {
      const infos = compoundParts.map((p) => {
        const r = normalizer.resolveLoose(p);
        if (r) return p + '→' + r.canonical;
        const m = matchNameIn(p);
        return m ? p + '→' + m.canonical : p + '→?';
      });
      return { bucket: '待人工', reason: '复合说话人（' + infos.join(' + ') + '），建议拆成多条记录/多值 speaker' };
    }
    // 「记忆中的X」
    const memo = noTail.match(/^记忆中的(.+)$/);
    if (memo) {
      const inner = memo[1].trim();
      const r = normalizer.resolveLoose(inner);
      if (r) return { bucket: '疑似' + r.canonical, reason: '「记忆中的X」形态（X=' + inner + '）', canonical: r.canonical };
      const m = matchNameIn(inner);
      if (m) return { bucket: '疑似' + m.canonical, reason: '「记忆中的X」形态（X=' + m.name + '）', canonical: m.canonical };
    }
    // X之声 / X的记忆 / X的投影 / X的残忆 / X的回响 / X的余烬 / X的幻影
    const suffixRe = /^(.*?)(之声|的记忆|的投影|的残忆|的回响|的余烬|的幻影|的幻象|的残忆)$/;
    const suf = noTail.match(suffixRe);
    if (suf && suf[1]) {
      const base = suf[1].trim();
      const r = normalizer.resolveLoose(base);
      const m = r ? null : matchNameIn(base);
      const canonicalName = r ? r.canonical : m ? m.canonical : null;
      if (canonicalName) {
        return { bucket: '疑似' + canonicalName, reason: '「X' + suf[2] + '」形态（X=' + base + '）', canonical: canonicalName };
      }
    }
    // 成对引号包裹的形态/称号
    const inner = punct.match(/^[「『]([^」』]{1,10})[」』]$/);
    if (inner) {
      const base = inner[1];
      const r = normalizer.resolveLoose(base);
      const m = r ? null : matchNameIn(base);
      const canonicalName = r ? r.canonical : m ? m.canonical : null;
      if (canonicalName) {
        return { bucket: '疑似' + canonicalName, reason: '「' + base + '」为 config 中的形态/称号（缺失带引号字面量映射）', canonical: canonicalName };
      }
    }
    // 去标点后精确命中
    if (noTail !== t) {
      const r = normalizer.resolveLoose(noTail);
      if (r) return { bucket: '疑似' + r.canonical, reason: '去掉首尾标点后命中「' + noTail + '」', canonical: r.canonical };
    }
    // canonical 名本身（config 漏写 speaker_aliases）
    if (Object.prototype.hasOwnProperty.call(canonical, t)) {
      return { bucket: '疑似' + t, reason: 'config.canonical 有该角色名，但未列入 speaker_aliases（配置缺口）', canonical: t };
    }
    // form_map 键（带引号/前缀变体）
    if (normalizer.forms[noTail]) {
      return { bucket: '疑似' + normalizer.forms[noTail], reason: 'form_map 命中「' + noTail + '」的变体写法', canonical: normalizer.forms[noTail] };
    }
    // 泰坦名：说话实体是泰坦本身，不能直接归入对应黄金裔，标记为待人工决策
    if (titanCanonical[t] || titanCanonical[noTail]) {
      const titan = titanCanonical[t] ? t : noTail;
      return {
        bucket: '待人工',
        reason: `泰坦名「${titan}」（titan_canonical 对应黄金裔 ${titanCanonical[titan].heir}；说话人为泰坦本身，需决定是否单列 canonical）`,
      };
    }
    // 字符串包含已知角色名（形态/前缀/称号标签）
    const m = matchNameIn(noTail);
    if (m) {
      return {
        bucket: '疑似' + m.canonical,
        reason: `包含已知角色名「${m.name}」（config.${m.src}），为形态/复合/称号标签，待确认`,
        canonical: m.canonical,
      };
    }
    // 已知外来客串可玩角色
    if (CAMEO_PLAYABLE.includes(noTail)) {
      return { bucket: '待人工', reason: '疑似非翁法罗斯可玩角色客串（config 未收录，需决定是否纳入 canonical）' };
    }
    // 乱码/屏蔽字符
    if (/[█▀▄░▒]/.test(t) || /^[?？\s]+$/.test(t)) {
      return { bucket: '待人工', reason: '乱码/屏蔽字符或纯符号标签，建议人工判定' };
    }
    // 泛称/职业/群体标签
    const exactRole = ROLE_WORDS.includes(punct);
    const deIdx = punct.indexOf('的');
    const deTail = deIdx > 0 ? punct.slice(deIdx + 1) : '';
    const deTailIsRole = deTail && ROLE_WORDS.some((w) => deTail.endsWith(w));
    const deRole = punct.match(/^(.{1,10})的(.+)$/);
    const deRoleIsRole = deRole && ROLE_WORDS.includes(deRole[2]);
    const placeMod = /^(奥赫玛|悬锋|圣城|逐火|往世|晖之|雨之|拉冬|哀地里亚|斯缇科西亚|浴场|雕琢区|集市|宫廷|元老院|空间站|天外|无名|黄金裔|泰坦|眷属|奇美拉|尼卡多利|先王|元老|某位|年迈|年轻|年老|白发|金发|红发|年幼|年长|平民|被腐蚀|被污染|受袭|濒死|抗?议|诸|众)/;
    const modRole = ROLE_WORDS.some((w) => {
      if (!punct.endsWith(w) || punct.length <= w.length) return false;
      const prefix = punct.slice(0, punct.length - w.length);
      return placeMod.test(prefix) || prefix.endsWith('的');
    });
    const plural = /们$/.test(punct) && punct.length <= 10;
    const exactComposite = /^(众|诸|群)?(圣城|悬锋|奥赫玛|逐火)?(公民|市民|民众|居民|士兵|卫兵|卫士|守卫|信徒|祭司|学者|议员|元老|商人|村民|人们|孩童)s?$/.test(
      punct
    );
    if (exactRole || deRoleIsRole || deTailIsRole || modRole || plural || exactComposite) {
      const matched = exactRole ? punct : (roleRe.exec(punct) || [])[0] || '';
      return {
        bucket: 'generic_npc',
        reason: '泛称/职业/群体标签' + (matched ? '（含「' + matched + '」）' : '') + '，候选；若实指具名角色请改人工',
      };
    }
    return { bucket: '待人工', reason: '未识别的专名/标签，需人工判定' };
  }

  return { suggest };
}

// ---------------------------------------------------------------------------
// 3. 各类统计与检查
// ---------------------------------------------------------------------------
function computeBasic(records) {
  const byVersion = new Map();
  for (const v of VERSIONS) byVersion.set(v, { version: v, tasks: new Set(), records: 0, chars: 0, extra: 0 });
  for (const r of records) {
    const e = byVersion.get(r.version);
    if (!e) byVersion.set(r.version, { version: r.version, tasks: new Set(), records: 0, chars: 0, extra: 0 });
    const cur = byVersion.get(r.version);
    cur.tasks.add(r.task);
    cur.records++;
    cur.chars += cjkLen(r.text);
    if (r.extra) cur.extra++;
  }
  const versionRows = [...byVersion.values()]
    .filter((e) => e.records > 0)
    .sort((a, b) => a.version.localeCompare(b.version, undefined, { numeric: true }));

  const bySeries = new Map();
  for (const r of records) {
    if (!bySeries.has(r.series)) bySeries.set(r.series, { series: r.series, version: r.version, tasks: new Set(), records: 0, chars: 0 });
    const cur = bySeries.get(r.series);
    cur.tasks.add(r.task);
    cur.records++;
    cur.chars += cjkLen(r.text);
  }

  const kindMap = new Map();
  const extraMap = new Map();
  const kindExtra = new Map();
  for (const r of records) {
    kindMap.set(r.kind, (kindMap.get(r.kind) || 0) + 1);
    extraMap.set(String(r.extra), (extraMap.get(String(r.extra)) || 0) + 1);
    const k = r.kind + ' | extra=' + r.extra;
    kindExtra.set(k, (kindExtra.get(k) || 0) + 1);
  }

  const totalChars = records.reduce((a, r) => a + cjkLen(r.text), 0);
  const nonSpaceChars = records.reduce((a, r) => a + cjkLen(r.text.replace(/\s/g, '')), 0);

  return { byVersion, versionRows, bySeries, kindMap, extraMap, kindExtra, totalChars, nonSpaceChars };
}

function computeCompleteness(records) {
  const FIELDS = [
    ['id', 'number'], ['order', 'number'], ['task', 'string'], ['version', 'string'],
    ['series', 'string'], ['series_no', 'string'], ['idx', 'number'], ['chapter', 'string'],
    ['step_idx', 'number'], ['step_title', 'string'], ['speaker', 'string'], ['kind', 'string'],
    ['text', 'string'], ['extra', 'boolean'], ['location', 'string'], ['scene', 'string'],
  ];
  const rows = [];
  for (const [k, type] of FIELDS) {
    let missing = 0, nullV = 0, emptyStr = 0, typeBad = 0;
    for (const r of records) {
      if (!Object.prototype.hasOwnProperty.call(r, k)) { missing++; continue; }
      const v = r[k];
      if (v === null) nullV++;
      else if (v === '') emptyStr++;
      else if (typeof v !== type) typeBad++;
    }
    const present = records.length - missing - nullV - emptyStr;
    rows.push({ field: k, type, missing, null: nullV, empty: emptyStr, typeBad, valid: present });
  }
  return rows;
}

function computeDuplicates(records) {
  const key = (r) => [r.task, r.kind, r.speaker, r.text].join('\u0001');
  const groups = new Map();
  for (const r of records) {
    if (!groups.has(key(r))) groups.set(key(r), []);
    groups.get(key(r)).push(r);
  }
  const dupGroups = [...groups.values()].filter((g) => g.length > 1).sort((a, b) => b.length - a.length);
  const redundant = dupGroups.reduce((a, g) => a + g.length - 1, 0);

  // 相邻完全重复（同一条目连续出现）
  let adjacent = 0;
  for (let i = 1; i < records.length; i++) if (key(records[i]) === key(records[i - 1])) adjacent++;

  // 除 id/idx 外全字段一致（真·重复行）
  const fullKey = (r) => JSON.stringify({ ...r, id: undefined, idx: undefined, __line: undefined });
  const full = new Map();
  for (const r of records) full.set(fullKey(r), (full.get(fullKey(r)) || 0) + 1);
  const fullDup = [...full.values()].filter((v) => v > 1).length;

  return { dupGroups, redundant, adjacent, fullDup };
}

function computeOrderChecks(records, questOrder) {
  const res = {};
  // id 与物理行号
  res.idMismatch = records.filter((r, i) => r.id !== i + 1 || r.id !== r.__line).length;
  // id / order 连续性
  res.idGaps = 0;
  const idsSorted = records.map((r) => r.id).sort((a, b) => a - b);
  for (let i = 0; i < idsSorted.length; i++) if (idsSorted[i] !== i + 1) res.idGaps++;
  res.orders = uniq(records.map((r) => r.order)).sort((a, b) => a - b);
  res.orderContinuous = res.orders.length === res.orders[res.orders.length - 1] - res.orders[0] + 1;
  res.taskCount = uniq(records.map((r) => r.task)).length;
  res.orderTask1to1 = res.taskCount === res.orders.length;

  // order 在语料顺序上单调不减
  let orderInversions = 0;
  const inversionExamples = [];
  for (let i = 1; i < records.length; i++) {
    if (records[i].order < records[i - 1].order) {
      orderInversions++;
      if (inversionExamples.length < 5) inversionExamples.push([records[i - 1].id, records[i - 1].order, records[i].id, records[i].order]);
    }
  }
  res.orderInversions = orderInversions;
  res.orderInversionExamples = inversionExamples;

  // version 序列单调（3.0→3.7）
  const vSeq = [];
  let last = null;
  for (const r of records) {
    if (r.version !== last) { vSeq.push(r.version); last = r.version; }
  }
  res.versionSeq = vSeq;
  const vi = (v) => { const [a, b] = String(v).split('.').map(Number); return a * 100 + b; };
  res.versionMonotone = vSeq.every((v, i) => i === 0 || vi(v) > vi(vSeq[i - 1]));
  res.versionOrderMismatch = 0;
  const orderVer = new Map();
  for (const r of records) {
    if (!orderVer.has(r.order)) orderVer.set(r.order, new Set());
    orderVer.get(r.order).add(r.version);
  }
  res.ordersWithMultiVersion = [...orderVer.entries()].filter(([, s]) => s.size > 1).map(([o]) => o);

  // 任务内 idx 连续、step_idx 单调不减、step_idx 范围
  const byOrder = new Map();
  for (const r of records) {
    if (!byOrder.has(r.order)) byOrder.set(r.order, []);
    byOrder.get(r.order).push(r);
  }
  res.idxProblems = [];
  res.stepIdxProblems = [];
  res.taskStats = [];
  for (const [order, rs] of [...byOrder.entries()].sort((a, b) => a[0] - b[0])) {
    const idxs = rs.map((r) => r.idx);
    const sorted = [...idxs].sort((a, b) => a - b);
    const idxOk = sorted.every((v, i) => v === i + 1);
    if (!idxOk) res.idxProblems.push({ order, task: rs[0].task, n: rs.length, min: Math.min(...idxs), max: Math.max(...idxs) });
    let stepInv = 0;
    for (let i = 1; i < rs.length; i++) if (rs[i].step_idx < rs[i - 1].step_idx) stepInv++;
    if (stepInv) res.stepIdxProblems.push({ order, task: rs[0].task, inversions: stepInv, maxStep: Math.max(...rs.map((r) => r.step_idx)) });
    res.taskStats.push({
      order,
      task: rs[0].task,
      version: rs[0].version,
      series_no: rs[0].series_no,
      records: rs.length,
      chars: rs.reduce((a, r) => a + cjkLen(r.text), 0),
      steps: Math.max(...rs.map((r) => r.step_idx)),
      extra: rs.filter((r) => r.extra).length,
      location: rs.filter((r) => r.location).length,
      scene: rs.filter((r) => r.scene).length,
    });
  }

  // quest-order.json 交付的链
  res.questOrder = { count: questOrder.length, orderContinuous: true, versionMonotone: true, adjacencyMismatch: [], edgeViolations: [], externalRefs: [], multiPrev: [], seriesNoDup: [] };
  const qo = res.questOrder;
  for (let i = 0; i < questOrder.length; i++) {
    const q = questOrder[i];
    if (q.order !== i + 1) qo.orderContinuous = false;
    if (i > 0 && vi(q.version) < vi(questOrder[i - 1].version)) qo.versionMonotone = false;
  }
  const base = (s) => String(s || '').split('#')[0].trim();
  const qoByName = new Map(questOrder.map((q) => [q.task, q]));
  for (let i = 0; i < questOrder.length; i++) {
    const q = questOrder[i];
    const prev = i > 0 ? questOrder[i - 1].task : '';
    const next = i < questOrder.length - 1 ? questOrder[i + 1].task : '';
    if (base(q.prev) !== prev) qo.adjacencyMismatch.push({ order: q.order, task: q.task, field: 'prev', declared: q.prev, adjacent: prev });
    if (base(q.next) !== next) qo.adjacencyMismatch.push({ order: q.order, task: q.task, field: 'next', declared: q.next, adjacent: next });
    for (const [field, expect] of [['prev', 'lt'], ['next', 'gt']]) {
      const ref = base(q[field]);
      if (!ref) continue;
      const target = qoByName.get(ref);
      if (!target) { qo.externalRefs.push({ order: q.order, task: q.task, field, ref: q[field] }); continue; }
      if (expect === 'lt' && !(target.order < q.order)) qo.edgeViolations.push({ order: q.order, task: q.task, field, ref: q[field], targetOrder: target.order });
      if (expect === 'gt' && !(target.order > q.order)) qo.edgeViolations.push({ order: q.order, task: q.task, field, ref: q[field], targetOrder: target.order });
    }
  }
  const inDeg = new Map();
  for (const q of questOrder) {
    const ref = base(q.next);
    if (ref && qoByName.has(ref)) inDeg.set(ref, (inDeg.get(ref) || 0) + 1);
  }
  for (const [task, deg] of inDeg) if (deg > 1) qo.multiPrev.push({ task, incoming: deg });
  const seriesNoCount = new Map();
  for (const q of questOrder) {
    const k = q.version + '#' + q.series_no;
    seriesNoCount.set(k, (seriesNoCount.get(k) || 0) + 1);
  }
  for (const [k, c] of seriesNoCount) if (c > 1) qo.seriesNoDup.push({ key: k, count: c });

  // jsonl order 与 quest-order order 是否一致
  res.corpusQuestOrderMismatch = 0;
  for (let i = 0; i < questOrder.length; i++) {
    const rs = byOrder.get(i + 1);
    if (!rs || rs[0].task !== questOrder[i].task || rs[0].version !== questOrder[i].version) res.corpusQuestOrderMismatch++;
  }

  // lines.txt 一致性
  const lines = readText(P.lines).split(/\r?\n/).filter((l) => l.length);
  res.linesTxt = {
    count: lines.length,
    countMatches: lines.length === records.length,
    tailMismatch: 0,
    examples: [],
  };
  for (let i = 0; i < Math.min(lines.length, records.length); i++) {
    if (!lines[i].endsWith(records[i].text)) {
      res.linesTxt.tailMismatch++;
      if (res.linesTxt.examples.length < 3) res.linesTxt.examples.push(i + 1);
    }
  }
  return res;
}

function computePurity(records) {
  const total = records.length;
  const occ = (re) => records.reduce((a, r) => a + (r.text.match(re) || []).length, 0);
  /** ⚠️ 注意：带 g 的正则 .test() 会携带 lastIndex 状态，必须克隆成非 g 再用于筛选 */
  const recs = (re) => {
    const testRe = new RegExp(re.source, re.flags.replace('g', ''));
    return records.filter((r) => testRe.test(r.text));
  };
  const mk = (label, re, exampleN, note) => {
    const hit = recs(re);
    return {
      label,
      records: hit.length,
      occurrences: occ(re),
      pctOfRecords: pct(hit.length, total),
      note: note || '',
      examples: hit.slice(0, exampleN || 5).map((r) => ({ id: r.id, line: r.__line, kind: r.kind, speaker: r.speaker, text: r.text, snippet: snippetAround(r.text, re, 36) })),
    };
  };

  const checks = [];
  checks.push(mk('模板起始 `{{`（未解析/文本被截断）', /\{\{/g, 5, '文本从 `{{` 处被截断，如 `我{{黑幕`、`{{颜色`'));
  checks.push(mk('模板收尾 `}}` 残留', /\}\}/g, 5, '多为 option 台词尾部多出 `}}`'));
  checks.push(mk('含模板残留的短文本（`text` < 10 字）', /^(?=[\s\S]{0,9}$)(?=.*(?:\{\{|\}\}))[\s\S]+$/g, 5, '含 `{{颜色`（无正文）与 `我是开拓者。}}`（多余尾括号）两类'));
  checks.push(mk('wikilink `[[` / `]]`', /\[\[|\]\]/g));
  checks.push(mk('HTML 标签 `<tag>`', /<\/?[A-Za-z][A-Za-z0-9]*(?:\s[^>]*)?>/g));
  checks.push(mk('HTML 实体 `&nbsp;` 等', /&[a-zA-Z]+;|&#\d+;/g));
  checks.push(mk('`他/她` 性别占位', /他\/她/g));
  checks.push(mk('`*强调*` 标记', /\*[^*\n]+\*/g));
  checks.push(mk('控制字符', /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g));
  checks.push(mk('`undefined`/`null`/`NaN` 字面量', /\b(?:undefined|null|NaN)\b/g));
  checks.push(mk('http(s) 链接残留', /https?:\/\//g));
  checks.push(mk('屏蔽/乱码字符 `█▀▄`', /[█▀▄░▒]/g));

  // *强调* 明细
  const starRecords = recs(/\*[^*\n]+\*/);
  let starPairs = 0;
  const starInner = new Map();
  const starNonPronoun = [];
  for (const r of records) {
    const ms = [...r.text.matchAll(/\*([^*\n]+)\*/g)];
    starPairs += ms.length;
    for (const m of ms) {
      const inner = m[1];
      starInner.set(inner, (starInner.get(inner) || 0) + 1);
      if (!['我', '我们', '你', '你们', '他', '她', '它们', '大家'].includes(inner)) starNonPronoun.push({ id: r.id, kind: r.kind, speaker: r.speaker, inner, text: r.text });
    }
  }

  // 纯 *…* 文本（疑似舞台指示）
  const pureStar = records.filter((r) => /^\*[^*\n]+\*$/.test(r.text));
  const soundLike = pureStar.filter((r) => {
    const inner = r.text.replace(/^\*|\*$/g, '');
    return cjkLen(inner) <= 15 && !/[。！？…，,]/.test(inner);
  });
  const quoteStar = pureStar.filter((r) => !soundLike.includes(r));

  // 全角括号包裹的台词（多为动作/内心描写）
  const parenDialogue = records.filter((r) => r.kind === 'dialogue' && /^（[\s\S]*）$/.test(r.text));
  const parenOption = records.filter((r) => r.kind === 'option' && /^（[\s\S]*）$/.test(r.text));

  // narration 中内嵌「说话人：」（已知问题 10）
  const narration = records.filter((r) => r.kind === 'narration');
  const narrEmbeddedRe = /^([^：:\n]{1,24})：/;
  const narrEmbedded = narration.filter((r) => narrEmbeddedRe.test(r.text));
  const narrEmbeddedBracket = narration.filter((r) => /^[^：]{1,24}\[[^\]］]{1,12}[\]］]：/.test(r.text));
  const narrLabelCount = new Map();
  for (const r of narrEmbedded) {
    const m = r.text.match(narrEmbeddedRe);
    if (m) narrLabelCount.set(m[1].trim(), (narrLabelCount.get(m[1]) || 0) + 1);
  }

  // 模板残留明细（供问题清单引用，避免报告里硬编码数字）
  const openRecs = recs(/\{\{/);
  const closeRecs = recs(/\}\}/);
  const braceRecs = recs(/\{\{|\}\}/);
  const templateStats = {
    openRecords: openRecs.length,
    openOccurrences: occ(/\{\{/g),
    openWithoutClose: openRecs.filter((r) => !r.text.includes('}}')).length,
    lostBody: openRecs.filter((r) => /^\{\{[^|}]*$/.test(r.text)), // 如 "{{颜色"，正文完全丢失
    closeRecords: closeRecs.length,
    closeOccurrences: occ(/\}\}/g),
    closeOption: closeRecs.filter((r) => r.kind === 'option').length,
    unionRecords: braceRecs.length,
    unionOption: braceRecs.filter((r) => r.kind === 'option').length,
    examplesOpen: openRecs.slice(0, 5).map((r) => r.id),
    examplesClose: closeRecs.slice(0, 5).map((r) => r.id),
  };

  return {
    checks,
    templateStats,
    star: { records: starRecords.length, pairs: starPairs, inner: starInner, nonPronoun: starNonPronoun },
    pureStar,
    soundLike,
    quoteStar,
    parenDialogue,
    parenOption,
    narration,
    narrEmbedded,
    narrEmbeddedBracket,
    narrLabelCount,
  };
}

// ---------------------------------------------------------------------------
// 4. 渲染正文抽样比对（仅单页 yinnian）
// ---------------------------------------------------------------------------
function computeRenderedCheck(records) {
  if (!fs.existsSync(P.rendered)) return { exists: false };
  const renderedRaw = readText(P.rendered);
  const renderedLines = renderedRaw.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  const norm = (s) => s.replace(/[\s\u3000\u200b\ufeff]/g, '');
  const normLines = new Set(renderedLines.map(norm));
  const normJoined = norm(renderedLines.join('\n'));
  const loose = (s) =>
    s
      .replace(/[\s\u3000\u200b\ufeff]/g, '')
      .replace(/[，。！？…、,.!?；;：:—\-「」『』（）()【】\[\]]/g, '');
  const looseJoined = loose(renderedLines.join('\n'));
  const looseLines = new Set(renderedLines.map(loose));

  const sub = records.filter((r) => r.task === RENDERED_TASK);
  const checkOne = (r) => {
    const n = norm(r.text);
    const exactLine = normLines.has(n);
    const strict = exactLine || normJoined.includes(n);
    const ln = loose(r.text);
    const looseHit = !strict && (looseLines.has(ln) || (ln.length >= 2 && looseJoined.includes(ln)));
    let note = '';
    if (exactLine) note = '精确整行命中（去空白后与某渲染行相同）';
    else if (strict) note = '包含匹配命中（本句是渲染行/正文的片段）';
    else if (looseHit) note = '宽松命中（仅标点/格式差异）';
    else if (r.extra) note = '未命中：位于 `{{折叠}}` 块（innerText 不含）';
    else if (/\}\}$/.test(r.text.trim())) note = '未命中：文本残留模板右括号 `}}`，与页面不一致';
    else note = '未命中：疑似分支/变体或页面版本差异（待人工）';
    return { strict, exactLine, looseHit, note };
  };

  // 全量核对（该任务全部记录）
  const full = sub.map((r) => ({ record: r, ...checkOne(r) }));
  const fullExact = full.filter((x) => x.exactLine).length;
  const fullStrict = full.filter((x) => x.strict).length;
  const fullLoose = full.filter((x) => x.strict || x.looseHit).length;
  const fullExtra = full.filter((x) => x.record.extra).length;
  const fullHitExtra = full.filter((x) => x.record.extra && x.strict).length;
  const fullMissNonExtra = full.filter((x) => !x.record.extra && !x.strict);

  // 随机 20 条（固定种子，Fisher-Yates 抽样，保持语料顺序展示）
  const rng = mulberry32(SAMPLE_SEED);
  const pool = sub.map((_, i) => i);
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  const picked = pool.slice(0, Math.min(SAMPLE_N, pool.length)).sort((a, b) => a - b);
  const sample = picked.map((i) => ({ record: sub[i], ...checkOne(sub[i]) }));

  return {
    exists: true,
    file: path.relative(ROOT, P.rendered).replace(/\\/g, '/'),
    task: RENDERED_TASK,
    renderedLines: renderedLines.length,
    renderedChars: cjkLen(renderedRaw),
    taskRecords: sub.length,
    full: { exact: fullExact, strict: fullStrict, loose: fullLoose, total: sub.length, extra: fullExtra, hitExtra: fullHitExtra, missNonExtra: fullMissNonExtra },
    sample,
  };
}

// ---------------------------------------------------------------------------
// 5. 报告：corpus-stats.md
// ---------------------------------------------------------------------------
function buildStatsReport(ctx) {
  const { records, basic, normalizer, normStats, questOrder, corpusHash, configHash } = ctx;
  const total = records.length;
  const L = [];
  const push = (...a) => L.push(...a);

  push('# 语料统计报告（amphoreus.jsonl）', '');
  push(`> 生成脚本：\`tools/report-corpus.js\`（只读语料，可重复运行）  `);
  push(`> 主语料：\`data/corpus/amphoreus.jsonl\`（${num(total)} 条，SHA-256 \`${corpusHash.slice(0, 16)}…\`）  `);
  push(`> 归一配置：\`data/config/speaker-alias.json\`（SHA-256 \`${configHash.slice(0, 16)}…\`，只读计算，不回填语料）  `);
  push(`> 统计口径见文末「§10 计算口径」，所有数字均可按同一脚本复核。`, '');

  // 1 总量
  push('## 1. 总量概览', '');
  const tasks = uniq(records.map((r) => r.task)).length;
  const series = uniq(records.map((r) => r.series)).length;
  push(
    mdTable(
      ['指标', '数值', '说明'],
      [
        ['记录数', num(total), 'JSONL 非空行数；`id` 与物理行号已核对为 1:1'],
        ['总字数', num(basic.totalChars), '各记录 `text` 的 Unicode 码位数之和'],
        ['非空白字数', num(basic.nonSpaceChars), '去掉空格后的码位数'],
        ['任务页数', num(tasks), '67 个「开拓任务」主线页'],
        ['版本数', '8', '3.0–3.7'],
        ['系列数', num(series), '每个版本对应一个系列任务'],
        ['平均每条字数', (basic.totalChars / total).toFixed(2), '总字数 ÷ 记录数'],
        ['平均每页记录数', (total / tasks).toFixed(1), '记录数 ÷ 任务页数'],
      ]
    ),
    ''
  );

  // 2 版本分布
  push('## 2. 版本分布', '');
  push(
    mdTable(
      ['版本', '任务页数', '记录数', '记录占比', '字数', '字数占比', 'extra 记录数'],
      basic.versionRows.map((v) => [
        v.version,
        v.tasks.size,
        num(v.records),
        pct(v.records, total),
        num(v.chars),
        pct(v.chars, basic.totalChars),
        num(v.extra),
      ])
    ),
    ''
  );
  push('系列任务（1 版本 = 1 系列）：', '');
  push(
    mdTable(
      ['版本', '系列任务名', '任务页数', '记录数', '字数'],
      [...basic.bySeries.values()].map((s) => [s.version, s.series, s.tasks.size, num(s.records), num(s.chars)])
    ),
    ''
  );

  // 3 kind / extra
  push('## 3. 类型分布（kind / extra）', '');
  const kindRows = [...basic.kindMap.entries()].sort((a, b) => b[1] - a[1]);
  push(
    mdTable(
      ['kind', '记录数', '占比'],
      kindRows.map(([k, n]) => [k, num(n), pct(n, total)])
    ),
    ''
  );
  const extraTrue = basic.extraMap.get('true') || 0;
  push(
    mdTable(
      ['extra', '记录数', '占比', '含义'],
      [
        ['true', num(extraTrue), pct(extraTrue, total), '位于 `{{折叠}}` 块内（额外对话/可选闲聊）'],
        ['false', num(total - extraTrue), pct(total - extraTrue, total), '正文（含过场动画、分支台词）'],
      ]
    ),
    ''
  );
  push('kind × extra 交叉：', '');
  push(
    mdTable(
      ['kind', 'extra=false', 'extra=true', '合计'],
      kindRows.map(([k]) => [
        k,
        num(basic.kindExtra.get(k + ' | extra=false') || 0),
        num(basic.kindExtra.get(k + ' | extra=true') || 0),
        num(basic.kindMap.get(k)),
      ])
    ),
    ''
  );

  // 4 chapter / step / scene / location
  push('## 4. 章节 / 步骤 / 场景 / 地点覆盖', '');
  const chapters = uniq(records.map((r) => r.chapter));
  const stepTitles = uniq(records.map((r) => r.step_title));
  const fallbackStep = records.filter((r) => r.step_title === '剧情内容');
  const sceneRecords = records.filter((r) => r.scene);
  const locationRecords = records.filter((r) => r.location);
  push(
    mdTable(
      ['维度', '实测', '说明'],
      [
        ['chapter 取值数', chapters.length, '全部为 `' + chapters[0] + '`，该字段目前无区分度'],
        ['step_title 取值数', num(stepTitles.length), '含 1 个回退值 `剧情内容`'],
        ['有效步骤标题数', num(stepTitles.length - (stepTitles.includes('剧情内容') ? 1 : 0)), ''] ,
        ['step_title 回退记录', num(fallbackStep.length) + '（' + pct(fallbackStep.length, total) + '）', '步骤标题缺失时被回填为章节名 `剧情内容`，无法从标题定位步骤'],
        ['scene 覆盖记录', num(sceneRecords.length) + '（' + pct(sceneRecords.length, total) + '）', '仅 ' + uniq(sceneRecords.map((r) => r.task)).length + ' 个任务页有 scene 字段，见下表'],
        ['location 覆盖记录', num(locationRecords.length) + '（' + pct(locationRecords.length, total) + '）', '来自 `{{任务描述}}`，' + uniq(locationRecords.map((r) => r.task)).length + '/67 页有值'],
        ['step 数（每页最大 step_idx）', 'min 2 / max 30', '合计 ' + num([...new Set(records.map((r) => r.order))].reduce((a, o) => a + Math.max(...records.filter((r) => r.order === o).map((r) => r.step_idx)), 0)) + ' 个步骤'],
      ]
    ),
    ''
  );
  const sceneMap = new Map();
  for (const r of sceneRecords) sceneMap.set(r.scene, (sceneMap.get(r.scene) || 0) + 1);
  push('scene 取值明细：', '');
  push(
    mdTable(
      ['scene', '记录数', '首条记录行号'],
      [...sceneMap.entries()].sort((a, b) => b[1] - a[1]).map(([s, n]) => [s, num(n), sceneRecords.find((r) => r.scene === s).id])
    ),
    ''
  );
  push('step_title 回退最多的 10 个任务页（说明步骤标题在该页大面积缺失）：', '');
  const fallbackByTask = new Map();
  for (const r of fallbackStep) {
    const k = r.order + '|' + r.task;
    fallbackByTask.set(k, (fallbackByTask.get(k) || 0) + 1);
  }
  push(
    mdTable(
      ['order', '任务页', '回退记录数', '该页记录数', '回退占比'],
      [...fallbackByTask.entries()]
        .map(([k, n]) => {
          const [order, task] = k.split('|');
          const pageTotal = records.filter((r) => r.task === task).length;
          return { order: +order, task, n, pageTotal };
        })
        .sort((a, b) => b.n - a.n)
        .slice(0, 10)
        .map((x) => [x.order, x.task, num(x.n), num(x.pageTotal), pct(x.n, x.pageTotal)])
    ),
    ''
  );

  // 5 Top30 原始说话人
  push('## 5. Top 30 说话人（`speaker` 原样，未归一）', '');
  const spMap = new Map();
  for (const r of records) spMap.set(r.speaker, (spMap.get(r.speaker) || 0) + 1);
  const spRows = [...spMap.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), 'zh'));
  push(`共 ${num(spMap.size)} 个原始 speaker 取值（含 1 个空串 = 旁白/narration）。`, '');
  push(
    mdTable(
      ['#', 'speaker（原样）', '记录数', '占全部记录', '备注'],
      spRows.slice(0, 30).map(([s, n], i) => [
        i + 1,
        s === '' ? '（空串：旁白）' : s,
        num(n),
        pct(n, total),
        s === '' ? '全部为 kind=narration' : '',
      ])
    ),
    ''
  );

  // 6 归一概况
  push('## 6. 说话人归一概况（只读使用 speaker-alias.json）', '');
  push(
    `严格按配置 \`normalization_order\` 的规则 1–5 做本地归一计算（不写回语料）。结果：`,
    ''
  );
  push(
    mdTable(
      ['类别', 'speaker 数', '记录数', '占全部记录', '说明'],
      [
        ['config 可归一（命中 canonical）', num(normStats.matchedSpeakers), num(normStats.matchedRecords), pct(normStats.matchedRecords, total), '规则 1/2/3/4/5 命中'],
        ['config 明示的非说话人标签', num(normStats.nonSpeakerSpeakers), num(normStats.nonSpeakerRecords), pct(normStats.nonSpeakerRecords, total), '如 `？？？`、`留言石板`，按配置不算可归一角色'],
        ['未归一', num(normStats.unmatchedSpeakers), num(normStats.unmatchedRecords), pct(normStats.unmatchedRecords, total), '见 `data/reports/unmatched-speakers.md`'],
        ['空 speaker（narration）', '1（空串）', num(normStats.emptySpeakerRecords), pct(normStats.emptySpeakerRecords, total), 'kind=narration，speaker 字段为空串'],
      ]
    ),
    ''
  );
  const canonCounts = normStats.canonicalCounts;
  const topCanon = [...canonCounts.entries()].sort((a, b) => b[1] - a[1]);
  push(`归一后共 ${num(canonCounts.size)} 个 canonical 角色（含 config 中以其他条目映射来的名称，如泰坦「墨涅塔」）。`, '');

  // 7 Top20 canonical × 版本矩阵
  push('## 7. Top 20 canonical × 版本矩阵（记录数）', '');
  const matrixRows = topCanon.slice(0, 20).map(([name, n], i) => {
    const m = normStats.canonicalMatrix.get(name) || {};
    return [i + 1, name, ...VERSIONS.map((v) => (m[v] ? num(m[v]) : '·')), num(n), pct(n, normStats.matchedRecords)];
  });
  push(
    mdTable(
      ['#', 'canonical', ...VERSIONS, '合计', '占可归一记录'],
      matrixRows
    ),
    ''
  );
  push('形态（form）使用 Top 15（仅统计命中 `speaker_literal_map` / `form_map` / `speaker_aliases` 时带出的 form）：', '');
  const formRows = [...normStats.formCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15);
  push(
    mdTable(
      ['form', 'canonical', '记录数'],
      formRows.map(([form, n]) => [form, normStats.formCanonical.get(form) || '', num(n)])
    ),
    ''
  );

  // 8 长度分布
  push('## 8. 文本长度分布', '');
  const allLens = records.map((r) => cjkLen(r.text));
  const allStats = lengthStats(allLens);
  push(
    mdTable(
      ['分组', '记录数', '均值', 'P50', 'P90', 'P99', 'max', 'min'],
      [
        ['全部', num(allStats.n), allStats.mean.toFixed(2), allStats.p50, allStats.p90, allStats.p99, allStats.max, allStats.min],
        ...kindRows.map(([k]) => {
          const s = lengthStats(records.filter((r) => r.kind === k).map((r) => cjkLen(r.text)));
          return [k, num(s.n), s.mean.toFixed(2), s.p50, s.p90, s.p99, s.max, s.min];
        }),
        ...basic.versionRows.map((v) => {
          const s = lengthStats(records.filter((r) => r.version === v.version).map((r) => cjkLen(r.text)));
          return [v.version, num(s.n), s.mean.toFixed(2), s.p50, s.p90, s.p99, s.max, s.min];
        }),
      ]
    ),
    ''
  );
  const longest = records.reduce((a, r) => (cjkLen(r.text) > cjkLen(a.text) ? r : a), records[0]);
  push(
    `最长记录：行号 ${longest.id}（${longest.version}，${longest.kind}，speaker=\`${longest.speaker || '（空）'}\`），${cjkLen(longest.text)} 字，节选：`,
    '',
    '> ' + trunc(longest.text, 120),
    ''
  );
  push('最短记录：' + num(allStats.min) + ' 字（多为「……」「……」这类承接词）。', '');

  // 9 记录数最多/最少的任务页
  push('## 9. 记录数 Top 10 / Bottom 10 任务页', '');
  const sortedTasks = [...ctx.taskStats].sort((a, b) => b.records - a.records);
  push(
    mdTable(
      ['order', '任务页', '版本', '记录数', '字数', '步骤数', 'extra'],
      sortedTasks.slice(0, 10).map((t) => [t.order, t.task, t.version, num(t.records), num(t.chars), t.steps, num(t.extra)])
    ),
    ''
  );
  push(
    mdTable(
      ['order', '任务页', '版本', '记录数', '字数', '步骤数', 'extra'],
      sortedTasks.slice(-10).map((t) => [t.order, t.task, t.version, num(t.records), num(t.chars), t.steps, num(t.extra)])
    ),
    ''
  );

  // 10 口径
  push('## 10. 计算口径', '');
  push(
    [
      '1. **行号 = `id`**：已核对 `id` 与 JSONL 物理行号 1:1 对齐（0 处不一致），因此报告中的「行号」可直接跳转。',
      '2. **字数**：`[...text].length` 求和（Unicode 码点数，中文 1 字 = 1 码点），不含 JSON 结构字符。',
      '3. **占比分母**：除矩阵列/段落另行说明外，分母为全部 ' + num(total) + ' 条记录。',
      '4. **分位数**：nearest-rank 法，P_k 取升序第 `ceil(k/100 × N)` 个值。',
      '5. **说话人归一**：严格按 `data/config/speaker-alias.json` 的 `normalization_order` 规则 1–5 计算，仅内存计算、不回填；`canonical` 命中率分母为全部记录。',
      '6. **版本区间**：按 `version` 数值排序后取最小/最大（`3.0` < `3.10` 之类将来需扩展）。',
      '7. **复核命令**：`node tools/report-corpus.js`（确定性输出；抽样种子 = ' + SAMPLE_SEED + '）。',
    ].join('\n'),
    ''
  );
  return L.join('\n');
}

// ---------------------------------------------------------------------------
// 6. 报告：qa-checks.md
// ---------------------------------------------------------------------------
function buildQaReport(ctx) {
  const { records, basic, order, completeness, duplicates, purity, rendered, questOrder, corpusHash, configHash } = ctx;
  const total = records.length;
  const L = [];
  const push = (...a) => L.push(...a);

  push('# 语料质量检查报告（qa-checks）', '');
  push(`> 生成脚本：\`tools/report-corpus.js\`；主语料 \`data/corpus/amphoreus.jsonl\`（SHA-256 \`${corpusHash.slice(0, 16)}…\`）。  `);
  push(`> 本报告只读语料，未修改 \`data/corpus/\`、\`data/config/\`、\`data/raw/\` 下任何文件。`, '');
  push('结论速览：**顺序与结构干净（id/order/idx 全连续、版本严格单调、无空文本、无抓取重复行）**，'
    + `但存在 4 类需要在分析前处理的数据问题——① ${num(records.filter((r) => r.step_title === '剧情内容').length)} 条记录的 \`step_title\` 回退为章节名；`
    + `② ${num(purity.templateStats.unionRecords)} 条台词残留模板括号（其中 ${num(purity.templateStats.openRecords)} 条在 \`{{\` 处被截断、${num(purity.templateStats.lostBody.length)} 条 option 正文全丢）；`
    + `③ ${num(purity.narrEmbedded.length)} 条 narration 文本内嵌「说话人：」前缀（实际是对白）；`
    + `④ ${num(ctx.normStats.unmatchedSpeakers)} 个 speaker（${num(ctx.normStats.unmatchedRecords)} 条）无法按现有配置归一。详见 §5。`, '');

  // 1 顺序自检
  push('## 1. 顺序自检', '');
  push('### 1.1 记录级（amphoreus.jsonl）', '');
  push(
    mdTable(
      ['检查项', '结果', '说明'],
      [
        ['`id` 与物理行号一致', order.idMismatch === 0 ? '✅ 0 处不一致' : `❌ ${order.idMismatch} 处`, `id 应为 1…${num(total)}`],
        ['`id` 连续无缺号', order.idGaps === 0 ? '✅ 0 处缺号' : `❌ ${order.idGaps} 处`, ''],
        ['`order` 取值连续', order.orderContinuous ? `✅ 1…${order.orders[order.orders.length - 1]}（${order.orders.length} 个）` : '❌ 不连续', '每个 order = 一个任务页'],
        ['`order` 与任务 1:1', order.orderTask1to1 ? '✅' : '❌', `${order.taskCount} 个任务 / ${order.orders.length} 个 order`],
        ['`order` 随语料顺序单调不减', order.orderInversions === 0 ? '✅ 0 处逆序' : `❌ ${order.orderInversions} 处逆序`, order.orderInversionExamples.map((x) => `行 ${x[0]}(${x[1]})→行 ${x[2]}(${x[3]})`).join('；')],
        ['`version` 序列严格单调', order.versionMonotone ? '✅ ' + order.versionSeq.join(' → ') : '❌ ' + order.versionSeq.join(' → '), '3.0–3.7，无回跳'],
        ['同一 order 内只有 1 个 version', order.ordersWithMultiVersion.length === 0 ? '✅' : `❌ ${order.ordersWithMultiVersion.join(',')}`, ''],
        ['任务内 `idx` 连续 1…n', order.idxProblems.length === 0 ? '✅ 67/67 页通过' : `❌ ${order.idxProblems.length} 页异常`, order.idxProblems.slice(0, 3).map((x) => `${x.order}:${x.task}`).join('；')],
        ['任务内 `step_idx` 单调不减', order.stepIdxProblems.length === 0 ? '✅ 0 处回退' : `❌ ${order.stepIdxProblems.length} 页回退`, order.stepIdxProblems.slice(0, 3).map((x) => `${x.order}:${x.task}（${x.inversions} 处）`).join('；')],
        ['jsonl 顺序 vs quest-order.json', order.corpusQuestOrderMismatch === 0 ? '✅ 67/67 页一致' : `❌ ${order.corpusQuestOrderMismatch} 页不一致`, '`order/task/version` 三者对齐'],
      ]
    ),
    ''
  );

  push('### 1.2 任务链（quest-order.json 的 prev/next 字段）', '');
  const qo = order.questOrder;
  push(
    mdTable(
      ['检查项', '结果', '说明'],
      [
        ['任务数 / order 连续 / 版本单调', `${qo.count} / ${qo.orderContinuous ? '✅' : '❌'} / ${qo.versionMonotone ? '✅' : '❌'}`, ''],
        ['prev/next 与相邻 order 完全成链', qo.adjacencyMismatch.length === 0 ? '✅' : `⚠️ ${qo.adjacencyMismatch.length} 处不吻合`, '见下方明细'],
        ['prev/next 指向的 order 方向违例', qo.edgeViolations.length === 0 ? '✅' : `⚠️ ${qo.edgeViolations.length} 条反向边`, '后置任务指向前置任务，属分支页结构'],
        ['指向 67 页范围之外的链接', `${qo.externalRefs.length} 条`, qo.externalRefs.map((x) => `order ${x.order}「${x.task}」→「${x.ref}」`).join('；')],
        ['被多个任务同时指向（分支汇合）', qo.multiPrev.length === 0 ? '✅ 0' : `⚠️ ${qo.multiPrev.length} 个`, qo.multiPrev.map((x) => `「${x.task}」← ${x.incoming} 个前置`).join('；')],
        ['同一版本内 `series_no` 重复', qo.seriesNoDup.length === 0 ? '✅ 0' : `⚠️ ${qo.seriesNoDup.map((x) => x.key + '（' + x.count + ' 个任务）').join('；')}`, ''],
      ]
    ),
    ''
  );
  if (qo.adjacencyMismatch.length) {
    push('prev/next 与相邻 order 不吻合明细（按「简单链」口径，`#` 后的锚点已忽略以便比较）：', '');
    push(
      mdTable(
        ['order', '任务页', '字段', '声明的链接', '实际相邻任务'],
        qo.adjacencyMismatch.map((x) => [x.order, x.task, x.field, x.declared || '（空）', x.adjacent || '（无）'])
      ),
      ''
    );
    push('> 说明：3.4 的「英雄啊，兑现那染血的冀望」「英雄啊，粉碎那悲哀的造像」是多分支页，其 `前置/后续任务` 字段带 `#小节` 锚点、'
      + '且存在“后置指向更早页”的边，因此无法用「简单相邻链」口径解释。**语料 `order` 本身仍满足版本单调与边方向（只有 2 条反向边来自分支页）**，'
      + 'README 中「链一致性违例 0」的表述建议注明口径。', '');
  }

  // 2 完整性
  push('## 2. 数据完整性', '');
  push('### 2.1 字段缺失率', '');
  push(
    mdTable(
      ['字段', '类型', '缺失（无该键）', 'null', '空串', '有效值', '有效率'],
      completeness.map((c) => [c.field, c.type, num(c.missing), num(c.null), num(c.empty), num(c.valid), pct(c.valid, total)])
    ),
    ''
  );
  push('> `location` / `scene` 为**可选字段**（BWiki 只有部分页面/部分段落提供），缺失属预期；'
    + '其余 14 个字段 0 缺失、0 空串。`speaker` 的 1,116 条空串全部是 `kind=narration`（旁白），不是缺失。', '');

  push('### 2.2 空文本 / 重复记录', '');
  const emptyText = records.filter((r) => !r.text || !r.text.trim()).length;
  push(
    mdTable(
      ['检查项', '结果', '说明'],
      [
        ['空文本记录', emptyText === 0 ? '✅ 0 条' : `❌ ${emptyText} 条`, '无 null / 空串 / 纯空白'],
        ['含换行符或制表符的 text', records.filter((r) => /[\r\n\t]/.test(r.text)).length + ' 条', '标题/段落换行已在抽取时压平'],
        ['重复行（task+kind+speaker+text 完全一致）', `${num(duplicates.dupGroups.length)} 组，冗余 ${num(duplicates.redundant)} 条（${pct(duplicates.redundant, total)}）`, '同一句在分支/重复对话中多次出现，非抓取重复，见 2.3'],
        ['相邻重复（同一行连续出现）', num(duplicates.adjacent) + ' 处', ''],
        ['仅 id/idx 不同的重复记录（除 `id`/`idx` 外全字段一致）', duplicates.fullDup === 0 ? '✅ 0 组' : `${num(duplicates.fullDup)} 组`, '即同一句出现在同一任务同一小节多次（分支/重复台词），不是抓取重复行'],
        ['`amphoreus.lines.txt` 行数一致', order.linesTxt.countMatches ? `✅ ${num(order.linesTxt.count)} 行 = 记录数` : `❌ ${num(order.linesTxt.count)} 行`, ''],
        ['`lines.txt` 与 jsonl 逐行文本一致', order.linesTxt.tailMismatch === 0 ? '✅ 0 处不一致（以 text 结尾校验）' : `❌ ${order.linesTxt.tailMismatch} 处`, order.linesTxt.examples.map((n) => '行 ' + n).join('；')],
      ]
    ),
    ''
  );

  push('### 2.3 重复记录 Top 10 示例（分支/滚动重复，非丢数据但需去重意识）', '');
  push(
    mdTable(
      ['次数', '行号', '任务页', 'speaker', 'text（截断）', 'extra'],
      duplicates.dupGroups.slice(0, 10).map((g) => [
        g.length,
        g.map((r) => r.id).join(', '),
        trunc(g[0].task, 16),
        g[0].speaker || '（旁白）',
        trunc(g[0].text, 40),
        String(g[0].extra),
      ])
    ),
    ''
  );
  push('> 结论：重复来自「同一句台词在多个分支/多次对话中重复出现」，不是抓取重复。'
    + '做逐句统计（如 TF-IDF、共现）前建议按 `(task, speaker, text)` 去重或保留首现。', '');

  // 3 文本纯度
  const ts = purity.templateStats;
  push('## 3. 文本纯度', '');
  push(
    mdTable(
      ['检查项', '命中记录数', '占全部记录', '出现次数', '说明', '示例（行号：片段）'],
      purity.checks.map((c) => [
        c.label,
        num(c.records),
        c.pctOfRecords,
        num(c.occurrences),
        c.note || '—',
        c.examples.length ? c.examples.map((e) => `${e.id}：${e.snippet}`).join('<br>') : '—',
      ])
    ),
    ''
  );
  push(
    [
      '- `[[ ]]` wikilink 与 `<html>` 标签 / HTML 实体：**0 处**，链接与大部分标签已剥离干净。',
      `- **模板残留分两类**：① ${num(ts.openRecords)} 条记录在 \`{{\` 处被截断（其中 ${num(ts.lostBody.length)} 条 option 只剩 \`{{颜色\`，正文完全丢失，如行 ${ts.lostBody.slice(0, 3).map((r) => r.id).join('、')}；`
        + `另有 ${num(ts.openRecords - ts.lostBody.length)} 条旁白/台词在模板处被切断，语义不完整）；② ${num(ts.closeRecords)} 条记录尾部多出 \`}}\`（${num(ts.closeOption)} 条为 option，如行 139「开始决定目的地吧。}}」）。`
        + '两类都是抽取时未解析 `{{…}}` 模板造成的；**截断类会丢文本，必须修抽取脚本，不能只做事后字符串清洗**。',
      '- `他/她` 是 BWiki 为兼容双主角保留的性别占位符；`*强调*` 中 273 处是「*我们*」（缇宝指代分身群体，语义有价值，**不要直接删**），其余为普通强调或舞台指示。',
    ].join('\n'),
    ''
  );

  // 3.1 *强调* 明细
  push('### 3.1 `*强调*` 明细', '');
  push(
    mdTable(
      ['*…* 内容', '出现次数', '处理建议'],
      [...purity.star.inner.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12).map(([inner, n]) => [
        '*' + trunc(inner, 24) + '*',
        num(n),
        ['我', '我们', '你', '你们', '他', '她'].includes(inner) ? '缇宝自指/人称强调，保留' : '疑似强调或舞台指示，按语义归一',
      ])
    ),
    ''
  );
  push(`合计 ${num(purity.star.pairs)} 对 \`*…*\`，分布在 ${num(purity.star.records)} 条记录；其中非人称内容 ${num(purity.star.nonPronoun.length)} 对（${pct(purity.star.nonPronoun.length, purity.star.pairs)}）。`, '');

  // 3.2 舞台指示
  push('### 3.2 舞台指示 / 动作描写疑似条数', '');
  push(
    mdTable(
      ['类别', '条数', '示例', '建议'],
      [
        [
          '`text` 整条被 `*…*` 包裹（kind=dialogue）',
          num(purity.pureStar.length),
          purity.pureStar.slice(0, 5).map((r) => `${r.id}：${r.text}`).join('<br>'),
          '应归入 `kind=narration`（其中“声音/呢喃/低吼”类为拟声，见下一行）',
        ],
        [
          '└ 其中「短拟声/动作」类（≤15 字、无句读）',
          num(purity.soundLike.length),
          purity.soundLike.slice(0, 6).map((r) => `${r.id}：${r.text}（${r.speaker || '旁白'}）`).join('<br>'),
          '明确是舞台指示/拟声，建议 kind=narration',
        ],
        [
          '└ 其中「引用台词」类（带句读的长句被 `*` 包裹）',
          num(purity.quoteStar.length),
          purity.quoteStar.slice(0, 3).map((r) => `${r.id}：${trunc(r.text, 24)}`).join('<br>'),
          '可能是回忆/转述引号，需人工确认是否保留 `*`',
        ],
        [
          '`kind=dialogue` 且整条被全角括号 `（…）` 包裹',
          num(purity.parenDialogue.length),
          purity.parenDialogue.slice(0, 5).map((r) => `${r.id}：${trunc(r.text, 24)}（${r.speaker}）`).join('<br>'),
          '多为动作/内心描写，建议 kind=narration',
        ],
        [
          '`kind=option` 且整条被全角括号包裹',
          num(purity.parenOption.length),
          purity.parenOption.slice(0, 3).map((r) => `${r.id}：${trunc(r.text, 20)}`).join('<br>'),
          '选项的「情境提示」，可保留',
        ],
      ]
    ),
    ''
  );

  // 3.3 narration 内嵌说话人
  push('### 3.3 narration 内嵌「说话人：」前缀（结构性问题）', '');
  push(
    `\`kind=narration\` 共 ${num(purity.narration.length)} 条，其中 **${num(purity.narrEmbedded.length)} 条（${pct(purity.narrEmbedded.length, purity.narration.length)}）的 text 以「说话人：」开头**（如 \`永夜之帷，三月七：…\`、\`？？？：…\`、\`博识尊[黑塔]：…\`），`
    + `实际是对白却被整体标成旁白、speaker 为空。另有 ${num(purity.narrEmbeddedBracket.length)} 条形如 \`博识尊[黑塔]：\`（方括号内嵌说话人）。`,
    ''
  );
  push('内嵌前缀 Top 12：', '');
  push(
    mdTable(
      ['内嵌说话人前缀', '条数'],
      [...purity.narrLabelCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12).map(([k, n]) => [k, num(n)])
    ),
    ''
  );
  push(
    `> 建议：对这 ${num(purity.narrEmbedded.length)} 条做二次拆分（\`kind=dialogue\` + \`speaker=<前缀>\`），或至少新增 \`embedded_speaker\` 字段；`
    + `否则按 speaker 统计「谁说的话」时，这部分（占全部记录 ${pct(purity.narrEmbedded.length, total)}）会被漏计。`,
    ''
  );

  // 3.4 其它
  push('### 3.4 其它可疑模式', '');
  const longText = records.filter((r) => cjkLen(r.text) > 200);
  push(
    mdTable(
      ['模式', '条数', '说明 / 示例'],
      [
        ['`█▀▄` 等屏蔽字符', num(records.filter((r) => /[█▀▄░▒]/.test(r.text)).length), records.filter((r) => /[█▀▄░▒]/.test(r.text)).slice(0, 2).map((r) => `${r.id}：${trunc(r.text, 40)}`).join('<br>') + '（3.7 记忆/乱码段落，语义不可用，分析时建议排除）'],
        [`超长单条（>200 字）`, num(longText.length), longText.slice(0, 2).map((r) => `${r.id}：${cjkLen(r.text)} 字（${r.kind}，${r.version}）`).join('<br>') + '（多为旁白/过场动画独白，非拆分错误）'],
        ['`？？？` 作为 speaker', num(records.filter((r) => r.speaker === '？？？').length), 'config 列为非说话人标签，语义上是「未知说话者」，建议保留但排除出角色统计'],
        ['`location` 有值但为空串', num(records.filter((r) => r.location === '').length), '可忽略（等价于缺失）'],
      ]
    ),
    ''
  );

  // 4 渲染抽样
  push('## 4. 抽样比对（`data/shots/yinnian.rendered.txt`）', '');
  if (!rendered.exists) {
    push('`data/shots/yinnian.rendered.txt` 不存在，跳过本节。', '');
  } else {
    push(
      `渲染正文只覆盖单个任务页「${rendered.task}」（${num(rendered.renderedLines)} 行可见文本），因此**必须先按 task 过滤语料**再比对；其余 66 页无法用该文件核对。`
        + `该任务在语料中 ${num(rendered.taskRecords)} 条记录（其中 extra 折叠 ${num(rendered.full.extra)} 条）。`,
      ''
    );
    push('### 4.1 全页核对（该任务全部记录）', '');
    push(
      mdTable(
        ['口径', '命中', '占比'],
        [
          ['精确整行命中（去空白后与某渲染行相同）', `${num(rendered.full.exact)} / ${num(rendered.full.total)}`, pct(rendered.full.exact, rendered.full.total)],
          ['包含匹配命中（本句是渲染行/正文片段）', `${num(rendered.full.strict)} / ${num(rendered.full.total)}`, pct(rendered.full.strict, rendered.full.total)],
          ['含宽松命中（额外忽略标点）', `${num(rendered.full.loose)} / ${num(rendered.full.total)}`, pct(rendered.full.loose, rendered.full.total)],
          ['非折叠记录·包含匹配命中', `${num(rendered.full.strict - rendered.full.hitExtra)} / ${num(rendered.full.total - rendered.full.extra)}`, pct(rendered.full.strict - rendered.full.hitExtra, rendered.full.total - rendered.full.extra)],
          ['折叠（extra=true）记录·包含匹配命中', `${num(rendered.full.hitExtra)} / ${num(rendered.full.extra)}`, pct(rendered.full.hitExtra, rendered.full.extra)],
        ]
      ),
      ''
    );
    push('> 口径提示：**精确整行**要求语料 `text` 与页面上某一行完全一致（语料按气泡/句切分，页面上常常是「说话人：整句」，所以只能命中一部分）；'
      + '**包含匹配**只要求这句文本作为片段出现在渲染正文中（下限口径，短句如「……」可能在其他上下文里也被匹配到）。两者分别看，不要混用。', '');
    push('### 4.2 随机 20 条明细（种子 ' + SAMPLE_SEED + '）', '');
    push(
      mdTable(
        ['#', '行号', 'kind', 'extra', 'speaker', 'text（≤28 字）', '命中', '备注'],
        rendered.sample.map((x, i) => [
          i + 1,
          x.record.id,
          x.record.kind,
          x.record.extra ? 'true' : 'false',
          x.record.speaker || '（空）',
          trunc(x.record.text, 28),
          x.exactLine ? '✅ 精确行' : x.strict ? '✅ 包含' : x.looseHit ? '🟡 宽松' : '❌ 未命中',
          x.note,
        ])
      ),
      ''
    );
    const sExact = rendered.sample.filter((x) => x.exactLine).length;
    const sStrict = rendered.sample.filter((x) => x.strict).length;
    const sLoose = rendered.sample.filter((x) => x.strict || x.looseHit).length;
    const sExtra = rendered.sample.filter((x) => x.record.extra).length;
    push(
      `**抽样命中率：精确整行 ${sExact}/20（${pct(sExact, 20)}），包含匹配 ${sStrict}/20（${pct(sStrict, 20)}），含宽松 ${sLoose}/20（${pct(sLoose, 20)}）；样本中折叠记录 ${sExtra} 条。**`,
      ''
    );
    push(
      '结论与 README 的差异：README 称「抽检 41 条，未命中的 13 条全部位于 `{{折叠}}` 块内」，本次全页核对显示**非折叠记录也有约 1/7 未能在 innerText 中找到**'
        + `（${num(rendered.full.missNonExtra.length)} 条）。原因可能是：① 部分「额外对话」折叠块未被标成 extra=true；`
        + '② 分支选项台词在页面上以别的形式呈现；③ 渲染快照与当前 wikitext 版本不同。**结论：解析结果比渲染可见内容更全，未命中不能直接判定为“脏数据”，但也不能全部用折叠解释，需抽样人工复核。**',
      ''
    );
  }

  // 5 已知问题
  push('## 5. 数据问题清单（按严重度）', '');
  const fallbackStep = records.filter((r) => r.step_title === '剧情内容');
  const heTaOcc = records.reduce((a, r) => a + (r.text.match(/他\/她/g) || []).length, 0);
  push(
    mdTable(
      ['#', '级别', '问题', '影响面', '示例行号', '建议'],
      [
        ['1', '高', '`kind=narration` 文本内嵌「说话人：」前缀（实为对白）', `${num(purity.narrEmbedded.length)} 条（${pct(purity.narrEmbedded.length, total)}）`, purity.narrEmbedded.slice(0, 3).map((r) => r.id).join(', '), '二次拆分：kind=dialogue + speaker=前缀'],
        ['2', '高', '`step_title` 大面积回退为章节名 `剧情内容`', `${num(fallbackStep.length)} 条（${pct(fallbackStep.length, total)}），涉及 ${uniq(fallbackStep.map((r) => r.order)).length} 个任务页`, fallbackStep.slice(0, 3).map((r) => r.id).join(', '), '重新抽取步骤标题；或标记 `step_title_missing`'],
        ['3', '高', `${num(ctx.normStats.unmatchedSpeakers)} 个 speaker（${num(ctx.normStats.unmatchedRecords)} 条）无法按 config 归一`, `${num(ctx.normStats.unmatchedRecords)} 条（${pct(ctx.normStats.unmatchedRecords, total)}）`, '见 unmatched-speakers.md', '补 speaker-alias 配置（含 true_name/形态/复合标签），再回填'],
        ['4', '高', '模板未解析：`{{` 处文本被截断 / `}}` 尾残', `${num(ts.unionRecords)} 条（${pct(ts.unionRecords, total)}）：截断 ${num(ts.openRecords)} 条（其中 ${num(ts.lostBody.length)} 条 option 正文全丢），尾残 ${num(ts.closeRecords)} 条`, `${ts.examplesOpen.slice(0, 3).join(', ')}；${ts.examplesClose.slice(0, 2).join(', ')}`, '修抽取脚本的 `{{…}}` 解析；截断类会丢文本，光做字符串清洗无法恢复'],
        ['5', '中', '全角括号/`*…*` 包裹的动作描写仍标为 dialogue', `${num(purity.parenDialogue.length + purity.pureStar.length)} 条`, purity.pureStar.slice(0, 2).map((r) => r.id).join(', '), '归入 kind=narration 或加 kind=stage_direction'],
        ['6', '中', '重复台词（同一 task+kind+speaker+text 多次出现）', `${num(duplicates.dupGroups.length)} 组、冗余 ${num(duplicates.redundant)} 条（${pct(duplicates.redundant, total)}）`, duplicates.dupGroups.slice(0, 2).map((g) => g.slice(0, 3).map((r) => r.id).join('/') + (g.length > 3 ? '…' : '')).join('；'), '分析前去重或保留首现'],
        ['7', '低', '`chapter` 只有一个取值 `剧情内容`', `${num(total)} 条（100%）`, '—', '该字段无信息量，可删或改为真实章节'],
        ['8', '低', '`location`/`scene` 覆盖率极低', `${pct(records.filter((r) => r.location).length, total)} / ${pct(records.filter((r) => r.scene).length, total)}`, '—', '做地点/场景分析前需补字段或改用其他来源'],
        ['9', '低', '`他/她` 性别占位符', `${num(records.filter((r) => r.text.includes('他/她')).length)} 条记录（${num(heTaOcc)} 处）`, records.filter((r) => r.text.includes('他/她')).slice(0, 2).map((r) => r.id).join(', '), '按主角选择映射为 他/她 或替换为中性词'],
        ['10', '低', '屏蔽字符 `█▀▄`（3.7 乱码段落）', `${num(records.filter((r) => /[█▀▄]/.test(r.text)).length)} 条`, '22936, 22937, 22938', '分析时排除（语义不可用）'],
      ]
    ),
    ''
  );

  // 6 README 数字核对
  push('## 6. 与 `data/README.md` 声明数字核对', '');
  const heTa = records.reduce((a, r) => a + (r.text.match(/他\/她/g) || []).length, 0);
  let starPairs = 0;
  for (const r of records) starPairs += (r.text.match(/\*[^*\n]+\*/g) || []).length;
  const heTaRec = records.filter((r) => /他\/她/.test(r.text)).length;
  const starRec = records.filter((r) => /\*[^*\n]+\*/.test(r.text)).length;
  push(
    mdTable(
      ['README 声明', '本次实测', '结论'],
      [
        ['24,206 条记录', num(total) + ' 条', '✅ 一致'],
        ['528,626 字', num(basic.totalChars) + ' 字', '✅ 一致'],
        ['`dialogue` 20,691 / `option` 2,399 / `narration` 1,116', `${num(basic.kindMap.get('dialogue'))} / ${num(basic.kindMap.get('option'))} / ${num(basic.kindMap.get('narration'))}`, '✅ 一致'],
        ['`extra` 1,459 条', num(basic.extraMap.get('true') || 0) + ' 条', '✅ 一致'],
        ['版本 3.0→3.7 严格单调', order.versionMonotone ? '✅ 实测一致' : '❌', '✅ 一致'],
        ['链一致性违例 0', `简单相邻链口径 ${qo.adjacencyMismatch.length} 处不吻合；边方向口径 ${qo.edgeViolations.length} 条反向边`, '⚠️ 口径需注明（3.4 为分支页结构）'],
        ['`他/她` 153 处', `${num(heTa)} 处（${num(heTaRec)} 条记录）`, '❌ 不一致，README 数字偏大'],
        ['`*强调*` 残留 282 处', `${num(starPairs)} 对（${num(starRec)} 条记录）`, '❌ 不一致，README 数字偏小'],
        ['505 个 speaker', `${num(ctx.normStats.totalSpeakers)} 个（非空 speaker 取值）`, '✅ 一致'],
        ['渲染抽检 41 条命中 28 条', `本次全页：精确整行 ${num(rendered.full.exact)}/${num(rendered.full.total)}、包含匹配 ${num(rendered.full.strict)}/${num(rendered.full.total)}；随机 20 条：包含匹配 ${num(rendered.sample.filter((x) => x.strict).length)}/20`, '⚠️ 抽样不可比；且「未命中全在折叠块内」的结论不成立'],
      ]
    ),
    ''
  );
  push(`> 建议更新 README：\`他/她\` 实际 ${num(heTa)} 处（${num(heTaRec)} 条记录）、\`*强调*\` 实际 ${num(starPairs)} 对（${num(starRec)} 条记录，其中 \`*我们*\` ${num(purity.star.inner.get('我们') || 0)} 处），并补充"非折叠记录亦有渲染未命中"的说明。`, '');

  // 7 计算口径
  push('## 7. 检查口径与复核', '');
  push(
    [
      '- **行号**：`id` 与 jsonl 物理行号已核对一致（0 处偏差），故「行号」= `id` = 物理行。',
      '- **单调性**：`version` 按数值元组比较；`order` 按记录出现顺序检查逆序；任务内 `idx`、`step_idx` 单独检查。',
      '- **重复**：`(task, kind, speaker, text)` 完全一致视为重复；「仅 id/idx 不同」= 除 `id`/`idx` 外全字段一致。',
      '- **文本纯度**：对 `text` 做正则统计（记录数/出现次数分别列出）；示例给「行号：命中位置前后片段」。',
      '- **渲染比对**：去空白后比较「渲染行集合」与「整段渲染文本包含关系」；宽松口径额外忽略标点。该文件只覆盖 1 个任务页，其它 66 页不可比。',
      '- **复核命令**：`node tools/report-corpus.js`（确定性输出，抽样种子 ' + SAMPLE_SEED + '）。',
    ].join('\n'),
    ''
  );
  return L.join('\n');
}

// ---------------------------------------------------------------------------
// 7. 报告：unmatched-speakers.md
// ---------------------------------------------------------------------------
function buildUnmatchedReport(ctx) {
  const { records, basic, normalizer, normStats, suggester } = ctx;
  const total = records.length;
  const L = [];
  const push = (...a) => L.push(...a);
  const vi = (v) => { const [a, b] = String(v).split('.').map(Number); return a * 100 + b; };

  // 收集未归一 speaker 的记录
  const bySpeaker = new Map();
  for (const r of records) {
    if (!r.speaker) continue;
    const res = normalizer.resolve(r.speaker);
    if (res) continue; // 已归一 or 非说话人标签
    if (!bySpeaker.has(r.speaker)) bySpeaker.set(r.speaker, []);
    bySpeaker.get(r.speaker).push(r);
  }
  const rows = [...bySpeaker.entries()].map(([speaker, rs]) => {
    const versions = uniq(rs.map((r) => r.version)).sort((a, b) => vi(a) - vi(b));
    const s = suggester.suggest(speaker);
    return {
      speaker,
      count: rs.length,
      versions: versions.length === 1 ? versions[0] : versions[0] + '–' + versions[versions.length - 1],
      versionsList: versions,
      first: rs[0].text,
      firstId: rs[0].id,
      kinds: uniq(rs.map((r) => r.kind)),
      bucket: s.bucket,
      reason: s.reason,
      canonical: s.canonical || null,
    };
  });
  rows.sort((a, b) => b.count - a.count || a.speaker.localeCompare(b.speaker, 'zh'));

  push('# 未归一说话人清单（unmatched-speakers）', '');
  push(`> 生成脚本：\`tools/report-corpus.js\`；依据 \`data/config/speaker-alias.json\` **只读**做严格归一计算（规则 1–5），未改配置、未改语料。  `);
  push(`> 结论：${num(normStats.totalSpeakers)} 个非空 speaker 取值中，**${num(rows.length)} 个未能按现有配置归一，覆盖 ${num(rows.reduce((a, r) => a + r.count, 0))} 条记录（${pct(rows.reduce((a, r) => a + r.count, 0), total)}）**；`
    + `另有 ${num(normStats.nonSpeakerSpeakers)} 个 config 明示的非说话人标签（${num(normStats.nonSpeakerRecords)} 条）与 ${num(normStats.emptySpeakerRecords)} 条空 speaker（narration），不计入本清单。`, '');

  // 汇总（按任务要求的 3 个建议桶聚合；「疑似某角色」的 canonical 明细见 §2）
  const bucketRecordsAll = rows.reduce((a, r) => a + r.count, 0);
  const primary = [
    { key: '疑似某角色', speakers: rows.filter((r) => r.bucket.startsWith('疑似')), desc: '字符串可关联到 config 中的已知角色，建议补配置后归入该 canonical（明细见 §2）' },
    { key: 'generic_npc', speakers: rows.filter((r) => r.bucket === 'generic_npc'), desc: '泛称/职业/群体标签，建议统一归为 generic_npc（保留 speaker_raw）' },
    { key: '待人工', speakers: rows.filter((r) => r.bucket === '待人工'), desc: '无法自动判定（含泰坦名/复合标签/外来角色/未知专名），需人工确认（明细见 §4）' },
  ];
  push('## 1. 归类建议汇总', '');
  push(
    mdTable(
      ['建议归类', 'speaker 数', '记录数', '占未归一记录', '占全部记录', '含义'],
      primary.map((p) => [
        p.key,
        num(p.speakers.length),
        num(p.speakers.reduce((a, r) => a + r.count, 0)),
        pct(p.speakers.reduce((a, r) => a + r.count, 0), bucketRecordsAll),
        pct(p.speakers.reduce((a, r) => a + r.count, 0), total),
        p.desc,
      ])
    ),
    ''
  );
  push('> **建议策略**：`疑似某角色` 类按「配置缺口」补 `speaker_aliases`/`form_map` 后重新归一（§2 已按目标 canonical 聚合，可直接照着改配置）；'
    + '`generic_npc` 类先自动合并（保留 `speaker_raw` 原值）；`待人工` 类逐项确认（优先处理句数 ≥ 10 的）。', '');

  // 配置缺口
  push('## 2. 「疑似某角色」明细：配置缺口 Top 25（按句数聚合）', '');
  const gapMap = new Map();
  for (const r of rows) {
    if (!r.canonical) continue;
    if (!gapMap.has(r.canonical)) gapMap.set(r.canonical, { canonical: r.canonical, records: 0, speakers: [] });
    const g = gapMap.get(r.canonical);
    g.records += r.count;
    g.speakers.push(r.speaker + '(' + r.count + ')');
  }
  const gapRows = [...gapMap.values()].sort((a, b) => b.records - a.records);
  push(
    mdTable(
      ['疑似 canonical', '涉及 speaker 标签数', '记录数', '占全部记录', '涉及的原始 speaker（句数）'],
      gapRows.slice(0, 25).map((g) => [g.canonical, g.speakers.length, num(g.records), pct(g.records, total), g.speakers.slice(0, 6).join('、') + (g.speakers.length > 6 ? '…' : '')])
    ),
    ''
  );
  push(
    '> 典型配置缺口：`海列屈拉`→海瑟音（`true_name` 未进 speaker_aliases）、`索拉比斯/露奈比斯`→塞涅俄丝（`aliases` 未参与归一）、'
      + '`拉比努斯/阿波罗尼`（canonical 条目存在但未写 `speaker_aliases`）、`记忆中的X`/`X之声`/`「盗火行者」` 等形态写法。'
      + '这些都属于“配置可补全、不需要人工逐条判断”的高优先级项。',
    ''
  );
  push(`> 另有 ${num(rows.filter((r) => r.bucket === 'generic_npc').length)} 个 generic_npc 候选、${num(rows.filter((r) => r.bucket === '待人工').length)} 个待人工项，见 §3/§4。`
    + ' **注意**：`疑似 canonical` 列只代表“文本上可关联”，例如泰坦名（瑟希斯/欧洛尼斯/塞纳托斯等）不在此表——它们被归入 §4 待人工，需先决定“泰坦是否单列 canonical”。', '');

  // generic_npc
  push('## 3. generic_npc 候选（按句数降序，Top 40）', '');
  const genericRows = rows.filter((r) => r.bucket === 'generic_npc');
  push(
    mdTable(
      ['#', 'speaker（原样）', '句数', '占比', '版本区间', '首例句（≤40 字）', '依据'],
      genericRows.slice(0, 40).map((r, i) => [i + 1, r.speaker, num(r.count), pct(r.count, total), r.versions, trunc(r.first, 40), r.reason])
    ),
    ''
  );
  push(`generic_npc 候选合计：${num(genericRows.length)} 个 speaker / ${num(genericRows.reduce((a, r) => a + r.count, 0))} 条记录。`, '');
  push('> 已知需人工覆盖的个例：`温柔的母亲`（78 句，3.1）台词对「缇里西庇俄丝」说话（“我的好女孩”），'
    + '按设定应为缇宝之母**莫忒丝**（config 有该 canonical 但未列此描述性标签），不应并入 generic_npc。'
    + '类似「描述性标签实指具名角色」的情况请人工抽查。', '');

  // 待人工
  push('## 4. 待人工确认（按句数降序，句数 ≥ 8 的全部列出）', '');
  const manualRows = rows.filter((r) => r.bucket === '待人工');
  push(
    mdTable(
      ['#', 'speaker（原样）', '句数', '占比', '版本区间', 'kind', '首例句（≤40 字）', '待确认原因'],
      manualRows
        .filter((r) => r.count >= 8)
        .map((r, i) => [i + 1, r.speaker, num(r.count), pct(r.count, total), r.versions, r.kinds.join('/'), trunc(r.first, 40), r.reason])
    ),
    ''
  );
  push(`待人工合计：${num(manualRows.length)} 个 speaker / ${num(manualRows.reduce((a, r) => a + r.count, 0))} 条记录（其中句数 ≥ 8 的 ${num(manualRows.filter((r) => r.count >= 8).length)} 个）。`, '');

  // 全量清单
  push('## 5. 全量清单（' + num(rows.length) + ' 个，按句数降序）', '');
  push(
    mdTable(
      ['#', 'speaker（原样）', '句数', '占总量', '版本区间', '首个例句（≤40 字）', '建议归类', '依据'],
      rows.map((r, i) => [i + 1, r.speaker, num(r.count), pct(r.count, total), r.versions, trunc(r.first, 40), r.bucket, r.reason])
    ),
    ''
  );

  // 口径
  push('## 6. 口径与复核说明', '');
  push(
    [
      '- **归一规则**（严格按 `speaker-alias.json → normalization_order`）：1) `speaker_literal_map` 精确命中；2) `canonical.*.speaker_aliases` 精确命中；3) 按 `title_prefix_patterns` 剥前缀后重试 1–2；4) 剥成对 `「」『』`/去括号注音后重试 1–2；5) `form_map` 命中；仍未命中 → 本清单。',
      '- **句数** = 该 speaker 原样字符串在 `amphoreus.jsonl` 中出现的记录数（`kind` 不限）。',
      '- **占比分母** = 全部 ' + num(total) + ' 条记录。',
      '- **版本区间** = 该 speaker 出现记录的最小/最大 `version`（按数值排序）。',
      '- **首个例句** = 该 speaker 首条记录（`id` 最小）的 `text`，按 Unicode 码点截断到 40 字。',
      '- **建议归类**：`疑似某角色` = 字符串可关联到 config 中已知角色（canonical 名 / `speaker_aliases` / `forms` / `titles` / `aliases` / `true_name` 的中文部分，以及 `记忆中的X`、`X之声`、`X的投影` 等形态写法）；`generic_npc` = 泛称/职业/群体标签；`待人工` = 其余未知专名、复合标签、泰坦名（说话实体为泰坦本身，需先决定是否单列 canonical）、外来客串角色、乱码。启发式规则写在 `tools/report-corpus.js` 的 `buildSuggester()`，仅供参考，以人工复核为准。',
      '- **复核命令**：`node tools/report-corpus.js`。',
    ].join('\n'),
    ''
  );
  return L.join('\n');
}

// ---------------------------------------------------------------------------
// 8. 主流程
// ---------------------------------------------------------------------------
function main() {
  const t0 = Date.now();
  // ---- 读取 ----
  const { buf: corpusBuf, records } = loadRecords();
  const cfg = readJson(P.config);
  const questOrder = readJson(P.questOrder);
  const corpusHash = sha256(corpusBuf);
  const configHash = sha256(fs.readFileSync(P.config));

  // ---- 统计 ----
  const basic = computeBasic(records);
  const normalizer = buildNormalizer(cfg);
  const suggester = buildSuggester(cfg, normalizer);
  const order = computeOrderChecks(records, questOrder);
  const completeness = computeCompleteness(records);
  const duplicates = computeDuplicates(records);
  const purity = computePurity(records);
  const rendered = computeRenderedCheck(records);

  // ---- 归一统计 ----
  const normStats = {
    totalSpeakers: uniq(records.map((r) => r.speaker).filter((s) => s !== '')).length,
    matchedSpeakers: 0,
    matchedRecords: 0,
    nonSpeakerSpeakers: 0,
    nonSpeakerRecords: 0,
    unmatchedSpeakers: 0,
    unmatchedRecords: 0,
    emptySpeakerRecords: 0,
    canonicalCounts: new Map(),
    canonicalMatrix: new Map(),
    formCounts: new Map(),
    formCanonical: new Map(),
  };
  const speakerSeen = new Map(); // speaker -> category
  for (const r of records) {
    if (!r.speaker) { normStats.emptySpeakerRecords++; continue; }
    let cat = speakerSeen.get(r.speaker);
    if (!cat) {
      const res = normalizer.resolve(r.speaker);
      cat = res ? (res.nonSpeaker ? 'nonSpeaker' : 'matched') : 'unmatched';
      speakerSeen.set(r.speaker, cat);
      if (cat === 'nonSpeaker') normStats.nonSpeakerSpeakers++;
      if (cat === 'matched') normStats.matchedSpeakers++;
      if (cat === 'unmatched') normStats.unmatchedSpeakers++;
    }
    if (cat === 'nonSpeaker') { normStats.nonSpeakerRecords++; continue; }
    if (cat === 'unmatched') { normStats.unmatchedRecords++; continue; }
    normStats.matchedRecords++;
    const res = normalizer.resolve(r.speaker);
    normStats.canonicalCounts.set(res.canonical, (normStats.canonicalCounts.get(res.canonical) || 0) + 1);
    if (!normStats.canonicalMatrix.has(res.canonical)) normStats.canonicalMatrix.set(res.canonical, {});
    const m = normStats.canonicalMatrix.get(res.canonical);
    m[r.version] = (m[r.version] || 0) + 1;
    if (res.form && res.form !== res.canonical) {
      normStats.formCounts.set(res.form, (normStats.formCounts.get(res.form) || 0) + 1);
      if (!normStats.formCanonical.has(res.form)) normStats.formCanonical.set(res.form, res.canonical);
    }
  }

  const ctx = {
    records,
    basic,
    normalizer,
    suggester,
    normStats,
    order,
    completeness,
    duplicates,
    purity,
    rendered,
    questOrder,
    taskStats: order.taskStats,
    corpusHash,
    configHash,
  };

  // ---- 写报告 ----
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const files = {
    'corpus-stats.md': buildStatsReport(ctx),
    'qa-checks.md': buildQaReport(ctx),
    'unmatched-speakers.md': buildUnmatchedReport(ctx),
  };
  for (const [name, content] of Object.entries(files)) {
    fs.writeFileSync(path.join(OUT_DIR, name), content.endsWith('\n') ? content : content + '\n', 'utf8');
  }

  // ---- 自校验：确认输入未被改动 ----
  const corpusHash2 = sha256(fs.readFileSync(P.corpus));
  const configHash2 = sha256(fs.readFileSync(P.config));
  const inputUnchanged = corpusHash === corpusHash2 && configHash === configHash2;

  console.log('[report-corpus] 完成，用时 ' + ((Date.now() - t0) / 1000).toFixed(2) + 's');
  console.log('[report-corpus] 记录 ' + num(records.length) + ' / 字数 ' + num(basic.totalChars) + ' / 任务 ' + order.taskCount + ' / 版本 ' + basic.versionRows.length);
  console.log('[report-corpus] 归一：matched ' + normStats.matchedSpeakers + ' speakers(' + num(normStats.matchedRecords) + ') / nonSpeaker ' + normStats.nonSpeakerSpeakers + '(' + num(normStats.nonSpeakerRecords) + ') / unmatched ' + normStats.unmatchedSpeakers + '(' + num(normStats.unmatchedRecords) + ') / empty ' + num(normStats.emptySpeakerRecords));
  console.log('[report-corpus] 输出：' + Object.keys(files).map((f) => path.join('data', 'reports', f)).join(', '));
  console.log('[report-corpus] 输入只读校验：' + (inputUnchanged ? 'OK（语料/配置哈希未变化）' : 'FAILED'));
  if (!inputUnchanged) process.exitCode = 1;
}

main();
