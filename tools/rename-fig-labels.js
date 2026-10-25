/** rename-fig-labels.js — 图内英文缩写改为中文主名：TF-IDF→词频加权、SBERT→语义向量
 * 只改显示标签/标题/轴说明的文字（大写缩写只出现在字符串与注释中，变量名是小写，安全）
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const files = [
  'tools/oracle_similarity_curves.py',
  'tools/export_plot_data.py',
  'tools/character_trajectory.py',
];
for (const rel of files) {
  const p = path.join(ROOT, rel);
  let t = fs.readFileSync(p, 'utf8');
  const before = t.length;
  t = t.split('TF-IDF').join('词频加权');
  t = t.split('SBERT').join('语义向量');
  // 图例里的 A/B1 也改成可读标签
  t = t.split('A mean score').join('检测器 A 分数');
  t = t.split('B1 mean score').join('检测器 B1 分数');
  t = t.split('B1 Top100 %').join('B1 前100命中率(%)');
  fs.writeFileSync(p, t, 'utf8');
  console.log(rel, '长度', before, '->', t.length);
}
