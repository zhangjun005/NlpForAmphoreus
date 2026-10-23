// 解析已抓取的 开拓任务 页面：按 h2 分段，抽出翁法罗斯段的条目
const fs = require('fs');
const path = require('path');

const file = path.join(__dirname, '..', 'data', 'raw', 'bwiki-kaiTuoRenWu.html');
const html = fs.readFileSync(file, 'utf8');
const region = html.slice(html.indexOf('<div class="mw-parser-output"'));

// 找 h2 标题位置
const h2s = [];
const reH2 = /<h2[^>]*>[\s\S]*?<span class="mw-headline"[^>]*>([\s\S]*?)<\/span>/g;
let m;
while ((m = reH2.exec(region))) {
  h2s.push({ title: m[1].replace(/<[^>]+>/g, '').trim(), at: m.index });
}
console.log('h2 段落:');
h2s.forEach((h, i) => console.log(`  ${i}. ${h.title}  @${h.at}`));

// 切段
const segs = h2s.map((h, i) => ({
  ...h,
  body: region.slice(h.at, i + 1 < h2s.length ? h2s[i + 1].at : region.length),
}));

const target = segs.find((s) => s.title.includes('翁法罗斯'));
if (!target) {
  console.log('!! 未找到翁法罗斯段');
  process.exit(0);
}
console.log(`\n=== 翁法罗斯段 长度=${target.body.length} ===`);

// 段内链接
const links = [];
const reA = /<a\s+href="(\/sr\/[^"#?]+)"[^>]*?(?:title="([^"]*)")?[^>]*>([\s\S]*?)<\/a>/g;
while ((m = reA.exec(target.body))) {
  const label = (m[2] || m[3] || '').replace(/<[^>]+>/g, '').trim();
  if (label && !label.includes('展开')) links.push({ label, href: m[1] });
}
const uniq = [...new Map(links.map((l) => [l.href, l])).values()];
console.log(`段内链接=${uniq.length}`);
uniq.slice(0, 40).forEach((l) => console.log(`   ${l.label}  ->  https://wiki.biligame.com${l.href}`));

// 段内纯文本片段（卡片描述）
const txt = target.body
  .replace(/<script[\s\S]*?<\/script>/g, '')
  .replace(/<style[\s\S]*?<\/style>/g, '')
  .replace(/<[^>]+>/g, '\n')
  .replace(/&nbsp;/g, ' ')
  .split('\n')
  .map((s) => s.trim())
  .filter(Boolean);
console.log(`\n纯文本行=${txt.length}，前 60 行:`);
txt.slice(0, 60).forEach((t) => console.log('   ' + t));
