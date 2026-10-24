# 03 · 说话人归一配置 v1 → v3（含两轮外部复核）

- **时间**：2026-10-23 20:58–23:25
- **目标**：把原始 `speaker` 标签（形态/称号/爵位/复合标签）映射成 `canonical_speaker` + `form`。

## 实际动作

1. 抓称呼原料：`tools/fetch-nicknames.js` 抓 BWiki 31 个角色/形态页的 `昵称/外号`；再用 SMW 取 `称号/全名/外文名`；百度百科、萌娘百科交叉核对。
2. 人工整理 `docs/speaker-aliases.md`（称呼集合 v4）：主角=阿基维利 + 命途外号；12 黄金裔 + X 爵体系；前世黄金裔；迷迷→昔涟演化线。
3. 生成配置 v1（38 canonical / 25 literal / 42 address_scan），跑 `tools/normalize-corpus.js`：v1 语料归一命中 19,058/23,090 = **82.54%**。
4. 分析 `data/reports/unmatched-speakers.md`（434 个未匹配标签 / 4,043 条），扩表为 v2（agent `alias-v2`）：canonical **124**、literal 128、pattern_rules 17、composite_rules 21。
5. 外部复核第一轮（Gemini）：指出 5 类勘误（老日关系反转、欢愉主/雷主越界、梗名混入 aliases、剑旗爵误杀、救世主/伙伴多义）+ 4 个架构拍板 + 9 条未归一处置 + 1 处可读性 → 写 `tools/patch-alias-v3.js` 生成 v3（25 条修订）。
6. 外部复核第二轮：发现 `萨姆` 优先级穿透 bug（`canonical.萨姆.speaker_aliases` 与 `literal_map` 抢键）、`meta.version` 类型、覆盖率投影未更新等 → 补 20 条修订。
7. 自查发现 `pattern_rules` 两条把**说明文字**写进了 `form` 字段，污染 204 条记录 → 置空修掉。

## 输入 / 输出

- 输入：31 个角色页标签、`unmatched-speakers.md`、外部复核建议
- 输出：`data/config/speaker-alias.json` / `.v2.json` / **`.v3.json`（交付用）**、`docs/speaker-aliases.md`、`docs/speaker-alias-changes.md`、`docs/speaker-alias-errata.md`、`tools/patch-alias-v3.js`

## 验证

- v3 在 v1 语料口径：23,090 条非空 speaker → 22,949 命中 + 141 条非说话人标签 = **有效归一 100%**；
- final 语料口径（v3.1 新增记录）实测 23,460/24,041 = **97.58%**；
- 修完 `form` 异常：204 → **0**。

## 问题与处置

- 「老日」方向写反：BWiki 字段语义是「别人怎么叫他」，必须用语料实证校对；
- 同一字符串不能既是某人的别名、又是另一个人的 canonical 键（萨姆案例）；
- 配置里的"说明文字"必须有专用字段，否则下游当数据用。

## 状态

完成（v3 为定稿）。
