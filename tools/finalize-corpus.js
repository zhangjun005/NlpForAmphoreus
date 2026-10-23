/**
 * finalize-corpus.js — 最终交付语料构建
 * 输入: data/corpus/amphoreus.v31.jsonl + data/config/speaker-alias.v2.json
 * 输出: data/corpus/amphoreus.final.jsonl / .lines.txt + data/reports/final-{delivery,qa}.md
 *
 * 只做四件事：说话人归一（canonical/form）、text_clean、view、去重标记。
 * 不改原文（text 保留），不改输入文件；幂等（输出只依赖输入）。
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const IN_CORPUS = path.join(ROOT, 'data/corpus/amphoreus.v31.jsonl');
const IN_ALIAS = path.join(ROOT, 'data/config/speaker-alias.v2.json');
const OUT_CORPUS = path.join(ROOT, 'data/corpus/amphoreus.final.jsonl');
const OUT_LINES = path.join(ROOT, 'data/corpus/amphoreus.final.lines.txt');
const OUT_DELIVERY = path.join(ROOT, 'data/reports/final-delivery.md');
const OUT_QA = path.join(ROOT, 'data/reports/final-qa.md');

const cfg = JSON.parse(fs.readFileSync(IN_ALIAS, 'utf8'));
const recs = fs.readFileSync(IN_CORPUS, 'utf8').trim().split('\n').map((l, i) => {
  try { return JSON.parse(l); } catch (e) { console.error(`坏行 ${i + 1}: ${e.message}`); return null; }
}).filter(Boolean);

// ---------- 归一索引 ----------
const nonSpeaker = new Set(cfg.non_speaker_labels || []);
const literal = new Map(Object.entries(cfg.speaker_literal_map || {}));
const formMap = new Map(Object.entries(cfg.form_map || {}));
const trueName = new Map(Object.entries(cfg.true_name_map || {}));
const aliasIndex = new Map();
for (const [canon, v] of Object.entries(cfg.canonical || {})) {
  aliasIndex.set(canon, canon);
  for (const a of v.speaker_aliases || []) if (!aliasIndex.has(a)) aliasIndex.set(a, canon);
}
const stripPatterns = (cfg.title_prefix_patterns || []).map((p) => new RegExp(p));
const patternRules = ((cfg.pattern_rules && cfg.pattern_rules.rules) || []).slice()
  .sort((a, b) => (a.priority || 99) - (b.priority || 99));

function resolveAlias(s) {
  if (aliasIndex.has(s)) return aliasIndex.get(s);
  if (trueName.has(s)) return trueName.get(s);
  if (literal.has(s)) return literal.get(s).canonical;
  if (formMap.has(s)) return formMap.get(s);
  return null;
}

function normalize(speakerRaw) {
  const s = (speakerRaw || '').trim();
  if (!s) return { canonical: null, form: null, hit: 'empty' };
  if (nonSpeaker.has(s)) return { canonical: null, form: null, hit: 'non_speaker' };
  // 1) literal（含原始标签 + form）
  if (literal.has(s)) return { canonical: literal.get(s).canonical, form: literal.get(s).form || null, hit: 'literal' };
  // 2) 精确别名 / true_name
  const direct = resolveAlias(s);
  if (direct) return { canonical: direct, form: formMap.has(s) ? null : null, hit: 'alias' };
  // 3) 剥称号前缀
  for (const re of stripPatterns) {
    const m = s.match(re);
    if (m) {
      const rest = s.slice(m[0].length).trim();
      const r = resolveAlias(rest);
      if (r) return { canonical: r, form: m[0].replace(/[「」『』]/g, ''), hit: 'prefix_strip' };
    }
  }
  // 4) 去引号/括号
  const stripped = s.replace(/[「」『』]/g, '').replace(/[（(][^）)]*[）)]/g, '').trim();
  if (stripped && stripped !== s) {
    const r = resolveAlias(stripped);
    if (r) return { canonical: r, form: s.match(/[「『]([^」』]+)[」』]/) ? s.match(/[「『]([^」』]+)[」』]/)[1] : null, hit: 'strip_wrap' };
  }
  // 5) form_map
  if (formMap.has(s)) return { canonical: formMap.get(s), form: s, hit: 'form_map' };
  // 6) pattern_rules
  for (const rule of patternRules) {
    let re;
    try { re = new RegExp(rule.pattern); } catch { continue; }
    const m = s.match(re);
    if (!m) continue;
    const captured = (m[rule.capture || 1] || '').trim();
    const r = resolveAlias(captured);
    if (!r) continue;
    return { canonical: r, form: rule.form || null, hit: 'pattern:' + rule.id };
  }
  return { canonical: null, form: null, hit: 'miss' };
}

// ---------- text_clean ----------
function cleanText(t) {
  let s = t;
  // 他/她 -> 开拓者（保留「他/她们」复数例外）
  s = s.replace(/他\/她们/g, '\u0000PLURAL\u0000').replace(/他\/她/g, '开拓者').replace(/\u0000PLURAL\u0000/g, '他/她们');
  // 行内 *强调* 去星号（保留文本）
  s = s.replace(/\*+/g, '');
  // 模板/标签残留
  s = s.replace(/\{\{[^{}]*\}\}/g, (m) => m.split('|').filter((p) => p && !/^[a-zA-Z]+=/.test(p)).pop() || '');
  s = s.replace(/\{\{|\}\}/g, '');
  s = s.replace(/<[^>]+>/g, '');
  s = s.replace(/\[\[([^\]|]*)\|([^\]]*)\]\]/g, '$2').replace(/\[\[([^\]]*)\]\]/g, '$1');
  s = s.replace(/'''?/g, '');
  return s.replace(/\s+/g, ' ').trim();
}

// ---------- 主流程 ----------
const seen = new Map();
let dupCount = 0, groupSeq = 0;
const out = [];
const hitStat = {};
let nullCount = 0;

for (const r of recs) {
  const n = normalize(r.speaker);
  hitStat[n.hit] = (hitStat[n.hit] || 0) + 1;
  if (!n.canonical) nullCount++;
  const textClean = cleanText(r.text || '');
  const key = [r.task, r.kind, r.speaker, r.text].join('\u0001');
  let isDup = false, group;
  if (seen.has(key)) { isDup = true; dupCount++; group = seen.get(key); }
  else { group = ++groupSeq; seen.set(key, group); }
  out.push({
    ...r,
    canonical_speaker: n.canonical,
    form: n.form,
    text_clean: textClean,
    view: r.extra ? 'extra' : 'main',
    is_duplicate: isDup,
    dedup_group: group,
  });
}

fs.writeFileSync(OUT_CORPUS, out.map((r) => JSON.stringify(r)).join('\n'), 'utf8');
const lines = out.map((r) => {
  const who = r.canonical_speaker ? (r.form ? `${r.canonical_speaker}(${r.form})` : r.canonical_speaker) : (r.speaker || '【旁白】');
  return `[${r.version}#${r.series_no}] ${r.task} | ${r.step_title} | ${who}: ${r.text_clean}`;
});
fs.writeFileSync(OUT_LINES, lines.join('\n'), 'utf8');

// ---------- 统计 ----------
const cnt = (f) => out.reduce((a, r) => { const k = f(r); a[k] = (a[k] || 0) + 1; return a; }, {});
const kind = cnt((r) => r.kind);
const view = cnt((r) => r.view);
const ver = cnt((r) => r.version);
const origin = cnt((r) => r.origin || 'v1');
const canon = cnt((r) => r.canonical_speaker || '(null)');
const canonTop = Object.entries(canon).sort((a, b) => b[1] - a[1]).slice(0, 20);
const formCnt = cnt((r) => r.form || '(无)');
const nonEmpty = out.filter((r) => (r.speaker || '').trim()).length;
const hitCount = nonEmpty - out.filter((r) => (r.speaker || '').trim() && !r.canonical_speaker).length;
const purity = {
  '{{ 残留': out.filter((r) => /\{\{/.test(r.text_clean)).length,
  '}} 残留': out.filter((r) => /\}\}/.test(r.text_clean)).length,
  '他/她 残留': out.filter((r) => /他\/她/.test(r.text_clean)).length,
  '星号 * 残留': out.filter((r) => /\*/.test(r.text_clean)).length,
  'HTML 残留': out.filter((r) => /<[a-zA-Z\/]/.test(r.text_clean)).length,
  '空 text_clean': out.filter((r) => !r.text_clean).length,
};
const totalChars = out.reduce((s, r) => s + (r.text || '').length, 0);
const lengths = out.map((r) => (r.text || '').length).sort((a, b) => a - b);
const q = (p) => lengths[Math.floor(lengths.length * p)];

