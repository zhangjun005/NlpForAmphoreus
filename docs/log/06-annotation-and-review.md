# 06 · 74 步标注 + 13 条神谕判定（agent）+ 5 条争议裁定

- **时间**：2026-10-24 15:10–15:50
- **目标**：得到人工 gold，供 A/B 检测器评测。

## 实际动作

1. 写 `tools/build-annotation-materials.js`：确定性等距抽样 7 层共 **74 个步骤**（L5 神谕 12 / L6 母题 10 / L4 长步 8 / L3 中长 12 / L2 中等 12 / L1 短步 10 / L7 普通 10），确保昔涟诞生段（`3.7|魔女的孤诣课题|21`）在 L6；同时生成 13 条神谕的候选兑现表（97 个候选）。
2. 派 agent `annotator`（读剧情 + 标注，task-8）：按 3.0→3.7 读 723 步骨架、74 样本 main_records 逐字精读（约 6.7 万字）、23 个神谕相关步骤全文（合计约 10 万字）。
3. annotator 产出：`annotation-labels.json`（74/74）、`oracle-fulfillment.filled.json`（13/13）、`annotation-review.md`（52.7 KB 人审稿）。
4. 一致性自检（隔轮重标 10 条）：等级完全一致 90%、类型集合完全一致 60%、平均 Jaccard 88.3%。
5. Lead 用脚本复核：74 条 segment_id 合法、枚举合法、note 非空；13 条 fulfillment segment 合法、类型分布 字面10/反转2/错位1。
6. 用户裁定 5 条争议（全部维持原判，写入口径 §12）：①回返|17 判 2 正确；②粉碎造像|2 身份线索可用（盗火行者=白厄）；③摇船|11 判 2 没问题；④O09 维持字面（昔涟补全因果）；⑤O10/O11 均算神谕达成（记忆形态也算）。

## 输入 / 输出

- 输入：`segments.jsonl`、`annotation-sample.json`、`oracle-fulfillment.json`、`amphoreus.final.lines.txt`
- 输出：`data/config/annotation-labels.json`（68.6 KB）、`data/config/oracle-fulfillment.filled.json`（49.3 KB）、`data/reports/annotation-review.md`（52.7 KB）、`data/reports/annotation-sample.md`、`data/reports/oracle-fulfillment-review.md`

## 验证

- 等级分布（文件实测）：0:18 / 1:28 / 2:17 / 3:11；置信度 high 42 / medium 31 / low 1；类型 world 27 / identity 24 / memory 23 / relationship 13 / motif 9 / sacrifice 8 / prophecy 7；
- 分层信号有效：L1 短步 7/10 判 0，L6 母题层 7/10 判 3。

## 问题与处置

- agent 汇报消息里的分布数字（0:27/1:22/2:14/3:11）与文件不一致 → **以文件为准**，Lead 用脚本复核；已把该坑写进 `docs/agents.md`；
- 单人标注无法算 kappa → 报告里如实说明，并建议正式报告补第二人标 20 条。

## 状态

完成（定稿）。
