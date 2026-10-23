# 翁法罗斯主线语料 · 交接文档

> **给下一个接手的同学**：这份文件回答四个问题——这是什么、数据长什么样、怎么重跑、哪里有坑。
> 字段的权威说明在 [`data/README.md`](../data/README.md)，本文不重复抄写，只补充**上手必需**的信息和**文档没写到的坑**。
>
> 状态（2026-10-23）：v1 语料、v2 初版、质检报告均已产出。
> 文中的数字都是撰写时对仓库文件实测的，方便你重跑后对照验收。

---

## 0. 30 秒速览

一句话：把 BWiki 上「崩坏：星穹铁道」翁法罗斯主线（3.0–3.7，**67 个开拓任务页**）的剧情文本，
抽成一行一条的结构化 JSONL，供 NLP 分析（情感轨迹、角色风格、称呼网络、说话人归属等）使用。

| 指标 | 数值 |
|---|---|
| 任务页 | 67（8 个系列汇总页无正文，已跳过） |
| 记录数 | 24,206（`kind`：dialogue 20,691 / option 2,399 / narration 1,116） |
| 台词字数 | 528,626 |
| 折叠块"额外对话" | 1,459 条（`extra=true`） |
| 不同说话人标签 | 505 个（**未归一**，归一见 v2） |
| 覆盖版本 | 3.0–3.7 共 8 幕 |
| 抓取来源 | `https://wiki.biligame.com/sr/` 的公开 MediaWiki 页面 |

建议阅读顺序：本文 §1–§5（看懂数据）→ §6.2 跑一遍重建（10 秒）→ §6.9 对照验收数字 → §7–§8（坑与待决策）。

---

## 1. 项目定位与范围决策

### 1.1 定位

- 这是一个**语料工程**项目，不是分析项目：目标是「可复现地把 wiki 文本变成干净可用的结构化语料」。
- 分析代码尚未开始写，但 [`docs/chatWithGemini.md`](chatWithGemini.md) 里有 4 个候选 NLP 选题（宿命/抗争语义轴、角色修辞指纹等），
  可作为后续方向参考，**不是已实现的东西**。
- 数据全部来自 wiki 公开页面，未做人工改写；因此「清洗」不是改文本，而是**另加字段**（见 §5.2）。

### 1.2 范围决策（已定，不要再扩大范围）

**只分析主线「开拓任务」**，即 3.0–3.7 的 8 个系列任务（一幕一个系列）、67 个任务页。
明确不纳入：翁法罗斯地区的 7 个冒险任务、4 个活动任务、同行/日常任务、支线，以及书籍/短信/道具文案等散落文本。

理由（原文见 [`data/README.md`](../data/README.md) 的「范围决策」一节）：活动多为整活番外、风格不同；
活动时间线可能早于当前版本，不可靠；支线多与黄金裔关系不大；散落文本时间线更乱。

> 注意：语料里的 `version`（3.0–3.7）指的是**系列任务/幕**，不是"游戏版本更新"。

### 1.3 最小术语表（非玩家也能看懂数据）

| 术语 | 含义 / 在数据里的表现 |
|---|---|
| 开拓任务 / 系列任务 | 主线任务页 / 一幕剧情；`task` 是页名，`series` 是系列名，`version` 是幕号 |
| 黄金裔 | 翁法罗斯的 12 位核心角色（白厄、昔涟、阿格莱雅…），`canonical` 里 `type=golden_heir` |
| 泰坦 | 神性存在，与黄金裔有火种对应关系；**泰坦 ≠ 黄金裔**，不要合并 |
| 「X爵」 | 逐火军将领爵位称号，语料里大量出现 `「冬霖爵」塞涅卡` 这种"称号+本名"署名 |
| 奇美拉 / 梗名 | 形象梗、网名、评书别名，`meme_terms` 里 `type=meme`，**不参与说话人归一** |
| 迷迷 / 昔涟 | 同一存在的不同阶段（迷迷→昔涟），归一为 `canonical=昔涟` + `form` |
| extra / 折叠块 | wiki 里默认折叠的「额外对话（可选闲聊）」，`extra=true`，建议时序分析时排除 |

---

## 2. 数据流

```
BWiki  wiki.biligame.com/sr
  │  ① SMW ask：[[分类:开拓任务]][[任务地区::翁法罗斯]]，limit=500
  ▼
data/raw/amphoreus-quest-index.json      ← 75 页索引（74 + 1 条章节卡片补漏）
  │  ② MediaWiki API action=parse&prop=wikitext（每页间隔 180ms）→ 写缓存
  ▼
data/raw/wt-cache/<encodeURIComponent(页名)>.txt   ← 75 个 wikitext，2.5 MB，**离线重建的唯一输入**
  │  ③ node tools/build-corpus-v3.js（纯本地解析，不联网）
  ▼
data/corpus/amphoreus.jsonl              ← v1 主语料，24,206 条
  │  ④ node tools/normalize-corpus.js（读 v1 + data/config/speaker-alias.json，不联网）
  ▼
data/corpus/amphoreus.v2.jsonl           ← v2：v1 全字段 + canonical_speaker/form/text_clean/view
```

