const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const R = fs.readFileSync(path.join(ROOT, 'data/corpus/amphoreus.final.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
const occ = R.filter((r) => (r.text || '').includes('明天'));
const fp = occ.filter((r) => /证明天|说明天/.test(r.text || '') && !/明天见/.test(r.text || ''));
const clean = occ.filter((r) => !(/证明天|说明天/.test(r.text || '') && !/明天见/.test(r.text || '')));
const sp = {};
for (const r of clean) { const s = r.canonical_speaker || r.speaker || '旁白'; sp[s] = (sp[s] || 0) + 1; }
const byv = {};
for (const r of clean) byv[r.version] = (byv[r.version] || 0) + 1;
const out = {
  raw: occ.length,
  false_positive: fp.length,
  clean: clean.length,
  speakers: Object.fromEntries(Object.entries(sp).sort((a, b) => b[1] - a[1]).slice(0, 10)),
  by_version: byv,
  mingtianjian: R.filter((r) => (r.text || '').includes('明天见')).length,
};
fs.writeFileSync(path.join(ROOT, 'data/config/mingtian-counts.json'), JSON.stringify(out, null, 2), 'utf8');
console.log(JSON.stringify(out, null, 2));
