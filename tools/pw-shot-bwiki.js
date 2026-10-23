// 用 playwright 打开 BWiki 页面：截图 + 抽取渲染后的正文（验证"界面"和 wikitext 是否一致）
const fs = require('fs');
const path = require('path');
const { chromium } = require('D:/AITools/mcps/playwright/node_modules/playwright-core');

const OUT = path.join(__dirname, '..', 'data', 'shots');
fs.mkdirSync(OUT, { recursive: true });

const pages = [
  { name: 'kaituo-renwu', url: 'https://wiki.biligame.com/sr/' + encodeURIComponent('开拓任务') },
  { name: 'yinnian', url: 'https://wiki.biligame.com/sr/' + encodeURIComponent('银辇啊，迅赴那黑色大地') },
];

(async () => {
  const browser = await chromium.launch({
    executablePath: 'D:/AITools/mcps/browsers/chromium-1243/chrome-win64/chrome.exe',
    headless: true,
  });
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, locale: 'zh-CN' });
  const page = await ctx.newPage();

  for (const p of pages) {
    const t0 = Date.now();
    await page.goto(p.url, { waitUntil: 'networkidle', timeout: 90000 }).catch((e) => console.log('goto warn: ' + e.message));
    await page.waitForTimeout(1500);

    const info = await page.evaluate(() => {
      const body = document.querySelector('#mw-content-text') || document.body;
      const h2 = [...body.querySelectorAll('h2 .mw-headline, h2')].map((h) => h.textContent.trim()).filter(Boolean);
      const links = [...body.querySelectorAll('a')].length;
      const text = body.innerText;
      const dialogs = (text.match(/^[^\s：:]{1,10}[：:]/gm) || []).length;
      return { title: document.title, h2, links, textLen: text.length, dialogs, canvas: body.querySelectorAll('canvas').length };
    });
    const shot = path.join(OUT, `${p.name}.png`);
    await page.screenshot({ path: shot, fullPage: true });
    const txtFile = path.join(OUT, `${p.name}.rendered.txt`);
    fs.writeFileSync(txtFile, await page.evaluate(() => (document.querySelector('#mw-content-text') || document.body).innerText), 'utf8');

    console.log(`\n### ${p.name}  (${Date.now() - t0} ms)`);
    console.log(`  title=${info.title}`);
    console.log(`  h2=${JSON.stringify(info.h2)}`);
    console.log(`  链接=${info.links}  渲染文本=${info.textLen} 字  行首"角色:"式=${info.dialogs}`);
    console.log(`  截图=${shot}  (${(fs.statSync(shot).size / 1024).toFixed(0)} KB)`);
    console.log(`  正文=${txtFile}`);
  }
  await browser.close();
})().catch((e) => { console.error('FAIL: ' + e.stack); process.exit(2); });
