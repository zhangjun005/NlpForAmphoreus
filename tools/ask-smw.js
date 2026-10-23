// SMW ask 探针 + 页面小节样例
const fs = require('fs');
const path = require('path');

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0';

async function ask(query) {
  const u = 'https://wiki.biligame.com/sr/api.php?action=ask&format=json&query=' + encodeURIComponent(query);
  const r = await fetch(u, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(40000) });
  const j = await r.json();
  if (j.error) throw new Error(JSON.stringify(j.error));
  return j.query;
}

(async () => {
  // 1) 小节样例
  const wt = fs.readFileSync(path.join(__dirname, '..', 'data', 'raw', 'wt-银辇啊，迅赴那黑色大地.txt'), 'utf8');
  const at = wt.indexOf('=== 参加航线会议');
  console.log('=== 流程小节样例（参加航线会议） ===');
  console.log(wt.slice(at, at + 1500));

  // 2) SMW ask
  console.log('\n=== SMW ask：翁法罗斯 开拓任务 ===');
  const q = await ask('[[分类:开拓任务]][[任务地区::翁法罗斯]]|?系列任务名|?任务编号|?所属版本|?任务类型|limit=500');
  const results = q.results || {};
  const names = Object.keys(results);
  console.log(`命中任务页=${names.length}`);
  const rows = names.map((n) => {
    const p = results[n].printouts || {};
    const one = (v) => (Array.isArray(v) ? v.map((x) => (x && x.fulltext) || x).join('; ') : v);
    return { 任务: n, 系列: one(p['系列任务名']), 编号: one(p['任务编号']), 版本: one(p['所属版本']) };
  });
  fs.writeFileSync(path.join(__dirname, '..', 'data', 'raw', 'amphoreus-quest-index.json'), JSON.stringify(rows, null, 2), 'utf8');
  rows.slice(0, 15).forEach((r) => console.log(`  ${r.版本}\t${r.编号}\t${r.系列}\t${r.任务}`));
  console.log(`\n共 ${rows.length} 条，已写 data/raw/amphoreus-quest-index.json`);
})();
