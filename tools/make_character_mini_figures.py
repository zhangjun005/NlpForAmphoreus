"""make_character_mini_figures.py — 每角色迷你图（3 面板：台词量/步骤、神谕相似度+关键时刻标注、称呼 Top5）
- 中文字体：Microsoft YaHei / SimHei（避免方框）
- 输出 docs/report/figures/chars/<角色>_mini.png；配对 data/plot_data/chars/<角色>_mini.{csv,json}
"""
import hashlib
import io
import json
import os
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(ROOT, "docs", "report", "figures", "chars")
DATA_DIR = os.path.join(ROOT, "data", "plot_data", "chars")
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

CHARS = ["白厄", "万敌", "那刻夏", "昔涟", "遐蝶", "缇宝", "海瑟音", "刻律德菈", "阿格莱雅", "赛飞儿", "风堇", "开拓者", "三月七", "丹恒"]
VERSIONS = ["3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"]


def _created_at(sources):
    """与 export_plot_data.created_at 同口径：取数据源里最新的 mtime。"""
    mtimes = []
    for s in sources:
        p = os.path.join(ROOT, s) if not os.path.isabs(s) else s
        if os.path.exists(p):
            mtimes.append(os.path.getmtime(p))
    ts = max(mtimes) if mtimes else os.path.getmtime(__file__)
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")

traj = json.load(io.open(os.path.join(ROOT, "data/config/character-trajectory-all.json"), encoding="utf-8"))["characters"]
oracles = {}
for line in io.open(os.path.join(ROOT, "data/corpus/oracles.jsonl"), encoding="utf-8"):
    if line.strip():
        o = json.loads(line)
        oracles[o["oracle_id"]] = o
knife_lines = io.open(os.path.join(ROOT, "data/plot_data/f6_knife_ranks.csv"), encoding="utf-8-sig").read().strip().split("\n")
knife_header = knife_lines[0].split(",")

