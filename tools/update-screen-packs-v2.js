/** update-screen-packs-v2.js — 数据包升级为 12 章：插入第2章（模型）与第3章（读图/检测器），并重编号 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const p = path.join(ROOT, 'docs/前端-章节数据包.json');
const j = JSON.parse(fs.readFileSync(p, 'utf8'));
const ch = j.chapters;

const ch02 = {
  id: 'ch02',
  title: '我们建了什么：哪些是拟合的，哪些是拿来用的',
  layout: 'left_figure_right_text',
  figures: [],
  data_files: ['data/models/manifest.json', 'data/models/manifest_sbert.json', 'data/models/character_centroids.npz'],
  key_numbers: {
    fitted: { tfidf_vocab_dim: 11737, lsa_dim: 100, similarity_matrices: '按需预先计算并保存' },
    pretrained_not_trained: 'bge-small-zh-v1.5（只推理，不微调）',
    derived: '14 个角色的质心向量（台词向量平均）',
    not_models: '检测器 A/B1/B2 是规则+特征打分；74 条标注只用于评测',
  },
  can: '每条曲线都可按“词表→向量→余弦”复算',
  cannot: '这些统计结构不代表“理解了剧情”',
};

const ch03 = {
  id: 'ch03',
  title: '图怎么读：坐标轴、分数与 A/B1/B2',
  layout: 'left_text_right_figure',
  figures: ['docs/report/figures/f1_level_scores.png', 'docs/report/figures/f15_retrieval_v3.png'],
  data_files: ['data/plot_data/f1_level_scores.csv', 'data/plot_data/f15_retrieval_v3.csv', 'docs/report/figures-index.md'],
  key_numbers: {
    detector_A: '词面+局部情绪：关键词/情绪词密度 + 相邻步骤语义突变',
    detector_B1: 'A + 叙事结构特征（转折/呼应/重复）',
    detector_B2: '短步骤修复版，已弃用（负结果）',
    score_scale: '标准化分数：0=平均水平，不是百分比',
    axes: {
      f1: 'x=人工显著等级 0–3；y=检测器标准化分数',
      f2: 'x=剧情顺序；y=686 步中的名次（越小越靠前）',
      f6: 'x=36 个刀子场景；y=场景最好名次（A 13/35、B1 25/35）',
      f12: 'x=版本 3.0–3.7；y=出现次数',
      f13: 'x=全局步序；y=与 K36 原文的余弦相似度',
      f14: 'x=全局步序；y=余弦相似度',
      f15: 'x=检索方法；y=MRR（越高越好）',
      f7_f8: 'x=版本；y=台词量/形态数/称呼命中/检测器分数',
    },
  },
  can: '分数可排序、可比较，但只说明“语言变化强度”',
  cannot: '不能说明“哪一段最感人”；检测器没有剧情记忆',
};

// 插入并重编号
const out = [];
let n = 0;
for (const c of ch) {
  if (c.id === 'ch01') {
    out.push({ ...c, id: 'ch01' });
    out.push(ch02);
    out.push(ch03);
  } else {
    out.push({ ...c });
  }
}
out.forEach((c, i) => { c.id = 'ch' + String(i + 1).padStart(2, '0'); });
j.chapters = out;
j.note = '前端章节数据包（12 章）。每项对应一屏：结论句标题、版面方向、要展示的真实数据文件、关键数字、能/不能说明。第 0 章见 frontend/docs/00-故事梗概.md。';
fs.writeFileSync(p, JSON.stringify(j, null, 2), 'utf8');
console.log('章节数 =', out.length);
out.forEach((c) => console.log(c.id, c.title.slice(0, 30)));
