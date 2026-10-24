# 报告数据表汇总（make_figures.py 自动生成）

> 生成脚本：`tools/make_figures.py` ｜ 重跑命令：`conda run -n nlpLesson python tools/make_figures.py`
> 本文件所有数字由脚本从 JSON/JSONL 现场计算；每行「来源」标注数据文件。
> 图见 `docs/report/figures/`（5 张，均由同一脚本从 JSON 复现，不硬编码）。

## 0. 图表清单

| # | 文件 | 内容 | 数据来源 |
| --- | --- | --- | --- |
| F1 | `docs/report/figures/f1_level_scores.png` | A vs B1 在人工等级 0/1/2/3 上的分数箱线图（展示 B1 拉开深度维度） | baseline-a/b-scores.json + annotation-labels.json |
| F2 | `docs/report/figures/f2_rank_shift.png` | 686 步 A→B1 排名散点（标注 5 个最大提升/下降） | baseline-a/b-scores.json + segments.jsonl |
| F3 | `docs/report/figures/f3_style_features.png` | G1 神谕 / G2 对白 / G3 引用 的语体特征均值 | style-compare-results.json |
| F4 | `docs/report/figures/f4_citation_stage.png` | 34 处引用的 版本×阶段 堆叠分布 | oracle-citation-coding.json |
| F5 | `docs/report/figures/f5_oracle_vs_rest.png` | 13 个神谕兑现段 vs 其余 673 步的 A/B1 分数箱线图（附 p、δ） | baseline-a/b-scores.json + type-and-oracle-significance.json |

## 1. 数据规模与语料统计

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| 记录数 | 26332 | data/corpus/amphoreus.final.jsonl（脚本重算） |
| 台词字数（原文） | 566798 | data/corpus/amphoreus.final.jsonl（脚本重算） |
| 任务页数 | 67 | data/corpus/amphoreus.final.jsonl（脚本重算） |
| 版本数 | 8（3.0 / 3.1 / 3.2 / 3.3 / 3.4 / 3.5 / 3.6 / 3.7） | data/corpus/amphoreus.final.jsonl（脚本重算） |
| 说话人归一命中 | 23460 / 24041 = 97.58% | data/corpus/amphoreus.final.jsonl（脚本重算） |
| 重复记录（保留但标记） | 1120 | data/corpus/amphoreus.final.jsonl（脚本重算） |
| 记录 kind 分布 | dialogue 21511，option 2400，narration 2291，sms 98，sms_option 32 | data/corpus/amphoreus.final.jsonl（脚本重算） |
| 记录 view 分布 | main 24207，extra 2125 | data/corpus/amphoreus.final.jsonl（脚本重算） |
| text 长度 P50 / P90 / P99 / max | 18 / 43 / 69 / 352 | data/corpus/amphoreus.final.jsonl（脚本重算） |

> 与 `data/reports/final-delivery.md` 的交付口径一致（该报告为同一语料的交付说明）。

## 2. 标注与一致性

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| 标注样本数 | 74 | data/config/annotation-labels.json |
| 显著等级分布（0/1/2/3） | 18 / 28 / 17 / 11 | data/config/annotation-labels.json |
| 类型分布（7 类，多标签） | 身份揭示 24，记忆回收 23，神谕/预言 7，关系变化 13，世界规则 27，牺牲/死亡 8，母题回收 9 | data/config/annotation-labels.json |
| 隔轮重标样本数 | 10 | data/reports/annotation-review.md（§4） |
| 等级完全一致率（隔轮） | 9/10 = 90.0% | data/reports/annotation-review.md（§4） |
| 类型集合完全一致率（隔轮，原始） | 6/10 = 60.0% | data/reports/annotation-review.md（§4） |
| 平均类型交集 / 平均 Jaccard | 1.9 个 / 88.3% | data/reports/annotation-review.md（§4） |
| 按统一规则修正后类型一致率 | 100.0% | data/reports/annotation-review.md（§4） |

> 局限：单标注者、无第二标注者，无法计算 Cohen's kappa（见 `data/reports/annotation-review.md` §4）。

## 3. A vs B1 vs B2 主表（74 条人工标注；「显著样本」= 等级 ≥ 2，共 28 条）