| 阶段 | 脚本 | 输入 | 输出 | 联网 |
|---|---|---|---|---|
| ① 任务索引 | `tools/ask-smw.js` | 无（SMW 查询） | `data/raw/amphoreus-quest-index.json` | ✅ |
| ② 正文缓存 | `tools/crawl-amphoreus.js`（内置 `apiWikitext`） | 索引 + 缓存命中检查 | `data/raw/wt-cache/*.txt` | ✅（缺失才抓） |
| ③ v1 解析 | `tools/build-corpus-v3.js` | `data/raw/wt-cache/` | `amphoreus.jsonl` / `.lines.txt` / `quest-order.json` | ❌ |
| ④ v2 归一清洗 | `tools/normalize-corpus.js` | v1 + config | `amphoreus.v2.jsonl` / `.v2.lines.txt` | ❌ |
| 旁支：角色标签 | `tools/fetch-nicknames.js` | 硬编码 35 个角色页名 | `data/raw/nicknames.txt` | ✅ |
| 旁支：人工核对 | `tools/pw-shot-*.js` | BWiki 页面 | `data/shots/` 截图 + 渲染文本 | ✅（需 Playwright） |

`build-corpus-v3.js` 的解析要点（读源码可确认）：
先整块剥掉 `{{任务}}` 元数据与 `{{系列任务}}`（否则模板里的清单会被当成旁白），
再**逐行**识别 `==`/`===` 标题（`chapter` 取二级、`step_title/step_idx` 取三级及以下），
然后按行型分别解析：`{{角色对话|…}}`（气泡对白，含 `场景`）、`{{剧情选项}}`（玩家选项 + 分支台词）、
`{{任务描述}}`（地点旁白）、`*角色：台词`（常规对白）、其余 `*` 开头行（旁白），
最后用页面自带的 `前置任务/后续任务` 建链做拓扑排序（同层用版本+编号兜底）。

---

## 3. 文件清单（精简版）

> 完整目录树见 [`data/README.md`](../data/README.md) 的「目录结构」。这里只列**交接时会碰到的文件**。

| 路径 | 是什么 | 谁生成 | 入 git？ |
|---|---|---|---|
| `data/README.md` | **数据目录唯一权威说明**（字段、已知问题、范围决策） | 人工 | ✅ |
| `data/config/speaker-alias.json` | 说话人归一配置（v1，人工维护，见 §4） | 人工 | ✅ |
| `data/corpus/amphoreus.jsonl` | **v1 主语料**，24,206 行 | `build-corpus-v3.js` | ❌ `.gitignore` |
| `data/corpus/amphoreus.lines.txt` | v1 人读版，`grep`/抽查用 | 同上 | ❌ |
| `data/corpus/quest-order.json` | 67 页剧情顺序 + 元数据（`order/prev/next/cast/region`） | 同上 | ❌ |
| `data/corpus/quest-meta.json` | **旧版元数据，含 `undefined`，不要用于分析** | `crawl-amphoreus.js` | ❌ |
| `data/corpus/amphoreus.v2.jsonl` | **v2 语料**（归一 + 清洗，初版，12.0 MB） | `normalize-corpus.js` | ❌ |
| `data/corpus/amphoreus.v2.lines.txt` | v2 人读版 | 同上 | ❌ |
| `data/raw/amphoreus-quest-index.json` | 75 页索引 | `ask-smw.js` | ❌ |
| `data/raw/wt-cache/*.txt` | **75 个任务页 wikitext 缓存，离线重建的唯一依赖** | `crawl-amphoreus.js` | ❌ |
| `data/raw/nicknames.txt` | 31 个角色页的「昵称/外号」字段（4 个 MISSING 标记） | `fetch-nicknames.js` | ❌ |
| `data/shots/` | 渲染截图 + `innerText`，人工核对用 | `pw-shot-*.js` | ❌ |
| `data/reports/` | 质检与统计报告（**已产出 3 份**）：`corpus-stats.md` 总量/分布/Top 说话人、`qa-checks.md` 自检/纯度/README 数字核对、`unmatched-speakers.md` 未归一 speaker 全量清单 | `tools/report-corpus.js` | ❌ |
| `docs/handoff.md` | 本文件 | 人工 | ✅ |
| `docs/corpus-pipeline.md` | v2 的规则、统计、变更示例（**v2 细节看这里**） | `normalize-corpus.js` 任务 | ✅ |
| `docs/speaker-aliases.md` | 角色称呼集合 v4（调研 + 语料实证 + 归一规则草案） | 人工 | ✅ |
| `docs/chatWithGemini.md` | 项目方向讨论原始记录（选题灵感，非实现） | 人工 | ✅ |
| `tools/*.js` | 全部抓取/解析脚本；`build-corpus-v3.js` 是 v1 唯一生成器 | 人工 | ✅ |
| `.tmp/` | 实验区（已 gitignore），可随意折腾 | — | ❌ |

