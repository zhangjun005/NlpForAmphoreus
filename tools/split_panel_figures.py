"""split_panel_figures.py — 把 f14 / f15 的两联图拆成单图（页面里 1:1 展示，图内文字可读）

f14 镜像对：左联=词频加权两条线重合，右联=语义向量两条线。拆成 f14a / f14b。
f15 检索：左联=MRR，右联=Recall@k。拆成 f15a / f15b。
输入为 export_plot_data 已配对好的 CSV；输出 PNG 由本脚本生成，配对数据由 data_f14a… 生成。
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

names = {f.name for f in font_manager.fontManager.ttflist}
for cand in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans SC"]:
    if cand in names:
        plt.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
        break
plt.rcParams["axes.unicode_minus"] = False


def rows(fn):
    with io.open(os.path.join(DATA, fn), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def mirror_panels():
    rs = rows("f14_mirror_pair_O10_O11.csv")
    xs = [int(r["step_index"]) for r in rs]
    panels = [
        ("f14a_mirror_tfidf.png", "词频加权", "tfidf_O10", "tfidf_O11", "#2e5c8a", "#c0392b",
         "O10 / O11 的词频加权曲线：语序被丢弃，两条线逐点相等（最大差 0）"),
        ("f14b_mirror_sbert.png", "语义向量", "sbert_O10", "sbert_O11", "#2e5c8a", "#c0392b",
         "O10 / O11 的语义向量曲线：只换语序，余弦只差 0.018"),
    ]
    for fn, yname, c1, c2, col1, col2, note in panels:
        fig, ax = plt.subplots(figsize=(7.0, 3.6))
        ax.plot(xs, [num(r[c1]) for r in rs], lw=2, color=col1, label="O10（海瑟音）")
        ax.plot(xs, [num(r[c2]) for r in rs], lw=1.6, ls="--", color=col2, label="O11（刻律德菈）")
        ax.set_xlabel("全局步序（1–686）", fontsize=11)
        ax.set_ylabel(yname + " 余弦相似度", fontsize=11)
        ax.tick_params(labelsize=10)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=10, frameon=False)
        ax.set_xlim(1, 686)
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, fn), dpi=150, bbox_inches="tight", pad_inches=0.25)
        plt.close(fig)


def retrieval_panels():
    rs = rows("f15_retrieval_v3.csv")
    # (a) MRR：x=方法，按 variant 分组柱
    mrr = [r for r in rs if r["panel"] == "mrr" and r["method"]]
    variants = []
    for r in mrr:
        if r["variant"] not in variants:
            variants.append(r["variant"])
    methods = []
    for r in mrr:
        if r["method"] not in methods:
            methods.append(r["method"])
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    width = 0.8 / max(1, len(variants))
    xs = np.arange(len(methods))
    for i, v in enumerate(variants):
        vals = []
        for m in methods:
            hit = [num(r["value"]) for r in mrr if r["variant"] == v and r["method"] == m]
            vals.append(hit[0] if hit else float("nan"))
        ax.bar(xs + i * width - 0.4 + width / 2, vals, width=width, label=v)
    ax.set_xticks(xs)
    ax.set_xticklabels(methods, rotation=25, ha="right", fontsize=9.5)
    ax.set_ylabel("MRR", fontsize=11)
    ax.tick_params(labelsize=10)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "f15a_retrieval_mrr.png"), dpi=150, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)

    # (b) Recall@k：x=k，每个方法一条线
    rec = [r for r in rs if r["panel"] == "recall" and r["method"]]
    ks = sorted({int(num(r["k"])) for r in rec})
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    for m in methods:
        vals = []
        for k in ks:
            hit = [num(r["value"]) for r in rec if r["method"] == m and int(num(r["k"])) == k]
            vals.append(hit[0] if hit else float("nan"))
        ax.plot(ks, vals, marker="o", lw=2, label=m)
    ax.set_xlabel("k（前 k 名）", fontsize=11)
    ax.set_xticks(ks)
    ax.set_ylabel("Recall@k", fontsize=11)
    ax.tick_params(labelsize=10)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "f15b_retrieval_recall.png"), dpi=150, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def main():
    mirror_panels()
    retrieval_panels()
    print("已拆 f14/f15 两联图")


if __name__ == "__main__":
    main()