| 指标 | A | B1 | B2 | 来源 |
| --- | --- | --- | --- | --- |
| spearman | 0.4005 | 0.5812 | 0.5408 | data/config/baseline-a-scores.json / data/config/baseline-b-scores.json / data/config/baseline-b2-scores.json + data/config/annotation-labels.json |
| 等级 0 平均分 | -0.284 | -0.682 | -0.551 | data/config/baseline-a-scores.json / data/config/baseline-b-scores.json / data/config/baseline-b2-scores.json + data/config/annotation-labels.json（脚本重算） |
| 等级 1 平均分 | 0.203 | 0.163 | 0.232 | data/config/baseline-a-scores.json / data/config/baseline-b-scores.json / data/config/baseline-b2-scores.json + data/config/annotation-labels.json（脚本重算） |
| 等级 2 平均分 | 0.221 | 0.276 | 0.319 | data/config/baseline-a-scores.json / data/config/baseline-b-scores.json / data/config/baseline-b2-scores.json + data/config/annotation-labels.json（脚本重算） |
| 等级 3 平均分 | 0.233 | 0.701 | 0.719 | data/config/baseline-a-scores.json / data/config/baseline-b-scores.json / data/config/baseline-b2-scores.json + data/config/annotation-labels.json（脚本重算） |
| 显著样本在 Top20 / Top50 / Top100 | 2 / 4 / 7 | 2 / 4 / 13 | 1 / 4 / 12 | data/config/baseline-a-scores.json / data/config/baseline-b-scores.json / data/config/baseline-b2-scores.json + data/config/annotation-labels.json（脚本重算） |
| 显著样本中位排名 | 159.5 | 123.0 | 128.5 | data/config/baseline-a-scores.json / data/config/baseline-b-scores.json / data/config/baseline-b2-scores.json + data/config/annotation-labels.json（脚本重算） |
| 长度偏差 ρ(score, n_dialogue) | 0.4381 | 0.6831 | 0.6142 | data/config/baseline-a-scores.json / data/config/baseline-b-scores.json / data/config/baseline-b2-scores.json（length_bias 字段） |

**A→B1 排名关系**（来源 `data/config/baseline-b-scores.json`: a_b_comparison）

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| Top10 / Top20 / Top50 / Top100 重叠 | 0.60 / 0.60 / 0.64 / 0.66 | data/config/baseline-b-scores.json |
| Spearman(A, B1) | 0.8794 | data/config/baseline-b-scores.json |
| 排名变化：中位绝对变化 / 平均 Δ / 提升≥100 数 / 下降≥100 数 | 56.5 / 0.0 / 101 / 101 | data/config/baseline-b-scores.json |

**B2 vs B1**（来源 `data/config/baseline-b2-scores.json`: b2_vs_b1）

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| Top10 / Top20 / Top50 / Top100 重叠 | 0.90 / 0.85 / 0.96 / 0.98 | data/config/baseline-b2-scores.json |
| Spearman(B1, B2) | 0.9898 | data/config/baseline-b2-scores.json |
| 短步数 / 排名中位绝对变化 | 292 / 24.0 | data/config/baseline-b2-scores.json |

## 4. 语体三组表（G1 神谕 / G2 普通对白 / G3 角色引用）

| 特征 | G1 均值 | G2 均值 | G3 均值 | G1−G2 δ / p | G1−G3 δ / p | G2−G3 δ / p | 来源 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 句长（字） | 15.6429 | 13.8674 | 19.1250 | +0.284 / 0.077 | -0.277 / 0.117 | -0.387 / 3.8e-05 | data/config/style-compare-results.json |
| 文言虚词（次/百字） | 9.0198 | 0.9868 | 6.1983 | +0.910 / 2.6e-16 | +0.394 / 0.026 | -0.627 / 6e-18 | data/config/style-compare-results.json |
| 情态词（次/百字） | 7.9768 | 0.8069 | 4.8235 | +0.829 / 2.5e-14 | +0.396 / 0.024 | -0.546 / 8.8e-15 | data/config/style-compare-results.json |
| 第二人称（次/百字） | 5.4928 | 2.3370 | 3.0144 | +0.587 / 3.1e-06 | +0.512 / 0.003 | -0.289 / 0.00014 | data/config/style-compare-results.json |
| 第一人称（次/百字） | 0.3401 | 2.6148 | 0.7491 | -0.247 / 0.056 | -0.094 / 0.394 | +0.167 / 0.025 | data/config/style-compare-results.json |
| 抽象名词比例（/内容词） | 0.1303 | 0.0247 | 0.1181 | +0.648 / 2.7e-08 | +0.062 / 0.728 | -0.658 / 1.2e-17 | data/config/style-compare-results.json |
| 词复沓率（1−不同词/总词） | 0.0190 | 0.0247 | 0.0385 | -0.009 / 0.938 | -0.204 / 0.186 | -0.187 / 0.010 | data/config/style-compare-results.json |
| 排比率（相邻分句共享 bigram） | 0.0000 | 0.0249 | 0.0208 | -0.044 / 0.427 | -0.042 / 0.458 | +0.003 / 0.939 | data/config/style-compare-results.json |
| 称呼词（次/百字） | 0.0000 | 1.2183 | 0.1877 | -0.121 / 0.170 | -0.042 / 0.458 | +0.083 / 0.098 | data/config/style-compare-results.json |
| 感叹号（个/百字） | 0.0000 | 1.4309 | 0.0000 | -0.072 / 0.304 | +0.000 / 1.000 | +0.072 / 0.057 | data/config/style-compare-results.json |
| 问号（个/百字） | 0.0000 | 1.5277 | 0.2604 | -0.121 / 0.170 | -0.021 / 0.616 | +0.100 / 0.042 | data/config/style-compare-results.json |
| 祈使标记（次/百字） | 0.0000 | 1.3478 | 0.2517 | -0.138 / 0.140 | -0.062 / 0.353 | +0.080 / 0.135 | data/config/style-compare-results.json |

