// sync-assets.mjs — 把仓库里的图与章节数据复制进前端 public（构建前自动跑）
import { copyFileSync, mkdirSync, existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const frontend = join(here, '..');
const repo = join(frontend, '..');

const figDir = join(frontend, 'public', 'figures');
mkdirSync(figDir, { recursive: true });

const figures = [
  'f1_level_scores.png',
  'f4_citation_stage.png',
  'f7_bai_trajectory.png',
  'f8_xi_trajectory.png',
  'f10_coverage.png',
  'f12_mingtian_timeline.png',
  'f13_crystal_flower_semantic.png',
  'f14_mirror_pair_O10_O11.png',
  'f15_retrieval_v3.png',
  'f16_char_oracle_similarity.png',
  'f7a_bai_lines.png',
  'f7b_bai_forms.png',
  'f7c_bai_address.png',
  'f7d_bai_detector.png',
  'f8a_xi_lines.png',
  'f8b_xi_forms.png',
  'f8c_xi_address.png',
  'f8d_xi_detector.png',
  'f14a_mirror_tfidf.png',
  'f14b_mirror_sbert.png',
  'f15a_retrieval_mrr.png',
  'f15b_retrieval_recall.png',
];
for (const f of figures) {
  const src = join(repo, 'docs', 'report', 'figures', f);
  if (existsSync(src)) copyFileSync(src, join(figDir, f));
}

// 角色迷你图（每章多角色展示）
const charsDir = join(repo, 'docs', 'report', 'figures', 'chars');
const charsOut = join(frontend, 'public', 'figures', 'chars');
mkdirSync(charsOut, { recursive: true });
if (existsSync(charsDir)) {
  for (const f of readdirSync(charsDir)) {
    if (f.endsWith('.png')) copyFileSync(join(charsDir, f), join(charsOut, f));
  }
}

// 角色曲线 CSV → JSON（供前端 Recharts 组件使用）
const charsJsonDir = join(frontend, 'public', 'data', 'chars');
mkdirSync(charsJsonDir, { recursive: true });
const charsCsvDir = join(repo, 'data', 'plot_data', 'chars');
if (existsSync(charsCsvDir)) {
  for (const f of readdirSync(charsCsvDir)) {
    if (!f.endsWith('_mini.csv')) continue;
    const raw = readFileSync(join(charsCsvDir, f), 'utf8').replace(/^\uFEFF/, '').trim().split(/\r?\n/);
    const head = raw[0].split(',');
    // 同名 oracle_sim CSV 提供 task / step_title（事件点标题）
    const curvePath = join(repo, 'data', 'plot_data', 'oracle_sim__' + f.replace('_mini.csv', '') + '.csv');
    let titles = [];
    if (existsSync(curvePath)) {
      const cRaw = readFileSync(curvePath, 'utf8').replace(/^\uFEFF/, '').trim().split(/\r?\n/);
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
    });
    writeFileSync(join(charsJsonDir, f.replace('_mini.csv', '.json')), JSON.stringify(rows));
  }
}

const dataDir = join(frontend, 'public', 'data');
mkdirSync(dataDir, { recursive: true });
const screens = join(frontend, 'data', 'screens.json');
if (existsSync(screens)) copyFileSync(screens, join(dataDir, 'screens.json'));

console.log('[sync-assets] figures + chars + screens.json 已同步');
