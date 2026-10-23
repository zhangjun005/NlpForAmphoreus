# data/ 数据目录说明

本目录存放「崩坏：星穹铁道 · 翁法罗斯」主线剧情的 NLP 语料及其抓取/解析中间产物。
所有数据来自 BWiki（`wiki.biligame.com/sr`）的**公开 MediaWiki 页面**，用 Python/Node 脚本
通过 MediaWiki API 抓取，未经人工改写。

一句话现状：**已完成 3.0–3.7 全 8 个版本、67 个任务页的剧情语料抽取与三轮迭代；最终交付版 `corpus/amphoreus.final.jsonl`：26,332 条记录 / 566,798 字 / 归一命中 97.56%**。

---

## 目录结构

```
data/
├── README.md                  ← 本文件
├── config/                    人工维护的配置
│   └── speaker-alias.json     角色称呼/别名/形态归一表（v1）
├── raw/                       原始抓取物（可重新生成）
│   ├── bwiki-kaiTuoRenWu.html
│   ├── bwiki-kaiTuoRenWu.wikitext
│   ├── amphoreus-quest-index.json
│   ├── nicknames.txt          31 个 BWiki 角色页的标签字段
│   ├── wt-*.txt
│   └── wt-cache/              75 个任务页的 wikitext 缓存
├── corpus/                    结构化语料（核心产物）
│   ├── amphoreus.jsonl
│   ├── amphoreus.lines.txt
│   ├── quest-order.json
│   └── quest-meta.json
└── shots/                     渲染截图与浏览器正文（用于核对）
    ├── qa-index.jpg
    ├── qa-quest.jpg
    ├── kaituo-renwu.png
    ├── yinnian.png
    ├── kaituo-renwu.rendered.txt
    └── yinnian.rendered.txt
```

---

## 范围决策（已定）

**只分析主线剧情**（3.0–3.7 的 67 个开拓任务页）。理由：
- 活动剧情基本是整活/番外篇，风格与主线不同；
- 活动背景时间可能早于当前版本（一个版本的活动可能对应前几个版本的时间点），时间线不可靠；
- 支线多数与黄金裔关系不大；
- 散落文本（书籍/短信/道具文案等）时间线更乱。

因此 `corpus/` 只含主线；冒险任务（7 个）、活动任务（4 个）明确不纳入。


---

## 一、corpus/（核心产物）

### `amphoreus.jsonl` — 主语料，8.5 MB / 24,206 行

一行一条记录（JSON Lines），按**剧情顺序**排列（拓扑排序，见下）。字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 全局递增序号，即全篇阅读顺序 |
| `order` | int | 所属任务在剧情中的序号（1–67） |
| `task` | str | 任务页名，如「银辇啊，迅赴那黑色大地」 |
| `version` | str | 所属版本，`3.0`–`3.7`（= 一个系列任务 = 一幕） |
| `series` | str | 系列任务名，如「落木逐火英雄纪」 |
| `series_no` | str | 任务编号（系列内 `01`–`10`） |
| `idx` | int | 任务内序号 |
| `chapter` | str | 二级章节名（目前基本是 `剧情内容`） |
| `step_idx` | int | 任务内步骤序号（1–30） |
| `step_title` | str | 步骤标题，如「参加航线会议，决定列车的下一站」 |
| `scene` | str | 气泡对白的场景名，如「星穹列车一家人」（仅部分页有） |
| `kind` | str | `dialogue`(台词 20,691) / `option`(玩家选项 2,399) / `narration`(旁白 1,116) |
| `speaker` | str | **说话人标签（未归一）**；旁白为空串 |
| `text` | str | 台词正文 |
| `extra` | bool | 是否位于 `{{折叠}}` 块内（= 额外对话/可选闲聊，1,459 条） |
| `location` | str | `{{任务描述}}` 里的地点（252 条） |

剧情顺序的确定方法：用每个任务页自带的 `前置任务` / `后续任务` 字段建链（64 条边），
做拓扑排序，同层用 (版本, 任务编号) 兜底。校验结果：链一致性违例 0，版本 3.0→3.7 严格单调。

### `amphoreus.lines.txt` — 3.7 MB，人读版

每行 `[版本#编号] 任务名 | 步骤标题 | 说话人: 台词`，方便 `grep` 和人工抽查。

