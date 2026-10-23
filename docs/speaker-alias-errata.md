# speaker-alias 外部复核勘误记录（v2 → v3）

> 来源：外部模型（Gemini）对 v2 配置与 5 份相关文档的交叉比对；本文件记录逐条采纳情况。
> 生成脚本：`tools/patch-alias-v3.js`；输出配置：`data/config/speaker-alias.v3.json`

## 采纳清单

| # | 类别 | 改动 |
|---|---|---|
| A | 关系反转 | 开拓者.called_by["星期日"] 移除「老日」 |
| A | 关系反转 | 星期日.called_by["开拓者"] 新增「老日」（开拓者叫星期日） |
| A | 关系反转 | address_scan_index["老日"] 指向改为 ["星期日"] |
| B | 越界版本 | 开拓者.form_titles_by_path 移除「欢愉」（4.2 版本，超出 3.0–3.7 范围） |
| C | 梗名污染 | 风堇.aliases 移除梗名「粉色芭芭拉」→ meme_terms |
| C | 梗名污染 | 丹恒.aliases 移除梗名「盾丹」→ meme_terms |
| C | 梗名污染 | 丹恒.aliases 移除梗名「炖蛋」→ meme_terms |
| C | 梗名污染 | 三月七.aliases 移除梗名「冷面小粉龙」→ meme_terms |
| C | 梗名污染 | 三月七.aliases 移除梗名「纠缠之缘」→ meme_terms |
| C | 梗名污染 | 姬子.aliases 移除梗名「狗粮大队长」→ meme_terms |
| C | 梗名污染 | 姬子.aliases 移除梗名「养母」→ meme_terms |
| D | 误杀正式爵位 | meme_terms 移除「剑旗爵」（海瑟音正式爵位，非梗名） |
| E | 多义称呼 | address_scan_index["救世主"] 改为多义 ["白厄","开拓者"] |
| E | 多义称呼 | address_scan_index["伙伴"] 改为多义 ["开拓者","白厄","昔涟"] |
| E | 多义称呼 | address_scan_index["心中的英雄"] 改为多义 ["白厄","开拓者"] |
| F | 推断升级 | medium 推断升级为 confirmed：9 条 literal 映射 |
| G | 架构拍板 | 萨姆 → 流萤 + form=萨姆（合并） |
| G | 架构拍板 | 第一面镜 → 面镜 + form（保持合并） |
| G | 架构拍板 | 第二面镜 → 面镜 + form（保持合并） |
| G | 架构拍板 | 第三面镜 → 面镜 + form（保持合并） |
| G | 架构拍板 | 第四面镜 → 面镜 + form（保持合并） |
| G | 架构拍板 | 刻法勒 → 卡厄斯（沿用 v1 判定） |
| H | 未归一处置 | non_speaker_labels 增加「闭嘴」（切分错位标签） |
| H | 未归一处置 | generic_npc.speaker_aliases 增加 先祖之灵（群体亡魂） |
| H | 未归一处置 | 古怪的弈者 → 来古士 + form（medium） |
| I |  | 流萤.forms 补「萨姆」；form_map["萨姆"]="流萤" |
| I |  | canonical.萨姆 删除 speaker_aliases（修复「萨姆」与 literal_map 的优先级穿透） |
| I |  | 来古士.forms 补「古怪的弈者」 |
| J |  | literal「「君王」」confidence → confirmed |
| J |  | literal「「长夜」」confidence → confirmed |
| J |  | literal「金丝若虫」confidence → confirmed |
| K |  | npc_registry.buckets.generic_npc.label_count → 248 |
| K |  | source_report_bucket.reclassified_from_pending 47 → 48 |
| K |  | meta.coverage_projection.v3_projected 更新为 0 未命中（v1 口径 100%） |
| K |  | known_conflicts 中萨姆条目改写为「已合并」 |
| K |  | pending_manual_review 中已解决项前缀改为【v3 已解决】 |
| L |  | pattern_rules.composite_multi 的 form 说明文字已清理（置 null） |
| L |  | pattern_rules.composite_descriptor 的 form 说明文字已清理（置 null） |

## 说明