for ch in CHARS:
    c = traj.get(ch)
    if not c:
        continue
    pv = c["per_version"]
    counts = [pv.get(v, {}).get("n_records", 0) for v in VERSIONS]
    steps = [pv.get(v, {}).get("n_steps", 0) for v in VERSIONS]
    curve_path = os.path.join(ROOT, f"data/plot_data/oracle_sim__{ch}.csv")
    curve = []
    if os.path.exists(curve_path):
        lines = io.open(curve_path, encoding="utf-8-sig").read().strip().split("\n")
        header = lines[0].split(",")
        keys = ["order", "version", "tfidf_own", "sbert_own", "n_lines",
                "in_oracle_first", "in_recitation", "in_fulfillment", "in_key_event", "in_knife"]
        idx = {k: header.index(k) for k in keys}
        for ln in lines[1:]:
            p = ln.split(",")
            try:
                curve.append({k: (float(p[i]) if k in ("tfidf_own", "sbert_own") else (int(p[i]) if k in ("order", "n_lines") else str(p[i]))) for k, i in idx.items()})
            except Exception:
                continue
    own = None
    for oid, o in oracles.items():
        if o.get("holder") == ch:
            own = oid
    k_names = []
    for ln in knife_lines[1:]:
        parts = ln.split(",")
        row = dict(zip(knife_header, parts))
        blob = " ".join(str(v) for v in row.values())
        if ch in blob:
            k_names.append(row.get("scene_id") or row.get("id") or "")

    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.2), gridspec_kw={"width_ratios": [1, 1.6, 0.9]})
    a1, a2, a3 = axes
    x = np.arange(len(VERSIONS))
    a1.bar(x, counts, color="#5b7f9e")
    a1b = a1.twinx()
    a1b.plot(x, steps, color="#c0703a", marker="o", ms=3, lw=1.2)
    a1.set_xticks(x)
    a1.set_xticklabels(VERSIONS, rotation=45, fontsize=7)
    a1.set_title("每版本台词量（柱）与步骤（线）", fontsize=8.5)
    a1.tick_params(labelsize=7)
    a1.grid(axis="y", alpha=0.25)

    if curve:
        xo = list(range(1, len(curve) + 1))  # 该角色第 N 次出场（order 会重复，不能当横轴）
        a2.plot(xo, [r["tfidf_own"] for r in curve], color="#8aa6bf", lw=0.9, label="词频加权")
        a2.plot(xo, [r["sbert_own"] for r in curve], color="#c0703a", lw=1.2, label="语义向量")
        labels = {"in_oracle_first": "文本首现", "in_recitation": "吟诵", "in_fulfillment": "兑现",
                  "in_key_event": "关键事件", "in_knife": "高光场景"}
        colors = {"in_oracle_first": "#2c3e50", "in_recitation": "#8e44ad", "in_fulfillment": "#c0392b",
                  "in_key_event": "#2e8b57", "in_knife": "#d35400"}
        for flag, nm in labels.items():
            pts = [r for r in curve if r.get(flag) in (1, "1")]
            if not pts:
                continue
            a2.scatter([xo[curve.index(r)] for r in pts], [r["sbert_own"] for r in pts], s=20, color=colors[flag],
                       zorder=5, label=nm)
            for r in pts[:2]:
                a2.annotate(nm, (xo[curve.index(r)], r["sbert_own"]), fontsize=6.5, color=colors[flag],
                            xytext=(0, 7), textcoords="offset points", ha="center")
        if own:
            a2.set_title(f"与 {own}（自己的神谕）相似度（横轴=该角色第 N 次出场）", fontsize=8.5)
        a2.tick_params(labelsize=7)
        a2.legend(fontsize=6, frameon=False, loc="upper left")
        a2.grid(alpha=0.2)
    else:
        a2.text(0.5, 0.55, "B 组：无自己的神谕\n（曲线取与 13 条最高值，未绘制）", ha="center", va="center", fontsize=8)
        a2.set_axis_off()

    addr = {}
    for v in VERSIONS:
        for k, n in (pv.get(v, {}).get("address_own") or {}).items():
            addr[k] = addr.get(k, 0) + n
    top = sorted(addr.items(), key=lambda x: -x[1])[:5]
    if top:
        a3.barh([k for k, _ in top][::-1], [n for _, n in top][::-1], color="#8fae8b")
        a3.set_title("自己台词里的称呼 Top5", fontsize=8.5)
        a3.tick_params(labelsize=7)
        a3.grid(axis="x", alpha=0.25)
    else:
        a3.set_axis_off()

    s = c["summary"]
    sub = f"{ch} · {s['n_records']} 条 / {s['n_steps']} 步"
    if k_names:
        sub += " · 相关刀景：" + "、".join(k_names[:4])
    fig.suptitle(sub, fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    out_png = os.path.join(FIG_DIR, f"{ch}_mini.png")
    fig.savefig(out_png, dpi=150)
    plt.close(fig)

    count_by_v = {v: pv.get(v, {}).get("n_records", 0) for v in VERSIONS}
    rows = [[r["order"], r["version"], r["tfidf_own"], r["sbert_own"], r["n_lines"], count_by_v.get(r["version"], 0),
             r.get("in_oracle_first", 0), r.get("in_recitation", 0), r.get("in_fulfillment", 0),
             r.get("in_key_event", 0), r.get("in_knife", 0)] for r in curve]
    csv_path = os.path.join(DATA_DIR, f"{ch}_mini.csv")
    with io.open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write("order,version,tfidf_own,sbert_own,n_lines,version_n_records,in_oracle_first,in_recitation,in_fulfillment,in_key_event,in_knife\n")
        for row in rows:
            f.write(",".join(str(x) for x in row) + "\n")
    raw = io.open(csv_path, encoding="utf-8").read().encode("utf-8")
    meta = {
        "figure": f"docs/report/figures/chars/{ch}_mini.png",
        "title": f"{ch} 迷你图：台词量/步骤、自身神谕相似度（标出文本首现/吟诵/兑现/关键事件/高光场景）、称呼 Top5",
        "axes": {"left": "x=版本；y=台词条数/出场步骤", "middle": "x=全局步序；y=余弦相似度（词频加权/语义向量）；标注=关键时刻名称",
                 "right": "x=命中次数；y=称呼"},
        "plot_data_csv": f"data/plot_data/chars/{ch}_mini.csv",
        "sources": ["data/config/character-trajectory-all.json", f"data/plot_data/oracle_sim__{ch}.csv", "data/corpus/oracles.jsonl"],
        "filters": "A/B 组按报告口径；B 组无自身神谕，中图留空",
        "generator": "tools/make_character_mini_figures.py",
        "run_command": "conda run -n nlpLesson python tools/make_character_mini_figures.py",
        "data_sha256_16": hashlib.sha256(raw).hexdigest()[:16],
        "created_at": _created_at(["data/config/character-trajectory-all.json",
                                   f"data/plot_data/oracle_sim__{ch}.csv"]),
    }
    json.dump(meta, io.open(os.path.join(DATA_DIR, f"{ch}_mini.meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("生成:", ch, "曲线点", len(curve), "刀景", k_names[:3])
print("完成")
