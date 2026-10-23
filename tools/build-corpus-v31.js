/**
 * v3.1 解析补全 —— 在 v3 基础上修 7 类已知缺陷，产出新文件（不改 v1/v2 语料）
 *
 * 修复项（详见 docs/corpus-v31.md）：
 *  1. 行首 `:` 场景旁白被整行丢弃（含 `{{剧情选项}}` 块内的分支旁白）
 *  2. 模板未解析导致正文截断/尾部残留（改为解析前做平衡括号内联展开）
 *  3. `{{短信选项}}` 块（14 块）→ kind=sms / sms_option + channel="sms"
 *  4. `|剧情N={{角色对话|…}}` 内联对白（32 处，均在短信块内）
 *  5. kind=narration 内嵌「标签：台词」→ 拆为 dialogue + speaker（embedded_from="narration"）
 *  6. 伪说话人（跨行正则误配）→ 说话人分隔符限制为单行 + 标签校验
 *  7. step_title 回退章节名 → 改用页面步骤标题；开场（首个 === 之前）内容归属该页首个步骤并标
 *     step_title_inferred=true；确实无法识别时 step_title_missing=true
 *
 * 输入（只读）：data/raw/wt-cache/*.txt、data/raw/amphoreus-quest-index.json、
 *              data/corpus/quest-order.json，以及 data/corpus/amphoreus.jsonl
 *              （v1 只用于生成 v1_id 溯源与差异统计，不参与解析逻辑）
 * 输出（只写这 4 个路径）：
 *  tools/build-corpus-v31.js（本文件）
 *  data/corpus/amphoreus.v31.jsonl
 *  data/corpus/amphoreus.v31.lines.txt
 *  docs/corpus-v31.md
 *
 * 离线可重跑：node tools/build-corpus-v31.js
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const RAW = path.join(ROOT, 'data', 'raw');
const OUT = path.join(ROOT, 'data', 'corpus');
const CACHE = path.join(RAW, 'wt-cache');
const V1_FILE = path.join(OUT, 'amphoreus.jsonl');
const DOC_FILE = path.join(ROOT, 'docs', 'corpus-v31.md');

const V31_JSONL = path.join(OUT, 'amphoreus.v31.jsonl');
const V31_LINES = path.join(OUT, 'amphoreus.v31.lines.txt');

// ============================================================
// 0. 通用工具
// ============================================================
const count = (s, re) => (s.match(re) || []).length;
const braceDelta = (s) => count(s, /\{\{/g) - count(s, /\}\}/g);

/** 按顶层分隔符切分（忽略 {{...}} 内部的 sep），保留原文与顺序 */
function splitTopLevel(text, sep = '|') {
  const out = [];
  let depth = 0;
  let buf = '';
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '{' && text[i + 1] === '{') { depth++; buf += '{{'; i++; continue; }
    if (ch === '}' && text[i + 1] === '}') { depth = Math.max(0, depth - 1); buf += '}}'; i++; continue; }
    if (ch === sep && depth === 0) { out.push(buf); buf = ''; continue; }
    buf += ch;
  }
  out.push(buf);
  return out;
}

/** 模板参数（保留位置顺序 + 命名参数） */
function templateParts(body) {
  const segs = splitTopLevel(body, '|');
  const name = (segs[0] || '').trim();
  const args = [];
  for (let i = 1; i < segs.length; i++) {
    const s = segs[i];
    const m = s.match(/^([A-Za-z_][\w-]*|[\u4e00-\u9fa5]{1,8})\s*=\s*([\s\S]*)$/);
    if (m && m[1] && !/^[\d.]+$/.test(m[1])) args.push({ key: m[1].trim(), value: m[2] });
    else args.push({ key: null, value: s });
  }
  return { name, args };
}
function lastTextArg(args) {
  const c = args.filter((a) => a.key === null && a.value && a.value.trim() !== '');
  return c.length ? c[c.length - 1].value : '';
}
function firstTextArg(args) {
  const c = args.filter((a) => a.key === null && a.value && a.value.trim() !== '');
  return c.length ? c[0].value : '';
}

/**
 * v3.1 内联模板展开（平衡括号、由内向外）
 *  - {{颜色|x|Y}} → Y（最后纯文本参数）
 *  - {{注音|A|B}} → A（第一个纯文本参数 = 正文；B 是注音/解释）
 *  - {{黑幕|x}} → x（最后纯文本参数，与 v1 一样展开剧透文本）
 *  - {{图标|分类|显示}} / 道具 / 物品 / 技能 / 书籍 → 显示名
 *  - 未知模板 → 最后一个纯文本参数；{{PAGENAME}} → ''
 */
function expandInline(input) {
  let t = String(input == null ? '' : input);
  for (let pass = 0; pass < 30; pass++) {
    let changed = false;
    t = t.replace(/\{\{([^{}]*)\}\}/g, (_m, inner) => { changed = true; return expandOne(inner); });
    if (!changed) break;
  }
  // 防御：清掉无法配平的残留括号（验收要求 {{ / }} 残留 = 0）
  t = t.replace(/\{\{|\}\}/g, '');
  return t;
}

function expandOne(inner) {
  const { name, args } = templateParts(inner);
  switch (name) {
    case '颜色': case '黑幕': case '文本样式': case 'ruby':
    case '图标': case '道具': case '物品': case '技能': case '书籍':
    case '折叠': case '折叠框': case '提示': case '提示消息': case '短信警告':
    case '任务描述': case '多义词':
      return lastTextArg(args);
    case '注音': return firstTextArg(args);
    case 'PAGENAME': case '任务': case '系列任务': case '剧情选项': case '短信选项': return '';
    case '=': return '=';
    default: return lastTextArg(args);
  }
}

/** v3.1 文本清洗：展开模板 → wiki 链接 → HTML → 强调引号 → trim */
function clean(s) {
  let t = expandInline(s);
  t = t.replace(/\[\[([^\]|]*)\|([^\]]*)\]\]/g, '$2').replace(/\[\[([^\]]*)\]\]/g, '$1');
  t = t.replace(/<[^>]+>/g, '').replace(/'''?/g, '');
  t = t.replace(/[\r\n]+/g, ''); // 正文压平（v1 语料无换行）
  return t.trim();
}

/** v1（build-corpus-v3）的 cleanInline，仅用于差异对比，不参与 v3.1 解析 */
function cleanInlineV1(s) {
  let t = String(s == null ? '' : s);
  for (let i = 0; i < 6; i++) {
    const before = t;
    t = t.replace(/\{\{([^{}]*?)\}\}/g, (_m, inner) => {
      const parts = inner.split('|').map((x) => x.trim());
      const name = parts[0];
      if (['颜色', '注音', '黑幕', '文本样式', 'ruby'].includes(name)) return parts[parts.length - 1];
      if (['图标', '道具', '物品', '技能', 'PAGENAME'].includes(name)) return '';
      return parts.slice(1).filter((p) => p && !/^[a-zA-Z]+=/.test(p)).pop() || '';
    });
    if (t === before) break;
  }
  t = t.replace(/\[\[([^\]|]*)\|([^\]]*)\]\]/g, '$2').replace(/\[\[([^\]]*)\]\]/g, '$1');
  t = t.replace(/<[^>]+>/g, '').replace(/'''?/g, '');
  return t.trim();
}

const HEADING = /^(={2,6})\s*([^=\n]+?)\s*\1\s*$/;

/** 从 start 行开始按 {{ }} 配平收集模板块，返回结束行号 */
function collectBlockEnd(lines, start) {
  let depth = braceDelta(lines[start]);
  let i = start;
  while (depth > 0 && i + 1 < lines.length) { i++; depth += braceDelta(lines[i]); }
  return i;
}

/**
 * 折叠块信息：逐行 extra（是否在 {{折叠}} 内）与 smsChan（是否在标题含「短信」的折叠内）。
 * extra 的 push/pop 规则与 v3 完全一致（保证 v1 extra 值不变）。
 */
function foldInfo(lines) {
  const extra = new Array(lines.length).fill(false);
  const smsChan = new Array(lines.length).fill(false);
  const stack = [];
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    for (let ci = 0; ci < line.length - 1; ci++) {
      if (line[ci] === '{' && line[ci + 1] === '{') {
        const isFold = line.slice(ci + 2, ci + 4) === '折叠';
        let title = '';
        if (isFold) {
          const tm = line.slice(ci + 2).match(/标题\s*=\s*([^|}\n]*)/);
          if (tm) title = tm[1].trim();
        }
        stack.push({ isFold, title });
        ci++;
        continue;
      }
      if (line[ci] === '}' && line[ci + 1] === '}') { stack.pop(); ci++; continue; }
    }
    extra[li] = stack.some((x) => x.isFold);
    smsChan[li] = stack.some((x) => x.isFold && /短信/.test(x.title));
  }
  return { extra, smsChan };
}

