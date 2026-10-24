# 07 · 基线 A（词面 + 局部情绪）

- **时间**：2026-10-24 15:50–16:10
- **目标**：建立"只看局部词面/情绪"的对照基线，量化它的能力边界。

## 实际动作

1. 派 agent `baseline-a`（task-9）实现 `tools/baseline_a.py`（conda `nlpLesson`，jieba + numpy，无新依赖）。
2. 10 个纯局部特征，权重先验固定、和=1.00：
   - 死亡/牺牲/告别 rate 0.18 + top20 0.12；
   - 负面情绪+否定 rate 0.12 + top20 0.08；
   - 第一人称脆弱 rate 0.12 + top20 0.08；
   - `pause_ratio` 0.10；短句 0.07；感叹 0.06；疑问 0.07。
3. 对 686 个合格候选打分排序，产出 JSON（含每特征 raw/z/contrib）+ 报告（Top30、末尾10、长度分层、敏感性 W1–W4、自校验）。
4. Lead 复核：686 条全覆盖、`score=Σcontrib`、两次运行 SHA-256 一致、`--verify` 通过。
5. 写 `data/reports/baseline-a-vs-human.md`：A 与 74 条标注首次对照。

## 输入 / 输出

- 输入：`segments.jsonl`（686 候选）
- 输出：`tools/baseline_a.py`、`data/config/baseline-a-scores.json`（952 KB）、`data/reports/baseline-a-ranking.md`、`data/reports/baseline-a-vs-human.md`

## 关键结果

- Top1：`3.5|囚人啊，踏过日影见沧溟|5`（4.126，回顾旁白死亡意象密集）；分数≥1 仅 21 步；
- 长度偏差：ρ(分数,句数)=**+0.438**，>30 句层占 Top100 的 46%；12 个零信号步并列末位；
- **vs 人工标注（74）**：Spearman **0.4005（另一算法 0.415，并列名次处理不同）**；等级 0 均值 −0.284，等级 1/2/3 = 0.203/0.221/0.233（**几乎持平**）；显著样本排名中位数 159.5；Top20 命中 2；Top100 覆盖 7/28。

## 问题与处置

- 结论：A 只能判断"有没有强信号"，判断不了"转折有多深"——这正是 B 的动机；
- Spearman 两处数字差异（0.4005 vs 0.415）来自并列名次/中位数取法，趋势一致，报告已加注。

## 状态

完成。