**入库规则**：仓库是公开仓库，`.gitignore` 忽略 `data/corpus/`、`data/raw/`、`data/shots/`、`data/reports/`、`.tmp/`、`*.log`。
也就是说**只有代码、配置、文档入库**；语料与质检报告都是派生产物，靠脚本从 BWiki 重新生成（合规原因见 §9）。
文件名要点：`wt-cache/` 下的文件名是 `encodeURIComponent(页名) + .txt`，用 `decodeURIComponent` 还原。

---

## 4. `data/config/speaker-alias.json` 怎么用

这个文件是**归一规则的唯一数据源**（`normalize-corpus.js` 只读它，不修改它）。
它实际有 **12 个顶层键**——`data/README.md` 第七节只列了 9 个，`normalization_order`、
`non_speaker_labels`、`title_prefix_patterns` 这三块是实现归一必需的，补在这里：

| 键 | 结构 | 用途 | 谁读 |
|---|---|---|---|
| `meta` | 对象 | 版本、范围、范围决策、来源、使用说明 | 人 + 脚本 |
| `normalization_order` | 6 条字符串 | **归一优先级**（见下），脚本按此顺序依次尝试 | `normalize-corpus.js` |
| `non_speaker_labels` | 8 个字符串 | 非说话人标签：`【旁白】/旁白/？？？/遥远的男声/留言石板/神性的回响/系统/未知` | 同上 |
| `title_prefix_patterns` | 3 条正则 | 剥离前缀：`「X爵」` / `「…」` / `『…』` | 同上 |
| `canonical` | 38 个角色 | 规范名 → `type/true_name/titan/speaker_aliases/forms/titles/aliases/called_by/notes` | 归一 + 分析 |
| `form_map` | 32 条 | 形态 → 角色（`迷迷→昔涟`、`缇安/缇宁→缇宝`、`丹枫→丹恒`…） | 归一 |
| `speaker_literal_map` | 25 条 | `speaker` 原样字符串 → `{canonical, form}`（`「冬霖爵」塞涅卡`、`「赛白厄」`…） | 归一（最高优先级） |
| `address_scan_index` | 42 条 | 称呼 → 被称呼者反查（`救世主→开拓者`、`小白→白厄`） | **称呼网络分析**，不参与 speaker 归一 |
| `titan_canonical` | 13 泰坦 | 泰坦称号 + 对应黄金裔 | 分析 |
| `meme_terms` | `{type,note,terms[41]}` | 奇美拉/网名/梗名清单，**排除在归一之外** | 归一（负向过滤） |
| `known_conflicts` | 6 条裁决 | 必须遵守：`卡厄斯≠卡厄斯兰那`、`铁墓≠白厄`、`长夜月→三月七`、`缇安/缇宁→缇宝`、`迷迷→昔涟`、`黑塔人偶/大黑塔→黑塔` | 归一 |
| `pending_manual_review` | 3 条 | 待人工确认项（长尾 NPC、`他/她们俩`、梗名是否入 form） | 人 |

**归一优先级**（`normalization_order`，从高到低，禁止跳步猜测）：
1. `speaker` 精确命中 `speaker_literal_map` → 直接取 `canonical + form`
2. 精确命中 `canonical.speaker_aliases` → 归一
3. 按 `title_prefix_patterns` 剥前缀后重试 1–2
4. 剥成对 `「」『』`、去括号注音后重试
5. 命中 `form_map` → `canonical + form`
6. 仍未命中 → `canonical_speaker=null`，进人工确认清单（预期是路人/NPC）

**三种用法**：
- **语料回填**（v2 已做）：给每条记录加 `canonical_speaker` + `form`；`canonical=null` 保留原 `speaker` 原文。
- **称呼网络**：用 `address_scan_index` 扫 `text` 里"谁在叫谁"，做人物关系图（尚未实现）。
- **一致性校验**：任何分析前先按 `known_conflicts` 检查有没有把两个角色合并了。

---

## 5. 字段字典

### 5.1 v1：`data/corpus/amphoreus.jsonl`（一行一条记录）

