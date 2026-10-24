# 16 · 报告材料（图表 + 数据表 + 大纲）

- **时间**：2026-10-24 17:45–18:10
- **目标**：把全部分析结果整理成课程报告可直接取用的材料，不改任何结论。

## 实际动作

1. 派 `baseline-a`（task-16）写 `tools/make_figures.py`：只读现有 JSON/JSONL，生成 5 张图 + 数据表，带 `--verify`；matplotlib 已装在 `nlpLesson`，中文用 Microsoft YaHei。
2. 生成 5 张图到 `docs/report/figures/`：
   - `f1_level_scores.png`：A vs B1 在人工等级 0/1/2/3 的箱线图（A 平坦、B1 等级 3 拉到 0.70）；
   - `f2_rank_shift.png`：686 步 A→B1 排名散点 + 5 个最大提升/下降案例；
   - `f3_style_features.png`：G1 神谕 / G2 对白 / G3 引用 三组语体特征；
   - `f4_citation_stage.png`：34 处引用按版本×阶段堆叠；
   - `f5_oracle_vs_rest.png`：神谕兑现 13 段 vs 其余 673 步（附 p 与 Cliff's δ）。
3. 生成 `docs/report/data-tables.md`：10 章节 / 8 张数据表 / 102 行数据 / 117 处来源标注。
4. 写 `docs/report/README.md`：报告章节大纲 + 12 条可直接抄的结论（每条带数字）+ 图表索引 + 复现命令 + 文件索引。
5. Lead 复核：图片非空、数据表数字与 JSON 交叉一致；发现并修正 agent 的一处口径偏差（"显著样本"阈值由等级≥1 改为与 baseline 一致的等级≥2）。
6. 更新口径文档 §8 第 8/9 项为完成，第 10 项（HMM/KG）记为"决定暂不做"。

## 输入 / 输出

- 输入：`annotation-labels.json`、`baseline-{a,b,b2}-scores.json`、`style-compare-results.json`、`oracle-citation-coding.json`、`retrieval-v2-results.json`、`type-and-oracle-significance.json`、`oracle-fulfillment.filled.json`
- 输出：`tools/make_figures.py`、`docs/report/figures/f1..f5.png`、`docs/report/data-tables.md`、`docs/report/README.md`

## 验证

- 5 张图均 >5 KB 且可从 JSON 复现（两次运行 SHA-256 一致）；
- 数据表数字与各 JSON 的 `human_eval` 等字段逐项核对一致；
- 唯一非 JSON 来源是"隔轮重标一致率"（来自 `annotation-review.md`），表中已标注。

## 状态

完成。项目分析阶段结束。
