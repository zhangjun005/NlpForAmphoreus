// sync-assets.mjs — 把仓库里的图与章节数据复制进前端 public（构建前自动跑）
import { copyFileSync, mkdirSync, existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const frontend = join(here, '..');
const repo = join(frontend, '..');

const figDir = join(frontend, 'public', 'figures');
mkdirSync(figDir, { recursive: true });

// 需要拷进 public/ 的报告图（源：docs/report/figures/<name>.png）。
// 每张图在 data/plot_data/<name>.csv 有配对数据、在 <name>.meta.json 有 sha256；
// 目录说明见 docs/report/figures-index.md，这里只列页面真正用到的图。
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
  // f17_lyrics_similarity.png：三格横条（14 角色质心 / 昔涟 8 版本质心 / 13 条神谕）与 24 条歌词的相似度；
  // 生成 tools/export_plot_data.py（make_new_figures），配对数据 data/plot_data/f17_lyrics_similarity.csv
  'f17_lyrics_similarity.png',
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

// 角色曲线最高点的原文证据索引：只把每个角色词频/语义最高步骤的少量记录
// 写入前端，避免页面为了说明峰值而加载整份 segments.jsonl。
const segmentsPath = join(repo, 'data', 'corpus', 'segments.jsonl');
const peakEvidence = {};
if (existsSync(segmentsPath)) {
  const byKey = new Map();
  const rawSegments = readFileSync(segmentsPath, 'utf8').split(/\r?\n/).filter(Boolean);
  for (const line of rawSegments) {
    const s = JSON.parse(line);
    const key = [s.version, s.task, s.step_title].join('\u0001');
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push(s);
  }
  for (const file of readdirSync(charsJsonDir)) {
    if (!file.endsWith('.json')) continue;
    const name = file.replace(/\.json$/, '');
    const rows = JSON.parse(readFileSync(join(charsJsonDir, file), 'utf8'));
    const seen = new Map();
    const enriched = rows.map((row) => {
      const key = [row.version, row.task, row.step_title].join('\u0001');
      const idx = seen.get(key) || 0;
      seen.set(key, idx + 1);
      const candidates = byKey.get(key) || [];
      return { row, segment: candidates[idx] || null };
    });
    const makePeak = (field) => {
      const item = enriched.reduce((best, current) => Number(current.row[field] || 0) > Number(best.row[field] || 0) ? current : best, enriched[0]);
      const segment = item.segment;
      const main = (segment?.main_records || []).filter((r) => !['option', 'sms_option'].includes(r.kind));
      const own = main.filter((r) => r.speaker === name);
      const records = (own.length ? own : main).slice(0, 4).map((r) => ({ id: r.id, speaker: r.speaker, kind: r.kind, text: r.text }));
      return {
        step_index: item.row.step_index,
        score: item.row[field],
        version: item.row.version,
        task: item.row.task,
        step_title: item.row.step_title,
        events: Object.fromEntries(['in_oracle_first', 'in_recitation', 'in_fulfillment', 'in_key_event', 'in_knife'].map((k) => [k, item.row[k] || 0])),
        segment_id: segment?.segment_id || null,
        records,
      };
    };
    if (enriched.length) peakEvidence[name] = { tfidf: makePeak('tfidf_own'), sbert: makePeak('sbert_own') };
  }
  writeFileSync(join(dataDir, 'character-peak-evidence.json'), JSON.stringify({
    note: '由角色轨迹峰值与 segments.jsonl 对齐生成；仅展示每角色词频/语义最高步骤的连续记录，不替代原始语料。',
    characters: peakEvidence,
  }));
}

const screens = join(frontend, 'data', 'screens.json');
if (existsSync(screens)) copyFileSync(screens, join(dataDir, 'screens.json'));
const rubyPairs = join(repo, 'data', 'corpus', 'ruby-pairs.jsonl');
if (existsSync(rubyPairs)) copyFileSync(rubyPairs, join(dataDir, 'ruby-pairs.jsonl'));

console.log('[sync-assets] figures + chars + screens.json 已同步');
