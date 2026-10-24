# 20 · 独立双标注与一致性（A2）

- **时间**：2026-10-24 19:20–20:00
- **目标**：补上 GPT/用户都指出的方法弱点——此前只有"同一 agent 隔轮重标"（稳定性），没有**两个互不可见的独立标注**。

## 实际动作

1. 生成盲标清单 `data/config/annotation-sample-ids-only.json`（只含 74 个 segment_id，不含层级/信号/A-B 分数/已有标签）。
2. 用 **`subagent`（独立上下文，不占 team 名额）** 做盲标：禁止读 `annotation-labels.json` / `annotation-sample.json` / `annotation-review.md` / A-B 分数；按「三问机械化规则」输出等级/类型/三问标志/before-after/证据（record_id+quote）/why_not_lower/alternative_level/confidence。
3. 写 `tools/compare-annotations.js` 计算一致性：等级 exact、差≤1、未加权/线性/二次加权 kappa、类型集合 exact、Jaccard、混淆矩阵、分歧清单。
4. **修 bug**：首版加权 kappa 公式写反（得到 −0.27），改为 κ=1−观测加权分歧/期望加权分歧后 → **0.788**。

## 结果

| 指标 | 数值 |
|---|---|
| 样本 | 74 |
| 等级完全一致 | **41/74 = 55.4%** |
| 等级相差 ≤1 | **73/74 = 98.6%** |
| 未加权 kappa | 0.404 |
| 线性加权 kappa | 0.736 |
| **二次加权 kappa** | **0.788** |
| 类型集合完全一致 | 31/74 = 41.9% |
| 类型 Jaccard 均值 | 0.663 |
| 分歧 | 33 条（多数为 ±1；仅 1 条 ±2） |

- 等级分布：annotator 0/1/2/3 = 18/28/17/11；independent = 12/19/21/22 → **独立标注更倾向给高等级**（22 个 3 级 vs 11 个），系统性偏差需在报告里说明；
- 分歧最大的一条：`3.6|大墓|13` annotator 1 vs independent 3（+2）。

## 产出

`data/config/annotation-labels.independent.json`（125 条 evidence，全部带 record_id 且 quote 逐字校验）、`data/reports/annotation-independent-notes.md`（规则边界案例）、`data/config/annotation-agreement.json`、`data/reports/annotation-agreement.md`、`tools/compare-annotations.js`

## 结论与用法

1. 报告里定位为「**独立重复标注**」：κ(quadratic)=0.79 说明**序数判断稳定**，但 exact 55% + 类型集合 42% 说明**边界模糊**，不能当准确率；
2. 33 条分歧 + 等级 3 + A/B 关键差异 = 人工复核优先集（比复标 74 条省得多）；
3. 独立标签可用于**敏感性分析**：换一套标签重看 A/B 结论是否稳定。

## 状态

完成（A2）。待用户复核分歧样本（A5）。
