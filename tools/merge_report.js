/** merge_report.js — 把 AnalysisV2/draft/ 阅读说明 + 7 章合并成一份完整报告（带目录、术语表、附录） */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const D = path.join(ROOT, 'AnalysisV2', 'draft');
const GLOSSARY = '00-阅读说明与术语表.md';
const files = [
  ['01-introduction.md', '第 1 章 导论：从「命定」到「语言」'],
  ['02-written-language.md', '第 2 章 命定如何被写成语言'],
  ['03-takeover.md', '第 3 章 命定如何被角色接管'],
  ['04-fulfillment.md', '第 4 章 命定如何被兑现'],
  ['05-salience.md', '第 5 章 叙事显著性 ≠ 刀子'],
  ['06-closure.md', '第 6 章 命定的闭环：告别、「明天见」与「收梢即起始」'],
  ['07-conclusion.md', '第 7 章 结论与局限'],
];

const parts = [];
parts.push(`# 命定如何被写进语言：翁法罗斯主线的神谕、引用与兑现（NLP 课程报告草稿）

> **先读「阅读说明与术语表」**：报告里的内部代码词（检测器 A/B1、Top100、MRR、κ、TF-IDF、句向量等）都在那一页用大白话解释。
> 数据：《崩坏：星穹铁道》翁法罗斯主线 3.0–3.7，67 个任务页，26,332 条台词/旁白/选项（566,798 字）。
> 角色口径：黄金裔 11 位（游戏称"十二"，但「岁月」席位历史更替，实际固定 11 位）+ 单列 3 人（开拓者、三月七、丹恒）；荒笛、玻吕茜亚只作注记。
> 方法口径：数据层全量（每条台词入语料、每步被打分）；解释层基于 14 个角色的逐条精读（L3）；人工/模型辅助标注的一致性为 κ=0.788（含义见术语表）；"自动找兑现"的实验基本失败（最好 MRR 0.132，含义见术语表）。
> 素材索引：根目录 \`INDEX.md\`；图-数据配对：\`docs/report/figures-index.md\`；本稿由 \`AnalysisV2/draft/\` 各章合并。

## 一句话总结（大白话）

翁法罗斯的"命定"不是一张写好的事件清单，而是**一套说法**：13 条神谕有固定的句式与腔调；角色们用五种方式跟它打交道——**不念它**（白厄）、**完整念完并自己宣布兑现**（阿格莱雅）、**把它从泰坦的话里提炼成箴言**（缇宝）、**改写它**（遐蝶）、**把"救世主"让给别人**（开拓者）；13 条神谕里 8 条照字面实现、2 条被读反、1 条换了对象，还有 1 条是"事件先发生、后来才被追认为预言"。同时，我们用统计方法找"最虐的剧情"基本失败——检测器测的是"语言变化大不大"，不是"读者痛不痛"。

## 目录

0. [阅读说明与术语表](#阅读说明与术语表先看这一页)
${files.map(([f, t], i) => `${i + 1}. ${t}`).join('\n')}

---
`);

// 0. 阅读说明（不编号章）
{
  let t = fs.readFileSync(path.join(D, GLOSSARY), 'utf8');
  const lines = t.split('\n');
  const start = lines.findIndex((l) => l.startsWith('# '));
  if (start >= 0) lines.splice(start, 1);
  parts.push(`\n\n# 阅读说明与术语表（先看这一页）\n\n${lines.join('\n').trim()}\n`);
}

for (const [f, title] of files) {
  let t = fs.readFileSync(path.join(D, f), 'utf8');
  // 统一章标题：删除文件内已有的一级标题，用目录里的标题
  const lines = t.split('\n');
  const start = lines.findIndex((l) => l.startsWith('# '));
  if (start >= 0) lines.splice(start, 1);
  t = lines.join('\n').trim();
  parts.push(`\n\n# ${title}\n\n${t}\n`);
}

// 附录：产物与核对
const auditPath = path.join(ROOT, 'docs/report/final-audit.md');
const audit = fs.existsSync(auditPath) ? fs.readFileSync(auditPath, 'utf8') : '（核对结果待生成）';
parts.push(`\n\n---\n\n# 附录 A：产物索引与归档核对\n\n${audit}\n`);
parts.push(`
# 附录 B：如何复现

- 语料与向量：\`data/models/manifest.json\`、\`data/models/manifest_sbert.json\`；
- 图与数据：\`docs/report/figures/\` + \`data/plot_data/\`（同名 CSV + meta，sha256 可验）；
- 角色曲线：\`data/config/oracle-similarity-curves.json\`、\`docs/report/oracle-similarity-curves.md\`；
- 逐角色精读：\`AnalysisV2/notes/l3/\`（14 份）；
- 任意新文本（如角色曲歌词）：\`conda run -n nlpLesson python tools/encode_text.py --file 歌词.txt --char 白厄\`；
- 全量核对：\`node tools/final_audit.js\`。
`);

fs.writeFileSync(path.join(ROOT, 'AnalysisV2', '报告.md'), parts.join('\n'), 'utf8');
console.log('合并完成：AnalysisV2/报告.md，长度', fs.statSync(path.join(ROOT, 'AnalysisV2', '报告.md')).size, 'bytes');
