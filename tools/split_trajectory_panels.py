"""split_trajectory_panels.py — 把 f7/f8 四联图拆成 4 张独立小图（每张可在页面里单独配文）

背景：四联图放在一页 1100px 宽里，每个子图只有 500px，图内字号等效 3px。拆开后
每张图单独出图（figsize 7.2x3.8 @150dpi ≈ 1080px），页面里 1:1 展示，图内文字可读。

输入：data/plot_data/f7_bai_trajectory.csv / f8_xi_trajectory.csv（export_plot_data 已配对）
输出：docs/report/figures/f7a..f7d / f8a..f8d；配对数据由 export_plot_data 的 data_f7a.. 生成
"""
import csv
import io
import os

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "plot_data")
FIG = os.path.join(ROOT, "docs", "report", "figures")
VERSIONS = ["3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"]

names = {f.name for f in font_manager.fontManager.ttflist}
for cand in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans SC"]:
    if cand in names:
        plt.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
        break
plt.rcParams["axes.unicode_minus"] = False

CMAP = plt.get_cmap("tab20")


def load(fn):
    with io.open(os.path.join(DATA, fn), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    by_v = {r["version"]: r for r in rows}
    out = []
    for v in VERSIONS:
        r = by_v.get(v)
        out.append(r if r else {"version": v})
    return out


def num(r, key, default=0.0):
    v = r.get(key, "")
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def style(ax, title, ylabel, xlabels=VERSIONS):
    pass  # 标题交给页面文字，图内不重复
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xticks(range(len(VERSIONS)))
    ax.set_xticklabels(xlabels, fontsize=10)
    ax.tick_params(axis="y", labelsize=10)
    ax.grid(axis="y", alpha=0.25)


def panel_lines(rows, char, out, color_bar="#2e5c8a", color_line="#d98c3f"):
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    xs = range(len(VERSIONS))
    ax.bar(xs, [num(r, "n_records") for r in rows], color=color_bar, alpha=0.85, label="台词条数")
    ax.set_ylabel("台词条数", color=color_bar, fontsize=11)
    ax.tick_params(axis="y", labelcolor=color_bar, labelsize=10)
    ax2 = ax.twinx()
    ax2.plot(xs, [num(r, "n_steps") for r in rows], color=color_line, marker="o", lw=2, label="出场步骤数")
    ax2.set_ylabel("出场步骤数", color=color_line, fontsize=11)
    ax2.tick_params(axis="y", labelcolor=color_line, labelsize=10)
    style(ax, "%s：台词量（柱）与出场步骤（线）" % char, "台词条数")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=9, frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def panel_forms(rows, char, out, form_cols):
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    xs = range(len(VERSIONS))
    bottom = np.zeros(len(VERSIONS))
    for i, col in enumerate(form_cols):
        vals = np.array([num(r, col) for r in rows], dtype=float)
        label = "本体" if col == "form_base" else col.replace("form_", "")
        ax.bar(xs, vals, bottom=bottom, label=label, color=CMAP(i % 20), edgecolor="white", linewidth=0.5)
        bottom += vals
    used = sum(num(r, c) for c in form_cols for r in [])
    others = np.array([sum(num(r, c) for c in rows[0] if c.startswith("form_") and c not in form_cols) for r in rows], dtype=float)
    if others.sum() > 0:
        ax.bar(xs, others, bottom=bottom, label="其他形态", color="0.7", edgecolor="white", linewidth=0.5)
    style(ax, "%s：语言形态构成（堆叠）" % char, "台词条数")
    ax.legend(fontsize=8, frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def panel_address(rows, char, out, addr_cols):
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    xs = range(len(VERSIONS))
    for i, col in enumerate(addr_cols):
        ax.plot(xs, [num(r, col) for r in rows], marker="o", lw=2,
                label=col.replace("addr_", ""), color=CMAP(i % 20))
    style(ax, "%s：称呼词命中（自己的台词）" % char, "命中次数")
    ax.legend(fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def panel_scores(rows, char, out):
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    xs = range(len(VERSIONS))
    ax.plot(xs, [num(r, "mean_score_a", float("nan")) for r in rows], marker="o", lw=2,
            color="#2e5c8a", label="检测器 A 分数")
    ax.plot(xs, [num(r, "mean_score_b1", float("nan")) for r in rows], marker="s", lw=2,
            color="#d98c3f", label="检测器 B1 分数")
    style(ax, "%s：所在步骤的检测器分数" % char, "所在步骤平均分")
    ax3 = ax.twinx()
    ax3.plot(xs, [num(r, "top100_b1") * 100 for r in rows], ls="--", lw=1.6, color="#8e44ad",
             label="B1 前 100 命中率 (%)")
    ax3.set_ylabel("B1 前 100 命中率 (%)", color="#8e44ad", fontsize=11)
    ax3.tick_params(axis="y", labelcolor="#8e44ad", labelsize=10)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax3.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8.5, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def form_cols(rows):
    cols = []
    for r in rows:
        for k in r:
            if k.startswith("form_") and k not in cols:
                cols.append(k)
    # 本体在最下、其余取总量前 5（其余合并为「其他形态」）
    others = sorted([c for c in cols if c != "form_base"], key=lambda c: -sum(num(r, c) for r in rows))
    others = [c for c in others if sum(num(r, c) for r in rows) > 0][:5]
    total_base = sum(num(r, "form_base") for r in rows)
    return (["form_base"] if total_base else []) + others


def addr_cols(rows):
    cols = []
    for r in rows:
        for k in r:
            if k.startswith("addr_") and k not in cols:
                cols.append(k)
    return sorted(cols, key=lambda c: -sum(num(r, c) for r in rows))


def main():
    os.makedirs(FIG, exist_ok=True)
    jobs = [
        ("f7_bai_trajectory.csv", "白厄", "f7", "bai"),
        ("f8_xi_trajectory.csv", "昔涟", "f8", "xi"),
    ]
    for fn, char, tag, short in jobs:
        rows = load(fn)
        panel_lines(rows, char, os.path.join(FIG, "%sa_%s_lines.png" % (tag, short)))
        panel_forms(rows, char, os.path.join(FIG, "%sb_%s_forms.png" % (tag, short)), form_cols(rows))
        panel_address(rows, char, os.path.join(FIG, "%sc_%s_address.png" % (tag, short)), addr_cols(rows))
        panel_scores(rows, char, os.path.join(FIG, "%sd_%s_detector.png" % (tag, short)))
        print("已拆：", tag, char)
    print("完成，输出目录", FIG)


if __name__ == "__main__":
    main()
