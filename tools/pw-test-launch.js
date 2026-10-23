// 探针：测试在当前沙箱下能否用 playwright 直接 launch 已装好的 chromium
const { chromium } = require('D:/AITools/mcps/playwright/node_modules/playwright-core');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'D:/AITools/mcps/browsers/chromium-1243/chrome-win64/chrome.exe',
    headless: true,
  });
  const page = await browser.newPage();
  await page.goto('https://wiki.biligame.com/sr/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log('TITLE=' + (await page.title()));
  console.log('URL=' + page.url());
  await browser.close();
})().catch((e) => {
  console.error('FAIL: ' + e.message);
  process.exit(2);
});