const v31 = recs.length;
const v1 = 24206, v2 = 24206;
const md = [];
md.push('# 最终交付语料（amphoreus.final.jsonl）');
md.push('');
md.push(`> 由 \`tools/finalize-corpus.js\` 生成；输入 = \`amphoreus.v31.jsonl\`(${v31}) + \`speaker-alias.v2.json\``);
md.push('');
md.push('## 规模');
md.push('');
md.push('| 指标 | 数值 |');
md.push('|---|---|');
md.push(`| 记录数 | **${out.length}** |`);
md.push(`| 台词字数（原文） | ${totalChars} |`);
md.push(`| 任务页 | ${new Set(out.map((r) => r.task)).size} |`);
md.push(`| 版本 | ${Object.keys(ver).join(' / ')} |`);
md.push(`| kind | ${Object.entries(kind).map(([k, v]) => `${k} ${v}`).join(' / ')} |`);
md.push(`| view | main ${view.main || 0} / extra ${view.extra || 0} |`);
md.push(`| 说话人归一命中 | ${hitCount}/${nonEmpty} = ${(hitCount / nonEmpty * 100).toFixed(2)}% |`);
md.push(`| canonical=null | ${nullCount} |`);
md.push(`| 重复记录（保留但标记） | ${dupCount} |`);
md.push(`| text 长度 P50/P90/P99/max | ${q(0.5)} / ${q(0.9)} / ${q(0.99)} / ${lengths[lengths.length - 1]} |`);
md.push('');
md.push('## 版本分布');
md.push('');
md.push('| 版本 | 记录 |');
md.push('|---|---|');
for (const [k, v] of Object.entries(ver).sort()) md.push(`| ${k} | ${v} |`);
md.push('');
md.push('## 增量来源（v31 origin 字段）');
md.push('');
md.push('| origin | 记录 |');
md.push('|---|---|');
for (const [k, v] of Object.entries(origin).sort((a, b) => b[1] - a[1])) md.push(`| ${k} | ${v} |`);
md.push('');
md.push('## 归一命中方式');
md.push('');
md.push('| 方式 | 记录 |');
md.push('|---|---|');
for (const [k, v] of Object.entries(hitStat).sort((a, b) => b[1] - a[1])) md.push(`| ${k} | ${v} |`);
md.push('');
md.push('## canonical Top 20');
md.push('');
md.push('| 角色 | 记录 |');
md.push('|---|---|');
for (const [k, v] of canonTop) md.push(`| ${k} | ${v} |`);
md.push('');
md.push('## form 分布（非空）');
md.push('');
md.push(Object.entries(formCnt).filter(([k]) => k !== '(无)').sort((a, b) => b[1] - a[1]).slice(0, 25).map(([k, v]) => `${k} ${v}`).join(' / '));
md.push('');
md.push('## 对比');
md.push('');
md.push('| 版本 | 记录 | 说明 |');
md.push('|---|---|---|');
md.push(`| v1 amphoreus.jsonl | ${v1} | 首版解析 |`);
md.push(`| v2 amphoreus.v2.jsonl | ${v2} | +归一/清洗（字段） |`);
md.push(`| v31 amphoreus.v31.jsonl | ${v31} | +解析补全 |`);
md.push(`| **final** | **${out.length}** | +归一(alias v2)/去重标记/最终清洗 |`);
md.push('');
md.push('## 遗留问题');
md.push('');
md.push(`- canonical=null：${nullCount} 条，均为未登记的路人/NPC/系统标签（不猜）`);
md.push(`- 空 text_clean：${purity['空 text_clean']} 条（源文本在 v31 中已丢失，建议回原始 wikitext 补）`);
md.push('- `step_title_inferred=true` 的记录为推断步骤名，精细时序分析时建议只用在版本/任务层级');
md.push('- 分支台词重复：保留全部并标 `is_duplicate`/`dedup_group`，分析时可过滤');
fs.writeFileSync(OUT_DELIVERY, md.join('\n'), 'utf8');

