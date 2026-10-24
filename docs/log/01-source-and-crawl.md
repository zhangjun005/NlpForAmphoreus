# 01 · 数据源选定与抓取

- **时间**：2026-10-23 16:39–16:47
- **目标**：为「翁法罗斯主线」找到可稳定获取、且保留对话结构的原始文本。

## 实际动作

1. 逐渠道评估数据源：BWiki、hakush/yatta、B 站 CC 字幕、Fandom 中文、中文维基、萌娘百科。
   - B 站字幕接口未登录返回空数组（需 SESSDATA，且有解说字幕噪声）；
   - Fandom 与中文维基本地 DNS 解析失败；
   - 萌娘百科可读 HTML，但 `action=parse` 返回 `action-notallowed`；
   - hakush 无剧情接口。
2. 确定 BWiki（`wiki.biligame.com/sr`）为唯一可行源，因为它同时提供：
   - `action=parse&prop=wikitext` 原文（保留说话人/选项/注音/折叠结构）；
   - Semantic MediaWiki（SMW）可按属性查任务索引；
   - 角色页 `昵称/外号` 字段（后续称呼归一的原料）。
3. 实测「开拓任务」页面：正文由 `{{#ask:}}` 服务端渲染，HTML 中 `<table>` 0 个、`<tr>` 0 个 → 必须走 SMW 查询。
4. 写脚本：
   - `tools/ask-smw.js`：`[[分类:开拓任务]][[任务地区::翁法罗斯]]` → 74 页；
   - `tools/parse-quest-list.js`：解析章节卡片，补上 1 页「魔女的镜中回天」（其 `任务地区` 写在黑塔空间站）；
   - `tools/crawl-amphoreus.js` / `tools/fetch-bwiki.js`：按标题抓 `prop=wikitext`，UA 用 Chrome/140，间隔 150–200ms，3 次重试，30–40s 超时。

## 输入 / 输出

- 输入：BWiki 页面（网络）
- 输出：
  - `data/raw/amphoreus-quest-index.json`（75 页 = 67 任务页 + 8 系列汇总页）
  - `data/raw/wt-cache/*.txt`（75 个原始 wikitext，2.48 MB，URL 编码文件名）
  - `data/corpus/quest-order.json`（拓扑排序后的 67 页顺序）

## 验证

- 75 页全部抓取成功、缓存文件非空；
- 用 Playwright 渲染「开拓任务」页与语料抽样比对（1/849 抽样：非折叠记录包含匹配 85.1%）；
- 首尾核对：拓扑排序后第一条是 3.0#01 开场（帕姆「喂喂」）。

## 问题与处置

- 「开拓任务」页无法用 HTML 表格抓取 → 改 SMW；
- 活动/支线/散落文本混入会污染时间线 → 范围决策只取主线 3.0–3.7（67 页）；
- 语料合规：BWiki CC BY-NC-SA 4.0 + 米哈游版权 → `.gitignore` 排除语料与报告，只提交代码/配置/文档。

## 状态

完成。