### `quest-order.json` — 24.6 KB

67 个任务页的剧情顺序与元数据（`order` / `task` / `version` / `series` / `series_no` / `prev` / `next` / `cast` / `region`）。

### `quest-meta.json` — 317 KB【旧版，仅供对照】

v1 阶段的元数据中间产物，字段未清洗（含 `undefined`、未剥离 `[[]]`）。**不要用于分析**，
当前版本请用 `quest-order.json`。

---

## 二、raw/（原始抓取物）

| 文件 | 大小 | 说明 |
|---|---|---|
| `bwiki-kaiTuoRenWu.html` | 502 KB | 「开拓任务」页面渲染后的 HTML。注意：正文是 Semantic MediaWiki 的 `{{#ask:}}` 服务端渲染结果，**没有 table/tr**，抓 `<p>/<tr>` 会失败 |
| `bwiki-kaiTuoRenWu.wikitext` | 3.3 KB | 同页原始 wikitext（只有 7 个章节标题 + `#ask` 查询语句） |
| `amphoreus-quest-index.json` | 8.7 KB | 75 个任务页索引。来源：SMW ask（`分类:开拓任务` + `任务地区::翁法罗斯`，74 页）+ 章节卡片补漏 1 页（「魔女的镜中回天」，剧情在黑塔空间站但归属 3.2 系列） |
| `wt-落木逐火英雄纪.txt`、`wt-银辇啊，迅赴那黑色大地.txt` | 0.5 / 81 KB | 早期单页 wikitext 抽样，**已被 `wt-cache/` 取代**，仅留档 |
| `wt-cache/*.txt` | 共 2.48 MB（75 个文件） | 75 个任务页的原始 wikitext 缓存。文件名是 **URL 编码**（如 `%E9%93%B6...`），解码后即页面名。**离线重跑语料只需要这个目录** |

其中 8 个文件是「系列任务」汇总页（无正文）：落木逐火英雄纪、门扉之启，王座之终、
走过安眠地的花丛、在黎明升起时坠落、因为太阳将要毁伤、英雄未死之前、于长夜重返大地、成为昨日的明天。

---

## 三、shots/（渲染核对）

| 文件 | 说明 |
|---|---|
| `qa-index.jpg`、`qa-quest.jpg` | 小尺寸视口截图（113 KB / 63 KB），可直接预览 |
| `kaituo-renwu.png`、`yinnian.png` | 全页截图（3.6 / 4.3 MB），**高度超过 8192px，读图工具打不开**，仅供人工查看 |
| `*.rendered.txt` | Playwright 渲染后的 `innerText`，用于核对「解析出的台词是否真的出现在页面上」 |

核对结论：抽检 41 条台词，28 条在渲染文本中命中；未命中的 13 条全部位于 `{{折叠}}` 块内
（默认折叠 → `innerText` 不包含），说明**解析比渲染可见内容更全**，不是丢数据。

---

## 四、tools/（脚本，均只读采集）

| 脚本 | 用途 |
|---|---|
| `fetch-bwiki.js` | HTTP 抓「开拓任务」页 + 结构统计（验证无 table） |
| `parse-quest-list.js` | 按 h2 切段、抽翁法罗斯段的任务卡片链接 |
| `fetch-wikitext.js` | MediaWiki API 取单页 wikitext（抽样用） |
| `ask-smw.js` | SMW ask 查询，生成任务索引 |
| `crawl-amphoreus.js` | v1 抓取+解析。**有 bug（step 全为「步骤1」、顺序是拼音序），保留供对照** |
| `build-corpus-v2.js` | v2。修了顺序，但章节切分仍错（只认 `==`），保留供对照 |
| `build-corpus-v3.js` | **当前版本**。逐行识别 `==`/`===` 标题、按前置/后续拓扑排序、剥 `{{任务}}` 元数据、解析 `{{角色对话}}` 气泡对白、标记 `{{折叠}}` |
| `audit-scope.js`、`audit-section.js` | 抽取范围核对（章节、任务类型、遗漏页） |
| `pw-test-launch.js`、`pw-test-cdp.js` | Playwright 启动探针（沙箱排查用） |
| `pw-shot-bwiki.js`、`pw-shot-small.js` | Playwright 渲染截图 + 一致性抽检 |
| `scan-sessions.js` | 一次性：扫 DSH 会话日志排查 Playwright 历史（与项目无关，可删） |

