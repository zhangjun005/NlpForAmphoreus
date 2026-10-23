// 用普通 HTTP 抓 BWiki 页面（不需要浏览器），并快速分析结构
const fs = require('fs');
const path = require('path');

const URL = 'https://wiki.biligame.com/sr/' + encodeURIComponent('开拓任务');
const OUT_DIR = path.join(__dirname, '..', 'data', 'raw');
fs.mkdirSync(OUT_DIR, { recursive: true });

(async () => {
  const res = await fetch(URL, {
    headers: {
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
      'Accept-Language': 'zh-CN,zh;q=0.9',
    },
    redirect: 'follow',
    signal: AbortSignal.timeout(20000),
  });
  const html = await res.text();
  const file = path.join(OUT_DIR, 'bwiki-kaiTuoRenWu.html');
  fs.writeFileSync(file, html, 'utf8');

  const title = (html.match(/<title>([^<]*)<\/title>/) || [])[1] || '?';
  const count = (re) => (html.match(re) || []).length;
  console.log(`HTTP ${res.status}  finalURL=${res.url}`);
  console.log(`title=${title}`);
  console.log(`HTML 长度=${html.length}  已存=${file}`);
  console.log(
    `结构统计: div=${count(/<div/g)} table=${count(/<table/g)} tr=${count(/<tr/g)} a=${count(/<a\s/g)} h2=${count(/<h2/g)} h3=${count(/<h3/g)}`
  );

  // 内容区
  const bodyStart = html.indexOf('<div class="mw-parser-output"');
  console.log(`mw-parser-output 位置=${bodyStart}`);
  const region = bodyStart >= 0 ? html.slice(bodyStart) : html;

  // 抽取所有站内链接（标题 + href）
  const links = [];
  const re = /<a\s+href="(\/sr\/[^"#?]+)"[^>]*title="([^"]*)"/g;
  let m;
  while ((m = re.exec(region)) && links.length < 4000) links.push({ href: m[1], title: m[2] });
  const uniq = [...new Map(links.map((l) => [l.href, l])).values()];
  console.log(`站内链接(去重)=${uniq.length}`);

  // 分类统计：看看链接标题里"任务/剧情/幕"的分布
  const bucket = {};
  for (const l of uniq) {
    const k = /任务/.test(l.title) ? '任务' : /剧情/.test(l.title) ? '剧情' : /篇|幕|章/.test(l.title) ? '篇章' : '其他';
    (bucket[k] = bucket[k] || []).push(l);
  }
  for (const k of Object.keys(bucket)) console.log(`  [${k}] ${bucket[k].length} 条`);
  console.log('样例（任务类前 12 条）:');
  (bucket['任务'] || []).slice(0, 12).forEach((l) => console.log(`   ${l.title}  ->  https://wiki.biligame.com${l.href}`));

  // 表格里是否有"说话人:台词"式的对白
  const rows = region.match(/<tr[\s\S]*?<\/tr>/g) || [];
  let dialogRows = 0;
  for (const r of rows) if (/：|:/.test(r.replace(/<[^>]+>/g, ''))) dialogRows++;
  console.log(`表格行=${rows.length}  含冒号的行=${dialogRows}`);
})();
