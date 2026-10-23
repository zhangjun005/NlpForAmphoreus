// 探针：通过 CDP 连接外部启动的 chromium（绕开 spawn EPERM）
const { chromium } = require('D:/AITools/mcps/playwright/node_modules/playwright-core');

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9333');
  const ctx = browser.contexts()[0] || (await browser.newContext());
  const page = ctx.pages()[0] || (await ctx.newPage());
  await page.goto('https://wiki.biligame.com/sr/', { waitUntil: 'domcontentloaded', timeout: 90000 });
  console.log('TITLE=' + (await page.title()));
  console.log('URL=' + page.url());
  console.log('HTML_LEN=' + (await page.content()).length);
  await browser.close();
})().catch((e) => {
  console.error('FAIL: ' + e.message);
  process.exit(2);
});
