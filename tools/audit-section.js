// 核对：第四幕•翁法罗斯 章节卡片 vs 我实际抓取的 74 页
const fs = require('fs');

const html = fs.readFileSync('data/raw/bwiki-kaiTuoRenWu.html', 'utf8');
const region = html.slice(html.indexOf('<div class="mw-parser-output"'));
const h2 = [...region.matchAll(/<h2[^>]*>[\s\S]*?<span class="mw-headline"[^>]*>([\s\S]*?)<\/span>/g)];
const segs = h2.map((m, i) => ({
  t: m[1].replace(/<[^>]+>/g, '').trim(),
  a: m.index,
  b: i + 1 < h2.length ? h2[i + 1].index : region.length,
}));
const target = segs.find((s) => s.t.includes('翁法罗斯'));
const body = region.slice(target.a, target.b);
const links = [...body.matchAll(/<a\s+href="\/sr\/([^"#?]+)"[^>]*?title="([^"]*)"/g)]
  .map((m) => m[2])
  .filter((x) => x && !x.includes('展开'));
const uniq = [...new Set(links)];
const meta = JSON.parse(fs.readFileSync('data/raw/amphoreus-quest-index.json', 'utf8')).map((r) => r.任务);
const set = new Set(meta);
const notMine = uniq.filter((t) => !set.has(t));
const notInSection = meta.filter((t) => !uniq.includes(t));
console.log(`章节卡片链接(去重)=${uniq.length}   我抓取=${meta.length}`);
console.log(`章节里有、我没抓 (${notMine.length}): ${notMine.join(' | ') || '无'}`);
console.log(`我抓了、章节没列 (${notInSection.length}): ${notInSection.join(' | ') || '无'}`);
