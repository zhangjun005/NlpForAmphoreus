# 19 · 由剧情 agent 设计最终报告结构 + 29 个关键事件

- **时间**：2026-10-24 19:15–19:50
- **目标**：用户明确"报告结构不按 GPT 的来，交给读过全剧情的 agent 定"，并产出关键事件「含义变化表」。

## 实际动作

1. 建 task-19，把 `docs/方向与理由v2.md` 与现有全部结果（data-tables / knife-analysis / citation-timeline / style-compare / retrieval-v2 / type-and-oracle-significance / annotation-review / oracle-fulfillment.v2）交给 `annotator`。
2. 要求：7 章以内大纲、每章「论点 → 剧情案例 → 证据表/图 → 写作要点」、正文以剧情解释为主统计作附录、给出与 v2 的逐项对应、并提炼 20–30 个关键事件（`before → after` 含义变化）。
3. Lead 复核：章节与 v2 对应、关键事件字段完整、引文 record_id 可核对。

## 结果

### 报告中心论点（agent 版）
> 翁法罗斯的「命定」不是预言写好的事件清单，而是一套被写成固定文体、由角色反复转述—认领—改写、并在旧记忆与旧意象的回收中完成意义翻转的语言机制；真正制造叙事转折的，不是「死亡/牺牲」这类强词，而是「前文被重新解释」的那一刻。

### 7 章结构（`docs/report/outline-annotator.md`）
1. 导论：从「命定」到「语言」（O09 链路 #15680→#16719→#26045 作全文缩影）
2. 命定如何被写成语言（神谕文体；引用靠拢 / 改写偏离）
3. 命定如何被角色接管（引用轨迹、谁替谁念神谕、镜像对 O10/O11）
4. 命定如何被兑现（13 条意义履历：字面 10 / 反转 2 / 错位 1）
5. 叙事显著性不等于刀子（失败案例开篇：K03 万敌告别 A225/B1 308；A/B/B2 边界；29 事件中 8 个与神谕无关）
6. 命定的闭环（3.7「明天见」时间线；Part C 19/60 判定作克制证据）
7. 结论与局限（LLM 辅助标注、小样本、检索 gold 问题、3.5 嵌套闪回、原文本不公开）

另含：与 v2 逐项对应表、可直接用/还需补两张表、方法附录 A1–A7、与旧 README / AnalysisV1 的差异、7 条写作红线。

### 关键事件表 29 条（`data/config/key-events.json` + `data/reports/key-events.md`）
- 前段 5 / 中段 8 / 后段 8 / 终段 8；覆盖 13/13 神谕、关联 28 个刀子场景；**8 条与神谕无关**（用于证明"刀子 ≠ 神谕兑现"）；
- 每条：`segment_id / phase / event_name / meaning_before / meaning_after / related_oracles / related_motifs / confidence / evidence_quote`；引文逐条 substring 校验通过。

## 产出

`docs/report/outline-annotator.md`、`data/config/key-events.json`、`data/reports/key-events.md`

## 状态

完成。报告结构以这份 outline 为准（`docs/report/README.md` 将同步指向它，旧大纲降级为数据索引）。
