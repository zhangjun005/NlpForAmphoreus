# 翁法罗斯主线语料工程 · 阶段工作记录总览

> 本目录（`docs/stages/`）按**阶段**记录这个项目「做了什么 / 怎么想的 / 为什么这么选」，
> 面向写课程报告、答辩材料、项目复盘的读者，可直接摘引。
> 所有数字以仓库文件实测为准；与旧文档冲突时，本文档标注了两边数字与判断依据（见 `06-qa-and-final.md` 末节）。

## 一句话项目

把 BWiki（`wiki.biligame.com/sr`，「崩坏：星穹铁道」WIKI）上**翁法罗斯主线 3.0–3.7 共 67 个开拓任务页**
的剧情文本，抽成一行一条的结构化 JSONL 语料，供后续 NLP 分析使用。
最终交付：`data/corpus/amphoreus.final.jsonl` = **26,332 条记录 / 566,798 字**（实测复核通过）。

## 阶段划分（7 个阶段 + 本总览）

| # | 文件 | 一句话 | 核心产物 | 关键数字 |
|---|---|---|---|---|
| 00 | `00-direction-review.md` | 先评审 4 个候选 NLP 方案，判定共同前置是「结构化语料」，决定先做语料、不做分析 | `docs/chatWithGemini.md`、范围决策 | 4 个方案 / 1 个范围 |
| 01 | `01-source-research.md` | 逐渠道评估数据源，选定 BWiki MediaWiki API + SMW | 渠道结论表 | 7 个渠道，2 个被 DNS 拦、1 个 API 禁 |
| 02 | `02-acquisition.md` | 用 SMW 取任务索引、`prop=wikitext` 取正文、拓扑排序定剧情顺序 | `wt-cache/` 75 个 wikitext、`quest-order.json` | 75 页索引 → 67 页有效、64 条链边 |
| 03 | `03-parser-iteration.md` | 解析器 4 代迭代，从 0 到 26,332 条 | `amphoreus.jsonl` / `.v31.jsonl` | v1 24,206 → v3.1 26,332（+2,126） |
| 04 | `04-role-aliases.md` | 建「角色称呼集合」，两轮扩表覆盖多写法/称号/形态/复合标签 | `speaker-alias.json` → `.v2` → `.v3` | canonical 38 → 124、literal 25 → 135 |
| 05 | `05-normalization-cleanup.md` | 说话人归一 + 文本清洗（不改原文，只加字段） | `amphoreus.v2.jsonl` | 命中率 82.54%，清洗 6 类 623 条 |
| 06 | `06-qa-and-final.md` | 三份 QA 报告 + 外部复核 + 最终交付 | `data/reports/*.md`、`amphoreus.final.jsonl` | 26,332 条 / 566,798 字 / 归一 97.58% |

## 时间线（2026-10-23，取自 git log 与文件 mtime）

| 时间 | 事件 | 对应阶段 |
|---|---|---|
| 15:45 | 仓库 Initial commit | — |
| 16:39–16:47 | 抓取与解析脚本成形：`fetch-bwiki.js`、`parse-quest-list.js`、`ask-smw.js`、`crawl-amphoreus.js`、`fetch-wikitext.js`、Playwright 探针与截图 | 01、02 |
| 16:47 | 旧版元数据 `quest-meta.json`（含 `undefined`，后弃用） | 02 |
| 17:06–17:09 | 解析器 v2、v3 完成；v1 主语料 24,206 条落盘（`amphoreus.jsonl`） | 03 |
| 17:09 | 提交 `f64fe95`（语料抽取管线） | 03 |
| 20:58 | `fetch-nicknames.js` 抓 31 个 BWiki 角色页标签 | 04 |
| 21:08 | `docs/speaker-aliases.md`（称呼集合 v4） | 04 |
| 21:26 | `data/config/speaker-alias.json`（配置 v1，38 canonical） | 04 |
| 21:35–21:38 | `normalize-corpus.js` 产出 v2 语料 + `corpus-pipeline.md`；`handoff.md` | 05 |
| 21:39 | 提交 `61aee7f`（v2 清洗归一 + 质检 + 交接） | 05 |
| 21:41–21:42 | `report-corpus.js` + 三份 QA 报告（stats / qa-checks / unmatched） | 06 |
| 22:02 | `speaker-alias.v2.json` 扩表 + `speaker-alias-changes.md`（命中率投影 99.37%） | 04 |
| 22:13 | `build-corpus-v31.js` 产出 v3.1 语料 26,332 条 + `corpus-v31.md` | 03 |
| 22:14 | 提交 `24fbe85`（v3.1 + alias v2 + 最终交付语料） | 03、06 |
| 22:25 | 外部复核勘误 `patch-alias-v3.js` → 配置 v3 + `speaker-alias-errata.md`；`finalize-corpus.js` 产出 final | 04、06 |
| 22:26 | 提交 `7b4b41b`（按外部复核修正称呼配置） | 04、06 |

