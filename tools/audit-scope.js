// 核对本次抽取的真实范围：哪些章节、哪些任务类型、哪些版本
const fs = require('fs');
const path = require('path');

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0';
const RAW = path.join(__dirname, '..', 'data', 'raw');

async function ask(q) {
  const u = 'https://wiki.biligame.com/sr/api.php?action=ask&format=json&query=' + encodeURIComponent(q);
  const r = await fetch(u, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(40000) });
  const j = await r.json();
  if (j.error) throw new Error(JSON.stringify(j.error));
  return Object.keys(j.query.results || {});
}

(async () => {
  // 1) 开拓任务页里我解析到的章节
  const html = fs.readFileSync(path.join(RAW, 'bwiki-kaiTuoRenWu.html'), 'utf8');
  const region = html.slice(html.indexOf('<div class="mw-parser-output"'));
  const h2 = [...region.matchAll(/<h2[^>]*>[\s\S]*?<span class="mw-headline"[^>]*>([\s\S]*?)<\/span>/g)].map((m) =>
    m[1].replace(/<[^>]+>/g, '').trim()
  );
  console.log('【开拓任务页的章节】共 ' + h2.length + ' 个');
  h2.forEach((t, i) => console.log(`  ${i}. ${t}${t.includes('翁法罗斯') ? '   ← 只取了这一章' : '   ← 未取'}`));

  // 2) 实际抓取的 74 个页面：按系列 / 版本归组
  const meta = JSON.parse(fs.readFileSync(path.join(RAW, 'amphoreus-quest-index.json'), 'utf8'));
  const qm = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'corpus', 'quest-meta.json'), 'utf8'));
  const metaByTitle = new Map(qm.map((m) => [m.task, m]));
  console.log(`\n【实际抓取页面】${meta.length} 个（索引来自 分类:开拓任务 + 任务地区::翁法罗斯）`);

  const byVer = {};
  const bySeries = {};
  for (const r of meta) {
    byVer[r.版本] = (byVer[r.版本] || 0) + 1;
    const m = metaByTitle.get(r.任务) || {};
    const s = (m['系列任务'] || '').replace(/\[\[|\]\]/g, '').trim() || '(无/系列汇总页)';
    (bySeries[s] = bySeries[s] || []).push(r.任务);
  }
  console.log('按版本: ' + Object.entries(byVer).sort().map(([v, c]) => `${v}:${c}`).join('  '));
  console.log('按系列任务:');
  Object.entries(bySeries).forEach(([s, arr]) => console.log(`  ${s}  (${arr.length} 页)`));

  // 3) 被排除掉的任务类型（同样在翁法罗斯地区）
  console.log('\n【未抓取：翁法罗斯地区的其他任务类型】');
  for (const cat of ['同行任务', '冒险任务', '日常任务', '活动任务', '系列任务']) {
    try {
      const list = await ask(`[[分类:${cat}]][[任务地区::翁法罗斯]]|limit=500`);
      const missing = list.filter((t) => !meta.some((r) => r.任务 === t));
      console.log(`  ${cat}: 共 ${list.length} 个，未抓 ${missing.length} 个` + (missing.length ? `  例: ${missing.slice(0, 4).join(' / ')}` : ''));
    } catch (e) {
      console.log(`  ${cat}: 查询失败 ${e.message}`);
    }
  }

  // 4) 是否存在"第四幕•翁法罗斯"章节里有、但我漏掉的
  const secStart = region.indexOf('第四幕•翁法罗斯');
  const nextH2 = region.indexOf('<h2', secStart);
  const section = region.slice(secStart, nextH2 > 0 ? nextH2 : undefined);
  const links = [...section.matchAll(/<a\s+href="\/sr\/([^"#?]+)"[^>]*title="([^"]*)"/g)].map((m) => m[2]);
  const uniqLinks = [...new Set(links)].filter((t) => t && !t.includes('展开'));
  const missingInSection = uniqLinks.filter((t) => !meta.some((r) => r.任务 === t));
  console.log(`\n【章节链接核对】第四幕•翁法罗斯段链接 ${uniqLinks.length} 个；不在我抓取清单里的 ${missingInSection.length} 个`);
  if (missingInSection.length) console.log('  ' + missingInSection.join(' / '));
})();
