# 可复用子智能体（Agent）登记表

> 目的：把做过重复性工作的 teammate 记录下来，以后需要同类工作时直接按这里的"角色说明"派活，不用重新摸索。
> 派活方式：`spawn_teammate(name, description, prompt, context=fresh)`；prompt 里把下面的「输入 / 产出 / 硬约束」抄进去即可。

---

## 1. annotator —— 剧情读解与标注员（★ 常用，务必保留）

**定位**：专门读《崩坏：星穹铁道》翁法罗斯主线原文，做剧情理解类判断（标注、争议裁定、个案核对）。以后凡是需要"弄懂剧情再下判断"的任务，优先调它。

**上次任务**：task-8（74 步显著性标注 + 13 条神谕兑现判定）
**产出位置**：
- `data/config/annotation-labels.json`
- `data/config/oracle-fulfillment.filled.json`
- `data/reports/annotation-review.md`

**能力与工作方式（实测有效）**：
- 能按版本顺序（3.0→3.7）读 `data/corpus/amphoreus.final.lines.txt`，并对指定步骤读 `segments.jsonl` 的 `main_records` 全文 + 前后各 1–2 步上下文；
- 标注时每条 note 必须引用可核查的台词原文；不确定标「不确定」+ confidence=low；
- 会做"隔轮重标"一致性自检（上次等级一致率 90%）；
- 阅读量：723 步骨架 + 74 样本精读（约 6.7 万字）+ 23 个神谕相关步骤全文（合计约 10 万字）。

**派活模板要点**：
1. 先 `team_task_get` → `claim` → 干活 → `complete` → `send_message` 汇报；
2. 输入：`amphoreus.final.lines.txt`、`segments.jsonl`、`annotation-sample.json`、`oracle-fulfillment.json`、`docs/实验口径与评测方案.md` §6/§11.5；
3. 产出：`data/config/*.json` + `data/reports/*.md`（供人审阅的表格 + 依据 + 置信度 + 争议点）；
4. 硬约束：只写指定文件、不改语料、不用 git、不联网、不编造。

**注意**：它的汇报消息里的统计数字可能与文件不一致（上次等级分布就写错了），**以文件为准**，Lead 必须用脚本复核后再采信。

---

## 2. baseline-a —— 基线实现者

**定位**：按口径文档实现某个"基线/检测器"，对全部候选打分并产出可复现的排名与特征明细。
**上次任务**：task-9（词面+局部情绪基线 A）
**产出**：`tools/baseline_a.py`、`data/config/baseline-a-scores.json`、`data/reports/baseline-a-ranking.md`
**特点**：会做 `--verify` 自校验、SHA-256 复现校验、长度分层诊断、权重敏感性分析（W1–W4）；会主动报告长度偏差（ρ=0.438）。

---

## 3. 其他历史 teammate（已归档）

| 名称 | 任务 | 产出 |
|---|---|---|
| `parser-v31` | v3.1 解析补全 | `build-corpus-v31.js`、`amphoreus.v31.jsonl` |
| `alias-v2` | 称呼配置扩表 | `speaker-alias.v2.json`、`speaker-alias-changes.md` |
| `corpus-pipeline` | 语料清洗+归一 | `amphoreus.v2.jsonl`、`normalize-corpus.js` |
| `qa-reporter` | 质检统计 | `data/reports/{corpus-stats,qa-checks,unmatched-speakers}.md` |
| `docs-writer` | 交接文档 | `docs/handoff.md` |
| `stage-docs` | 阶段记录 | `docs/stages/`（8 篇） |

---

## 使用建议

- **剧情理解类** → `annotator`（记住它的工作方式，别让它从零摸索）；
- **算法实现/基线/评测类** → 新建 fresh agent，prompt 里写清"输入 / 产出 / 硬约束 / 复现命令 / 自校验要求"；
- 派活前先建 shared task 并写清 write_scopes，避免多人同写一个文件；
- Lead 必须复核：JSON 合法性、segment_id/枚举合法性、报告与 JSON 一致性、agent 汇报数字 vs 文件数字。