| 字段 | 类型 | 说明 | 覆盖 / 实测 |
|---|---|---|---|
| `id` | int | 全局递增，全篇阅读顺序 | 1–24,206 连续 |
| `order` | int | 所属任务在剧情中的序号 | 1–67 |
| `task` | str | 任务页名，如「银辇啊，迅赴那黑色大地」 | 67 个不同值 |
| `version` | str | 幕号 `3.0`–`3.7` | 8 个值 |
| `series` | str | 系列任务名，如「落木逐火英雄纪」 | 8 个值（一幕一个系列） |
| `series_no` | str | 系列内编号 `01`–`10` | — |
| `idx` | int | 任务内序号（从 1 起） | — |
| `chapter` | str | 二级章节名 | **恒为「剧情内容」**（每页只有 1 个 `==`） |
| `step_idx` | int | 任务内步骤序号 | 1–30（页内递增） |
| `step_title` | str | 步骤标题，如「参加航线会议，决定列车的下一站」 | 628 个不同值 |
| `scene` | str | 气泡对白场景名（`{{角色对话|模板开始|场景}}` 包裹范围） | **仅 141 条**，稀疏 |
| `kind` | str | `dialogue` 台词 / `option` 玩家选项 / `narration` 旁白 | 20,691 / 2,399 / 1,116 |
| `speaker` | str | **说话人标签，未归一**；旁白为空串 | 505 个不同值，1,116 条空 |
| `text` | str | 台词正文（已去模板/链接标记，但仍有残留，见 §7） | 无空值 |
| `extra` | bool | 是否在 `{{折叠}}` 块内（额外对话/可选闲聊） | 1,459 条 true |
| `location` | str | `{{任务描述}}` 里的地点 | **稀疏**：254 条有该键、252 条非空 |

示例（v1，一条带 `location` 的旁白）：

```json
{"id":114,"order":1,"task":"银辇啊，迅赴那黑色大地","version":"3.0","series":"落木逐火英雄纪","series_no":"01","idx":114,"kind":"narration","speaker":"","text":"匹诺康尼的旅程再次告一段落。如今列车能源告急，亟需一场足够「开拓」的旅程进行补充。","location":"星穹列车-观景车厢","chapter":"剧情内容","step_idx":2,"step_title":"参加航线会议，决定列车的下一站","extra":false}
```

**使用建议**：`kind=narration` 是"解析器判定的旁白"，**不等于真旁白**——其中 855 条其实是 `标签：台词`（见 §7.2-C）；
做说话人统计用 `speaker`（v1）或 `canonical_speaker`（v2），两套口径不要混用。

### 5.2 v2 新增字段：`data/corpus/amphoreus.v2.jsonl`

v2 = **v1 全字段（含稀疏的 `location`）** + 下面 4 个字段，共 19 个键；不覆盖 `text` 原文：

| 字段 | 类型 | 说明 | 初版实测 |
|---|---|---|---|
| `canonical_speaker` | str \| null | 归一后的规范名；未命中为 `null`（保留原 `speaker`） | `null` 5,148 条（21.3%）；32 个不同规范名 |
| `form` | str \| null | 形态/分身/称号形态（`缇安`、`迷迷`、`长夜月`、`三月七(幻象/相机形态)`…） | 非 null 2,607 条 |
| `text_clean` | str | 清洗后文本（`他/她`→开拓者、去 `*强调*` 星号、去模板/HTML/链接残留） | 2 条示例：`我会看好他/她的。` → `我会看好开拓者的。` |
| `view` | str | 视图字段：`main`（主任线）/ `extra`（折叠额外对话） | `main` 22,747 / `extra` 1,459 |

补充说明（细节与统计以 [`docs/corpus-pipeline.md`](corpus-pipeline.md) 为准）：
- `view` 只是**逻辑切分**，没有物理拆成两个文件；要排除额外对话就 `filter(r => r.view === 'main')`。
- 舞台指示会被改判：`kind` 从 `dialogue` 改为 `narration`，`text_clean` 去掉星号。
- 有 10 条记录的 `text_clean` 清洗后为空（原 `text` 保留），下游用 `text_clean` 时要兜底。

### 5.3 `data/corpus/quest-order.json`（67 条）

`order` / `task` / `version` / `series` / `series_no` / `prev` / `next` / `cast`（出场人物，顿号分隔） / `region`。
⚠️ `prev`/`next` **不能直接当上一页/下一页**用：有 3 条 `next`、2 条 `prev` 带 `#小节锚点`，
且末页 `next` 指向范围外任务（见 §7.2-E）。

---

## 6. 复现步骤（命令级）

### 6.1 环境

- **Node v22**（本机实测 `v22.23.3`）。仓库**没有 `package.json`、没有 `node_modules`**，
  脚本只用 Node 内置模块 + 内置全局 `fetch`（需 Node ≥ 18），**不需要 `npm install`**。
- 平台任意；下面命令用 PowerShell 写法（Windows），Linux/macOS 把 `Copy-Item` 换成 `cp -r` 即可。
- Playwright 相关脚本（`pw-*.js`）**不是语料管线必需**，且硬编码了本机路径，换机不可直接用（见 §7.2-H）。

### 6.2 最常用：从缓存离线重建 v1（10 秒内，不联网）