重跑顺序：`ask-smw.js` →（可选）`parse-quest-list.js` 补漏 → `build-corpus-v3.js`。

---

## 五、数据来源与协议

- 页面：`https://wiki.biligame.com/sr/`（BWiki，崩坏：星穹铁道 WIKI）
- BWiki 内容按 **CC BY-NC-SA 4.0** 提供；游戏文本著作权属米哈游。
- **本项目仅在课程/研究范围内做文本分析，不要公开分发 `data/corpus/` 或 `wt-cache/` 的原文**；
  如需发布，代码可开源（仓库已有 MIT LICENSE），语料不要一起推。

---

## 六、已知问题（截至当前版本）

1. **说话人未归一**：`speaker` 是页面原样标签，存在真名/常用名/称号/形态混用（如 昔涟 = 迷迷 = 德谬歌 = 「往昔的涟漪」）。
   归一方案见 `docs/speaker-aliases.md`，尚未回填到语料。
2. **分支按文档顺序并列**：选项下的多条分支台词都在，没有"玩家路径"。已确认可接受（分支很快收束）。
3. **`extra=true`（1,459 条）仍在原位**：是 `{{折叠}}` 里的可选闲聊，做时序分析前建议单独排除。
4. **8 个系列汇总页无正文**（已在语料生成时跳过）。
5. **版本号按字符串比较**：目前只有 `3.0`–`3.7`，将来出现 `3.10` 需改成数值元组。
6. **范围限定**：只含「开拓任务」主线（67 页）。翁法罗斯地区的 7 个冒险任务、4 个活动任务未纳入。
7. `data/shots/*.png` 全页截图过大（>8192px），需要预览时请用 `qa-*.jpg`。
8. **`他/她` 性别占位符**：实测 **110 条记录 / 117 处**（此前误记为 153）。BWiki 为兼容双主角写作「他/她」，
   v2 版已替换为「开拓者」，仅保留 3.6#07「长夜月」的「他/她们俩」1 处。
9. **`*强调*` 标记**：实测 **342 对 / 299 条记录**，其中 `*我们*` 273 处（缇宝指代分身群体，语义有价值）。
   v2 版已去星号保留文本；另 19 条整句 `*舞台指示*` 已改判 `kind=narration`。
10. **`【旁白】` 内嵌说话人**：如 `博识尊[黑塔]：「阿基维利！」`、`永夜之帷，三月七：「…」`、
    `？？？：…`，实际是对白，`kind` 与 `speaker` 需二次拆分。
11. **复合说话人标签**：`「赛白厄」`（赛飞儿冒充白厄）这类"一人扮另一人"的写法。
12. **称号当说话人**：`「门匠」`（缇宝）、`「羁客」`（赛飞儿）、`心中的英雄`（白厄）。

## 七、config/（人工维护配置）

### `speaker-alias.json` — 角色称呼/别名/形态归一表 v1

| 字段 | 内容 |
|---|---|
| `meta` | 版本、范围、范围决策、来源、归一优先级说明 |
| `canonical` | **38 个角色**：`type`（protagonist/playable/golden_heir/npc/titan/antagonist）、`true_name`、`titan`、`speaker_aliases`（可能出现在 speaker 字段的写法）、`forms`、`titles`、`aliases`、`called_by`（谁这么叫 → 用于台词扫描）、`notes` |
| `form_map` | 32 条「形态 → 角色」映射（迷迷→昔涟、缇安/缇宁→缇宝、丹枫→丹恒、长夜月→三月七、心中的英雄→白厄…） |
| `speaker_literal_map` | 25 条「speaker 原样字符串 → canonical + form」（`「冬霖爵」塞涅卡`、`「赛白厄」`、`「往昔的涟漪」`…） |
| `address_scan_index` | 42 条「称呼 → 被称呼者」反查表（救世主→开拓者、小白→白厄、吾师→缇宝…） |
| `titan_canonical` | 13 泰坦：称号 + 对应黄金裔 |
| `meme_terms` | 41 个梗名/奇美拉名/网名（**type=meme，不参与说话人归一**） |
| `known_conflicts` | 6 条合并冲突裁决（卡厄斯≠卡厄斯兰那、铁墓≠白厄、迷迷 vs 昔涟…） |
| `pending_manual_review` | 待人工确认项 |

