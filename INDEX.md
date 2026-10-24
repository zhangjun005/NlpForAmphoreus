# 本项目总索引（想找东西从这里进）

> 一句话：用《崩坏：星穹铁道》翁法罗斯主线（3.0–3.7）的 26,332 条台词，研究"命定如何被写进语言、被角色认领与改写"。
> 最后更新：2026-10-24 ｜ 报告草稿在 `AnalysisV2/draft/`，进度见 §9。

## 1. 先看这四份（按顺序）

| 文档 | 用途 |
|---|---|
| [`docs/产物总览.md`](docs/产物总览.md) | **通俗版**：每个产物是什么、模型是不是每角色一个、数字怎么回原文 |
| [`docs/README.md`](docs/README.md) | docs 目录指引 |
| [`docs/交付物规格.md`](docs/交付物规格.md) | 图-数据配对规范、模型归档清单、**最终核对清单** |
| [`AnalysisV2/README.md`](AnalysisV2/README.md) | 报告工作区（章节草稿 + L3 笔记归档） |

## 2. 研究设计

- [`docs/方向与理由v2.md`](docs/方向与理由v2.md)：研究问题与方向（主计划）
- [`docs/实验口径与评测方案.md`](docs/实验口径与评测方案.md)：冻结的评测协议
- [`docs/report/outline-annotator.md`](docs/report/outline-annotator.md)：**报告 7 章结构**（剧情 agent 定）
- [`docs/method/向量与角色向量.md`](docs/method/向量与角色向量.md)：向量三层结构（每条台词→角色质心→用法）

## 3. 数据（`data/`，不入 git：版权/体积）

| 路径 | 是什么 |
|---|---|
| `data/corpus/amphoreus.final.jsonl` | **主语料**：26,332 条台词/旁白/选项（带说话人、形态、版本、任务、步骤、重复功能） |
| `data/corpus/segments.jsonl` | 723 个剧情步骤 |
| `data/corpus/oracles.jsonl` | 13 条神谕 + 34 处引用 + O02 泰坦源句 |
| `data/corpus/ruby-pairs.jsonl` | 注音对照表（1,020 对） |

## 4. 配置与分析结果（`data/config/`，入 git，48 个文件）

关键几个：`speaker-alias.v3.json`（谁是谁）、`annotation-labels.json`（74 条标注）、`oracle-fulfillment.v2.json`（13 神谕吟诵/兑现段）、`oracle-citation-coding.json`（34 处引用编码）、`knife-scenes.json`（36 刀子场景）、`key-events.json`（30 关键事件）、`character-trajectory-all.json`（14 角色轨迹）、`oracle-similarity-curves.json`（14 角色曲线）、`l3-open-questions.json`（21 条口径记录）、`song-lyrics.json`（歌词 24 条）。

## 5. 模型（`data/models/`，不入 git）

- **只有一套共享模型**：TF-IDF 向量器、LSA、bge-small 句向量（512 维）+ 模型本体 `sbert_model/`；
- **角色向量**：`character_centroids.npz`（14 角色质心 + 按版本质心，共 124 个）；
- 使用：`tools/encode_text.py --file 歌词.txt --char 白厄`。

## 6. 图 + "它画的数据"（图与索引入 git）

- `docs/report/figures/`：**29 张图**；`data/plot_data/`：**29 份 CSV + 29 份 meta**；
- [`docs/report/figures-index.md`](docs/report/figures-index.md)：图 ↔ 数据 ↔ 脚本 ↔ 来源 一页索引；
- [`docs/report/figure-captions.md`](docs/report/figure-captions.md)：f12/f13/f14 的核验与图注。

## 7. 角色级材料

- 轨迹与覆盖率：`data/reports/character-trajectory-all.md`（14 角色，A11+B3 分区）；
- 上下文表：`data/context/<角色>.jsonl`（每条台词 + 前3/后3）；
- **L3 全量精读笔记**：`AnalysisV2/notes/l3/`（14 份 md + json，入 git）；原始在 `data/reports/l3/`；
- 神谕相似度曲线报告：[`docs/report/oracle-similarity-curves.md`](docs/report/oracle-similarity-curves.md)。

## 8. 专题报告（`data/reports/`，25 份，不入 git）

`annotation-review.md`（标注复核）、`annotation-agreement.md`（κ=0.788）、`baseline-{a,b,b2}-ranking.md`、`style-compare.md`（语体）、`retrieval-v3.md`（检索 v3 负结果）、`knife-scenes.md`（36 场景）、`key-events.md`（30 事件）、`character-trajectory-all.md`、`oracle-citation-timeline.md` 等。

## 9. 报告草稿（`AnalysisV2/draft/`）

| 章 | 文件 | 状态 |
|---|---|---|
| 1 导论（O09 链路缩影） | `01-introduction.md` | 待写 |
| 2 命定如何被写成语言 | `02-written-language.md` | ✅ 初稿 |
| 3 命定如何被角色接管 | `03-takeover.md` | ✅ 已用 L3 重写（五种接管方式） |
| 4 命定如何被兑现 | `04-fulfillment.md` | ✅ 初稿（13 条履历） |
| 5 叙事显著性≠刀子 | `05-salience.md` | 待写 |
| 6 命定的闭环 | `06-closure.md` | ✅ 初稿 |
| 7 结论与局限 | `07-conclusion.md` | 待写 |

## 10. 过程记录与脚本

- 日志：`docs/log/`（01–23）；阶段：`docs/stages/`；方法：`docs/method/`；
- 脚本：`tools/`（语料构建、分析、评测、作图、歌词查询）；图-数据导出：`tools/export_plot_data.py`。

## 11. 怎么核对"产物是否归档正确"

按 [`docs/交付物规格.md`](docs/交付物规格.md) §5 清单：图=CSV=meta 数量、sha256、index 行数、模型 manifest、`sbert_model/` 离线加载、`encode_text.py` 冒烟、`ids.json` 对齐、git 状态。