```powershell
# 0) 保护现有产物（脚本会覆盖 data/corpus 下 3 个文件）
Copy-Item data/corpus data/corpus.bak -Recurse -Force

# 1) 重建（只读 data/raw/wt-cache/，不联网）
node tools/build-corpus-v3.js

# 2) 看 stdout 的校验输出，对照 §6.9 的基准数字
#    重点看：链一致性违例=0、版本单调 ✓、step_idx 范围、kind 分布、记录数

# 3) 确认无误后删备份（约 27 MB）
Remove-Item data/corpus.bak -Recurse -Force
```

产物：`data/corpus/amphoreus.jsonl`、`amphoreus.lines.txt`、`quest-order.json`。
**只要 `wt-cache/` 还在，这一步永远能离线复现**；这也是为什么语料不入库也能交接。

### 6.3 生成 v2（离线）

```powershell
node tools/normalize-corpus.js      # 读 v1 + data/config/speaker-alias.json，写 v2
```

产物：`data/corpus/amphoreus.v2.jsonl`、`amphoreus.v2.lines.txt`、`docs/corpus-pipeline.md`。
**前提**：v1 已存在且未被改写（v2 规则里写死了以 v1 为输入）。

### 6.4 重新抓任务索引（联网，只有需要更新页面清单时）

```powershell
node tools/ask-smw.js
```

- 行为：先打印一段 `data/raw/wt-银辇啊，迅赴那黑色大地.txt` 的样例，然后跑 SMW ask 并**覆盖** `data/raw/amphoreus-quest-index.json`。
- ⚠️ 前置依赖：该 `wt-银辇…txt` 样例文件必须存在（脚本第 17 行直接 `readFileSync`），删了会 **ENOENT 崩溃**。
- 查询语句（改范围时改这里）：`[[分类:开拓任务]][[任务地区::翁法罗斯]]|?系列任务名|?任务编号|?所属版本|?任务类型|limit=500`。

### 6.5 重抓单个任务页正文（调试解析时用）

```powershell
# 抓一页 wikitext：打印摘要，并把正文写到 data/raw/wt-<页名>.txt
node tools/fetch-wikitext.js "银辇啊，迅赴那黑色大地"
# 注意：它写的是 data/raw/wt-*.txt（历史抽样位置），文件名是原始页名，不是 wt-cache/ 的 URL 编码名
```

要**进缓存**供 v3 使用，需要手工放到 `data/raw/wt-cache/` 下且文件名为 URL 编码形式：
`decodeURIComponent` 对照现有缓存文件名即可（`node -e "console.log(encodeURIComponent('页面名'))"`）。

### 6.6 缓存缺失时批量补抓（联网）

`crawl-amphoreus.js` 内置的 `apiWikitext` 是唯一会写 `wt-cache/` 的代码（缓存命中则跳过）。
它**同时会用有 bug 的 v1 逻辑覆盖 `data/corpus/`**，所以正确姿势是"补完立刻用 v3 覆盖回来"：

```powershell
Copy-Item data/corpus data/corpus.bak -Recurse -Force        # 先备份
Get-ChildItem data/raw/wt-cache                             # 确认要重抓哪些
Remove-Item 'data/raw/wt-cache/<要重抓的编码文件名>.txt'      # 删掉才会重抓
node tools/crawl-amphoreus.js                                # 联网补缓存（约 180ms/页）
node tools/build-corpus-v3.js                                # 立刻用 v3 覆盖回来
Remove-Item data/corpus.bak -Recurse -Force
```

### 6.7 重抓角色标签（联网，仅更新称呼调研时）

```powershell
node tools/fetch-nicknames.js    # 35 个硬编码页名 → data/raw/nicknames.txt（31 命中 + 4 MISSING）
```

### 6.8 抓取礼节（改抓取脚本时必须遵守）

- **UA**（统一用 Chrome 140，避免被 wiki 拦）：
  `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0`
  注：`fetch-nicknames.js` 里的 UA 少了 `(KHTML, like Gecko)`，差异无关紧要，但新增脚本请统一用上面完整版。
- **间隔**：任务页 180ms/页（`crawl-amphoreus.js`），角色页 150ms/页（`fetch-nicknames.js`）。**不要并发、不要缩短**。
- **重试**：3 次，指数退避（任务页 800ms×尝试次数，角色页 600ms×尝试次数）；`missingtitle` 直接放弃，不重试。
- **超时**：25–40s（`AbortSignal.timeout`）。
- **SMW 查询**：`limit=500`，一次拿全；索引补漏只补 1 页（「魔女的镜中回天」），不要盲目扩大。
- 全部脚本**只读采集**，不改 wiki 任何内容。

### 6.9 验收：重跑后应对得上的基准数字

