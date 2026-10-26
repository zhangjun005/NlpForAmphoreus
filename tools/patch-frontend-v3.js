/** patch-frontend-v3.js — 1) 迷你图 x 轴改为"该角色第 N 次出场"（不再挤在 order 上）
 * 2) sync-assets 额外生成角色 JSON 供前端组件使用
 * 3) 文档"怎么判好坏"→"怎么读"
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

// 1) python: x 轴用角色出场序号
const py = path.join(ROOT, 'tools/make_character_mini_figures.py');
let p = fs.readFileSync(py, 'utf8');
p = p.replace('        xo = [r["order"] for r in curve]', '        xo = list(range(1, len(curve) + 1))  # 该角色第 N 次出场（order 会重复，不能当横轴）');
p = p.replace('a2.annotate(nm, (r["order"], r["sbert_own"])', 'a2.annotate(nm, (xo[curve.index(r)], r["sbert_own"])');
p = p.replace('a2.scatter([r["order"] for r in pts], [r["sbert_own"] for r in pts]', 'a2.scatter([xo[curve.index(r)] for r in pts], [r["sbert_own"] for r in pts]');
p = p.replace('a2.set_title(f"与 {own}（自己的神谕）相似度；标注=关键时刻名称", fontsize=8.5)', 'a2.set_title(f"与 {own}（自己的神谕）相似度（横轴=该角色第 N 次出场）", fontsize=8.5)');
fs.writeFileSync(py, p, 'utf8');
console.log('python 迷你图 x 轴已改');

// 2) sync-assets: 生成 public/data/chars/<char>.json
const sy = path.join(ROOT, 'frontend/scripts/sync-assets.mjs');
let s = fs.readFileSync(sy, 'utf8');
if (!s.includes('charsJson')) {
  s = s.replace(
    "const dataDir = join(frontend, 'public', 'data');",
    `// 角色曲线 CSV → JSON（供前端 Recharts 组件使用）
const charsJsonDir = join(frontend, 'public', 'data', 'chars');
mkdirSync(charsJsonDir, { recursive: true });
const charsCsvDir = join(repo, 'data', 'plot_data', 'chars');
if (existsSync(charsCsvDir)) {
  for (const f of readdirSync(charsCsvDir)) {
    if (!f.endsWith('_mini.csv')) continue;
    const raw = readFileSync(join(charsCsvDir, f), 'utf8').replace(/^\\uFEFF/, '').trim().split(/\\r?\\n/);
    const head = raw[0].split(',');
    const rows = raw.slice(1).map((line) => {
      const parts = line.split(',');
      const o = {};
      head.forEach((h, i) => {
        const v = parts[i];
        o[h] = ['order','n_lines','version_n_records','in_oracle_first','in_recitation','in_fulfillment','in_key_event','in_knife','step_index'].includes(h) ? Number(v) : (h === 'version' ? v : Number(v));
      });
      return o;
    });
    rows.forEach((r, i) => { r.step_index = i + 1; });
    writeFileSync(join(charsJsonDir, f.replace('_mini.csv', '.json')), JSON.stringify(rows));
  }
}

const dataDir = join(frontend, 'public', 'data');`
  );
  s = s.replace(
    "import { copyFileSync, mkdirSync, existsSync, readdirSync } from 'node:fs';",
    "import { copyFileSync, mkdirSync, existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';"
  );
  fs.writeFileSync(sy, s, 'utf8');
  console.log('sync-assets 已加 chars JSON 生成');
}

// 3) 文档术语：怎么判好坏 → 怎么读
for (const rel of ['frontend/docs/13-章节正文.md', 'docs/前端改版-章节正文.md']) {
  const f = path.join(ROOT, rel);
  if (!fs.existsSync(f)) continue;
  let t = fs.readFileSync(f, 'utf8');
  t = t.split('**怎么判好坏**').join('**怎么读**');
  fs.writeFileSync(f, t, 'utf8');
}
console.log('文档「怎么判好坏」→「怎么读」');
