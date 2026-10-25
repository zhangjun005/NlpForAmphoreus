// sync-assets.mjs — 把仓库里的图与章节数据复制进前端 public（构建前自动跑）
import { copyFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const frontend = join(here, '..');
const repo = join(frontend, '..');

const figDir = join(frontend, 'public', 'figures');
mkdirSync(figDir, { recursive: true });

const figures = [
  'f1_level_scores.png',
  'f7_bai_trajectory.png',
  'f8_xi_trajectory.png',
  'f10_coverage.png',
  'f12_mingtian_timeline.png',
  'f13_crystal_flower_semantic.png',
  'f14_mirror_pair_O10_O11.png',
  'f15_retrieval_v3.png',
];
for (const f of figures) {
  const src = join(repo, 'docs', 'report', 'figures', f);
  if (existsSync(src)) copyFileSync(src, join(figDir, f));
}

const dataDir = join(frontend, 'public', 'data');
mkdirSync(dataDir, { recursive: true });
const screens = join(frontend, 'data', 'screens.json');
if (existsSync(screens)) copyFileSync(screens, join(dataDir, 'screens.json'));

console.log('[sync-assets] figures + screens.json 已同步');
