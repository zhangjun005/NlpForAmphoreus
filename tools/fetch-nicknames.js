/**
 * 只读采集：从 BWiki 角色页抽取「称号 / 全名 / 外文名 / 昵称外号 / 实装版本」
 * 说明：
 *  - 角色页只覆盖「进卡池的角色」，多形态角色是分页的（开拓者•毁灭/存护/同谐/记忆/欢愉 等）
 *  - 无角色页的（NPC、非卡池）会记为 MISSING，不做猜测
 *  - 只写 data/raw/nicknames.txt，不碰语料、不改已有文件
 */
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, '..', 'data', 'raw', 'nicknames.txt');
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0';

// 形态页 + 黄金裔 + 其他重要角色 + NPC 探针
const TITLES = [
  // 主角（多形态）
  '开拓者•毁灭', '开拓者•存护', '开拓者•同谐', '开拓者•记忆', '开拓者•欢愉',
  // 三月七（多形态 + 3.6 形态独立页）
  '三月七•存护', '三月七•巡猎', '长夜月',
  // 丹恒（多形态）
  '丹恒', '丹恒•饮月', '丹恒•腾荒',
  // 黄金裔
  '万敌', '阿格莱雅', '遐蝶', '那刻夏', '赛飞儿', '缇宝', '风堇', '海瑟音', '刻律德菈', '白厄', '昔涟',
  // 其他重要角色
  '黑塔', '大黑塔', '螺丝咕姆', '黑天鹅', '姬子', '瓦尔特', '星期日', '帕姆',
  // NPC / 非卡池探针（预期可能无角色页）
  '荒笛', '来古士', '缇安', '缇宁', '塞涅卡',
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function raw(title) {
  const u = `https://wiki.biligame.com/sr/index.php?title=${encodeURIComponent(title)}&action=raw`;
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch(u, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(30000) });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.text();
    } catch (e) {
      await sleep(600 * (i + 1));
    }
  }
  return null;
}

function field(wt, name) {
  const m = wt.match(new RegExp('\\|\\s*' + name + '\\s*=([^\\n]*)'));
  return m ? m[1].trim() : '';
}

// {{#info:...}} → 〔注：...〕，方便阅读
function readable(s) {
  return s.replace(/\{\{#info:([\s\S]*?)\}\}/g, (m, inner) => `〔注：${inner.replace(/<br\s*\/?>/g, ' / ')}〕`);
}

(async () => {
  const lines = [];
  let hits = 0, missing = 0;
  for (const t of TITLES) {
    let wt = await raw(t);
    let used = t;
    if (!wt) {
      lines.push(`${t}\tMISSING\t(页面不存在或无权限)`);
      missing++;
      console.log(`${t}\tMISSING`);
      continue;
    }
    // 跟随重定向
    const rd = wt.match(/^#重定向\s*\[\[([^\]|]+)/);
    if (rd) {
      const t2 = rd[1].trim();
      const wt2 = await raw(t2);
      if (wt2) { wt = wt2; used = t2; }
    }
    if (!wt.includes('|昵称/外号')) {
      lines.push(`${used}\tNO_NICK_FIELD\t(页面存在但无「昵称/外号」字段，可能不是角色页)`);
      missing++;
      console.log(`${used}\tNO_NICK_FIELD`);
      continue;
    }
    const rec = {
      title: used,
      名称: field(wt, '名称'),
      外文名: field(wt, '外文名'),
      称号: readable(field(wt, '称号')),
      全名: readable(field(wt, '全名')),
      实装版本: field(wt, '实装版本'),
      昵称外号: readable(field(wt, '昵称/外号')),
    };
    hits++;
    lines.push(
      [
        `### ${used}`,
        `名称=${rec.名称}\t外文名=${rec.外文名}\t称号=${rec.称号}\t全名=${rec.全名}\t实装版本=${rec.实装版本}`,
        `昵称/外号=${rec.昵称外号}`,
      ].join('\n')
    );
    console.log(`${used}\tOK\t昵称长度=${rec.昵称外号.length}`);
    await sleep(150);
  }

  fs.writeFileSync(OUT, lines.join('\n\n'), 'utf8');
  console.log(`\n有角色页=${hits}  无/非角色页=${missing}  共 ${TITLES.length}`);
  console.log(`已写入 ${OUT}`);
})();
