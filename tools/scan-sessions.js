// 从历史会话里精确提取 playwright 工具调用 + 对应结果，回答"之前到底能不能用"
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const root = 'D:\\DSH\\sessions';
const files = [];
(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith('.zstd')) files.push(p);
  }
})(root);

const MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]);
function decompressAll(buf) {
  const offs = [];
  let i = 0;
  while ((i = buf.indexOf(MAGIC, i)) !== -1) { offs.push(i); i += 4; }
  let out = '';
  for (let k = 0; k < offs.length; k++) {
    const end = k + 1 < offs.length ? offs[k + 1] : buf.length;
    try { out += zlib.zstdDecompressSync(buf.subarray(offs[k], end)).toString('utf8'); } catch {}
  }
  return out;
}

function collect(node, calls, results, seen) {
  if (!node || typeof node !== 'object' || seen.has(node)) return;
  if (Array.isArray(node)) { for (const v of node) collect(v, calls, results, seen); return; }
  seen.add(node);
  if (node.type === 'tool-call' && typeof node.name === 'string' && node.name.startsWith('mcp__playwright') && node.id) {
    calls.set(node.id, { name: node.name, args: node.arguments });
  }
  if (node.toolCallId && node.content) {
    const txt = JSON.stringify(node.content).slice(0, 400);
    results.set(node.toolCallId, { isError: !!node.isError, txt });
  }
  for (const k of Object.keys(node)) collect(node[k], calls, results, seen);
}

for (const f of files.sort()) {
  const text = decompressAll(fs.readFileSync(f));
  const calls = new Map(), results = new Map();
  const seen = new Set();
  let ok = 0;
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try { collect(JSON.parse(line), calls, results, seen); } catch { ok++; }
  }
  if (!calls.size) continue;
  console.log(`\n### ${path.basename(path.dirname(f))}  (playwright 调用 ${calls.size} 次)`);
  for (const [id, c] of calls) {
    const r = results.get(id);
    const short = (s) => (s || '').replace(/\\[nrt]/g, ' ').replace(/\s+/g, ' ').slice(0, 200);
    console.log(`  - ${c.name}  ${short(c.args)}`);
    console.log(`    => ${r ? (r.isError ? '[ERROR] ' : '[OK] ') + short(r.txt) : '(无结果记录)'}`);
  }
}
