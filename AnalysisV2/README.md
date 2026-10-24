# AnalysisV2 —— 翁法罗斯主线 · 报告与分析（我们的版本）

> 与 `AnalysisV1/`（GPT 版本）并列：**V2 以 11 位黄金裔 + 3 位单列角色为口径，正文以剧情解释为主、统计作证据**。
> 报告结构以 `docs/report/outline-annotator.md`（剧情 agent 设计，7 章）为准。
> 状态：**写作中**（章节草稿逐步落盘）。

## 目录结构

```
AnalysisV2/
├── README.md              # 本文件（索引/状态）
│   ├── 00-术语与阅读说明.md   # 大白话术语表（报告最前面）
├── draft/
│   ├── 01-introduction.md     # 导论：从「命定」到「语言」（O09 链路缩影）
│   ├── 02-written-language.md # 命定如何被写成语言（神谕文体；引用靠拢/改写偏离）
│   ├── 03-takeover.md         # 命定如何被角色接管（引用轨迹、镜像对 O10/O11）
│   ├── 04-fulfillment.md      # 命定如何被兑现（13 条意义履历）（待写）
│   ├── 05-salience.md         # 叙事显著性 ≠ 刀子（A/B、检索、Q3/Q4）（待写）
│   ├── 06-closure.md          # 命定的闭环（明天见 / 水晶花 / 结局）（待写）
│   └── 07-conclusion.md       # 结论与局限（待写）
└── notes/
    └── l3/                    # 逐角色全量精读笔记（L3，agent 产出后汇总）
```

## 素材索引（写作时引用）

| 素材 | 位置 |
|---|---|
| 图（29 张）+ 配对数据 | `docs/report/figures/`、`data/plot_data/`、`docs/report/figures-index.md` |
| 图注（f12–f14 已核验） | `docs/report/figure-captions.md` |
| 数据表（8 张） | `docs/report/data-tables.md` |
| 36 刀子场景（完整原文） | `data/config/knife-scenes.json`、`data/reports/knife-scenes.md` |
| 30 关键事件（含义变化） | `data/config/key-events.json`、`data/reports/key-events.md` |
| 13 神谕表 + 吟诵/事件段 | `data/corpus/oracles.jsonl`、`data/config/oracle-fulfillment.v2.json` |
| 引用轨迹编码 | `data/config/oracle-citation-coding.json`、`data/reports/oracle-citation-timeline.md` |
| 语体对比 | `data/reports/style-compare.md` |
| 显著性 A/B/B2 | `data/reports/baseline-a-ranking.md`、`baseline-b-ranking.md`、`baseline-b2-ranking.md` |
| 检索 v1/v2/v3 | `data/reports/oracle-retrieval.md`、`retrieval-v2.md`、`retrieval-v3.md` |
| 角色轨迹/覆盖 | `data/reports/character-trajectory-all.md`、`character-trajectory.md` |
| 神谕相似度曲线 | `docs/report/oracle-similarity-curves.md` |
| 标注与一致性 | `data/reports/annotation-review.md`、`annotation-agreement.md` |
| 方法/流程 | `docs/method/`、`docs/实验口径与评测方案.md`、`docs/交付物规格.md` |

## 口径（必须遵守）

- 黄金裔 = **11 位**；单列 = 开拓者/三月七/丹恒；荒笛、玻吕茜亚仅 NPC 注记；
- 正文以剧情解释为主，统计放节末/附录；纵轴写"与神谕文本的相似度"不写"含义强度"；
- 标注是 **LLM 辅助标注**（kappa 0.788），不是人工 gold；
- 吟诵段 ≠ 兑现事件；检索任务在事件段 gold 上现有方法全部失效（v3 结论），只能作探索性工具。
