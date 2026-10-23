// 通过 MediaWiki API 取页面 wikitext，检查剧情/对白是否在页面里
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, '..', 'data', 'raw');
fs.mkdirSync(OUT, { recursive: true });

const titles = process.argv.slice(2);

async function getWikitext(title) {
  const u =
    'https://wiki.biligame.com/sr/api.php?action=parse&format=json&formatversion=2&prop=wikitext&page=' +
    encodeURIComponent(title);
  const r = await fetch(u, {
    headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0.0.0' },
    signal: AbortSignal.timeout(25000),
  });
  const j = await r.json();
  if (j.error) return { error: j.error.info || JSON.stringify(j.error) };
  return { wt: j.parse.wikitext, title: j.parse.title };
}

(async () => {
  for (const t of titles) {
    const res = await getWikitext(t);
    if (res.error) {
      console.log(`\n### ${t}  ->  ERROR ${res.error}`);
      continue;
    }
    const safe = t.replace(/[\\/:*?"<>|]/g, '_');
    const f = path.join(OUT, `wt-${safe}.txt`);
    fs.writeFileSync(f, res.wt, 'utf8');
    console.log(`\n### ${t}   wikitext=${res.wt.length} 字   ->  ${path.basename(f)}`);

    // 判断有没有对白特征
    const hasTable = /^\{\|/m.test(res.wt);
    const hasSpeakerCol = /说话人|角色|对话|台词|旁白/.test(res.wt);
    const templateUses = [...new Set([...res.wt.matchAll(/\{\{([^|}\n]{1,30})/g)].map((m) => m[1].trim()))]
      .slice(0, 25);
    console.log(`  表格=${hasTable}  对白关键词=${hasSpeakerCol}`);
    console.log(`  模板: ${templateUses.join(' | ')}`);
    console.log('  --- 前 700 字 ---');
    console.log(res.wt.slice(0, 700).split('\n').map((s) => '   ' + s).join('\n'));
  }
})();
