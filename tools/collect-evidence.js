/**
 * collect-evidence.js
 * 1) 抽取全部 {{注音|正文|注音}} 对 -> data/corpus/ruby-pairs.jsonl
 * 2) 为方法文档收集「原文片段 -> 语料结果」对照证据（打印到 stdout）
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const CACHE = path.join(ROOT, 'data/raw/wt-cache');
const OUT_RUBY = path.join(ROOT, 'data/corpus/ruby-pairs.jsonl');

const final = fs.readFileSync(path.join(ROOT, 'data/corpus/amphoreus.final.jsonl'), 'utf8')
  .trim().split('\n').map(JSON.parse);
const byText = (t) => final.find((r) => (r.text || '').includes(t) || (r.text_clean || '').includes(t));

const files = fs.readdirSync(CACHE).filter((f) => f.endsWith('.txt'));
const ruby = [];
const pages = [];

for (const f of files) {
  const page = decodeURIComponent(f.replace(/\.txt$/, ''));
  const wt = fs.readFileSync(path.join(CACHE, f), 'utf8');
  pages.push({ page, wt });
  const lines = wt.split('\n');
  lines.forEach((line, i) => {
    const re = /\{\{注音\|([^|}]+)\|([^|}]+)\}\}/g;
    let m;
    while ((m = re.exec(line))) {
      ruby.push({ page, line: i + 1, display: m[1].trim(), gloss: m[2].trim(), context: line.replace(/\s+/g, ' ').slice(0, 160) });
    }
  });
}

fs.writeFileSync(OUT_RUBY, ruby.map((r) => JSON.stringify(r)).join('\n'), 'utf8');
const uniq = new Map();
for (const r of ruby) uniq.set(r.display + '\u0001' + r.gloss, (uniq.get(r.display + '\u0001' + r.gloss) || 0) + 1);
console.log(`注音对: ${ruby.length} 条 / 唯一 ${uniq.size} 组 / 覆盖 ${new Set(ruby.map((r) => r.page)).size} 页`);
console.log('高频注音对 Top 15:');
[...uniq.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15).forEach(([k, v]) => {
  const [d, g] = k.split('\u0001');
  console.log(`  ${v}x  「${d}」 注音「${g}」`);
});

// ---------- 证据抽样 ----------
const show = (label, pattern, max = 2, mapTo = null) => {
  console.log(`\n===== ${label} =====`);
  let shown = 0;
  for (const { page, wt } of pages) {
    if (shown >= max) break;
    const lines = wt.split('\n');
    for (let i = 0; i < lines.length && shown < max; i++) {
      if (!pattern.test(lines[i])) continue;
      console.log(`[原文] ${page} 第${i + 1}行:`);
      console.log('  ' + lines[i].replace(/\s+/g, ' ').slice(0, 170));
      const key = mapTo ? mapTo(lines[i]) : null;
      if (key) {
        const hit = byText(String(key).slice(0, 12));
        if (hit) console.log(`[语料] id=${hit.id} kind=${hit.kind} speaker=${hit.speaker} text=${(hit.text || '').slice(0, 70)}`);
        else console.log(`[语料] 未直接匹配（key=${String(key).slice(0, 20)}）`);
      }
      shown++;
    }
  }
};

show('① 气泡式对白 {{角色对话}}', /\{\{角色对话\|(左|右|中)\|/, 2, (l) => l.split('|').slice(4).join('|').replace(/\}\}.*$/, ''));
show('② 剧情选项 {{剧情选项}}', /\{\{剧情选项/, 2, (l) => l.split('|').slice(2).join('|').split('}}')[0]);
show('③ 行首冒号 :{{颜色}} 场景旁白', /^\s*:\s*\{\{颜色/, 2, (l) => l.replace(/^\s*:\s*/, ''));
show('④ 步骤标题 ===', /^===\s*/, 2);
show('⑤ 折叠块 {{折叠}}', /\{\{折叠/, 2);
show('⑥ 任务前置/后续链', /\|前置任务=/, 2);
show('⑦ 短信选项 {{短信选项}}', /\{\{短信选项/, 1);
show('⑧ 舞台指示整句 *…*', /^\*\s*\*[^*]+\*\s*$/, 2);
show('⑨ 称号前缀「…爵」', /「[^」]{1,6}爵」/, 2);
show('⑩ 注音', /\{\{注音\|/, 2, (l) => (l.match(/\{\{注音\|([^|}]+)/) || [])[1]);
