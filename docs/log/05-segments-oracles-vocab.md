# 05 · 步骤实例表、13 条神谕表、四份词表

- **时间**：2026-10-24 14:00–15:10
- **目标**：把分析口径落成可计算的数据结构，为 A/B 检测与神谕检索准备输入。

## 实际动作

1. 写 `tools/build-segments.js`：按 `version|task|step_idx` 聚合出 **723 个步骤实例**（合格候选 686），字段含：
   - 统计：`n_records/n_main/n_dialogue/n_narration/n_option/n_sms`、`char_len`、`speakers`；
   - 标记：`has_option/has_dialogue/system_only/low_content/inferred`；
   - 重复：`pause_ratio`、`motif_count`、`ritual_count`、`structure_count`、`translation_count`、`surface_repetition_count`、`semantic_recall_*`；
   - 顺序：`main_records`（按 `id` 升序的 `{id,kind,speaker,text}`，供滑窗/身份变化计算）；
   - 滑窗：`n_windows`、`short_for_window`（记录数<20 时整步 1 窗）。
2. 第一版只有拼接文本 `text_all`，用户指出"滑窗必须保留原始顺序"→ 加 `main_records` 重跑。
3. 写 `tools/build-oracles.js`：手工整理 **13 条神谕**（12 黄金裔；遐蝶有两条：缇宁解读版 + 玻吕茜亚版），脚本自动：
   - 找引用 occurrence（支持半句引用，如只引「花海尽头…」）；
   - 从注音对归属隐喻（只对白厄预言 O09 成立：汝→白厄、黎明→天外的救世主、灰白的黎明→开拓者）；
   - 按关键词给每条 8 个候选兑现场景（仅提示）。
4. 生成四份词表：`vocab-oracle`(38) / `vocab-motif`(28) / `vocab-address`(55) / `vocab-ballad`(8)。

## 输入 / 输出

- 输入：`amphoreus.final.jsonl`、`ruby-pairs.jsonl`、`speaker-alias.v3.json`
- 输出：`data/corpus/segments.jsonl`（723 行 / 6.47 MB）、`data/corpus/oracles.jsonl`（13 条 / 34 处引用）、`data/config/vocab-*.json`、`tools/build-segments.js`、`tools/build-oracles.js`

## 验证

- 686 合格池与口径文档的 65/148/236/237 长度分布一致；
- `main_records` 样例（3.7|魔女|21）484 条有序记录，首条为旁白「我来为你讲述『迷路迷境』…」；
- 神谕 34 处引用逐条可 grep 核对；13 条兑现 segment 全部为合法 segment_id。

## 问题与处置

- 第一版 `汝→白厄` 被错误挂到全部 13 条神谕（单字注音匹配）→ 改为"display≥2 字 + O09 特例"；
- 步骤长度极不均匀（P50 472 字、最长 9,152 字）→ 引入"步骤内滑窗、评测仍以步骤为单位"的两层粒度（用户认可）。

## 状态

完成。