| 项 | 基准 |
|---|---|
| 任务页 / 记录 / 字数 | 67 / 24,206 / 528,626 |
| `kind` | dialogue 20,691 / option 2,399 / narration 1,116 |
| `extra=true` / `location` 非空 / `scene` | 1,459 / 252 / 141 |
| 版本分布 | 3.0:4,361 3.1:3,226 3.2:3,232 3.3:3,330 3.4:1,996 3.5:2,440 3.6:2,483 3.7:3,138 |
| 不同 `speaker` | 505 |
| `id` / `order` / `step_idx` | 1–24,206 连续 / 1–67 / 1–30 |
| 链校验 | 有效 next 边 64、一致性违例 0、版本单调 ✓ |

> 数字对不上先别慌：先确认 `wt-cache/` 是否完整（应为 **75** 个文件），再确认没有被 `crawl-amphoreus.js` 覆盖成 v1 旧产物（旧产物 step 全是「步骤1」）。
> 同口径的完整统计见 `data/reports/corpus-stats.md`；质量自检与"README 声明数字 vs 实测"逐项对照见 `data/reports/qa-checks.md`。

---

## 7. 已知坑

### 7.1 先读 `data/README.md` 第六节（12 条）

说话人未归一、分支并列、`extra` 未拆分、系列汇总页无正文、版本号字符串比较、范围限定、
截图过大、`他/她` 占位符、`*强调*` 残留、`【旁白】`内嵌说话人、复合说话人标签、称号当说话人。
**这 12 条仍然有效**，下面只补充 README 没写到、这次实测发现的问题（按严重度排序）。
更细的问题清单与逐项证据见 `data/reports/qa-checks.md` 第 5 节，可与本节互校。

### 7.2 本次实测补充的坑

| # | 坑 | 实测证据 | 影响 / 建议 |
|---|---|---|---|
| **A** | **以 `:` 开头的行被整行丢弃**（v3 无该分支） | `wt-cache` 里行首 `:` 共 **1,963 行**；例 `:{{颜色\|描述\|数日后，在命运重渊的车厢坠毁点……}}`、`:水车纹丝不动。` 均**不在语料**中 | **最大的隐性缺口**：大量场景过渡/时间跳跃旁白缺失，影响叙事时序分析。修复=v3 加 `^:` 分支（cleanInline 后 `kind=narration`）；1,963 行里有一部分在 `{{剧情选项}}` 块内会被块解析消耗，**实际入语料数会小于此**，但量级 ~1.9k → 属基线变更，见 §8-4 |
| **B** | `{{短信选项}}` 块整块未解析 | 共 **14 块**（分布在 10 个页面）；另 `wt-cache` 中有 **32 处** `\|剧情N={{角色对话\|…}}` 内联对白同样未解析 | 玩家短信选项与其分支台词缺失（例：3.0#01 的「要跃迁了，对吧？」不在语料）。影响玩家选项统计；修复需在 v3 加 `短信选项` 分支 + 限定正则不跨行 |
| **C** | **1,116 条 `narration` 里 855 条其实是 `标签：台词`** | `？？？：` 344 / `永夜之帷，三月七：` 56 / `磐岩之脊，丹恒：` 48 / `天谴之矛，迈德漠斯：` 42 / `博识尊[黑塔]：` 15 … | 根因：`*` 行说话人正则要求标签不含 `，。！？、[`，含标点即落回 `narration` 分支（`？？？` 含问号也中招）。**真旁白只有 ~261 条**；README §六#10 提过这个现象，这里是量化。建议二次拆分（拆完再看 v2 `canonical=null` 残量，5,148 条里有相当一部分正是这类） |
| **D** | 跨行误配产生**伪说话人** | `speaker="？天啊，太可惜了。"`（2 条，id 5349/5360）：`{{剧情选项}}` 内 `: *正常*？天啊…` + 下一行 `:` 旁白被 `innerRe` 跨行拼成一条 | 量小但说明 `剧情选项` 块内正则没锚定行首；修复时把 `innerRe` 限制在单行 |
| **E** | 前置/后续链有断点 | 3 条 `next`、2 条 `prev` 带 `#小节锚点`（`cleanLink` 只取 `[[…]]` 不剥 `#`）；另有 3.7 末页 `next` 指向范围外「幻月是慈悲的女王」 | 有效边只有 **64**（不是 66）。v3 自检"违例 0"只代表**边方向**一致；`data/reports/qa-checks.md` 用"简单相邻链"口径发现 8 处不吻合、2 条反向边（3.4 是分支页结构）→ **别把自检 0 当绝对正确**；`quest-order.json` 的 `prev/next` 不能直接当相邻页用 |
| **F** | 稀疏字段容易被误当全表字段 | `location` 只有 `{{任务描述}}` 记录有（254 带键/252 非空）；`scene` 仅 141 条；`chapter` 恒为「剧情内容」 | 做「场景/地点」维度分析前先看覆盖率；`chapter` 没有分组价值，用 `step_title` |
| **G** | **旧脚本会覆盖当前产物** | `crawl-amphoreus.js`（v1 有 bug：step 全「步骤1」、顺序拼音序）与 `build-corpus-v2.js` 都会写 `data/corpus/amphoreus.jsonl` | 误跑=基线被毁且很难察觉。规范：**v1 只认 `build-corpus-v3.js`**；跑任何会写 corpus 的脚本前先备份 |
| **H** | 无依赖声明，Playwright 脚本绑本机 | 仓库无 `package.json`；`pw-shot-bwiki.js` 硬编码 `D:/AITools/mcps/playwright/node_modules/playwright-core` 与 Chromium 路径 | 换机时 `pw-*.js` 必改路径；它们只用于人工核对，不参与语料生成 |
| **I** | 口径杂项（分析前先定规则） | `text=="……"` **671 条**（纯省略号 2.8%）；全角 `：`/半角 `:` 混用；`{{黑幕\|…}}` 取最后参数 → **剧透文本被展开**（19 处，无标记）；版本用 `parseFloat`/字符串比较（3.10 会错，现范围安全）；`他/她`：`text` 内 **117 处/110 条**、`step_title` 内另有 **43 处**（合计 160，README 写 153）；`*…*` 成对 **342 对**（其中 `*我们*` 273；限长 ≤20 字口径 325 对，README 写 282 处） | 句子统计/情感分析先 `filter(text !== '……')`；`{{黑幕}}` 如需"玩家可见"口径要单独过滤；**`step_title` 里的 `他/她` v2 未清洗**，按步骤做性别指代分析前要先处理；README 与 alias 文档的数字口径需校正（`data/reports/qa-checks.md` 第 6 节有逐项对照） |

