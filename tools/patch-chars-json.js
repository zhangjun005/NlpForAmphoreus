/** patch-chars-json.js — chars JSON 补 task/step_title（事件点显示剧情标题）；加风堇 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const sy = path.join(ROOT, 'frontend/scripts/sync-assets.mjs');
let s = fs.readFileSync(sy, 'utf8');
if (!s.includes('titles')) {
  const old = `    const rows = raw.slice(1).map((line) => {
      const parts = line.split(',');
      const o = {};
      head.forEach((h, i) => {
        const v = parts[i];
        o[h] = ['order','n_lines','version_n_records','in_oracle_first','in_recitation','in_fulfillment','in_key_event','in_knife','step_index'].includes(h) ? Number(v) : (h === 'version' ? v : Number(v));
      });
      return o;
    });
    rows.forEach((r, i) => { r.step_index = i + 1; });`;
  const neu = `    // 同名 oracle_sim CSV 提供 task / step_title（事件点标题）
    const curvePath = join(repo, 'data', 'plot_data', 'oracle_sim__' + f.replace('_mini.csv', '') + '.csv');
    let titles = [];
    if (existsSync(curvePath)) {
      const cRaw = readFileSync(curvePath, 'utf8').replace(/^\\uFEFF/, '').trim().split(/\\r?\\n/);
      const cHead = cRaw[0].split(',');
      const ti = cHead.indexOf('task');
      const si = cHead.indexOf('step_title');
      titles = cRaw.slice(1).map((line) => {
        const parts = line.split(',');
        return { task: parts[ti] || '', step_title: parts[si] || '' };
      });
    }
    const rows = raw.slice(1).map((line) => {
      const parts = line.split(',');
      const o = {};
      head.forEach((h, i) => {
        const v = parts[i];
        o[h] = ['order','n_lines','version_n_records','in_oracle_first','in_recitation','in_fulfillment','in_key_event','in_knife','step_index'].includes(h) ? Number(v) : (h === 'version' ? v : Number(v));
      });
      return o;
    });
    rows.forEach((r, i) => {
      r.step_index = i + 1;
      r.task = titles[i] ? titles[i].task : '';
      r.step_title = titles[i] ? titles[i].step_title : '';
    });`;
  if (s.includes(old)) { s = s.replace(old, neu); fs.writeFileSync(sy, s, 'utf8'); console.log('sync-assets 已补 task/step_title'); }
  else console.log('sync-assets 未匹配，需手动改');
}

// python: 加风堇
const py = path.join(ROOT, 'tools/make_character_mini_figures.py');
let p = fs.readFileSync(py, 'utf8');
p = p.replace('"阿格莱雅", "赛飞儿", "开拓者", "三月七", "丹恒"]', '"阿格莱雅", "赛飞儿", "风堇", "开拓者", "三月七", "丹恒"]');
fs.writeFileSync(py, p, 'utf8');
console.log('python CHARS 已加风堇');