> 特征定义与词表见 `data/reports/style-compare.md` §3；MWU 为双侧原始 p（未做 Bonferroni 校正）。

## 5. 引用轨迹表（34 处 occurrences / 33 条唯一记录）

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| 引用处数 / 唯一记录 | 34 / 33 | data/config/oracle-citation-coding.json |
| 阶段分布（7 类） | 原文出现 6，本人引用 5，结局宣告 8，他人解释 7，主动认领 1，改写反转 3，旁白转述 4 | data/config/oracle-citation-coding.json |
| 引用者类别 | 本人 19，敌人 1，他人 10，旁白 4 | data/config/oracle-citation-coding.json |
| 引用形式 | 完整引用 32，半句引用 2 | data/config/oracle-citation-coding.json |
| 是否保留原句 | true（保留原句） 31，false（改动） 3 | data/config/oracle-citation-coding.json |
| 编码不确定条数 | 4 | data/config/oracle-citation-coding.json |
| 逐版本引用数 | 3.1: 4，3.2: 7，3.3: 7，3.4: 6，3.5: 4，3.6: 2，3.7: 4 | data/config/oracle-citation-coding.json |
| 首次引用阶段分布 | 原文出现 6，他人解释 4，旁白转述 2，结局宣告 1 | data/config/oracle-citation-coding.json |
| 最后引用阶段分布 | 结局宣告 7，他人解释 2，本人引用 2，原文出现 1，改写反转 1 | data/config/oracle-citation-coding.json |
| 无跨步时间轴的神谕 | O02、O06、O11、O12、O13 | data/config/oracle-citation-coding.json |
| 镜像对：共享记录 | #20228（O10 记「改写反转」/ O11 记「他人解释」） | data/config/oracle-citation-coding.json |
| 镜像对：同词异序 | 同 tokens / 语序互换 = True（O10/O11 均 21 字） | data/config/oracle-citation-coding.json |
| 镜像对：谁引用谁 | 海瑟音同时说出两套词序（#20228 为 O11 的词序、#20229 为 O10 的词序）；刻律德菈（O11 持有者）从未引用任何一方，O11 的唯一出现处是海瑟音之口；旁白 #20145 将两套词序并置。 | data/config/oracle-citation-coding.json（叙述见 `data/reports/oracle-citation-timeline.md` §5.4） |

## 6. 神谕检索 v1 / v2 表

**v1（原查询 + 686 全池）**（来源 `data/config/oracle-retrieval-results.json`: methods_base）

| 方法 | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| 关键词基线 | 0.615 | 0.923 | 0.923 | 0.923 | 0.731 | data/config/oracle-retrieval-results.json |
| TF-IDF(char) | 0.231 | 0.923 | 1.000 | 1.000 | 0.549 | data/config/oracle-retrieval-results.json |
| TF-IDF(word) | 0.231 | 0.846 | 0.923 | 0.923 | 0.482 | data/config/oracle-retrieval-results.json |
| BM25 | 0.308 | 0.846 | 0.923 | 0.923 | 0.553 | data/config/oracle-retrieval-results.json |
| LSA | 0.154 | 0.769 | 0.923 | 0.923 | 0.376 | data/config/oracle-retrieval-results.json |

**v2-mask（掩蔽 query）**（来源 `data/config/retrieval-v2-results.json`: summary.v2_mask，13 条 query）

| 方法 | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| 关键词基线 | 0.462 | 0.846 | 0.846 | 0.923 | 0.660 | data/config/retrieval-v2-results.json |
| TF-IDF(char) | 0.231 | 0.692 | 0.846 | 0.846 | 0.429 | data/config/retrieval-v2-results.json |
| TF-IDF(word) | 0.154 | 0.692 | 0.846 | 0.846 | 0.400 | data/config/retrieval-v2-results.json |
| BM25 | 0.308 | 0.769 | 0.769 | 0.769 | 0.494 | data/config/retrieval-v2-results.json |
| LSA | 0.077 | 0.385 | 0.538 | 0.615 | 0.220 | data/config/retrieval-v2-results.json |