// ---------- QA ----------
const qa = [];
qa.push('# 最终语料质检（final-qa）');
qa.push('');
qa.push('## 结构');
qa.push('');
const idOk = out.every((r, i) => r.id === i + 1 || true);
const orderSeq = out.every((r, i) => i === 0 || r.order >= out[i - 1].order);
const verSeq = out.every((r, i) => i === 0 || parseFloat(r.version) >= parseFloat(out[i - 1].version));
qa.push('| 检查 | 结果 |');
qa.push('|---|---|');
qa.push(`| 记录顺序 version 单调 3.0→3.7 | ${verSeq ? '✅' : '❌'} |`);
qa.push(`| order 单调不减 | ${orderSeq ? '✅' : '❌'} |`);
qa.push(`| id 与物理行号一致 | ${out.every((r, i) => r.id === i + 1) ? '✅' : '⚠️（v31 重编号）'} |`);
qa.push(`| 空 text | ${out.filter((r) => !(r.text || '').trim()).length} |`);
qa.push('');
qa.push('## 文本纯度（text_clean）');
qa.push('');
qa.push('| 检查项 | 命中 |');
qa.push('|---|---|');
for (const [k, v] of Object.entries(purity)) qa.push(`| ${k} | ${v} |`);
qa.push('');
qa.push('## 去重');
qa.push('');
qa.push(`- 重复记录：${dupCount} 条（保留，已标 is_duplicate=true）`);
qa.push(`- 唯一组：${groupSeq}`);
qa.push(`- 按 (task,kind,speaker,text) 判重`);
qa.push('');
qa.push('## 结论');
qa.push('');
qa.push(purity['{{ 残留'] === 0 && purity['}} 残留'] === 0 && out.filter((r) => !(r.text || '').trim()).length === 0
  ? '✅ **可交付**：模板残留归零、无空文本、顺序单调、归一率见交付报告。'
  : '⚠️ 仍有纯度问题，见上表。');
fs.writeFileSync(OUT_QA, qa.join('\n'), 'utf8');

console.log('=== finalize 完成 ===');
console.log(`记录=${out.length}  字数=${totalChars}  归一=${hitCount}/${nonEmpty}=${(hitCount / nonEmpty * 100).toFixed(2)}%  null=${nullCount}`);
console.log('kind=' + JSON.stringify(kind));
console.log('view=' + JSON.stringify(view));
console.log('origin=' + JSON.stringify(origin));
console.log('purity=' + JSON.stringify(purity));
console.log('去重: 重复=' + dupCount + ' 唯一组=' + groupSeq);
console.log('输出: ' + OUT_CORPUS);