---

## 8. 待决策项（接手后需要拍板的）

| # | 问题 | 影响面 | 选项 | 建议 |
|---|---|---|---|---|
| 1 | **长尾说话人归属**：`data/reports/unmatched-speakers.md` 实测 **434 个 speaker 未归一，覆盖 4,043 条（16.70%）**：待人工 220 个 / generic_npc 候选 155 个 / 疑似已知角色约 59 个（配置缺口，如 `瑟希斯→那刻夏`、`露奈比斯/索拉比斯→塞涅俄丝`、`来古士之声→来古士`）；v2 实际 `canonical=null` 5,148 条（21.3%，口径更宽） | 说话人级统计的分母 | (a) 全部 `generic_npc` 合并 (b) 保留原名不归一 (c) 按清单人工补 `canonical` | **按清单分层处理**：`generic_npc` 类先自动合并（保留 `speaker_raw`）；`疑似X` 类补配置；`待人工` 只处理句数 ≥ 10 的。不要盲目 `generic_npc`（会把"？？？"和真 NPC 混在一起） |
| 2 | **`extra` 是否物理拆分** | 下游读文件路径 | (a) 保持单文件 + `view` 软切 (b) 拆成 `amphoreus.v2.main.jsonl` / `.extra.jsonl` | 保持单文件（当前 v2 已用 `view`），下游用 `filter`；物理拆分会让 id 连续性/关联变复杂 |
| 3 | **奇美拉/梗名是否入 `form`** | `form` 语义纯度 | (a) 保持 `type=meme` 排除 (b) 以 `form=meme` 混入 | 保持排除（当前配置即此）；梗名做修辞分析时单独用 `meme_terms` 匹配 `text` |
| 4 | **`:` 开头的场景旁白是否补回**（§7.2-A） | 语料基线（量级 +1.9k 行），需重跑 v2/质检 | (a) 不补，接受缺口 (b) v3 加分支补回 | **建议补**：叙事语料没有场景描写是硬伤；但要在 v2 重跑前完成，避免两次基线 |
| 5 | `{{短信选项}}`/内联对白是否补解析（§7.2-B） | 玩家选项统计 | (a) 不补 (b) 与第 4 项一起做 | 和 4 一起做（同一次 v3.1 变更） |
| 6 | 泰坦称号格式怎么拆：`永夜之帷，三月七：`、`博识尊[黑塔]：` | `narration` 里 855 条 | 拆成 `speaker=三月七` + `title=永夜之帷`？还是保留整串当 speaker？ | 拆：`speaker` 取逗号/方括号后的角色名，称号另存字段（需先补解析，见 4） |
| 7 | 版本号比较方式 | 只有 8 个版本时无碍 | 字符串 vs 数值元组 `[3,10]` | 出现 3.10 前改成数值元组，成本很低 |
| 8 | `他/她们俩`（3.6#07「长夜月」台词，唯一复数例外） | 1 条 | 保留 / 人工标注 | 保留并在变更日志标注即可（v2 现状） |

---

## 9. 合规与仓库策略（不要踩线）