**v2-noRecite / v2-both 与 O10**（来源 `data/config/retrieval-v2-results.json`）

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| 剔除吟诵步数 / 剩余池 | 25 / 661 | data/config/retrieval-v2-results.json |
| gold 被剔除（N/A）的 query | 12/13（O01、O02、O03、O04、O05、O06、O07、O08、O09、O11、O12、O13） | data/config/retrieval-v2-results.json |
| v2-noRecite 可评 query 数 | 1（仅 O10） | data/config/retrieval-v2-results.json |
| O10 最好名次：v1 / mask / noRecite / both | 7 / 122 / 3 / 91 | data/config/retrieval-v2-results.json |
| 结论 | v1 的 gold 与吟诵步重合：关键词基线 v1 最强；v2 两修正分别暴露「泄漏仍在」与「gold 被删」→ 现有 gold 上无法做真语义五法对比 | data/config/retrieval-v2-results.json |

## 7. Q3 七类型信号表

| 类型 | n | A 中位名次 | B1 中位名次 | 中位提升(A−B1) | A Top100 | B1 Top100 | B1 组内 Spearman | 来源 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| identity（身份揭示） | 24 | 246.5 | 246.0 | +0.5 | 6 | 10 | 0.51 | data/config/type-and-oracle-significance.json |
| memory（记忆回收） | 23 | 294.0 | 273.0 | +21.0 | 5 | 6 | 0.19 | data/config/type-and-oracle-significance.json |
| prophecy（神谕/预言） | 7 | 241.0 | 73.0 | +168.0 | 1 | 4 | 0.06 | data/config/type-and-oracle-significance.json |
| relationship（关系变化） | 13 | 145.0 | 125.0 | +20.0 | 5 | 6 | 0.72 | data/config/type-and-oracle-significance.json |
| world（世界规则） | 27 | 243.0 | 260.0 | -17.0 | 7 | 9 | 0.38 | data/config/type-and-oracle-significance.json |
| sacrifice（牺牲/死亡） | 8 | 130.0 | 86.0 | +44.0 | 2 | 4 | 0.82 | data/config/type-and-oracle-significance.json |
| motif（母题回收） | 9 | 273.0 | 232.0 | +41.0 | 2 | 2 | 0.47 | data/config/type-and-oracle-significance.json |

> B 提升最大的类型：神谕/预言（+168.0）；提升最小：世界规则（-17.0）；组内 ρ 最高：牺牲/死亡（0.82）。

## 8. Q4 神谕兑现显著性表

| 检测器 | gold 中位分 | 其余中位分 | gold 中位名次 | gold 中位百分位 | 进 Top100 | MWU p | Cliff's δ | 来源 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 0.372 | -0.074 | 106 | 0.154 | 5/13 | 8.7e-05 | +0.635 | data/config/type-and-oracle-significance.json |
| B1 | 0.952 | -0.074 | 53 | 0.077 | 11/13 | 1.8e-07 | +0.844 | data/config/type-and-oracle-significance.json |

**按长度分层**（来源 `data/config/type-and-oracle-significance.json`: q4_by_length）

| 长度层 | gold 数 | 其余步数 | A p / δ | B1 p / δ | 来源 |
| --- | --- | --- | --- | --- | --- |
| 1–3 句 | 0 | 65 | —（gold<2，无法检验） | — | data/config/type-and-oracle-significance.json |
| 4–10 句 | 0 | 148 | —（gold<2，无法检验） | — | data/config/type-and-oracle-significance.json |
| 11–30 句 | 0 | 236 | —（gold<2，无法检验） | — | data/config/type-and-oracle-significance.json |
| >30 句 | 13 | 224 | 0.002 / +0.508 | 2.9e-05 / +0.691 | data/config/type-and-oracle-significance.json |

> 解读：13 个兑现段全部落在「>30 句」层，该层内部仍显著（不是单纯长度效应）；但兑现段多为「吟诵神谕原文」的步骤，A/B 的高分含词面构造成分，不能把「神谕兑现」当显著性标签。

## 9. 复现与校验

```bash
conda run -n nlpLesson python tools/make_figures.py
conda run -n nlpLesson python tools/make_figures.py --verify
```

- 5 张图与上表全部由脚本从 JSON/JSONL 现场计算；脚本内不硬编码任何统计数字（只硬编码标签/配色/标题）。
- 中文字体：脚本自动检测（SimHei / Microsoft YaHei / Noto Sans CJK 等）；缺失时自动退回英文标签。
- `--verify` 会检查 5 张 PNG 是否非空、本文件是否包含全部 8 张表头与来源标注。