> 说明：初版语料 v1 的时间戳是 17:09，但 v1 的生成脚本是 `build-corpus-v3.js`（v3 解析器），
> 早期 `crawl-amphoreus.js` 的 buggy 产物已被覆盖；详见 `03-parser-iteration.md`。

## 核心产物索引

| 类别 | 路径 | 说明 |
|---|---|---|
| 最终语料 | `data/corpus/amphoreus.final.jsonl`（16.4 MB） | 26,332 条；25 个字段（含归一/清洗/去重标记） |
| 最终人读版 | `data/corpus/amphoreus.final.lines.txt`（4.2 MB） | 每行「任务 \| 步骤 \| 说话人: 台词」 |
| 阶段语料 | `amphoreus.jsonl`(v1, 24,206) / `.v2.jsonl`(24,206) / `.v31.jsonl`(26,332) | 版本链，均不入 git |
| 原始缓存 | `data/raw/wt-cache/*.txt`（75 个，实测 2.48 MB） | **离线重建的唯一输入**，文件名为 URL 编码 |
| 索引/顺序 | `data/raw/amphoreus-quest-index.json`、`data/corpus/quest-order.json` | 75 页索引 / 67 页剧情顺序 |
| 配置 | `data/config/speaker-alias.json` / `.v2.json` / `.v3.json` | 归一配置 v1 / v2 / v3（后者为交付用） |
| 质检报告 | `data/reports/corpus-stats.md`、`qa-checks.md`、`unmatched-speakers.md`、`final-delivery.md`、`final-qa.md` | 统计 / 自检 / 未归一清单 / 交付 / 终检 |
| 过程文档 | `docs/handoff.md`、`corpus-pipeline.md`、`corpus-v31.md`、`speaker-aliases.md`、`speaker-alias-changes.md`、`speaker-alias-errata.md` | 交接 / 清洗 / 补全 / 称呼 / 扩表 / 外部勘误 |
| 脚本 | `tools/*.js`（20 个，无 npm 依赖，Node ≥ 18） | 采集 6 + 解析/生成 5 + 质检 3 + 截图/探针 4 + 配置/杂项 2 |

## 关键决策总表（写报告可直接引这张表）

