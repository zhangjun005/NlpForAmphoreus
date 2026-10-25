/** unify-terms.js — 统一术语：TF-IDF（词面表示）/ 句向量（语义表示）/ 余弦相似度（比较方式） */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const jp = (p) => path.join(ROOT, p);
function patch(p, pairs) {
  let t = fs.readFileSync(p, 'utf8');
  let n = 0;
  for (const [a, b] of pairs) {
    if (t.includes(a)) { t = t.split(a).join(b); n++; }
  }
  fs.writeFileSync(p, t, 'utf8');
  console.log(path.basename(p), '替换', n, '处');
}

// 1) 章节正文：ch4 的"词袋相同"
patch(jp('frontend/docs/13-章节正文.md'), [
  ['两条神谕词序互换、词袋相同（见第 1 章）', '两条话用词相同、只换了语序（所以 TF-IDF 分不开，见第 1 章）'],
]);

// 2) 歌词前端参考：SBERT → 句向量（首现括注模型名），表头统一
patch(jp('docs/歌词向量分析-前端参考.md'), [
  ['- **已有向量**：每条台词的 TF-IDF 向量与 512 维句向量（`data/models/vec_rec.joblib`、`Z_sbert_rec.npy`）；',
   '- **已有向量**：每条台词的 TF-IDF 向量（词面）与 512 维句向量（语义；`data/models/vec_rec.joblib`、`Z_sbert_rec.npy`）；'],
  ['- 句向量（SBERT/bge-small-zh-v1.5，512 维，语义向量）：看"意思像不像"。',
   '- 句向量（用 bge-small-zh-v1.5 生成，512 维）：看"意思像不像"。'],
  ['| 角色 | SBERT | TF-IDF |', '| 角色 | 句向量 | TF-IDF |'],
  ['### 4.1 与 14 个角色质心（SBERT，前 6）', '### 4.1 与 14 个角色质心（句向量，前 6）'],
  ['### 4.2 与昔涟 8 个版本质心（SBERT）', '### 4.2 与昔涟 8 个版本质心（句向量）'],
  ['### 4.3 与 13 条神谕（SBERT，前 5）', '### 4.3 与 13 条神谕（句向量，前 5）'],
  ['| 神谕 | 持有者 | SBERT | TF-IDF |', '| 神谕 | 持有者 | 句向量 | TF-IDF |'],
  ['### 4.4 最接近的非歌词台词（SBERT，前 5）', '### 4.4 最接近的非歌词台词（句向量，前 5）'],
  ['SBERT 整体在 0.5–0.6 的叙事基线', '句向量整体在 0.5–0.6 的叙事基线'],
  ['TF-IDF（词面）与 SBERT（语义）会不一致：如对 O02/O09/O11，TF-IDF 几乎为 0，SBERT 却有 0.42',
   'TF-IDF（词面）与句向量（语义）会不一致：如对 O02/O09/O11，TF-IDF 几乎为 0，句向量却有 0.42'],
  ['"sbert": round(float(np.dot(osb[i], qs)), 4)', '"句向量": round(float(np.dot(osb[i], qs)), 4)'],
]);

// 3) 前端章节数据包：ch01 标题/说明统一
patch(jp('docs/前端-章节数据包.json'), [
  ['"title": "两套语言测量，测的不是同一件事"', '"title": "两种表示：TF-IDF 与句向量"'],
  ['"can": "两套方法测的是不同层面；词面相似不足以判定命定归属"', '"can": "TF-IDF 与句向量测的是不同层面；只看词或只看语义都不能判定命定归属"'],
]);

// 4) 报告术语表：补"词袋"与句向量模型说明
patch(jp('AnalysisV2/draft/00-阅读说明与术语表.md'), [
  ['| **TF-IDF** | 一种**按词计数**的文本向量：一个词在本段常见、在全局少见，就更重要。它只看"字面像不像" |',
   '| **TF-IDF** | 一种**按词加权**的文本向量：一个词在本段常见、在全局少见，就更重要。它的前提是"词袋"（只看词出现没有、不看词序），所以只看"字面像不像" |\n| **词袋** | TF-IDF 的建模前提：把文本当成一袋词，不管词序。只在解释 TF-IDF 时用这个词，它不是第三种方法 |'],
  ['| **句向量（SBERT/bge）** | 一种**按语义**把句子变成数字向量的模型；"字面不同但意思像"也能算相似 |',
   '| **句向量** | 一种**按语义**把句子变成数字向量的表示（本文用 bge-small-zh-v1.5 生成，512 维；文中统一叫"句向量"）；"字面不同但意思像"也能算相似 |\n| **SBERT / bge** | 生成句向量的具体模型名，只在本文首次说明时出现；正文不再把它当方法名 |'],
]);

// 5) 同步前端副本（章节正文/术语）
for (const [src, dst] of [
  ['frontend/docs/13-章节正文.md', 'docs/前端改版-章节正文.md'],
  ['docs/歌词向量分析-前端参考.md', 'frontend/docs/10-歌词向量分析.md'],
]) {
  fs.copyFileSync(jp(src), jp(dst));
  console.log('同步', src, '->', dst);
}