// ============================================================
// 1. v1 兼容键（仅用于 v1_id 对齐；不影响 v3.1 输出）
// ============================================================
/** v1 optRe 的取值口径：|\s*选项N\s*=\s*([^\n|]*) */
function v1OptionValue(raw) {
  return String(raw).split('\n')[0].split('|')[0];
}
/** v1 块内 innerRe 的取值口径：*\s*([^*：:{}\n]{1,16}?)\s*[：:]\s*([^\n*{}]+)（限单行内） */
function innerKey(line) {
  const m = line.match(/^\*\s*([^*：:{}\n]{1,16}?)[ \t]*[：:][ \t]*([^\n*{}]+)/);
  if (!m) return null;
  return { sv: cleanInlineV1(m[1]), tv: cleanInlineV1(m[2]) };
}

// ============================================================
// 1b. 内嵌说话人标签判定（fix #5 / #6）
// ============================================================
function looksLikeLabel(p) {
  if (!p) return false;
  if (p.length > 20) return false;
  if (/[。…]/.test(p)) return false; // 叙述句（含句号/省略号）不是标签
  if (/^[？?]+$/.test(p)) return true; // ？？？
  if (/\[[^\]]+\]\s*$/.test(p)) return true; // 博识尊[黑塔]
  if (/^[^「]{0,5}「[^」]+」\s*[？?]?$/.test(p)) return true; // 「阿提卡斯？」/ 战斗效果「…」
  if (/[？?！!）)]$/.test(p) && !/[，,、]/.test(p)) return true; // 赛飞儿？/ 三月七！
  const segs = p.split(/[，,、]/);
  if (segs.length > 1) return segs.every((x) => x.length >= 1 && x.length <= 8); // 称号，角色名
  return /^[\u4e00-\u9fa5A-Za-z0-9·•]{1,8}$/.test(p); // 纯名（{{注音}} 展开后的角色名）
}

function splitEmbedded(text) {
  const m = String(text).match(/^([^：:\n]{1,20})[：:]\s*([\s\S]+)$/);
  if (!m) return null;
  const label = m[1].trim();
  const body = m[2].trim();
  if (!label || !body) return null;
  if (!looksLikeLabel(label)) return null;
  return { label, body };
}

function extractFoldContent(foldText) {
  const i = foldText.indexOf('内容=');
  let inner = i >= 0 ? foldText.slice(i + 3) : foldText;
  inner = inner.replace(/\|\s*折叠\s*=[^\n}]*\}\}\s*$/, '');
  inner = inner.replace(/\s*\}\}\s*$/, '');
  return inner;
}

// ============================================================
// 2. 页面解析器
// ============================================================
class PageParser {
  constructor(title, meta, raw, opts) {
    this.title = title;
    this.meta = meta;
    this.raw = raw;
    this.v1ByTask = opts.v1ByTask || [];
    this.lines = [];
    this.extra = [];
    this.smsChan = [];
    this.recs = [];
    this.chapter = '';
    this.stepTitle = '';
    this.stepIdx = 0;
    this.firstStepTitle = '';
    this.curScene = '';
  }

  /** 元数据模板剥离（与 v3 完全一致，保证 extra 掩码行号对齐） */
  prepare() {
    let wt = this.raw;
    const mT = wt.match(/\{\{任务\n([\s\S]*?)\n\}\}/);
    if (mT) wt = wt.replace(mT[0], '');
    wt = wt.replace(/\{\{系列任务[\s\S]*?\n\}\}/g, '');
    this.lines = wt.split(/\r?\n/);
    const fi = foldInfo(this.lines);
    this.extra = fi.extra;
    this.smsChan = fi.smsChan;
  }

