# data/ 数据目录说明

本目录存放「崩坏：星穹铁道 · 翁法罗斯」主线剧情的 NLP 语料及其抓取/解析中间产物。
所有数据来自 BWiki（`wiki.biligame.com/sr`）的**公开 MediaWiki 页面**，用 Python/Node 脚本
通过 MediaWiki API 抓取，未经人工改写。

一句话现状：**已完成 3.0–3.7 全 8 个版本、67 个任务页的剧情语料抽取，共 24,206 条记录 / 528,626 字**。

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
| `wt-cache/*.txt` | 共 ~4 MB | 75 个任务页的原始 wikitext 缓存。文件名是 **URL 编码**（如 `%E9%93%B6...`），解码后即页面名。**离线重跑语料只需要这个目录** |

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
8. **`他/她` 性别占位符 153 处**：BWiki 为兼容双主角写作「他/她」，未清洗。
9. **`*强调*` 残留 282 处**：wiki 斜体标记被当普通字符保留。其中 `*我们*` 是缇宝指代其分身群体的
   特有用法（语义有价值，勿直接删）；另有 `*泰坦悲伤的低鸣*`、`*嘶哑的呢喃*` 等舞台指示，
   应归入 `kind=narration` 而非台词。
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

## 八、相关文档

- `docs/speaker-aliases.md` — 角色称呼集合 v4（主角/三月七/丹恒/12 黄金裔/X爵体系/其他/无角色页者），
  含渠道调研结论、语料实证、归一规则、清洗待办。
- `docs/chatWithGemini.md` — 项目方向讨论的原始记录。