- **A 老日**：原文 `星期日 ... 老日〔注：开拓者〕`，意为「开拓者叫星期日为老日」。v2 把它写成了「星期日叫开拓者老日」，方向反了，已纠正。
- **B 欢愉主/雷主**：属 4.2 版本，3.0–3.7 语料不会出现，移除以保持范围纯粹。
- **C 梗名**：`粉色芭芭拉`（原神对比梗）、`盾丹/炖蛋`（玩家黑话）、`冷面小粉龙/纠缠之缘`（配色梗）、`狗粮大队长/养母`（社区梗）均来自 BWiki `{{黑幕}}`，移入 `meme_terms`，台词扫描默认忽略。
- **D 剑旗爵**：海瑟音在第一次逐火之旅的正式爵位，与 金织爵/命运爵/捷足爵/摇光爵 同级，不应作为梗名过滤。
- **E 救世主/伙伴**：`救世主` 在 3.0–3.3 主要指南白厄（万敌常用「救世主」揶揄白厄），3.4 后才转向开拓者；`伙伴` 为白厄、昔涟互称。改为多义，扫描时需结合上下文。
- **F**：10 组 medium 推断经剧情上下文复核全部成立，置信度提升；依据见各 literal 的 `review_note`。
- **G**：4 个架构问题按外部建议拍板——萨姆合并进流萤（form=萨姆）、面镜不拆（canonical=面镜 + form=第N面镜）、泰坦之声留 generic_npc、刻法勒沿用 v1 判定。
- **H**：「闭嘴」是切分错位标签（非说话人）；先祖之灵为群体亡魂（generic_npc）；古怪的弈者映射为来古士（medium，3.5#07 对弈场景）。

## 未采纳/待确认

- 外部建议中「开拓者•欢愉（雷主）」的移除仅作用于 `form_titles_by_path`，`canonical.开拓者` 其余字段不动。
- 若后续重新纳入 4.x 内容，需恢复「欢愉」分支。
## 第二次复核（Gemini 对 v3 的复核）

| # | 类别 | 改动 |
|---|---|---|
| I | 二次复核 | 流萤.forms 补「萨姆」；form_map["萨姆"]="流萤" |
| I | 二次复核 | canonical.萨姆 删除 speaker_aliases（修复「萨姆」与 literal_map 的优先级穿透） |
| I | 二次复核 | 来古士.forms 补「古怪的弈者」 |
| J | 二次复核 | literal「「君王」」confidence → confirmed |
| J | 二次复核 | literal「「长夜」」confidence → confirmed |
| J | 二次复核 | literal「金丝若虫」confidence → confirmed |
| K | 二次复核 | npc_registry.buckets.generic_npc.label_count → 248 |
| K | 二次复核 | source_report_bucket.reclassified_from_pending 47 → 48 |
| K | 二次复核 | meta.coverage_projection.v3_projected 更新为 0 未命中（v1 口径 100%） |
| K | 二次复核 | known_conflicts 中萨姆条目改写为「已合并」 |
| K | 二次复核 | pending_manual_review 中已解决项前缀改为【v3 已解决】 |
| L | 二次复核 | pattern_rules.composite_multi 的 form 说明文字已清理（置 null） |
| L | 二次复核 | pattern_rules.composite_descriptor 的 form 说明文字已清理（置 null） |

- **I 优先级穿透 Bug**：`canonical.萨姆.speaker_aliases` 会把 `萨姆` 注册给 `canonical=萨姆`，导致走「剥引号重试」的变体（如 `「萨姆」`）归到萨姆而非流萤。已删除该 alias，改为 `form_map["萨姆"]="流萤"` + `流萤.forms=["萨姆"]`，`canonical.萨姆` 仅保留为查询索引（对齐「长夜月」的标准写法）。
- **J**：`「君王」`/`「长夜」`/`金丝若虫`/`深海的女王` 四条仍为 `medium-high`，一并升级为 `confirmed`。
- **K 账面同步**：`meta.version` 改回整型 `3`（v2 为数字，避免 `config.meta.version >= 2` 类比较出错）；`coverage_projection` 更新为 0 未命中；`generic_npc.label_count` 与 `reclassified_from_pending` 同步；`known_conflicts`/`pending_manual_review` 文案更新。
- 注：`coverage_projection` 的 100% 是 **v1 语料口径**（23,090 非空 speaker）；v3.1/final 语料因新增记录里有未登记路人，实测 97.58%，两者口径已在该字段内分别标注。