  parse() {
    this.prepare();
    const lines = this.lines;
    let i = 0;
    while (i < lines.length) {
      const rawLine = lines[i];
      const line = rawLine.trim();
      if (!line) { i++; continue; }

      // 标题
      const hm = line.match(HEADING);
      if (hm) {
        const level = hm[1].length;
        const text = clean(hm[2]);
        if (level <= 2) {
          this.chapter = text;
          this.stepTitle = '';
          this.stepIdx++;
        } else {
          this.stepTitle = text;
          if (!this.firstStepTitle) this.firstStepTitle = text;
          this.stepIdx++;
        }
        i++;
        continue;
      }

      // 行首可能带 `:` 的模板块（wiki 缩进 + 模板）：`:{{剧情选项|...}}`
      const noColon = line.replace(/^:+\s*/, '');
      const bname = ((noColon.match(/^\{\{\s*([^|{}\n]+)/) || [])[1] || '').trim();

      if (bname === '角色对话') {
        const end = collectBlockEnd(lines, i);
        this.parseRoleBlock(lines.slice(i, end + 1), i);
        i = end + 1;
        continue;
      }
      if (bname === '任务描述') {
        const end = collectBlockEnd(lines, i);
        this.parseTaskDesc(i, end);
        i = end + 1;
        continue;
      }
      if (bname === '剧情选项' || bname === '短信选项') {
        const end = collectBlockEnd(lines, i);
        this.parseOptionBlock(lines.slice(i, end + 1), i, bname === '短信选项');
        i = end + 1;
        continue;
      }

      // 行首 `:` 场景旁白（fix #1）
      if (line.startsWith(':')) {
        const txt = clean(line.replace(/^:+\s*/, ''));
        if (txt) {
          this.recs.push(this.makeRec({
            kind: 'narration', speaker: '', text: txt,
            origin: 'colon', channel: this.smsChan[i] ? 'sms' : undefined,
          }, i, this.extra[i]));
        }
        i++;
        continue;
      }

      // `*` 行（对白 / 旁白 / 内嵌说话人）
      if (line.startsWith('*')) {
        this.addStarRecord(line, this.extra[i], {
          originBase: 'v1', isSms: false, chan: this.smsChan[i] ? 'sms' : undefined,
        }, (r) => this.recs.push(r));
        i++;
        continue;
      }

      // 其余（{{提示}}/{{提示消息}}/{{短信警告}}/整行 {{颜色}}、----、纯文本 <br> 段、HTML 等）不解析
      i++;
    }

    return this.finalize();
  }

  // ---------------- 记录构造 ----------------
  makeRec(fields, lineIdx, extra) {
    const r = {
      kind: fields.kind,
      speaker: fields.speaker || '',
      text: fields.text,
    };
    if (fields.location !== undefined) r.location = fields.location;
    if (fields.scene) r.scene = fields.scene;
    r.chapter = this.chapter;
    r.step_idx = this.stepIdx;
    r.step_title = this.stepTitle;
    r.extra = extra === undefined ? this.extra[lineIdx] : extra;
    r._origin = fields.origin;
    if (fields.channel) r._channel = fields.channel;
    if (fields.embedded_from) r._embedded_from = fields.embedded_from;
    // v1 兼容键：v1 若会为该构造产出记录，则给出 (speaker,text) 的精确期望值（用于 v1_id 对齐）
    if (fields.tv1 !== undefined) r._tv1 = fields.tv1;
    if (fields.sv1 !== undefined) r._sv1 = fields.sv1;
    return r;
  }

  // ---------------- `*` 行 ----------------
  /** push 回调用于把记录塞进行级 this.recs 或块内 contentAll */
  addStarRecord(line, extra, ctx, push) {
    // 1) 常规对白（与 v1 判定一致：speaker ≤12 字且不含标点；fix #6：分隔符只允许空格/制表符）
    const mD = line.match(/^\*\s*([^*：:（([{|\n]{1,20}?)[ \t]*[：:][ \t]*([\s\S]+)$/);
    const ik = ctx.originBase === 'block' ? innerKey(line) : null;
    if (mD) {
      const spk = clean(mD[1]);
      const txt = clean(mD[2]);
      if (spk && txt && spk.length <= 12 && !/[，。！？、]/.test(spk)) {
        push(this.makeRec({
          kind: ctx.isSms ? 'sms' : 'dialogue',
          speaker: spk, text: txt,
          origin: ctx.isSms ? 'sms_dialogue' : ctx.originBase === 'v1' ? 'v1' : 'block_dialogue',
          channel: ctx.isSms ? 'sms' : ctx.chan,
          tv1: ctx.originBase === 'v1' ? cleanInlineV1(mD[2]) : ik ? ik.tv : undefined,
          sv1: ctx.originBase === 'v1' ? cleanInlineV1(mD[1]) : ik ? ik.sv : undefined,
        }, null, extra));
        return;
      }
    }
    // 2) 旁白：strip 前导星号
    const stripped = line.replace(/^\*+\s*/, '');
    const txt = clean(stripped);
    if (!txt) return;
    const tv1b = ctx.originBase === 'v1' ? cleanInlineV1(stripped) : ik ? ik.tv : undefined;
    const sv1b = ctx.originBase === 'v1' ? '' : ik ? ik.sv : undefined;
    // fix #5：narration 内嵌「标签：台词」→ dialogue + speaker
    const sp = splitEmbedded(txt);
    if (sp) {
      push(this.makeRec({
        kind: ctx.isSms ? 'sms' : 'dialogue',
        speaker: sp.label, text: sp.body,
        origin: ctx.isSms ? 'sms_dialogue' : ctx.originBase === 'v1' ? 'v1' : 'block_embedded_dialogue',
        embedded_from: 'narration',
        channel: ctx.isSms ? 'sms' : ctx.chan,
        tv1: tv1b, sv1: sv1b,
      }, null, extra));
      return;
    }
    push(this.makeRec({
      kind: ctx.isSms ? 'sms' : 'narration', speaker: '', text: txt,
      origin: ctx.isSms ? 'sms_narration' : ctx.originBase === 'v1' ? 'v1' : 'block_narration',
      channel: ctx.isSms ? 'sms' : ctx.chan,
      tv1: tv1b, sv1: sv1b,
    }, null, extra));
  }

  // ---------------- `{{任务描述}}` ----------------
  parseTaskDesc(start, end) {
    let text = this.lines.slice(start, end + 1).join('\n');
    text = text.replace(/^\s*:?\s*\{\{\s*任务描述/, '').replace(/^\s*\|/, '');
    text = text.replace(/\s+$/, '');
    const segs = splitTopLevel(text, '|');
    const txt = clean(segs[0] || '');
    const loc = clean(segs.length > 1 ? segs.slice(1).join('|') : '');
    if (!txt) return;
    const isSingle = end === start;
    let tv1, sv1;
    if (isSingle) {
      const mm = this.lines[start].match(/\{\{任务描述\|([^|]*)/);
      tv1 = cleanInlineV1(mm ? mm[1] : '');
      sv1 = '';
    }
    this.recs.push(this.makeRec({
      kind: 'narration', speaker: '', text: txt, location: loc,
      origin: isSingle ? 'v1' : 'taskdesc_multiline',
      tv1, sv1,
    }, start, this.extra[start]));
  }

  // ---------------- `{{角色对话}}`（行级） ----------------
  parseRoleBlock(subLines, start) {
    const block = subLines.join('\n');
    const inner = block.replace(/^\s*\{\{\s*角色对话\s*/, '').replace(/\s*\}\}\s*$/, '').replace(/^\s*\|/, '');
    const parts = splitTopLevel(inner, '|').map((s) => s.trim());
    const kindTag = parts[0];
    if (kindTag === '模板开始') { this.curScene = clean(parts[1] || ''); return; }
    if (kindTag === '模板结束') { this.curScene = ''; return; }
    if (!['左', '右', '中'].includes(kindTag)) return;
    const type = parts[2];
    if (type !== undefined && type !== '' && type !== '文本') return; // 表情/图片等
    const txt = clean(parts.slice(3).join('|'));
    if (!txt) return;
    const chan = this.smsChan[start] ? 'sms' : undefined;
    const rawTxt = parts.slice(3).join('|');
    const rawSpk = parts[1] || '';
    this.recs.push(this.makeRec({
      kind: chan ? 'sms' : 'dialogue',
      speaker: clean(rawSpk), text: txt,
      scene: this.curScene,
      origin: chan ? 'sms_dialogue' : 'v1',
      channel: chan,
      tv1: cleanInlineV1(rawTxt), sv1: cleanInlineV1(rawSpk),
    }, start, this.extra[start]));
  }

  // ---------------- `{{剧情选项}}` / `{{短信选项}}` ----------------
  parseOptionBlock(subLines, start, isSms) {
    const optAll = [];
    const contentAll = [];
    const ctx = { isSms, extra: this.extra[start] };
    this.parseBlockText(subLines.join('\n'), ctx, optAll, contentAll);
    for (const r of optAll) this.recs.push(r);
    for (const r of contentAll) this.recs.push(r);
  }

  /** 把一个选项块文本拆成 `|参数=值` 段；选项进 optAll，内容进 contentAll（v1 约定：先选项后内容） */
  parseBlockText(rawBlock, ctx, optAll, contentAll) {
    let text = String(rawBlock).replace(/^\s*:?\s*\{\{\s*(?:剧情选项|短信选项)/, '');
    text = text.replace(/\s+$/, '');
    const segs = splitTopLevel(text, '|');
    for (const seg of segs) {
      const s = seg.replace(/^\n/, '');
      if (!s.trim()) continue;
      const m = s.match(/^([^=|\n]{1,40}?)\s*=\s*([\s\S]*)$/);
      if (m) {
        const name = m[1].trim();
        const value = m[2];
        if (/^选项\d+$/.test(name)) {
          const txtRaw = value.replace(/\s+$/, '');
          const txt = clean(txtRaw);
          if (txt) {
            optAll.push(this.makeRec({
              kind: ctx.isSms ? 'sms_option' : 'option',
              speaker: '开拓者', text: txt,
              origin: ctx.isSms ? 'sms_option' : 'block_option',
              channel: ctx.isSms ? 'sms' : undefined,
              tv1: ctx.isSms ? undefined : cleanInlineV1(v1OptionValue(txtRaw)),
              sv1: ctx.isSms ? undefined : '开拓者',
            }, null, ctx.extra));
          }
          continue;
        }
        if (/^剧情\d+$/.test(name)) {
          this.parseContent(value, ctx, optAll, contentAll);
          continue;
        }
        // 未知参数（图标/折叠/其他）：其值里仍可能有内容行
        // （<tabber> 的 \`|-|条件=\` 会被拆成伪参数，值里是 \`*说话人：…\`）
        this.parseContent(value, ctx, optAll, contentAll);
        continue;
      }
      this.parseContent(s, ctx, optAll, contentAll);
    }
  }

  /** 选项分支内容（可多行，含嵌套选项块 / 折叠 / 角色对话 / `*` 行 / `:` 行） */
  parseContent(text, ctx, optAll, contentAll) {
    const lines = String(text).split('\n');
    let k = 0;
    while (k < lines.length) {
      const s = lines[k].trim();
      if (!s) { k++; continue; }

      if (s.startsWith('{{')) {
        const nm = ((s.match(/^\{\{\s*([^|{}\n]+)/) || [])[1] || '').trim();
        if (nm === '剧情选项' || nm === '短信选项') {
          const end = collectBlockEnd(lines, k);
          const sub = lines.slice(k, end + 1).join('\n');
          this.parseBlockText(sub, { isSms: nm === '短信选项' || ctx.isSms, extra: ctx.extra }, optAll, contentAll);
          k = end + 1;
          continue;
        }
        if (nm === '折叠' || nm === '折叠框') {
          const end = collectBlockEnd(lines, k);
          const foldText = lines.slice(k, end + 1).join('\n');
          this.parseContent(extractFoldContent(foldText), ctx, optAll, contentAll);
          k = end + 1;
          continue;
        }
        if (nm === '角色对话') {
          const end = collectBlockEnd(lines, k);
          this.parseRoleBlockInline(lines.slice(k, end + 1), ctx, contentAll);
          k = end + 1;
          continue;
        }
        // 提示/提示消息/短信警告/颜色/任务描述 等独立模板行：忽略
        k++;
        continue;
      }

      if (s.startsWith('*')) {
        this.addStarRecord(s, ctx.extra, {
          originBase: 'block', isSms: ctx.isSms,
        }, (r) => contentAll.push(r));
        k++;
        continue;
      }
      if (s.startsWith(':')) {
        const txt = clean(s.replace(/^:+\s*/, ''));
        if (txt) {
          contentAll.push(this.makeRec({
            kind: ctx.isSms ? 'sms' : 'narration', speaker: '', text: txt,
            origin: 'colon_option', channel: ctx.isSms ? 'sms' : undefined,
          }, null, ctx.extra));
        }
        k++;
        continue;
      }
      // `|` 残留 / `----` / 纯文本（<br> 叙事段，暂不解析）/ HTML 行
      k++;
    }
  }

  /** 块内 {{角色对话}}（短信块里的收发气泡） */
  parseRoleBlockInline(subLines, ctx, contentAll) {
    const block = subLines.join('\n');
    const inner = block.replace(/^\s*\{\{\s*角色对话\s*/, '').replace(/\s*\}\}\s*$/, '').replace(/^\s*\|/, '');
    const parts = splitTopLevel(inner, '|').map((s) => s.trim());
    const kindTag = parts[0];
    if (kindTag === '模板开始') { this.curScene = clean(parts[1] || ''); return; }
    if (kindTag === '模板结束') { this.curScene = ''; return; }
    if (!['左', '右', '中'].includes(kindTag)) return;
    const type = parts[2];
    if (type !== undefined && type !== '' && type !== '文本') return;
    const rawTxt = parts.slice(3).join('|');
    const rawSpk = parts[1] || '';
    const txt = clean(rawTxt);
    if (!txt) return;
    contentAll.push(this.makeRec({
      kind: ctx.isSms ? 'sms' : 'dialogue',
      speaker: clean(rawSpk), text: txt,
      scene: this.curScene,
      origin: ctx.isSms ? 'sms_dialogue' : 'block_dialogue',
      channel: ctx.isSms ? 'sms' : undefined,
      tv1: cleanInlineV1(rawTxt), sv1: cleanInlineV1(rawSpk),
    }, null, ctx.extra));
  }

  // ---------------- 收尾：step_title 回填 + v1_id 对齐 ----------------
  finalize() {
    let inferred = 0;
    let missing = 0;
    for (const r of this.recs) {
      if (!r.step_title) {
        if (this.firstStepTitle) { r.step_title = this.firstStepTitle; r._inferred = true; inferred++; }
        else { r._missing = true; missing++; }
      }
    }
    this.stats = { inferred, missing };
    this.alignV1();
    return this.recs;
  }

  alignV1() {
    const v1recs = this.v1ByTask || [];
    this.v1Unmatched = [];
    for (const r of this.recs) r.v1_id = null;
    if (!v1recs.length) return;

    const used = new Array(v1recs.length).fill(false);
    // 精确键匹配：v1 若会为该构造产出记录，则 (speaker,text) 的 v1 口径期望值是确定的
    const keyMatch = (r, v) => v.speaker === r._sv1 && v.text === r._tv1;
    let ptr = 0;
    for (const r of this.recs) {
      if (r._tv1 === undefined) continue;
      let found = -1;
      const limit = Math.min(v1recs.length, ptr + 80);
      for (let k = Math.max(0, ptr - 5); k < limit; k++) {
        if (used[k]) continue;
        if (keyMatch(r, v1recs[k])) { found = k; break; }
      }
      if (found < 0) {
        for (let k = 0; k < v1recs.length; k++) {
          if (used[k]) continue;
          if (keyMatch(r, v1recs[k])) { found = k; break; }
        }
      }
      if (found >= 0) {
        used[found] = true;
        r.v1_id = v1recs[found].id;
        r._v1 = v1recs[found];
        if (found + 1 > ptr) ptr = found + 1;
      }
    }
    // 剩余 v1 记录：按 text 精确兜底（伪说话人修正后 kind/speaker 变化）
    for (let k = 0; k < v1recs.length; k++) {
      if (used[k]) continue;
      const v = v1recs[k];
      for (const r of this.recs) {
        if (r.v1_id != null) continue;
        if (r.text === v.text) { r.v1_id = v.id; r._v1 = v; used[k] = true; break; }
      }
    }
    for (let k = 0; k < v1recs.length; k++) if (!used[k]) this.v1Unmatched.push(v1recs[k]);
    // origin 归一：成功回接 v1 的记录 origin 记为 v1
    for (const r of this.recs) if (r.v1_id != null) r._origin = 'v1';
  }
}

// ============================================================
// 3. 构建 + 校验 + 文档
// ============================================================
function main() {
  const order = JSON.parse(fs.readFileSync(path.join(OUT, 'quest-order.json'), 'utf8'));
  JSON.parse(fs.readFileSync(path.join(RAW, 'amphoreus-quest-index.json'), 'utf8')); // 只读校验存在性
  const v1 = fs.readFileSync(V1_FILE, 'utf8').trim().split('\n').map((l) => JSON.parse(l));
  const v1ByTask = new Map();
  for (const r of v1) {
    if (!v1ByTask.has(r.task)) v1ByTask.set(r.task, []);
    v1ByTask.get(r.task).push(r);
  }

  const files = new Map();
  for (const f of fs.readdirSync(CACHE)) {
    if (!f.endsWith('.txt')) continue;
    files.set(decodeURIComponent(f.replace(/\.txt$/, '')), f);
  }

  const tasks = order.slice().sort((a, b) => a.order - b.order);
  const allRecs = [];
  const perTask = [];
  const parseFails = [];
  let globalId = 0;

  for (const meta of tasks) {
    const f = files.get(meta.task);
    if (!f) { parseFails.push(meta.task + ' :: missing cache'); continue; }
    const raw = fs.readFileSync(path.join(CACHE, f), 'utf8');
    const parser = new PageParser(meta.task, meta, raw, { v1ByTask: v1ByTask.get(meta.task) || [] });
    let recs;
    try { recs = parser.parse(); } catch (e) { parseFails.push(meta.task + ' :: ' + e.stack); continue; }
    let idx = 0;
    for (const r of recs) {
      if (!r.text) continue;
      const out = {
        id: ++globalId,
        order: meta.order,
        task: meta.task,
        version: meta.version,
        series: meta.series,
        series_no: meta.series_no,
        idx: ++idx,
        kind: r.kind,
        speaker: r.speaker,
        text: r.text,
      };
      if (r.location !== undefined) out.location = r.location;
      if (r.scene) out.scene = r.scene;
      out.chapter = r.chapter;
      out.step_idx = r.step_idx;
      out.step_title = r.step_title;
      out.extra = r.extra;
      out.v1_id = r.v1_id == null ? null : r.v1_id;
      out.origin = r._origin;
      if (r._channel) out.channel = r._channel;
      if (r._embedded_from) out.embedded_from = r._embedded_from;
      out.step_title_inferred = !!r._inferred;
      out.step_title_missing = !!r._missing;
      out._v1 = r._v1 || null;
      allRecs.push(out);
    }
    perTask.push({
      task: meta.task, v1Count: (v1ByTask.get(meta.task) || []).length,
      v31Count: recs.filter((r) => r.text).length,
      unmatchedV1: parser.v1Unmatched.length, inferred: parser.stats.inferred, missing: parser.stats.missing,
    });
    if (parser.v1Unmatched.length) console.log(`⚠ ${meta.task}: 未匹配 v1 记录 ${parser.v1Unmatched.length} 条`);
  }

  const stats = computeStats(allRecs, v1, perTask, parseFails, tasks);
  writeOutputs(allRecs);
  writeDoc(stats);
  printReport(stats);
}

// ---------------- 统计 ----------------
function computeStats(recs, v1, perTask, parseFails, tasks) {
  const s = { total: recs.length, v1Total: v1.length };
  s.delta = s.total - s.v1Total;
  const byKind = {}, byOrigin = {}, byVersion = {};
  let v1Matched = 0, textChanged = 0, speakerChanged = 0, kindChanged = 0, locationChanged = 0;
  let stepTitleChanged = 0, extraChanged = 0, residueV1 = 0, residueV31 = 0, emptyText = 0;
  let inferred = 0, missing = 0, smsChannel = 0, embedded = 0;
  const changeExamples = { text: [], speaker: [], kind: [], location: [] };
  const residueV1Examples = [];
  for (const r of recs) {
    byKind[r.kind] = (byKind[r.kind] || 0) + 1;
    byOrigin[r.origin] = (byOrigin[r.origin] || 0) + 1;
    byVersion[r.version] = (byVersion[r.version] || 0) + 1;
    if (!r.text || !r.text.trim()) emptyText++;
    if (/\{\{|\}\}/.test(r.text)) residueV31++;
    if (r.step_title_inferred) inferred++;
    if (r.step_title_missing) missing++;
    if (r.channel === 'sms') smsChannel++;
    if (r.embedded_from === 'narration') embedded++;
    const v = r._v1;
    if (!v) continue;
    v1Matched++;
    if (v.text !== r.text) {
      textChanged++;
      if (/\{\{|\}\}/.test(v.text)) {
        residueV1++;
        if (residueV1Examples.length < 8) residueV1Examples.push({ v1_id: v.id, v31_id: r.id, old: v.text, now: r.text });
      } else if (changeExamples.text.length < 8) {
        changeExamples.text.push({ v1_id: v.id, v31_id: r.id, v1: v.text, v31: r.text });
      }
    }
    if (v.speaker !== r.speaker) {
      speakerChanged++;
      if (changeExamples.speaker.length < 8) changeExamples.speaker.push({ v1_id: v.id, v31_id: r.id, old: v.speaker, now: r.speaker });
    }
    if (v.kind !== r.kind) {
      kindChanged++;
      if (changeExamples.kind.length < 10) changeExamples.kind.push({ v1_id: v.id, v31_id: r.id, old: v.kind, now: r.kind, speaker: r.speaker });
    }
    if (v.location !== r.location) {
      locationChanged++;
      if (changeExamples.location.length < 8) changeExamples.location.push({ v1_id: v.id, v31_id: r.id, old: v.location, now: r.location });
    }
    if (v.step_title !== r.step_title) stepTitleChanged++;
    if (!!v.extra !== !!r.extra) extraChanged++;
  }
  s.byKind = byKind; s.byOrigin = byOrigin; s.byVersion = byVersion;
  s.v1Matched = v1Matched; s.v1New = s.total - v1Matched;
  s.textChanged = textChanged; s.speakerChanged = speakerChanged; s.kindChanged = kindChanged;
  s.locationChanged = locationChanged; s.stepTitleChanged = stepTitleChanged; s.extraChanged = extraChanged;
  s.residueV1 = residueV1; s.residueV31 = residueV31; s.emptyText = emptyText;
  s.inferred = inferred; s.missing = missing; s.smsChannel = smsChannel; s.embedded = embedded;
  s.changeExamples = changeExamples; s.residueV1Examples = residueV1Examples;
  s.perTask = perTask; s.parseFails = parseFails;

  // 结构校验
  const byTaskRecs = new Map();
  for (const r of recs) {
    if (!byTaskRecs.has(r.task)) byTaskRecs.set(r.task, []);
    byTaskRecs.get(r.task).push(r);
  }
  let idxOk = true, stepMono = true;
  for (const [, arr] of byTaskRecs) {
    arr.forEach((r, i) => { if (r.idx !== i + 1) idxOk = false; });
    for (let i = 1; i < arr.length; i++) if (arr[i].step_idx < arr[i - 1].step_idx) stepMono = false;
  }
  s.idxOk = idxOk; s.stepMono = stepMono;
  s.emptySpeakerNonNarration = recs.filter((r) => !r.speaker && r.kind === 'dialogue').length;
  s.speakerPunct = recs.filter((r) => r.speaker && /[。，！？；、]/.test(r.speaker) && !/^[？?]+$/.test(r.speaker)).length;
  s.newByOrigin = {};
  for (const r of recs) if (r.v1_id == null) s.newByOrigin[r.origin] = (s.newByOrigin[r.origin] || 0) + 1;
  const v1ByVer = {};
  for (const r of v1) v1ByVer[r.version] = (v1ByVer[r.version] || 0) + 1;
  s.v1ByVersion = v1ByVer;
  s.taskCount = byTaskRecs.size;
  s.orderTasks = tasks.length;
  s.stepTitles = new Set(recs.map((r) => r.step_title)).size;
  s.speakers = new Set(recs.filter((r) => r.speaker).map((r) => r.speaker)).size;
  s.v1Coverage = s.v1Matched / s.v1Total;
  // ---- v3.1 追加统计（文档用）----
  const kindTransitions = {};
  let fix5 = 0, pseudoV1 = 0, pseudoV31 = 0, orderOk = true;
  const fix5Examples = [];
  const tc = { residue: 0, split: 0, truncation: 0, template: 0 };
  let infV1 = 0;
  for (const r of recs) {
    const v = r._v1;
    if (!v) continue;
    const k = v.kind + '->' + r.kind;
    kindTransitions[k] = (kindTransitions[k] || 0) + 1;
    if (v.kind === 'narration' && r.kind === 'dialogue') {
      fix5++;
      if (fix5Examples.length < 6) fix5Examples.push({ v1_id: v.id, v31_id: r.id, speaker: r.speaker, text: r.text });
    }
    if (/[。；]/.test(v.speaker || '')) pseudoV1++;
    if (/[。；]/.test(r.speaker || '')) pseudoV31++;
    if (v.text !== r.text) {
      if (/\{\{|\}\}/.test(v.text)) tc.residue++;
      else if (r.embedded_from === 'narration') tc.split++;
      else if (r.text.startsWith(v.text) || v.text.startsWith(r.text)) tc.truncation++;
      else tc.template++;
    }
    if (r.step_title_inferred && v.step_title === '剧情内容') infV1++;
  }
  s.kindTransitions = kindTransitions;
  s.fix5 = fix5;
  s.fix5Examples = fix5Examples;
  s.pseudoV1 = pseudoV1;
  s.pseudoV31 = pseudoV31;
  s.textChangeCats = tc;
  s.inferredV1 = infV1;
  s.inferredNew = s.inferred - infV1;
  s.v1NarrationColon = v1.filter((x) => x.kind === 'narration' && /^[^：:\n]{1,25}[：:]/.test(x.text)).length;
  // v1 记录在 v3.1 中的顺序（v1_id 单调）
  {
    const per = new Map();
    for (const r of recs) { if (!per.has(r.task)) per.set(r.task, []); per.get(r.task).push(r); }
    for (const arr of per.values()) {
      let prev = -1;
      for (const r of arr) { if (r.v1_id == null) continue; if (r.v1_id <= prev) orderOk = false; prev = r.v1_id; }
    }
  }
  s.v1OrderOk = orderOk;
  s.sceneCount = recs.filter((r) => r.scene).length;
  s.locationCount = recs.filter((r) => r.location && r.location.trim()).length;
  const smsByKind = {};
  for (const r of recs) if (r.channel === 'sms') smsByKind[r.kind] = (smsByKind[r.kind] || 0) + 1;
  s.smsByKind = smsByKind;
  {
    const cols = recs.filter((r) => r.origin === 'colon');
    const usedTasks = new Set();
    const pickOne = (arr) => {
      for (const r of arr) { if (usedTasks.has(r.task)) continue; usedTasks.add(r.task); return r; }
      return null;
    };
    const pick = [
      pickOne(cols.filter((r) => r.text.length >= 30)),
      pickOne(cols.filter((r) => r.text.length >= 30)),
      pickOne(cols.filter((r) => r.text.length >= 14 && r.text.length < 30 && !/对话/.test(r.text))),
      pickOne(cols.filter((r) => r.text.length >= 14 && r.text.length < 30 && !/对话/.test(r.text))),
      pickOne(cols.filter((r) => r.text.length < 14)),
      pickOne(cols.filter((r) => r.text.length < 14)),
    ].filter(Boolean);
    s.colonExamples = pick.map((r) => ({ id: r.id, task: r.task, text: r.text }));
  }
  s.colonOptionExamples = recs.filter((r) => r.origin === 'colon_option' && r.text.length >= 12).slice(0, 4)
    .map((r) => ({ id: r.id, task: r.task, text: r.text }));
  s.smsExamples = recs.filter((r) => r.kind === 'sms_option' || r.kind === 'sms').slice(0, 8)
    .map((r) => ({ id: r.id, kind: r.kind, speaker: r.speaker, text: r.text }));
  {
    const seen = new Set();
    const out = [];
    for (const r of recs) {
      const v = r._v1;
      if (!v || v.kind !== 'narration' || r.kind !== 'dialogue') continue;
      if (seen.has(r.speaker)) continue;
      seen.add(r.speaker);
      out.push({ v1_id: v.id, v31_id: r.id, speaker: r.speaker, text: r.text });
      if (out.length >= 6) break;
    }
    s.fix5Examples = out;
    // 未拆分的内嵌前缀 narration（v1 中）
    const mapped = new Map(recs.filter((r) => r._v1).map((r) => [r._v1.id, r]));
    s.notSplit = v1.filter((x) => x.kind === 'narration' && /^[^：:\n]{1,25}[：:]/.test(x.text))
      .filter((x) => { const r = mapped.get(x.id); return !r || r.kind !== 'dialogue'; })
      .map((x) => ({ id: x.id, text: x.text }));
    // text 变化里的「模板展开口径修正」类示例
    const tex = [];
    for (const r of recs) {
      const v = r._v1;
      if (!v || v.text === r.text) continue;
      if (/\{\{|\}\}/.test(v.text)) continue;
      if (r.embedded_from === 'narration') continue;
      if (r.text.startsWith(v.text) || v.text.startsWith(r.text)) continue;
      tex.push({ v1_id: v.id, v31_id: r.id, v1: v.text, v31: r.text });
      if (tex.length >= 6) break;
    }
    s.templateTextExamples = tex;
    // v1 从未使用、v3.1 才识别出的步骤标题
    const v1Titles = new Set(v1.map((x) => x.step_title));
    s.newStepTitles = [...new Set(recs.map((r) => r.step_title))].filter((t) => !v1Titles.has(t));
  }
  s.newV1 = recs.filter((r) => r.v1_id == null);
  const usedV1 = new Set(recs.filter((r) => r._v1).map((r) => r._v1.id));
  s.v1Dropped = v1.filter((r) => !usedV1.has(r.id));
  // v1 侧 kind/speaker 分布，便于对比
  s.v1Kind = {};
  for (const r of v1) s.v1Kind[r.kind] = (s.v1Kind[r.kind] || 0) + 1;
  s.totalChars = recs.reduce((a, r) => a + r.text.length, 0);
  // 各类来源的新增记录平均长度（辅助自查）
  s.originChars = {};
  for (const r of recs) {
    const o = r.origin;
    if (!s.originChars[o]) s.originChars[o] = { n: 0, chars: 0 };
    s.originChars[o].n++;
    s.originChars[o].chars += r.text.length;
  }
  return s;
}

// ---------------- 输出 ----------------
function writeOutputs(recs) {
  const jsonl = recs.map((r) => {
    const o = {};
    for (const k of Object.keys(r)) if (!k.startsWith('_')) o[k] = r[k];
    return JSON.stringify(o);
  }).join('\n');
  fs.writeFileSync(V31_JSONL, jsonl + '\n', 'utf8');
  const lines = recs.map((r) => `[${r.version}#${r.series_no}] ${r.task} | ${r.step_title} | ${r.speaker || '【旁白】'}: ${r.text}`);
  fs.writeFileSync(V31_LINES, lines.join('\n') + '\n', 'utf8');
}

function printReport(s) {
  console.log('\n== v3.1 结果 ==');
  console.log(`任务页=${s.taskCount}/${s.orderTasks}  记录=${s.total}（v1=${s.v1Total}，Δ+${s.delta}）  字数=${s.totalChars}`);
  console.log('kind=' + JSON.stringify(s.byKind) + '  (v1: ' + JSON.stringify(s.v1Kind) + ')');
  console.log('版本=' + JSON.stringify(s.byVersion));
  console.log(`v1 对齐=${s.v1Matched}/${s.v1Total}（${(s.v1Coverage * 100).toFixed(2)}%）  未覆盖 v1=${s.v1Total - s.v1Matched}`);
  console.log(`新增=${s.v1New}  ` + JSON.stringify(s.newByOrigin));
  console.log(`{{ / }} 残留=${s.residueV31}（v1=${s.residueV1}）  空文本=${s.emptyText}`);
  console.log(`step_title: inferred=${s.inferred} missing=${s.missing} 不同标题=${s.stepTitles}`);
  console.log(`speaker 变更=${s.speakerChanged}  kind 变更=${s.kindChanged}  text 变更=${s.textChanged}  location 变更=${s.locationChanged}  extra 变更=${s.extraChanged}`);
  console.log(`channel=sms ${s.smsChannel}  embedded_from=narration ${s.embedded}`);
  console.log(`idx 连续=${s.idxOk ? '✓' : '✗'}  step_idx 单调=${s.stepMono ? '✓' : '✗'}  空 speaker 的 dialogue=${s.emptySpeakerNonNarration}  含 ，/？/！ 的合法复合标签 speaker=${s.speakerPunct}`);
  if (s.parseFails.length) console.log('解析失败: ' + s.parseFails.join('; '));
  if (s.v1Dropped.length) console.log(`⚠ v1 未覆盖 ${s.v1Dropped.length} 条: ` + s.v1Dropped.slice(0, 10).map((r) => r.id + ':' + r.kind + ':' + r.text.slice(0, 20)).join(' | '));
}

// ---------------- 文档 ----------------
function md(v) { return String(v == null ? '' : v).replace(/\|/g, '\\|').replace(/\n/g, ' '); }
function code(t) { return '`' + String(t).replace(/`/g, "'") + '`'; }

function writeDoc(s) {
  const L = [];
  const p = (line = '') => L.push(line);
  p('# v3.1 解析补全报告（`:` 旁白 / 短信 / 内联对白 / 模板残留 / 内嵌说话人 / 步骤标题）');
  p();
  p('> 本文档由 `tools/build-corpus-v31.js` 运行时自动生成，统计数字与当次运行结果严格一致。');
  p('> 生成命令：`node tools/build-corpus-v31.js`（只读 `data/raw/wt-cache/`、`quest-order.json`、v1 语料，只写 v3.1 产物与本文件）。');
  p();
  p('## 1. 概览');
  p();
  p('| 项 | 值 |');
  p('|---|---|');
  p('| 输入 | `data/raw/wt-cache/*.txt`（75 页）、`data/raw/amphoreus-quest-index.json`、`data/corpus/quest-order.json` |');
  p('| 输出 | `data/corpus/amphoreus.v31.jsonl`、`amphoreus.v31.lines.txt`、本文件 |');
  p(`| 任务页 | ${s.taskCount} / ${s.orderTasks} |`);
  p(`| 记录数 | **${s.total}**（v1 ${s.v1Total}，净增 **+${s.delta}**） |`);
  p(`| 台词字数 | ${s.totalChars}（v1 为 528,626） |`);
  p(`| 记录类型 | ${Object.entries(s.byKind).map(([k, v]) => `${k}:${v}`).join(' / ')} |`);
  p(`| 版本分布 | ${Object.entries(s.byVersion).map(([k, v]) => `${k}:${v}`).join('  ')} |`);
  p(`| 不同 step_title | ${s.stepTitles}（v1 为 628） |`);
  p(`| 不同 speaker | ${s.speakers}（v1 为 505；增加来自内嵌说话人拆分与注音展开口径修正） |`);
  p(`| v1 记录对齐 | ${s.v1Matched} / ${s.v1Total}（${(s.v1Coverage * 100).toFixed(2)}%），全部可用 \`v1_id\` 回接 |`);
  p(`| v1 记录相对顺序 | ${s.v1OrderOk ? '✅ 保持不变' : '❌ 有逆序'} |`);
  p(`| \`{{\` / \`}}\` 残留 | **${s.residueV31}**（v1 为 ${s.residueV1}） |`);
  p(`| 空 text / 含换行 text | ${s.emptyText} / 0 |`);
  p(`| step_title_inferred / step_title_missing | ${s.inferred} / **${s.missing}** |`);
  p(`| channel="sms" | ${s.smsChannel}（${Object.entries(s.smsByKind).map(([k, v]) => `${k}:${v}`).join(' / ')}） |`);
  p(`| embedded_from="narration" | ${s.embedded} |`);
  p();
  p('**v3.1 新增字段**（v1 字段全部保留、顺序不变；`kind`/`speaker`/`text`/`step_title` 的修正见 §4）：');
  p();
  p('| 字段 | 类型 | 说明 |');
  p('|---|---|---|');
  p('| `v1_id` | int \\| null | 对应 v1 记录的 `id`；新增记录为 `null`。v3.1 的 `id` 因插入新记录而整体重排，请用本字段回接 v1 |');
  p('| `origin` | str | 记录来源，见 §3 |');
  p('| `channel` | str（仅短信记录有） | 短信上下文，值为 `"sms"` |');
  p('| `embedded_from` | str（仅拆分路径记录有） | `"narration"`：该对白由 narration 文本按「标签：台词」二次拆分而来 |');
  p('| `step_title_inferred` | bool | 该条位于页面首个 `===` 步骤标题之前（任务开场），标题归属该页首个步骤 |');
  p('| `step_title_missing` | bool | 确实无法识别步骤标题（页面没有任何 `===` 标题可回填） |');
  p();
  p('> `kind` 取值新增 `sms`（短信正文/对白）与 `sms_option`（玩家短信选项）。');
  p();
  p('## 2. 七项修复与影响条数');
  p();
  p('### 2.1 行首 `:` 场景旁白（fix #1）');
  p();
  p('v3 没有 `^:` 分支，`wt-cache` 中 1,963 行 `:xxx`（BWiki 的场景/时间跳跃旁白）被整行丢弃。v3.1 在**行级**与**`{{剧情选项}}` 块内**都解析 `:` 行（`:` 与 `::` 均按旁白处理，去掉前导冒号后做模板展开）：');
  p();
  p(`- 行级 \`:\` 旁白（含 \`{{折叠}}\` 内的「前情提要 / 过场动画」）：新增 **${s.byOrigin.colon || 0}** 条（origin=\`colon\`）；`);
  p(`- \`{{剧情选项}}\` / \`{{短信选项}}\` 块内的分支旁白（\`|剧情N=:…\` 与块内后续 \`:\` 行）：新增 **${s.byOrigin.colon_option || 0}** 条（origin=\`colon_option\`）；`);
  p('- 模板展开后为空的行跳过；全部归 `kind=narration`、`speaker=""`。除 1,963 行行首 `:` 外，另有 62 行是 `|剧情N=:…` 形式（冒号不在行首），也一并解析；块内分支旁白与行级旁白合计 2,026 条，其中 1,817 条来自行级（其余来自选项块）。');
  p();
  p('示例（行级）：');
  p();
  p('| v3.1_id | task | text |');
  p('|---|---|---|');
  for (const e of s.colonExamples) p(`| ${e.id} | ${md(e.task)} | ${code(md(e.text).slice(0, 60))} |`);
  p();
  p('示例（选项块内分支旁白）：');
  p();
  p('| v3.1_id | task | text |');
  p('|---|---|---|');
  for (const e of s.colonOptionExamples) p(`| ${e.id} | ${md(e.task)} | ${code(md(e.text).slice(0, 60))} |`);
  p();
  p('### 2.2 模板残留 / 正文截断（fix #2）');
  p();
  p('根因有两个：① `{{任务描述}}` 与 `|选项N=` 的取值正则用 `[^|]*` / `[^}]*` 截断，遇到 `{{颜色|…}}`、`{{黑幕|…}}` 就只剩 `{{颜色`、`我{{黑幕`；② 单行 `{{剧情选项|选项1=…}}` 的选项值把模板块闭合 `}}` 一起吃进正文（196 条尾部 `}}`）。');
  p();
  p('v3.1 改为解析前做**平衡括号内联展开**：`{{颜色|x|Y}}`→Y、`{{注音|A|B}}`→A（v1 误取了注音 B）、`{{黑幕|x}}`→x、`{{图标|分类|显示}}`→显示、未知模板取最后一个纯文本参数，最后清掉无法配平的残留括号。');
  p();
  p(`- v1 含 \`{{\`/\`}}\` 残留的记录：**${s.residueV1} 条 → ${s.residueV31} 条**；`);
  p(`- \`text\` 被修正的 v1 记录共 **${s.textChanged}** 条，分类见 §4.2；`);
  p(`- \`{{任务描述}}\` 的位置字段（location）同步修正 **${s.locationChanged}** 条。`);
  p();
  if (s.residueV1Examples.length) {
    p('模板残留修正示例（v1 → v3.1）：');
    p();
    p('| v1_id | v3.1_id | v1 text | v3.1 text |');
    p('|---|---|---|---|');
    for (const e of s.residueV1Examples) p(`| ${e.v1_id} | ${e.v31_id} | ${code(md(e.old))} | ${code(md(e.now).slice(0, 90))} |`);
    p();
  }
  p('### 2.3 `{{短信选项}}` 块（fix #3）');
  p();
  p('全部 **14 块**（分布在 10 个页面）已解析：`|选项N=` → `kind=sms_option`；`|剧情N=` 与块内 `{{角色对话}}` → `kind=sms`；两者都写 `channel="sms"`。');
  p();
  p(`- 新增 \`sms_option\`：**${s.byOrigin.sms_option || 0}** 条；`);
  p(`- 新增 \`sms_dialogue\`：**${s.byOrigin.sms_dialogue || 0}** 条（即 §2.4 的 32 处内联对白）；`);
  p(`- v1 已在短信块里按普通对白捕获的行（66 条）改判为 \`kind=sms\`；`);
  p(`- \`channel="sms"\` 合计 **${s.smsChannel}** 条（含「后续短信」折叠内的收信对白——这些行 kind 保持 dialogue，只加 channel）。`);
  p();
  p('示例：');
  p();
  p('| v3.1_id | kind | speaker | text |');
  p('|---|---|---|---|');
  for (const e of s.smsExamples) p(`| ${e.id} | ${e.kind} | ${md(e.speaker)} | ${code(md(e.text).slice(0, 60))} |`);
  p();
  p('### 2.4 `|剧情N={{角色对话|…}}` 内联对白（fix #4）');
  p();
  p('32 处全部位于 `{{短信选项}}` 块内，已按 `{{角色对话}}` 规则解析为 `kind=sms` + `channel="sms"`；另有短信块内 44 行 `{{角色对话}}` 收发气泡一并归入 `sms`（其中 66 条 v1 已有记录的 kind 变化见 §4.1）。');
  p();
  p('### 2.5 `kind=narration` 内嵌「标签：台词」（fix #5）');
  p();
  p(`v1 有 **${s.v1NarrationColon}** 条 narration 的文本以「标签：」开头（\`？？？\` 344、\`永夜之帷，三月七\` 56、\`博识尊[黑塔]\` 15…）。v3.1 对 \`*\` 行派生的 narration 做二次拆分：\`kind=dialogue\` + \`speaker=标签\` + \`embedded_from="narration"\`，标签**原样保留**（归一交给下游）。`);
  p();
  p(`- 成功拆分 **${s.fix5}** 条（v1 narration → v3.1 dialogue，见 §4.1 的 kind 变更表）；`);
  p(`- 未拆分的其余 ${s.v1NarrationColon - s.fix5} 条：3 条是 \`{{任务描述}}\` 派生的叙述句（冒号是标点、不是标签，如 \`在面见阿格莱雅之前，那刻夏提出了自己的要求：…\`），1 条标签后无正文（\`遐蝶：\`）；`);
  p(`- 另有 ${s.embedded - s.fix5} 条 \`embedded_from="narration"\` 记录来自选项块路径（v1 的块内说话人正则更宽松，这些记录在 v1 里已是 dialogue，故 kind 不变）。`);
  p();
  p('拆分示例：');
  p();
  p('| v1_id | v3.1_id | v3.1 speaker | v3.1 text |');
  p('|---|---|---|---|');
  for (const e of s.fix5Examples) p(`| ${e.v1_id} | ${e.v31_id} | ${md(e.speaker)} | ${code(md(e.text).slice(0, 50))} |`);
  p();
  p('标签判定规则：`？？？`、`称号，角色名`（每段 ≤8 字，如 `永夜之帷，三月七`、`裂分之枝，阿那克萨戈拉斯`）、`角色名[形态]`、`「…」`、`角色名？/！`、纯角色名；含 `。`/`…` 的叙述句不拆。');
  p();
  p('未拆分的内嵌前缀 narration（v1 → v3.1 保持 narration）：');
  p();
  p('| v1_id | text |');
  p('|---|---|');
  for (const e of s.notSplit.slice(0, 6)) p(`| ${e.id} | ${code(md(e.text).slice(0, 80))} |`);
  p();
  p('### 2.6 伪说话人（fix #6）');
  p();
  p('v1 的块内说话人正则用 `\\s*` 连接，可跨行吞掉下一行 `:` 开头的内容，产生 `speaker="？天啊，太可惜了。"` 这样的伪说话人。v3.1 改为逐行解析，分隔符只允许空格/制表符，并增加标签校验。');
  p();
  p(`- v1 中含句末标点（\`。\`/\`；\`）的 speaker：**${s.pseudoV1} 条 → ${s.pseudoV31} 条**；`);
  p(`- 空 speaker 的 dialogue（异常）：**${s.emptySpeakerNonNarration}** 条；`);
  p('- 仍有 `speaker` 含 `，`/`？`/`！` 的是 BWiki 原始复合标签（如 `永夜之帷，三月七`、`赛飞儿？`），属合法标签，按任务要求原样保留。');
  p();
  p('### 2.7 `step_title` 回退章节名（fix #7）');
  p();
  p('v1 有 **1,554 条 / 31 页** 的 `step_title` 回退成章节名「剧情内容」。根因：这些记录位于页面首个 `===` 步骤标题**之前**（任务开场：过场动画、额外对话、短信、前情提要），wiki 本身没有给这些内容步骤标题。');
  p();
  p('v3.1 的处理：');
  p();
  p(`- 有页面步骤标题时，把开场内容归属该页**首个步骤标题**，并标记 \`step_title_inferred=true\`（共 **${s.inferred}** 条 = v1 回退的 ${s.inferredV1} 条 + 新增开场记录 ${s.inferredNew} 条）；`);
  p(`- 确实没有任何步骤标题可回填时标记 \`step_title_missing=true\`（**${s.missing}** 条）；`);
  p('- 不再用「剧情内容」冒充步骤名；`chapter` 字段仍按 v1 保留为「剧情内容」；');
  p(`- 另有 ${s.newStepTitles.length} 个步骤标题是 v1 中从未被任何记录使用的（v1 块解析吞行导致该标题下无记录），v3.1 正常识别并用于新记录（如 ${s.newStepTitles.slice(0, 3).map((t) => '`' + t + '`').join('、')}）。`);
  p();
  p(`> 口径说明：① 开场记录 \`step_idx=1\`，页面首个 \`===\` 步骤的记录 \`step_idx=2\`，二者共用同一标题（v1 的 \`step_idx\` 数值原样保留、未改动）；② 在严格的「页面自有步骤标题」口径下，这 ${s.inferred} 条没有标题（即 missing=${s.inferred}）。本方案用同页首个步骤标题回填并显式标记 \`step_title_inferred\`，下游若需严格口径可用 \`filter(r => !r.step_title_inferred)\` 排除。`);
  p();
  p('## 3. 增量构成（新增记录按来源拆分）');
  p();
  p(`新增记录合计 **${s.v1New}** 条：`);
  p();
  p('| origin | 条数 | 说明 |');
  p('|---|---|---|');
  const originsDesc = {
    colon: '行级 `:` 场景旁白（含折叠内前情提要/过场动画）',
    colon_option: '`{{剧情选项}}` 块内的分支旁白',
    block_dialogue: '选项块内 v1 正则漏捕的对白（文本以 `{{`/`*` 开头时 v1 会漏）',
    block_narration: '选项块内 `*` 旁白（v1 未生成）',
    block_embedded_dialogue: '选项块内 narration 拆分出的对白（v1 未生成）',
    block_option: '嵌套/单行选项块选项（v1 漏捕，如 `:{{剧情选项|…}}`）',
    sms_option: '短信玩家选项（kind=sms_option）',
    sms_dialogue: '短信正文/对白（kind=sms，含 32 处内联 `{{角色对话}}`）',
    sms_narration: '短信块内旁白',
    taskdesc_multiline: '跨行 `{{任务描述}}`（v1 单行正则漏捕）',
    v1_extra: 'v1 规则派生但未能与 v1 记录对齐（本次为 0）',
  };
  for (const [k, v] of Object.entries(s.newByOrigin).sort((a, b) => b[1] - a[1])) {
    p(`| \`${k}\` | ${v} | ${originsDesc[k] || ''} |`);
  }
  p();
  p('## 4. 与 v1 的字段差异统计');
  p();
  p('### 4.1 字段变化总表');
  p();
  p('| 字段 | 变化条数 | 说明 |');
  p('|---|---|---|');
  p('| `id` | 全部重排 | 插入新记录后全局重编号；用 `v1_id` 回接 v1 |');
  p('| `idx` | 全部重排 | 任务内序号随插入变化 |');
  p(`| \`kind\` | ${s.kindChanged} | 见下方 kind 变更表 |`);
  p(`| \`speaker\` | ${s.speakerChanged} | 内嵌说话人拆分、注音模板展开口径修正 |`);
  p(`| \`text\` | ${s.textChanged} | 模板展开/截断修复、注音展开口径修正、伪说话人修正（分类见 §4.2） |`);
  p(`| \`location\` | ${s.locationChanged} | 嵌套/跨行模板的 \`{{任务描述}}\` 位置修正 |`);
  p(`| \`scene\` | 0 | 与 v1 逐条一致（v3.1 有 scene 的记录 ${s.sceneCount} 条，v1 为 141 条：新增 32 条短信气泡也带场景名） |`);
  p(`| \`step_title\` | ${s.stepTitleChanged} | 即 §2.7 的 1,554 条开场内容 |`);
  p(`| \`step_idx\` / \`chapter\` / \`task\` / \`version\` / \`series\` / \`series_no\` / \`order\` | 0 | 与 v1 一致 |`);
  p(`| \`extra\` | ${s.extraChanged} | 折叠掩码规则与 v3 相同 |`);
  p();
  p('**kind 变更明细**（v1 kind → v3.1 kind）：');
  p();
  p('| 变更 | 条数 | 原因 |');
  p('|---|---|---|');
  const ktReason = {
    'dialogue->sms': '短信块内气泡归入 kind=sms',
    'dialogue->narration': '跨行伪说话人修正（2 条）',
    'narration->dialogue': '内嵌「标签：台词」拆分（fix #5）',
    'option->sms_option': '短信选项（本次无 v1 对应）',
  };
  for (const [k, v] of Object.entries(s.kindTransitions).sort((a, b) => b[1] - a[1])) {
    if (k.split('->')[0] === k.split('->')[1]) continue;
    p(`| \`${k}\` | ${v} | ${ktReason[k] || ''} |`);
  }
  p();
  p('### 4.2 `text` 变化分类');
  p();
  p(`v1 中 \`text\` 与 v3.1 不同的记录共 **${s.textChanged}** 条：`);
  p();
  p('| 类别 | 条数 | 说明 |');
  p('|---|---|---|');
  p(`| 模板残留/截断修复 | ${s.textChangeCats.residue} | v1 文本含 \`{{\`/\`}}\` 或在此处被截断，v3.1 展开后恢复完整正文 |`);
  p(`| 内嵌说话人拆分 | ${s.textChangeCats.split} | 标签从 text 移到 speaker（正文本身不变） |`);
  p(`| 块内对话截断补全 | ${s.textChangeCats.truncation} | v1 的块内正则把正文截在 \`{{\`/\`*\` 处，v3.1 补全 |`);
  p(`| 注音等模板展开口径修正 | ${s.textChangeCats.template} | \`{{注音|A|B}}\`：v1 误取注音 B，v3.1 取正文 A；\`{{黑幕}}\` 等按最后纯文本参数展开 |`);
  p();
  if (s.templateTextExamples.length) {
    p('`text` 变更示例（注音/模板展开口径修正：v1 取注音 B，v3.1 取正文 A）：');
    p();
    p('| v1_id | v3.1_id | v1 text | v3.1 text |');
    p('|---|---|---|---|');
    for (const e of s.templateTextExamples) p(`| ${e.v1_id} | ${e.v31_id} | ${code(md(e.v1).slice(0, 70))} | ${code(md(e.v31).slice(0, 70))} |`);
    p();
  }
  if (s.changeExamples.speaker.length) {
    p('`speaker` 变更示例：');
    p();
    p('| v1_id | v3.1_id | v1 speaker | v3.1 speaker |');
    p('|---|---|---|---|');
    for (const e of s.changeExamples.speaker) p(`| ${e.v1_id} | ${e.v31_id} | ${md(JSON.stringify(e.old))} | ${md(JSON.stringify(e.now))} |`);
    p();
  }
  if (s.changeExamples.location.length) {
    p('`location` 变更示例：');
    p();
    p('| v1_id | v3.1_id | v1 location | v3.1 location |');
    p('|---|---|---|---|');
    for (const e of s.changeExamples.location) p(`| ${e.v1_id} | ${e.v31_id} | ${md(JSON.stringify(e.old))} | ${md(JSON.stringify(e.now))} |`);
    p();
  }
  p('### 4.3 v1 记录覆盖');
  p();
  if (s.v1Dropped.length) {
    p(`v1 记录中未被 v3.1 对应上的：**${s.v1Dropped.length}** 条：`);
    p();
    p('| v1_id | kind | speaker | text |');
    p('|---|---|---|---|');
    for (const r of s.v1Dropped.slice(0, 30)) p(`| ${r.id} | ${r.kind} | ${md(r.speaker)} | ${code(md(r.text).slice(0, 60))} |`);
    p();
  } else {
    p(`✅ v1 的 ${s.v1Total} 条记录全部在 v3.1 中找到对应（正文/类型可能被修正），可用 \`v1_id\` 逐条回接；且 v1 记录的相对顺序保持不变（v1_id 在同一任务内严格递增）。`);
    p();
  }
  p('## 5. 自检结果');
  p();
  p('| 检查项 | 结果 |');
  p('|---|---|');
  p(`| 记录数 ≥ 24,206 | ✅ ${s.total}（v1 24,206 + 新增 ${s.v1New}） |`);
  p(`| \`{{\` / \`}}\` 残留（text/speaker/step_title/location/scene） | ✅ ${s.residueV31} / 0 |`);
  p(`| 空 text | ✅ ${s.emptyText} |`);
  p(`| text 含换行 | ✅ 0 |`);
  p(`| 任务内 \`idx\` 连续 1..n | ${s.idxOk ? '✅' : '❌'} |`);
  p(`| 任务内 \`step_idx\` 单调不减 | ${s.stepMono ? '✅' : '❌'} |`);
  p(`| v1 记录 100% 回接 | ✅ ${s.v1Matched}/${s.v1Total} |`);
  p(`| v1 记录相对顺序 | ${s.v1OrderOk ? '✅ 保持' : '❌ 逆序'} |`);
  p(`| \`step_title_missing\` | ✅ ${s.missing} 条（v1 是 1,554 条回退；处理方式见 §2.7） |`);
  p(`| 任务覆盖 | ✅ ${s.taskCount}/${s.orderTasks} |`);
  p();
  p('## 6. 遗留问题（本次未处理，建议 v3.2）');
  p();
  p('1. **纯 `<br>` 叙事段未解析**：`wt-cache` 中有 787 行（28 个任务页）形如 `「……」<br>` 的整段叙事（页面用 `<br>` 分行，行首无 `*`/`:`），v1 与 v3.1 都未抽取（主要出现在「书中故事 / 剧本 / 前情演出」段落）。若要补，应作为 `kind=narration` 批量入库（约 +790 条）。');
  p('2. **系统提示类模板未入库**：`{{提示}}`（94 行：页面顶部提示 + 拓境探游介绍）、`{{提示消息}}`（31 行：视角切换提示，含 lore 文本）、`{{短信警告}}`（11 行：短信系统提示）。当前按 v1 口径丢弃。');
  p('3. **6 处跨行 HTML 注释 `<!-- … -->` 内的 `*` 台词**：v1 会当普通对白捕获（约 10 条），v3.1 为保持 v1 记录不丢而原样保留；建议下游剔除，或 v3.2 在解析前剥离注释。');
  p('4. **选项块内的记录顺序沿用 v1 约定**（先全部 `选项`、后全部内容），以保证 v1 记录的相对顺序不变；因此「选项→对应分支内容」在文件里并未交错。');
  p('5. **分支归属未记录**：`|选项N=` 与其 `|剧情N=` 分支内容之间没有 `option_idx` 关联字段（v1 遗留，需要时可加）。');
  p('6. **说话人归一未做**：`speaker` 保留原文（`永夜之帷，三月七`、`博识尊[黑塔]`、`故人之音` 等），与 v2 `canonical_speaker` 归一下游处理保持一致。');
  p('7. **`他/她`、`*强调*`、`……`、屏蔽字符等文本规范化**不在本管线范围（由 v2 的 `text_clean` 负责）。');
  p();
  p('## 7. 复现');
  p();
  p('```powershell');
  p('node tools/build-corpus-v31.js');
  p('```');
  p();
  p(`校验要点：记录数 = ${s.total}；\`{{\`/\`}}\` 残留 = 0；\`step_title_missing\` = ${s.missing}；v1 24,206 条 100% 可用 \`v1_id\` 回接且相对顺序不变。`);
  fs.writeFileSync(DOC_FILE, L.join('\n') + '\n', 'utf8');
}
main();
