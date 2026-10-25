/** rename-doc-terms.js — 文档里的 SBERT/TF-IDF 统一显示为中文主名（首次出现处补括注一次） */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const files = [
  'docs/report/figure-captions.md',
  'docs/歌词向量分析-前端参考.md',
  'docs/收束三题分析-前端参考.md',
  'docs/明天见母题向量分析-前端参考.md',
];
for (const rel of files) {
  const p = path.join(ROOT, rel);
  if (!fs.existsSync(p)) continue;
  let t = fs.readFileSync(p, 'utf8');
  t = t.split('SBERT').join('语义向量');
  t = t.split('TF-IDF').join('词频加权');
  if (!t.includes('术语对照')) {
    // 在文件开头标题后插入一行对照说明
    const lines = t.split('\n');
    const idx = lines.findIndex((l) => l.startsWith('# '));
    if (idx >= 0) lines.splice(idx + 1, 0, '', '> 术语对照：本文用「词频加权」指 TF-IDF（词面表示）、「语义向量」指 SBERT/bge 句向量（语义表示）。');
    t = lines.join('\n');
  }
  fs.writeFileSync(p, t, 'utf8');
  console.log(rel, '已统一');
}
