# 23 · 角色口径修正：11 黄金裔 + 3 单列 + 2 NPC

- **时间**：2026-10-24 21:00–21:30
- **目标**：用户连续指正角色名单口径，最终定稿：黄金裔 11 位、单列 3 人、NPC 2 人，并同步到所有产物。

## 用户裁定（按时间）

1. 昔涟的水晶花寓言「就当是她自己」（按设定）：K36/E30 改为「昔涟（记忆形态，原文标注『记忆的花』）为最初的种子/桃子讲述」。
2. O04/O05 不能都是遐蝶：O05「汝将凋零」是**双子共有**神谕，holder 改为 **玻吕茜亚**。
3. 昔涟 3.4 与 3.7 都重要：O13 改为**多事件段**（3.4|点燃|7 意义转折 + 3.7|魔女|21 兑现）。
4. 丹恒才是对应的荒笛 → 后来进一步明确：**丹恒单列分析**，荒笛归 NPC。
5. 黄金裔名单最终为 **11 位**：白厄、万敌、阿格莱雅、缇宝、遐蝶、那刻夏、风堇、赛飞儿、海瑟音、刻律德菈、昔涟。
   - 原因：游戏称「十二黄金裔」，但**「岁月」席位历史上多次更换**（欧洛尼斯一线 / 德谬歌与昔涟的演化），实际固定 11 位。
6. **荒笛、玻吕茜亚 = NPC 类**（70 条/4 步；72 条/5 步），不进黄金裔主表。
7. **开拓者、三月七、丹恒 = 单列分析**（3 人；三月七含长夜月/永夜之帷/幻象/记忆形态）。

## 实际动作

1. 修 A1：`oracles.jsonl` 的 O05 holder → 玻吕茜亚；`oracle-fulfillment.v2.json` 升级为 `event_segments: [{segment_id, role, note}]` 多段结构（O13 两段、O05 两段）。
2. 修 K36/E30 的讲述者口径（昔涟本人）。
3. 派 `annotator`（task-25）改自己的 5 个产物：`knife-scenes.json` 加 `roster_policy` + 三分组、`knife-scenes.md` 覆盖表拆分、`key-events.json/.md` 加 `role_group`、`outline-annotator.md` 同步口径。
4. 派/通知 `baseline-a`：task-24（L1/L2）与 task-23（曲线）改为 **A 11 / B 3 / NPC 2** 三分区，补丹恒、三月七的上下文与曲线。

## 结果（annotator 回报）

- 黄金裔覆盖 **11/11**（白厄 2、万敌 3、阿格莱雅 3、缇宝 2、遐蝶 2、那刻夏 3、风堇 1、赛飞儿 3、海瑟音 1、刻律德菈 1、昔涟 5 个场景）；
- 单列：开拓者 K23/K34、三月七 K33、丹恒无独立场景（在 K22/K23 同场）；
- NPC：荒笛 K22、玻吕茜亚 K13；非黄金裔关键刀子 4 个（K30/K31/K32/K35）；
- 场景内容与引文未动（36 场景 / 2,031 条 / 47,022 字；30 事件，evidence 全部校验通过）。

## 产出

`data/config/knife-scenes.json`、`data/reports/knife-scenes.md`、`data/config/key-events.json`、`data/reports/key-events.md`、`docs/report/outline-annotator.md`、`data/config/oracle-fulfillment.v2.json`、`data/corpus/oracles.jsonl`

## 状态

完成（口径定稿）。待 baseline-a 的 task-23/24 按新口径重跑；A1 仍需用户确认 O04/O05 类型与 O01/O07/O09/O11/O12 是否保留。
