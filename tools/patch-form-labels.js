/** patch-form-labels.js — form=null 不再显示为「无形态」，改为「角色名（本体）」 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

// 1) character_trajectory.py
const p = path.join(ROOT, 'tools/character_trajectory.py');
let t = fs.readFileSync(p, 'utf8');

// (b) 图例：null → 角色名（本体）
t = t.replace(
  '    top_forms = [f for f, _ in form_tot.most_common(5)]\n    bottom = np.zeros(len(vers))',
  '    top_forms = [f for f, _ in form_tot.most_common(5)]\n    _nm = ch.get("name") or ch.get("char") or "本体"\n    bottom = np.zeros(len(vers))'
);
t = t.replace(
  'label=L(f, f) if f else L("无形态", "none"),',
  'label=L(f, f) if f else L(_nm + "（本体）", _nm + " (base)"),'
);

// 分版本统计表：null → 角色名（本体）
t = t.replace(
  '            forms = "、".join("%s %d" % (k or "无形态", n) for k, n in list(pv["forms"].items())[:3])',
  '            _nm2 = ch.get("name") or ch.get("char") or "本体"\n            forms = "、".join("%s %d" % (k or (_nm2 + "（本体）"), n) for k, n in list(pv["forms"].items())[:3])'
);

// L1 汇总表：null → 角色名（本体）
t = t.replace(
  '        top_form = next(("%s（%d）" % (k or "无形态", n) for k, n in forms.items()), "—")',
  '        _nm3 = ch.get("name") or ch.get("char") or ch.get("summary", {}).get("name") or "本体"\n        top_form = next(("%s（%d）" % (k or (_nm3 + "（本体）"), n) for k, n in forms.items()), "—")'
);

// 白厄叙述文本
t = t.replace('「幼年/无形态 + 老师', '「幼年/白厄（本体）+ 老师');
t = t.replace('以无形态为主、出现「盗火行者」', '以白厄（本体）为主、出现「盗火行者」');

// 说明行
t = t.replace('3. 形态（form）字段有 null，null 不等于「无形态」；',
              '3. 形态（form）字段的 null 表示角色本人常态（图上按「角色名（本体）」标注，不再写「无形态」）；');

fs.writeFileSync(p, t, 'utf8');
console.log('character_trajectory.py 标签已改');

// 2) export_plot_data.py：配对 CSV 增加 form_base 列
const ep = path.join(ROOT, 'tools/export_plot_data.py');
let e = fs.readFileSync(ep, 'utf8');
e = e.replace(
  '            ["form_" + t for t in FORM_TERMS] + ["addr_" + t for t in ADDR_TERMS] + \\',
  '            ["form_base"] + ["form_" + t for t in FORM_TERMS] + ["addr_" + t for t in ADDR_TERMS] + \\'
);
e = e.replace(
  '            for t in FORM_TERMS:\n                row["form_" + t] = pv["forms"].get(t, 0)',
  '            row["form_base"] = pv["forms"].get("null", 0)  # null=角色本人常态\n            for t in FORM_TERMS:\n                row["form_" + t] = pv["forms"].get(t, 0)'
);
fs.writeFileSync(ep, e, 'utf8');
console.log('export_plot_data.py form_base 列已加');