说明：本文件**只是配置**，语料的 `speaker` 字段尚未回填。

---

## 八、v2 语料与质检结果（本轮并行产出）

### `corpus/amphoreus.v2.jsonl` — 清洗 + 说话人归一版（24,206 行，未入库）

在 v1 基础上**只新增 4 个字段**，v1 的 `text`/`speaker` 0 处改动（另有 19 条舞台指示 `kind` 由 dialogue 改判为 narration）：

| 新字段 | 说明 |
|---|---|
| `canonical_speaker` | 规范角色名（按 `config/speaker-alias.json`）；未命中为 `null` |
| `form` | 形态/称号形态（迷迷、长夜月、双生子分身名、赛白厄…）；无则 `null` |
| `text_clean` | 清洗后文本（去 `*` 星号、`他/她`→开拓者、清模板残留）；原文仍在 `text` |
| `view` | `main`（22,747）/ `extra`（1,459，折叠额外对话） |

归一覆盖：非空 speaker 23,090 条中 **19,058 条命中（82.54%）**；`canonical=null` 5,148（旁白 1,116 + 未匹配 4,032）。
脚本 `tools/normalize-corpus.js` 幂等可重跑；处理规则与统计见 `docs/corpus-pipeline.md`。

### `data/reports/` — 质检与统计（QA 产出，未入库）

| 文件 | 内容 |
|---|---|
| `corpus-stats.md` | 总量/版本/kind/extra 分布、Top30 说话人、Top20 canonical×版本矩阵、长度分位 |
| `qa-checks.md` | 顺序自检、字段缺失率、文本纯度、重复检测、渲染抽样比对、问题清单（按严重度） |
| `unmatched-speakers.md` | 434 个未归一 speaker 的逐条清单（句数/版本区间/例句/建议） |

**QA 关键结论**（已由 Lead 独立复核）：
- ✅ 结构干净：`id`/`order`/`idx` 连续、版本严格单调、0 空文本、0 重复抓取
- ⚠️ 高优先级待修：
  1. **859 条 `kind=narration` 的 text 内嵌「说话人：」前缀**（实为对白，占 3.55%）→ 需二次拆分为 dialogue+speaker
  2. **1,554 条 `step_title` 回退为章节名**（涉及 31 个任务页）→ 需重抽步骤标题或加 `step_title_missing` 标记
  3. **4,043 条（434 个写法）未归一** → 补 alias 配置（true_name/泰坦/`X之声`/`记忆中的X`/复合标签）
- ⚠️ 中优先级：194 条 option 尾部残留 `}}`；406 条动作描写被标为 dialogue；901 条分支重复台词（分析前去重）
- ℹ️ 低优先级：`chapter` 全为「剧情内容」（无信息量）；`location`/`scene` 覆盖率 1.04%/0.58%；108 条 3.7 乱码段（`█▀▄`）建议分析时排除
- 口径修正：README 原「链一致性违例 0」应注明是"边方向"口径（简单相邻链口径有 8 处不吻合，3.4 为分支页结构）

### `config/speaker-alias.json` 的 8 条待扩充建议（未改配置）

1. `true_name` 已登记但未进 `speaker_aliases`：海列屈拉→海瑟音、雅辛忒丝→风堇、赛法利娅→赛飞儿、阿那克萨戈拉斯→那刻夏、迈德漠斯→万敌
2. 泰坦作说话人无 canonical 条目：瑟希斯(157)、欧洛尼斯(60)、塞纳托斯(53)、雅努斯(11)
3. 模式未覆盖：`X之声`（来古士之声 136）、`记忆中的X`、`X的记忆`、`的投影`
4. 复合标签未拆：`永夜之帷，三月七`(8)、`开拓者&昔涟`(6)、`毁灭的容器，卡厄斯兰那`(6)
5. NPC 未登记：巴特鲁斯(138)、克拉特鲁斯(116)、凯妮斯(121)、露奈比斯/索拉比斯(146)
6. 客串角色：卡芙卡(79)、景元(28)、流萤(26)、银狼(17)
7. `「墨涅塔的幻影」` 归到 `墨涅塔` 但 canonical 无该条目
8. `form` 取值口径需统一（「记忆/幻象形态」vs「记忆形态」）