- **数据来源**：`https://wiki.biligame.com/sr/`（BWiki，崩坏：星穹铁道 WIKI）。
- **许可**：BWiki 内容按 **CC BY-NC-SA 4.0** 提供；**游戏文本著作权属米哈游**。
- **本项目定位**：仅课程/研究范围内做文本分析，**不要公开分发** `data/corpus/` 或 `wt-cache/` 原文。
- **仓库策略**：代码可开源（根目录已有 MIT `LICENSE`，只覆盖代码），语料**不入库**——`.gitignore` 已忽略
  `data/corpus/`、`data/raw/`、`data/shots/`、`data/reports/`。要发布时只推代码 + 配置 + 文档，语料由他人自行跑脚本生成。
- 引用/致谢 BWiki 与米哈游；不要给语料加更宽松的许可证。

---

## 10. 交接后 15 分钟上手清单

```powershell
# 1) 环境与数据在位
node -v                                              # 期望 v22.x
Get-ChildItem data/raw/wt-cache -File | Measure-Object   # 期望 75 个文件
Get-ChildItem data/corpus | Select-Object Name,Length    # 期望 v1 4 个 + v2 2 个

# 2) 离线重建一遍并对照 §6.9（先备份）
Copy-Item data/corpus data/corpus.bak -Recurse -Force
node tools/build-corpus-v3.js
Remove-Item data/corpus.bak -Recurse -Force

# 3) 抽查 3 条，确认能读
Get-Content data/corpus/amphoreus.jsonl -TotalCount 3
#    用 Node 统计（PowerShell 里 JSON 转对象慢，写脚本更快）
node -e "const fs=require('fs');const r=fs.readFileSync('data/corpus/amphoreus.jsonl','utf8').trim().split('\n').map(JSON.parse);const k={};r.forEach(x=>k[x.kind]=(k[x.kind]||0)+1);console.log(r.length,k,r.filter(x=>x.extra).length)"

# 4) 读 §7 的坑；再看 docs/corpus-pipeline.md（v2 规则）与 data/reports/（质检结论）
```

接手建议：**先不要改 `build-corpus-v3.js`**。如果要动，按 §8-4/5 一次性改完并同步重跑 v2，
同时把 §6.9 的基准数字更新到本文件（否则下一个人会对不上数）。

---

## 11. 文档索引

| 文档 | 定位 |
|---|---|
| [`data/README.md`](../data/README.md) | **数据权威说明**：目录、v1 字段、已知问题、范围决策、配置概览 |
| `docs/handoff.md`（本文） | 交接入口：数据流、复现、坑、待决策、合规 |
| [`docs/corpus-pipeline.md`](corpus-pipeline.md) | v2 归一 + 清洗规则、统计、变更示例、遗留项 |
| [`docs/speaker-aliases.md`](speaker-aliases.md) | 角色称呼集合 v4：渠道调研、38 角色、X爵体系、归一规则草案 |
| [`docs/chatWithGemini.md`](chatWithGemini.md) | 项目方向讨论原始记录（4 个 NLP 选题灵感） |
| `data/reports/corpus-stats.md` | 语料统计：总量、版本/类型分布、Top 30 说话人、长度分位 |
| `data/reports/qa-checks.md` | 质量自检 + **README 声明数字 vs 实测**逐项对照 + 问题清单 |
| `data/reports/unmatched-speakers.md` | 434 个未归一 speaker 的分层清单（待人工/generic_npc/疑似已知角色） |
| `data/config/speaker-alias.json` | 归一/称呼配置（12 个键，见 §4） |

---

## 附：本文数字的取数方法（想自己复核时用）

```powershell
# 总量 / kind / extra / 说话人数
node -e "const fs=require('fs');const r=fs.readFileSync('data/corpus/amphoreus.jsonl','utf8').trim().split('\n').map(JSON.parse);const c=(f)=>r.reduce((a,x)=>(a[f(x)]=(a[f(x)]||0)+1,a),{});console.log('records',r.length);console.log(c(x=>x.kind));console.log('extra',r.filter(x=>x.extra).length);console.log('speakers',new Set(r.filter(x=>x.speaker).map(x=>x.speaker)).size)"

# wt-cache 文件数
(Get-ChildItem data/raw/wt-cache -File).Count

# 行首 ":" 行数（§7.2-A 的依据）
$all = Get-ChildItem data/raw/wt-cache -File | ForEach-Object { [System.IO.File]::ReadAllText($_.FullName) }
([regex]::Matches(($all -join "`n"), '(?m)^:[^\r\n]{2,}')).Count

# narration 中以"标签："开头的条数（§7.2-C 的依据）
node -e "const fs=require('fs');const r=fs.readFileSync('data/corpus/amphoreus.jsonl','utf8').trim().split('\n').map(JSON.parse);const n=r.filter(x=>x.kind==='narration');console.log(n.length, n.filter(x=>/^[^\s：:]{1,14}[：:]/.test(x.text)).length)"
```
