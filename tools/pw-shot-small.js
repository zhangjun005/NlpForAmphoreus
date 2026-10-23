// 小尺寸截图（给用户看渲染效果）+ wikitext 解析结果与渲染文本的一致性核对
const fs = require('fs');
const path = require('path');
const { chromium } = require('D:/AITools/mcps/playwright/node_modules/playwright-core');

const OUT = path.join(__dirname, '..', 'data', 'shots');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'D:/AITools/mcps/browsers/chromium-1243/chrome-win64/chrome.exe',
    headless: true,
  });
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 }, locale: 'zh-CN', deviceScaleFactor: 1 });
  const page = await ctx.newPage();

  const cases = [
    { name: 'qa-index', url: 'https://wiki.biligame.com/sr/' + encodeURIComponent('开拓任务'), anchor: '第四幕•翁法罗斯' },
    { name: 'qa-quest', url: 'https://wiki.biligame.com/sr/' + encodeURIComponent('银辇啊，迅赴那黑色大地'), anchor: '剧情内容' },
  ];

  for (const c of cases) {
    await page.goto(c.url, { waitUntil: 'networkidle', timeout: 90000 });
    await page.waitForTimeout(1200);
    // 滚到目标标题
    await page.evaluate((anchor) => {
      const hs = [...document.querySelectorAll('h1,h2,h3')];
      const h = hs.find((x) => x.textContent.includes(anchor));
      if (h) h.scrollIntoView({ block: 'start' });
    }, c.anchor);
    await page.waitForTimeout(600);
    const file = path.join(OUT, `${c.name}.jpg`);
    await page.screenshot({ path: file, type: 'jpeg', quality: 72 });
    console.log(`截图 ${c.name}: ${(fs.statSync(file).size / 1024).toFixed(0)} KB  -> ${file}`);
  }

  // 一致性核对：随机取语料里的台词，看是否出现在渲染文本里
  const rendered = fs.readFileSync(path.join(OUT, 'yinnian.rendered.txt'), 'utf8');
  const recs = fs
    .readFileSync(path.join(__dirname, '..', 'data', 'corpus', 'amphoreus.jsonl'), 'utf8')
    .trim()
    .split('\n')
    .map(JSON.parse)
    .filter((r) => r.task === '银辇啊，迅赴那黑色大地' && r.kind === 'dialogue');
  let hit = 0;
  const sample = [];
  for (let i = 0; i < recs.length; i += Math.max(1, Math.floor(recs.length / 40))) {
    const r = recs[i];
    const ok = rendered.includes(r.text.replace(/\s+/g, ''));
    if (ok) hit++;
    sample.push(`${ok ? 'OK ' : 'MISS'} ${r.speaker}: ${r.text.slice(0, 34)}`);
  }
  console.log(`\n一致性抽检: ${hit}/${sample.length} 条台词在浏览器渲染文本中命中`);
  sample.slice(0, 8).forEach((s) => console.log('  ' + s));

  await browser.close();
})().catch((e) => { console.error('FAIL: ' + e.stack); process.exit(2); });