| # | 决策 | 结论 | 理由出处 |
|---|---|---|---|
| 1 | 是否先做 NLP 分析 | **不先做**，先做语料工程 | 00、`handoff.md` §1.1 |
| 2 | 语料范围 | 只「开拓任务」主线 3.0–3.7 共 67 页 | 00、`data/README.md` 范围决策 |
| 3 | 数据源 | BWiki MediaWiki API + SMW（放弃 hakush / B站字幕 / Fandom / 中文维基 / 萌娘 API） | 01 |
| 4 | 正文获取 | `action=parse&prop=wikitext` 抓原文并缓存，不用 HTML 正文 | 02 |
| 5 | 剧情顺序 | 用页面自带 `前置任务/后续任务` 建链做拓扑排序，同层用 (版本, 编号) 兜底 | 02 |
| 6 | 解析策略 | 纯本地正则逐行解析 wikitext，不引入 MediaWiki 解析器依赖 | 03 |
| 7 | 基线保护 | v1 定稿 24,206 条后不再改；后续修复一律**新增文件**（v2 / v3.1 / final） | 03、05、06 |
| 8 | 文本清洗 | **不改 `text` 原文**，清洗结果写 `text_clean`；归一写 `canonical_speaker`/`form` | 05 |
| 9 | 说话人归一 | 配置驱动，严格优先级；未命中一律 `null` 不猜 | 05 |
| 10 | 泰坦/黄金裔 | 泰坦 ≠ 黄金裔；卡厄斯 ≠ 卡厄斯兰那；铁墓 ≠ 白厄 | 04 |
| 11 | 梗名 | 梗名/网名不入归一（`meme_terms` 负向过滤）；正式爵位「剑旗爵」纠回 | 04、06 |
| 12 | generic_npc | 聚合为一个 canonical，但**必须保留 `speaker_raw`** | 04 |
| 13 | extra 折叠对话 | 不物理拆文件，加 `view=main/extra` 软切分 | 05 |
| 14 | 重复台词 | 不删除，加 `is_duplicate` / `dedup_group` 标记 | 06 |
| 15 | 合规 | 语料不入 git；只在课程/研究范围使用，不公开分发原文 | 01 |

## 最终数字口径速查（均已对本仓库文件实测复核）

| 指标 | 数值 | 来源 |
|---|---|---|
| 任务页 / 版本 / 系列 | 67 / 8（3.0–3.7）/ 8 | `quest-order.json`、语料 |
| 最终记录数 / 原文总字数 | **26,332 / 566,798** | `amphoreus.final.jsonl` |
| v1 记录数 / 字数 | 24,206 / 528,626 | `amphoreus.jsonl` |
| 增量 | +2,126（`: ` 旁白 1,817 + 选项块旁白 209 + 短信 64 + 其他 36） | `amphoreus.v31.jsonl` 的 `origin` |
| kind（final） | dialogue 21,511 / option 2,400 / narration 2,291 / sms 98 / sms_option 32 | final 实测 |
| view（final） | main 24,207 / extra 2,125 | final 实测 |
| 说话人归一（final） | 23,460 / 24,041 非空 speaker = **97.58%**；`canonical=null` 2,872（其中空 speaker 2,291） | final 实测 |
| 说话人归一（v1 用配置 v1） | 19,058 / 23,090 = 82.54% | `corpus-pipeline.md` §2.1 |
| 说话人归一（v1 用配置 v2） | 22,944 / 23,090 = 99.37% | `speaker-alias-changes.md` §0 |
| 重复记录（final，保留并标记） | 1,120 条（626 组；唯一 25,212 条） | final 实测 |
| 文本纯度（final `text_clean`） | `{{`/`}}`/`他/她`/星号/HTML 残留均为 0；空 `text_clean` 0 | `final-qa.md`、实测 |
| 长度分位（final `text`） | P50 18 / P90 43 / P99 69 / max 352 | final 实测 |

> 注意：`data/README.md` 写的是「23,455 / 97.56%」「P90 42 / P99 67」，与实测差 5 条记录与分位口径，
> 差异成因见 `06-qa-and-final.md` §「文档间数字不一致清单」。写报告请以上表为准。

## 怎么用这 8 篇

- **课程报告「相关工作/方案设计」章**：用 `00`（选题来源与判定）+ `01`（数据源对比）。
- **「数据构建/方法」章**：用 `02`（采集）+ `03`（解析迭代）+ `05`（归一清洗），每篇都有「方案→实施→坑」三段。
- **「实验设置/数据质量」章**：用 `04`（称呼体系）+ `06`（质检与交付数字）。
- **答辩可能的追问**：「为什么不用解包数据」「为什么顺序可信」「归一率怎么算的」——分别见 `01`、`02`、`05`/`06`。
