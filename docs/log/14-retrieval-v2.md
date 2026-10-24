# 14 · 神谕检索 v2（修正 gold/query）

- **时间**：2026-10-24 17:20–17:40
- **目标**：修正 v1「gold 就是吟诵步」的问题，看方法对比能否成立。

## 实际动作

1. 派 `baseline-a`（task-15 A 部分）实现 `tools/retrieval_v2.py`，在原五法（关键词/TF-IDF-char/TF-IDF-word/BM25/LSA）上做 4 个变体：
   - `v1`：原版复现（逐 query 对账 0 差异）；
   - `v2_mask`：query 掩蔽（去掉神谕原句，只留 keywords/metaphors/弱提示）；
   - `v2_noRecite`：候选池剔除含神谕原文的吟诵步（6-gram 覆盖 ≥0.50）；
   - `v2_both`：两者同时。
2. 对 13 条 query 重算 Recall@k / MRR，并专项报告 O10。

## 结果

| 变体 | 最佳方法 | MRR | R@10 | 说明 |
|---|---|---|---|---|
| v1 | 关键词 | 0.731 | 0.92 | 原结论（受 gold 污染） |
| v2_mask | 关键词 | 0.660 | 0.85 | **泄漏仍在**：keywords 本身就是神谕字面（沐浴/黄金/涛声），gold 吟诵步里有这些词 |
| v2_noRecite | — | — | — | 剔除 25 步后，**12/13 条 gold 本身被剔除**（N/A），只剩 O10，n=1 无法比较 |
| v2_both | — | — | — | 同上 |

**O10（唯一不引原文的兑现）**：v1 第 7 名（char）→ mask 第 122 → **noRecite 第 3 名**（char）→ both 第 91。
→ 说明 v1 里 **O11 的吟诵步在污染 O10 的排序**（同词异序），剔除后 O10 明显提前；但 n=1 只是方向性证据。

## 结论

- 两个修正各自暴露同一件事：**gold 与吟诵步不可分割**——mask 去不掉泄漏，noRecite 会删掉 gold。
- **在现有 gold 上无法给出"真语义检索下五法优劣"的可靠结论**；要重评必须先重标"不含神谕原文的兑现场景" gold，或改用句向量。
- 报告里 v2 的写法应为："该 gold 上无法做方法对比 + O10 单例证据"，不能宣称任何方法更优。

## 产出

`tools/retrieval_v2.py`、`data/config/retrieval-v2-results.json`、`data/reports/retrieval-v2.md`

## 状态

完成（v2 结论：gold 需重标）。