---

## 九、相关文档

- `docs/speaker-aliases.md` — 角色称呼集合 v4（主角/三月七/丹恒/12 黄金裔/X爵体系/其他/无角色页者），
  含渠道调研结论、语料实证、归一规则、清洗待办。
- `docs/chatWithGemini.md` — 项目方向讨论的原始记录。

---

## 十、最终交付语料（final）

### `corpus/amphoreus.final.jsonl` — 26,332 条 / 566,798 字（未入库）

由 `tools/finalize-corpus.js` 从 `amphoreus.v31.jsonl` + `config/speaker-alias.v3.json`（外部复核勘误版）生成：

| 指标 | 数值 |
|---|---|
| 记录数 | **26,332**（v1 24,206 → v31 26,332，增量 2,126） |
| kind | dialogue 21,511 / narration 2,291 / option 2,400 / sms 98 / sms_option 32 |
| view | main 24,207 / extra 2,125 |
| 说话人归一 | 23,460 / 24,041 非空 speaker = **97.58%**（canonical=null 均为未登记路人/系统标签，不猜） |
| 重复 | 1,120 条保留并标 `is_duplicate` + `dedup_group`（未删除） |
| 文本纯度 | `{{`/`}}`/`他/她`/星号/HTML 残留 **全部为 0**；空 text_clean 0 |
| 长度 | P50 18 / P90 43 / P99 69 / max 352 |

新增字段：`canonical_speaker`、`form`、`text_clean`、`view`、`is_duplicate`、`dedup_group`、`channel`（短信）、`origin`/`v1_id`（溯源）、**`repeat_kind`/`repeat_scope`/`repeat_count`（重复台词的叙事功能分类：motif/catchphrase/structure/translation/ritual/pause/branch/loop_interaction，见 `docs/method/04-重复台词判定案例集.md`）**。

### v3.1 解析补全（`corpus/amphoreus.v31.jsonl`）

修复 v3 的 7 类缺陷，增量构成：
- 行首 `:` 场景旁白 **1,817 + 209 选项**（v3 整行丢弃）
- 短信对白/选项 **98 + 32**（`{{短信选项}}` 14 块）
- 其他修复：模板截断（10 条恢复）、`}}` 尾残（196→0）、narration 内嵌说话人 894 条拆分、伪说话人 21 处
- `step_title`：0 条回退为「剧情内容」；1,706 条为 `step_title_inferred=true`（推断，精细时序分析时注意）

### 配置 v2

`config/speaker-alias.v2.json`：canonical 38 → **124**（含 13 泰坦、26 客串、57 具名 NPC、4 系统、generic_npc 池 247）、form_map 47、literal_map 128、pattern_rules 17、composite_rules 21 实例。变更见 `docs/speaker-alias-changes.md`。


---

## 十一、外部复核与阶段记录（最新）

- **外部复核（Gemini）**：对 v2 配置交叉比对后指出 5 类勘误 + 4 个架构拍板 + 9 条未归一处置 + 1 处可读性问题，已全部采纳：
  - 配置产物：`config/speaker-alias.v3.json`（**最终交付用**，v2 保留供追溯）
  - 勘误记录：`docs/speaker-alias-errata.md`；脚本：`tools/patch-alias-v3.js`
  - 关键修正：关系反转「老日」、越界版本「欢愉主/雷主」、梗名移出 aliases、正式爵位「剑旗爵」纠回、救世主/伙伴改多义、10 组推断升级、萨姆→流萤、面镜不拆、泰坦之声留 generic_npc、刻法勒沿用 v1、「闭嘴」/先祖之灵/古怪的弈者处置
  - `finalize-corpus.js` 现在读 v3 配置，并支持复合标签拆解；`final.lines.txt` 在 `generic_npc` 时回退显示原始标签（可读性）
- **阶段记录（写报告用）**：`docs/stages/` 下 8 篇（README + 00–06），每篇含「目标与意图 / 方案 / 实施 / 产出 / 决策与取舍 / 踩过的坑与修正」
- **数字口径**：`docs/stages/README.md` 的「最终数字口径速查」为最新实测，冲突时以它为准
