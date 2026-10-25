/** fix-yichao-and-mirror.js — 1) 修正「忆潮」误称（#21860–21861 实际在 3.6 大墓任务）2) 镜像神谕处补原文 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

// 1) 修正 docs/AnalysisV2/前端章节里的"3.6 忆潮"
const files = [
  'AnalysisV2/draft/03-takeover.md',
  'AnalysisV2/draft/04-fulfillment.md',
  'frontend/docs/13-章节正文.md',
  'docs/前端改版-章节正文.md',
  'docs/收束三题分析-前端参考.md',
  'frontend/docs/15-收束三题.md',
];
for (const rel of files) {
  const p = path.join(ROOT, rel);
  if (!fs.existsSync(p)) continue;
  let t = fs.readFileSync(p, 'utf8');
  const before = t;
  t = t.split('3.6 忆潮还补了一句').join('3.6 大墓的记忆场景里，她还补了一句');
  t = t.split('3.6 忆潮确认').join('3.6 大墓的记忆场景确认');
  t = t.split('3.6 忆潮').join('3.6 大墓（记忆场景）');
  if (t !== before) { fs.writeFileSync(p, t, 'utf8'); console.log(rel, '忆潮已改为「3.6 大墓记忆场景」'); }
}

// 2) 第 1 章镜像句补原文
const c = path.join(ROOT, 'frontend/docs/13-章节正文.md');
let t = fs.readFileSync(c, 'utf8');
const old = '最干净的证据是 O10/O11 两条"镜像神谕"：两句用词相同、只换语序，所以词频加权给出的两条曲线在 686 步上**逐点相等（最大差 0）**';
const neu = '最干净的证据是两条"镜像神谕"——O10「汝将长眠于涛声中，于天地境界之海完成征服」（海瑟音）与 O11「汝将于天地境界之海完成征服，长眠于涛声中」（刻律德菈）：两句用词相同、只换语序，所以词频加权给出的两条曲线在 686 步上**逐点相等（最大差 0）**';
if (t.includes(old)) { t = t.replace(old, neu); fs.writeFileSync(c, t, 'utf8'); console.log('镜像句已补原文'); }
else console.log('镜像句未匹配');
