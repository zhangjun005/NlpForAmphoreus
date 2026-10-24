# 09 · 可复用 agent 登记

- **时间**：2026-10-24 17:00–17:10
- **目标**：把做过重复工作的子智能体固化成可复用角色，避免以后重新摸索。

## 实际动作

1. 新建 `docs/agents.md`，记录：
   - `annotator`（★常用）：专门读翁法罗斯剧情做判断（标注/争议裁定/个案核对）。写了它的工作方式（读 lines.txt + segments.main_records、依据必须引用原文、隔轮重标自检）、上次产出位置、派活模板要点、以及"汇报数字可能与文件不一致，以文件为准"的坑；
   - `baseline-a`（基线实现者）：会自校验、SHA-256 复现、长度分层、权重敏感性；
   - 其他历史 teammate 归档表（parser-v31/alias-v2/corpus-pipeline/qa-reporter/docs-writer/stage-docs）；
   - 使用建议（派活前建 shared task + write_scopes；Lead 必须复核 JSON/枚举/数字一致性）。
2. 在本轮实际复用 `baseline-a` 做检测器 B（team member 上限 8，不再新建）。

## 输入 / 输出

- 输入：历史 agent 汇报与产出
- 输出：`docs/agents.md`

## 验证

- 下次派活可直接照抄 prompt 模板（输入/产出/硬约束）；
- 实际复用成功：baseline-a 完成 task-10（检测器 B）。

## 问题与处置

- 队友上限 8 → 需要新任务时优先复用现有 teammate（`send_message` 唤醒），而不是新建。

## 状态

完成（持续维护）。
