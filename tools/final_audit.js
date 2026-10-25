/** final_audit.js — 最终归档核对（按 docs/交付物规格.md §5 清单） */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.join(__dirname, '..');
const jp = (p) => path.join(ROOT, p);
const results = [];
const ok = (name, cond, detail = '') => results.push({ name, pass: !!cond, detail });

// 1. 图 / CSV / meta 数量
function walk(dir, ext) {
  let out = [];
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    const s = fs.statSync(p);
    if (s.isDirectory()) out = out.concat(walk(p, ext));
    else if (f.endsWith(ext)) out.push(p);
  }
  return out;
}
const pngs = walk(jp('docs/report/figures'), '.png');
const csvs = fs.readdirSync(jp('data/plot_data')).filter((f) => f.endsWith('.csv'));
const metas = fs.readdirSync(jp('data/plot_data')).filter((f) => f.endsWith('.meta.json'));
ok('图数 = 配对 CSV 数 = 配对 meta 数', pngs.length === csvs.length && csvs.length === metas.length, `png=${pngs.length} csv=${csvs.length} meta=${metas.length}`);

// 2. sha256 校验
let shaOk = 0, shaBad = [];
for (const m of metas) {
  const j = JSON.parse(fs.readFileSync(jp('data/plot_data/' + m), 'utf8'));
  const csvName = String(j.plot_data_csv || '').split('/').pop();
  const csvPath = jp('data/plot_data/' + csvName);
  if (!fs.existsSync(csvPath)) { shaBad.push(m + ' (csv missing)'); continue; }
  const h = crypto.createHash('sha256').update(fs.readFileSync(csvPath)).digest('hex').slice(0, 16);
  if (h === j.data_sha256_16) shaOk++; else shaBad.push(m);
}
ok('meta 的 data_sha256_16 与 CSV 一致', shaBad.length === 0, `ok=${shaOk} bad=${shaBad.length}${shaBad.length ? ' ' + shaBad.slice(0, 3).join(',') : ''}`);

// 3. figures-index 行数
const idx = fs.readFileSync(jp('docs/report/figures-index.md'), 'utf8').split('\n').filter((l) => l.trim().startsWith('|') && !l.includes('---') && !l.includes('图文件'));
ok('figures-index 数据行数 = 图数', idx.length === pngs.length, `index=${idx.length} png=${pngs.length}`);

// 4. 模型 manifest
for (const mf of ['data/models/manifest.json', 'data/models/manifest_sbert.json']) {
  const m = JSON.parse(fs.readFileSync(jp(mf), 'utf8'));
  const arts = m.artifacts || [];
  const miss = arts.filter((a) => !fs.existsSync(jp('data/models/' + (a.file || a.name))));
  ok(`${mf} 文件全部存在`, miss.length === 0, `${arts.length - miss.length}/${arts.length}`);
}

// 5. ids 对齐
const ids = JSON.parse(fs.readFileSync(jp('data/models/ids.json'), 'utf8'));
ok('ids.records 长度 = 26332', ids.records.length === 26332, `records=${ids.records.length}`);
ok('ids.segments 长度 = 686', ids.segments.length === 686, `segments=${ids.segments.length}`);
ok('ids.oracles 长度 = 13', ids.oracles.length === 13, `oracles=${ids.oracles.length}`);

// 6. sbert 模型本体
ok('sbert_model 本地存在（离线可用）', fs.existsSync(jp('data/models/sbert_model/config.json')) && fs.existsSync(jp('data/models/sbert_model/model.safetensors')), fs.readdirSync(jp('data/models/sbert_model')).join(','));

// 7. 角色向量
const npz = fs.existsSync(jp('data/models/character_centroids.npz'));
const cc = JSON.parse(fs.readFileSync(jp('data/config/character-centroids.json'), 'utf8'));
ok('角色质心产物存在（14 角色）', npz && Object.keys(cc.characters).length === 14, `npz=${npz} chars=${Object.keys(cc.characters).length}`);

// 8. L3 笔记
const l3 = fs.readdirSync(jp('data/reports/l3')).filter((f) => f.endsWith('.md'));
const l3arch = fs.readdirSync(jp('AnalysisV2/notes/l3')).filter((f) => f.endsWith('.md'));
ok('L3 笔记 14 份 + 归档 14 份', l3.length === 14 && l3arch.length === 14, `runtime=${l3.length} archive=${l3arch.length}`);

// 9. context 表（14 主角 + 荒笛历史派生，共 15 个）
const ctx = fs.readdirSync(jp('data/context')).filter((f) => f.endsWith('.jsonl'));
ok('上下文表 ≥14 个角色（含荒笛历史派生）', ctx.length >= 14, `files=${ctx.length}`);

// 10. 报告章节
const drafts = fs.readdirSync(jp('AnalysisV2/draft')).filter((f) => f.endsWith('.md'));
const merged = fs.existsSync(jp('AnalysisV2/报告.md'));
ok('报告 7 章草稿 + 术语表 + 合并稿', drafts.length >= 7 && merged, `drafts=${drafts.length} merged=${merged}`);

// 11. git 状态（忽略 AnalysisV1 与派生目录）
const { execSync } = require('child_process');
let st = '';
try { st = execSync('git status --short', { cwd: ROOT, encoding: 'utf8' }); } catch (e) { st = String(e.stdout || ''); }
const dirty = st.split('\n').filter((l) => l.trim() && !l.includes('AnalysisV1/') && !l.includes('frontend/') && !l.includes('data/context/') && !l.includes('data/models/') && !l.includes('data/plot_data/') && !l.includes('data/reports/') && !l.includes('data/corpus/'));
ok('git 工作区干净（派生数据除外）', dirty.length === 0, dirty.slice(0, 5).join(' | ') || 'clean');

// 输出
const pass = results.filter((r) => r.pass).length;
console.log('=== 归档核对 ===');
for (const r of results) console.log((r.pass ? '✅' : '❌') + ' ' + r.name + ' —— ' + r.detail);
console.log(`\n通过 ${pass}/${results.length}`);
fs.writeFileSync(jp('docs/report/final-audit.md'), ['# 最终归档核对结果', '', '> 由 `tools/final_audit.js` 生成', '',
  '| 检查项 | 结果 | 详情 |', '|---|---|---|',
  ...results.map((r) => `| ${r.name} | ${r.pass ? '✅' : '❌'} | ${String(r.detail).replace(/\|/g, '/')} |`),
  '', `**通过 ${pass}/${results.length}**`].join('\n'), 'utf8');
if (pass !== results.length) process.exitCode = 1;
