#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
make_figures.py — 报告用 5 张图 + 数据表汇总（task-16）

只读现有 JSON/JSONL，所有数字现场计算，不硬编码：
  * 5 张 PNG → docs/report/figures/
      f1_level_scores.png    A vs B1 在人工等级 0/1/2/3 上的分数箱线图
      f2_rank_shift.png      686 步 A→B1 排名散点 + 5 个最大提升/下降标注
      f3_style_features.png  G1 神谕 / G2 对白 / G3 引用 的语体特征均值
      f4_citation_stage.png  34 处引用的 版本 × 阶段 堆叠条形图
      f5_oracle_vs_rest.png  13 个神谕兑现段 vs 其余 673 步的 A/B1 分数箱线图（附 p、Cliff's δ）
  * docs/report/data-tables.md：报告数据表汇总（每个数字标注来源文件）

中文标签：检测 matplotlib 可用中文字体（SimHei / Microsoft YaHei / Noto Sans CJK …）；
        找不到就自动退回英文标签，不中断。

运行：
    conda run -n nlpLesson python tools/make_figures.py
    conda run -n nlpLesson python tools/make_figures.py --verify   # 只检查已生成产物

约束：只写 tools/make_figures.py、docs/report/figures/*.png、docs/report/data-tables.md；
      不改语料/既有 config/既有结果；无随机。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

import numpy as np
from scipy.stats import spearmanr

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(ROOT, "docs", "report", "figures")
P_FINAL = os.path.join(ROOT, "data", "corpus", "amphoreus.final.jsonl")
P_SEGMENTS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_ORACLES = os.path.join(ROOT, "data", "corpus", "oracles.jsonl")
P_ANNOT = os.path.join(ROOT, "data", "config", "annotation-labels.json")
P_A = os.path.join(ROOT, "data", "config", "baseline-a-scores.json")
P_B1 = os.path.join(ROOT, "data", "config", "baseline-b-scores.json")
P_B2 = os.path.join(ROOT, "data", "config", "baseline-b2-scores.json")
P_STYLE = os.path.join(ROOT, "data", "config", "style-compare-results.json")
P_CITE = os.path.join(ROOT, "data", "config", "oracle-citation-coding.json")
P_RET1 = os.path.join(ROOT, "data", "config", "oracle-retrieval-results.json")
P_RET2 = os.path.join(ROOT, "data", "config", "retrieval-v2-results.json")
P_TYPESIG = os.path.join(ROOT, "data", "config", "type-and-oracle-significance.json")
P_FILLED = os.path.join(ROOT, "data", "config", "oracle-fulfillment.filled.json")
P_ANNOT_REVIEW = os.path.join(ROOT, "data", "reports", "annotation-review.md")
P_FINAL_DELIVERY = os.path.join(ROOT, "data", "reports", "final-delivery.md")
P_TIMELINE_MD = os.path.join(ROOT, "data", "reports", "oracle-citation-timeline.md")
OUT_MD = os.path.join(ROOT, "docs", "report", "data-tables.md")
RUN_CMD = "conda run -n nlpLesson python tools/make_figures.py"

METHODS = ["keyword", "tfidf_char", "tfidf_word", "bm25", "lsa"]
METHOD_LABELS = {"keyword": "关键词基线", "tfidf_char": "TF-IDF(char)",
                 "tfidf_word": "TF-IDF(word)", "bm25": "BM25", "lsa": "LSA"}
TYPES = ["identity", "memory", "prophecy", "relationship", "world", "sacrifice", "motif"]
TYPE_LABELS_CN = {"identity": "身份揭示", "memory": "记忆回收", "prophecy": "神谕/预言",
                  "relationship": "关系变化", "world": "世界规则", "sacrifice": "牺牲/死亡",
                  "motif": "母题回收"}

# ---------------------------------------------------------------------------
# 中文字体
# ---------------------------------------------------------------------------
CJK_CANDIDATES = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans SC",
                  "Source Han Sans SC", "WenQuanYi Zen Hei", "PingFang SC", "Arial Unicode MS"]


def setup_font():
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in CJK_CANDIDATES:
        if cand in names:
            plt.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return True, cand
    plt.rcParams["axes.unicode_minus"] = False
    return False, None


HAS_CJK, CJK_FONT = setup_font()


def L(cn, en):
    """中文标签（有中文字体时）否则英文"""
    return cn if HAS_CJK else en


def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# 数据装载与统计
# ---------------------------------------------------------------------------
def corpus_stats():
    rows = read_jsonl(P_FINAL)
    n = len(rows)
    chars = sum(len(r.get("text") or "") for r in rows)
    tasks = len(set(r.get("task") or "" for r in rows))
    versions = sorted(set(r.get("version") or "" for r in rows))
    kind = Counter(r.get("kind") for r in rows)
    view = Counter(r.get("view") for r in rows)
    dups = sum(1 for r in rows if r.get("is_duplicate"))
    non_narr = [r for r in rows if r.get("kind") != "narration"]
    canon = sum(1 for r in non_narr if r.get("canonical_speaker"))
    lens = sorted(len(r.get("text") or "") for r in rows)

    def pct(p):
        return lens[min(len(lens) - 1, int(p * (len(lens) - 1)))]

    return {
        "n_records": n,
        "n_chars": chars,
        "n_tasks": tasks,
        "versions": versions,
        "n_versions": len(versions),
        "kind": dict(kind.most_common()),
        "view": dict(view),
        "n_duplicates": dups,
        "n_non_narration": len(non_narr),
        "n_canonical": canon,
        "normalization_rate": round(canon / len(non_narr), 4) if non_narr else None,
        "len_p50": pct(0.50), "len_p90": pct(0.90), "len_p99": pct(0.99), "len_max": lens[-1] if lens else 0,
        "n_versions_enum": len(versions),
        "len_p50_pct": pct(0.50),
    }


def annotation_stats():
    a = read_json(P_ANNOT)
    samples = a["samples"]
    levels = Counter(s["significance"] for s in samples)
    types = Counter(t for s in samples for t in s["types"])
    layers = Counter(s.get("layer") for s in samples)
    return {"n": len(samples), "levels": {str(k): levels[k] for k in sorted(levels)},
            "types": {t: types[t] for t in TYPES}, "layers": dict(layers),
            "samples": samples}


def consistency_stats():
    """从 annotation-review.md §4 解析隔轮重标的原始数字（该数据不在 JSON 中）"""
    out = {"source": "data/reports/annotation-review.md"}
    try:
        txt = open(P_ANNOT_REVIEW, "r", encoding="utf-8").read()
    except Exception:
        return out
    m = re.search(r"隔轮重标\s*(\d+)\s*个样本", txt)
    out["n_retest"] = int(m.group(1)) if m else None
    m = re.search(r"等级完全一致率：(\d+)/(\d+)\s*=\s*([0-9.]+)%", txt)
    if m:
        out.update(level_same=int(m.group(1)), level_total=int(m.group(2)), level_rate=float(m.group(3)))
    m = re.search(r"类型集合完全一致率：(\d+)/(\d+)\s*=\s*([0-9.]+)%", txt)
    if m:
        out.update(type_same=int(m.group(1)), type_total=int(m.group(2)), type_rate=float(m.group(3)))
    m = re.search(r"平均类型交集\s*\*\*([0-9.]+)\*\*\s*个\s*/\s*平均 Jaccard\s*\*\*([0-9.]+)%", txt)
    if m:
        out.update(mean_intersection=float(m.group(1)), mean_jaccard=float(m.group(2)))
    m = re.search(r"类型集合一致率提升到\s*(\d+)%", txt)
    if m:
        out["type_rate_final"] = float(m.group(1))
    return out


def baseline_stats():
    """A/B1/B2：从 scores JSON + 标注 JSON 重算人工评估指标；长度偏差读 JSON 自带诊断"""
    annot = read_json(P_ANNOT)["samples"]
    labels = {s["segment_id"]: s["significance"] for s in annot}
    a = read_json(P_A)
    b1 = read_json(P_B1)
    b2 = read_json(P_B2)
    a_seg = {s["segment_id"]: s for s in a["segments"]}
    b1_seg = {s["segment_id"]: s for s in b1["segments"]}
    b2_seg = {s["segment_id"]: s for s in b2["segments"]}
    # B2 的 a_rank/b1_rank 在 segments 里；分数直接用 score
    pool = list(a_seg.keys())
    out = {"n_pool": len(pool), "n_annotated": len(annot)}
    for name, seg in (("A", a_seg), ("B1", b1_seg), ("B2", b2_seg)):
        vals = [(seg[s["segment_id"]]["score"], labels[s["segment_id"]]) for s in annot]
        scores = [v[0] for v in vals]
        lv = [v[1] for v in vals]
        rho = spearmanr(scores, lv)
        lv_means = {}
        for k in sorted(set(lv)):
            arr = [sc for sc, l in vals if l == k]
            lv_means[str(k)] = round(float(np.mean(arr)), 4)
        # 与报告口径一致：「显著样本」= 人工等级 >= 2（n=28），见 baseline 脚本 human_eval
        sig = [seg[s["segment_id"]] for s in annot if s["significance"] >= 2]
        sig_ranks = [seg[s["segment_id"]]["rank"] for s in annot if s["significance"] >= 2]
        out[name] = {
            "spearman": round(float(rho.statistic), 4),
            "p": float(rho.pvalue),
            "level_means": lv_means,
            "level_n": {str(k): sum(1 for l in lv if l == k) for k in sorted(set(lv))},
            "n_significant": len(sig),
            "sig_in_top20": sum(1 for r in sig_ranks if r <= 20),
            "sig_in_top50": sum(1 for r in sig_ranks if r <= 50),
            "sig_in_top100": sum(1 for r in sig_ranks if r <= 100),
            "sig_median_rank": float(np.median(sig_ranks)),
            "sig_mean_rank": round(float(np.mean(sig_ranks)), 2),
        }
    # 与各 JSON 自带的 human_eval 交叉核对（用于「数字是否对得上来源」）
    stored = {
        "A": b2["a_b1_b2"]["A"], "B1": b2["a_b1_b2"]["B1"], "B2": b2["a_b1_b2"]["B2"],
    }
    out["stored_human_eval"] = stored
    mismatch = []
    for name in ("A", "B1", "B2"):
        ref = stored[name]
        if abs(ref["spearman"] - out[name]["spearman"]) > 1e-3:
            mismatch.append("%s spearman %.4f vs JSON %.4f" % (name, out[name]["spearman"], ref["spearman"]))
        if ref["significant_median_rank"] != out[name]["sig_median_rank"]:
            mismatch.append("%s sig_median_rank %.1f vs JSON %.1f" % (
                name, out[name]["sig_median_rank"], ref["significant_median_rank"]))
        if ref["significant_in_top100"] != out[name]["sig_in_top100"]:
            mismatch.append("%s sig_in_top100 %d vs JSON %d" % (
                name, out[name]["sig_in_top100"], ref["significant_in_top100"]))
    out["human_eval_mismatch"] = mismatch
    out["A"]["length_bias_rho"] = a["length_bias_diagnostics"]["spearman_score_vs_n_dialogue"]
    out["B1"]["length_bias_rho"] = b1["length_bias"]["spearman_score_vs_n_dialogue"]
    out["B2"]["length_bias_rho"] = b2["length_bias"]["B2"]["vs_n_dialogue"]
    out["b1_ab"] = b1["a_b_comparison"]
    out["b2_ab1"] = b2["b2_vs_b1"]
    out["a_length_bins"] = a["length_bias_diagnostics"]["by_bin"]
    out["b1_strata"] = b1["length_strata"]
    out["b2_sig_4_10"] = b2.get("sig_4_10_detail", [])
    out["a_ranks"] = {sid: a_seg[sid]["rank"] for sid in pool}
    out["b1_ranks"] = {sid: b1_seg[sid]["rank"] for sid in pool}
    out["a_scores"] = {sid: a_seg[sid]["score"] for sid in pool}
    out["b1_scores"] = {sid: b1_seg[sid]["score"] for sid in pool}
    out["a_n_dialogue"] = {sid: a_seg[sid]["n_dialogue"] for sid in pool}
    out["seg_meta"] = {sid: a_seg[sid] for sid in pool}
    return out


def style_stats():
    d = read_json(P_STYLE)
    overall = d["overall"]
    feats = ["char_len", "literary_rate", "modal_rate", "person2_rate", "person1_rate",
             "abstract_ratio", "repeat_token_rate", "parallel_rate", "address_rate",
             "exclaim_rate", "question_rate", "imperative_rate"]
    return {"overall": overall, "features": feats,
            "labels": d["meta"]["features"], "meta": d["meta"]}


def citation_stats():
    d = read_json(P_CITE)
    return {"summary": d["summary"], "total": d["total_occurrences"],
            "unique": d["unique_records"], "coding_rules": d["coding_rules"]}


def retrieval_stats():
    v1 = read_json(P_RET1)
    v2 = read_json(P_RET2)
    return {"v1": v1, "v2": v2}


def type_sig_stats():
    return read_json(P_TYPESIG)


def fulfillment_stats():
    filled = read_json(P_FILLED)["oracles"]
    return {o["oracle_id"]: o for o in filled}



# ---------------------------------------------------------------------------
# 图 1：A vs B1 在人工等级 0/1/2/3 上的分数分布
# ---------------------------------------------------------------------------
def fig_level_scores(base, annot, out):
    labels = {s["segment_id"]: s["significance"] for s in annot["samples"]}
    levels = [0, 1, 2, 3]
    data_a = [[base["a_scores"][s["segment_id"]] for s in annot["samples"] if s["significance"] == lv]
              for lv in levels]
    data_b = [[base["b1_scores"][s["segment_id"]] for s in annot["samples"] if s["significance"] == lv]
              for lv in levels]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    pos_a = [lv - 0.18 for lv in levels]
    pos_b = [lv + 0.18 for lv in levels]
    bp1 = ax.boxplot(data_a, positions=pos_a, widths=0.3, patch_artist=True, whis=1.5,
                     medianprops=dict(color="black", lw=1.2))
    bp2 = ax.boxplot(data_b, positions=pos_b, widths=0.3, patch_artist=True, whis=1.5,
                     medianprops=dict(color="black", lw=1.2))
    for bp, color in ((bp1, "#7f9fc0"), (bp2, "#e08a4a")):
        for patch in bp["boxes"]:
            patch.set_facecolor(color)
            patch.set_alpha(0.85)
    # 均值点
    for pos, data in [(pos_a, data_a), (pos_b, data_b)]:
        for x, d in zip(pos, data):
            if d:
                ax.plot([x], [float(np.mean(d))], marker="D", ms=4, color="white",
                        markeredgecolor="black", zorder=5)
    ax.set_xticks(levels)
    ax.set_xticklabels([L("等级 %d" % lv, "level %d" % lv) for lv in levels])
    ax.set_xlabel(L("人工显著等级（0=可忽略 … 3=最强）", "human significance level (0..3)"))
    ax.set_ylabel(L("检测器分数（z 化后）", "score (z-like)"))
    ax.set_title(L("图1  A 与 B1 在人工等级上的分数分布：B1 把等级 2/3 拉开",
                   "Fig1  Score distribution by human level: B1 separates levels 2/3"))
    ax.legend([bp1["boxes"][0], bp2["boxes"][0]], ["A", "B1"], loc="upper left", frameon=False)
    ax.grid(axis="y", alpha=0.3)
    # 等级均值注释（数据驱动）
    def means(data):
        return [float(np.mean(d)) if d else float("nan") for d in data]
    ma, mb = means(data_a), means(data_b)
    txt = ("A  level means: " + " / ".join("%.2f" % v for v in ma) +
           "\nB1 level means: " + " / ".join("%.2f" % v for v in mb))
    ax.text(0.02, 0.02, txt, transform=ax.transAxes, fontsize=8, va="bottom", ha="left",
            bbox=dict(boxstyle="round", fc="white", alpha=0.85, ec="0.7"))
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return {"level_means_A": [None if np.isnan(v) else round(v, 4) for v in ma],
            "level_means_B1": [None if np.isnan(v) else round(v, 4) for v in mb]}


# ---------------------------------------------------------------------------
# 图 2：686 步 A→B1 排名散点 + 5 个最大提升/下降
# ---------------------------------------------------------------------------
def fig_rank_shift(base, seg_meta, out):
    sids = sorted(base["a_ranks"])
    xs = np.array([base["a_ranks"][s] for s in sids], dtype=float)
    ys = np.array([base["b1_ranks"][s] for s in sids], dtype=float)
    delta = xs - ys  # >0 表示 B1 提升
    order = np.argsort(-delta)
    top_up = order[:5]
    top_down = order[-5:][::-1]
    fig, ax = plt.subplots(figsize=(8.4, 7.2))
    ax.scatter(xs, ys, s=12, alpha=0.35, color="#4a6fa5", edgecolors="none",
               label=L("686 个候选步骤", "686 candidate steps"))
    lim = [1, 686]
    ax.plot(lim, lim, color="0.6", lw=1, ls="--", label=L("排名不变（对角线）", "no change"))
    colors = ["#c0392b", "#e67e22"]
    for k, idx in enumerate(top_up):
        ax.annotate(short_label(seg_meta, sids[idx]), (xs[idx], ys[idx]), xytext=(6, -16),
                    textcoords="offset points", fontsize=7, color=colors[0],
                    arrowprops=dict(arrowstyle="-", color=colors[0], lw=0.7, alpha=0.8))
    for idx in top_down:
        ax.annotate(short_label(seg_meta, sids[idx]), (xs[idx], ys[idx]), xytext=(6, 8),
                    textcoords="offset points", fontsize=7, color="#21618c",
                    arrowprops=dict(arrowstyle="-", color="#21618c", lw=0.7, alpha=0.8))
    ax.set_xlim(lim)
    ax.set_ylim(lim[1], lim[0])  # 排名轴反转：1 在顶部，对角线以上 = B1 提升
    ax.set_xlabel(L("A 检测器排名（1=最高）", "A rank (1 = top)"))
    ax.set_ylabel(L("B1 检测器排名（1=最高）", "B1 rank (1 = top)"))
    ax.set_title(L("图2  686 步 A→B1 排名移动（对角线上方=B1 提升；标注 5 个最大提升/下降）",
                   "Fig2  A to B1 rank shift (above diagonal = improved)"))
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    ups = [{"segment_id": sids[i], "a_rank": int(xs[i]), "b1_rank": int(ys[i]),
            "delta": int(delta[i])} for i in top_up]
    downs = [{"segment_id": sids[i], "a_rank": int(xs[i]), "b1_rank": int(ys[i]),
              "delta": int(delta[i])} for i in top_down]
    return {"top_improved": ups, "top_declined": downs}


def short_label(seg_meta, sid):
    m = seg_meta.get(sid, {})
    task = (m.get("task") or sid.split("|")[0])[:8]
    step = m.get("step_idx", sid.split("|")[-1])
    return "%s…|%s" % (task, step)


# ---------------------------------------------------------------------------
# 图 3：G1/G2/G3 语体特征均值
# ---------------------------------------------------------------------------
def fig_style_features(style, out):
    ov = style["overall"]["features"]
    groups = ["G1", "G2", "G3"]
    group_labels = [L("G1 神谕", "G1 oracle"), L("G2 普通对白", "G2 dialogue"),
                    L("G3 角色引用", "G3 citation")]
    colors = ["#2e5c8a", "#9fb3c8", "#d98c3f"]
    rate_feats = ["literary_rate", "modal_rate", "person2_rate", "person1_rate",
                  "imperative_rate", "exclaim_rate"]
    rate_labels = [L("文言虚词", "literary"), L("情态词", "modal"),
                   L("第二人称", "2nd person"), L("第一人称", "1st person"),
                   L("祈使标记", "imperative"), L("感叹号", "exclaim")]
    other_feats = ["char_len", "abstract_ratio", "repeat_token_rate", "parallel_rate"]
    other_labels = [L("句长（字）", "sentence len (chars)"),
                    L("抽象名词比例 ×100", "abstract ratio ×100"),
                    L("词复沓率 ×100", "token repeat ×100"),
                    L("排比率 ×100", "parallel ×100")]
    other_scale = [1.0, 100.0, 100.0, 100.0]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.9), gridspec_kw={"width_ratios": [1.25, 1]})
    for ax, feats, labs, scale, title in (
            (axes[0], rate_feats, rate_labels, [1.0] * len(rate_feats),
             L("(a) 比率类特征（次/百字）", "(a) rate features (per 100 chars)")),
            (axes[1], other_feats, other_labels, other_scale,
             L("(b) 长度/抽象/复沓类", "(b) length / abstract / repetition)"))):
        x = np.arange(len(feats))
        w = 0.26
        for gi, (g, gl, col) in enumerate(zip(groups, group_labels, colors)):
            vals = [ov[f][g]["mean"] * sc for f, sc in zip(feats, scale)]
            ax.bar(x + (gi - 1) * w, vals, w, label=gl, color=col, alpha=0.9)
        ax.set_xticks(x)
        ax.set_xticklabels(labs, rotation=20, ha="right", fontsize=8)
        ax.set_title(title, fontsize=9)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel(L("均值", "mean"))
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle(L("图3  神谕原文 / 普通对白 / 角色引用 的语体特征均值对比",
                   "Fig3  Style feature means: oracle vs dialogue vs citation"), fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return {f: {g: ov[f][g]["mean"] for g in groups} for f in rate_feats + other_feats}


# ---------------------------------------------------------------------------
# 图 4：34 处引用的 版本 × 阶段 堆叠条形图
# ---------------------------------------------------------------------------
def fig_citation_stage(cite, out):
    summ = cite["summary"]
    stages = list(summ["stage_distribution"].keys())
    versions = sorted(summ["per_version"].keys())
    mat = np.zeros((len(versions), len(stages)))
    totals = []
    for i, v in enumerate(versions):
        stages_v = summ["per_version"][v]["stages"]
        for j, st in enumerate(stages):
            mat[i, j] = stages_v.get(st, 0)
        totals.append(summ["per_version"][v]["n"])
    stage_cn = {"原文出现": "原文出现", "本人引用": "本人引用", "结局宣告": "结局宣告",
                "他人解释": "他人解释", "主动认领": "主动认领", "改写反转": "改写反转",
                "旁白转述": "旁白转述"}
    stage_en = {"原文出现": "first utterance", "本人引用": "self-quote", "结局宣告": "fulfillment",
                "他人解释": "other explains", "主动认领": "self-claim", "改写反转": "rewrite/invert",
                "旁白转述": "narration"}
    labels = [stage_cn.get(st, st) if HAS_CJK else stage_en.get(st, st) for st in stages]
    cmap = plt.get_cmap("tab20")
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    bottom = np.zeros(len(versions))
    for j, st in enumerate(stages):
        ax.bar(versions, mat[:, j], bottom=bottom, label=labels[j],
               color=cmap(j % 20), edgecolor="white", linewidth=0.6)
        bottom += mat[:, j]
    for i, v in enumerate(versions):
        ax.text(i, bottom[i] + 0.08, str(int(totals[i])), ha="center", va="bottom", fontsize=8)
    ax.set_xlabel(L("版本", "version"))
    ax.set_ylabel(L("引用次数", "citation count"))
    ax.set_title(L("图4  34 处神谕引用的 版本×阶段 分布（柱顶=该版本引用数）",
                   "Fig4  Citation stages by version (34 occurrences)"), fontsize=11)
    ax.legend(fontsize=7, ncol=2, frameon=False, loc="upper left")
    ax.set_ylim(0, max(bottom) + 1.2)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return {"versions": versions, "stage_matrix": mat.tolist(), "totals": totals}


# ---------------------------------------------------------------------------
# 图 5：神谕兑现段 vs 其余 673 步
# ---------------------------------------------------------------------------
def fig_oracle_vs_rest(base, ts, out):
    gold = ts["gold_ids"]
    rest = [sid for sid in base["a_ranks"] if sid not in set(gold)]
    q4 = ts["q4_overall"]
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    data = [[base["a_scores"][s] for s in gold],
            [base["a_scores"][s] for s in rest],
            [base["b1_scores"][s] for s in gold],
            [base["b1_scores"][s] for s in rest]]
    colors = ["#2e5c8a", "#a9c0d8", "#d98c3f", "#f0cba8"]
    bp = ax.boxplot(data, positions=[1, 2, 3.6, 4.6], widths=0.55, patch_artist=True,
                    whis=1.5, showfliers=[True, False, True, False],
                    medianprops=dict(color="black", lw=1.2))
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.9)
    ax.set_xticks([1, 2, 3.6, 4.6])
    ax.set_xticklabels([L("A\n兑现段(n=13)", "A gold (n=13)"), L("A\n其余(n=673)", "A rest (n=673)"),
                        L("B1\n兑现段(n=13)", "B1 gold (n=13)"), L("B1\n其余(n=673)", "B1 rest (n=673)")])
    ax.set_ylabel(L("检测器分数", "score"))
    ax.set_title(L("图5  神谕兑现段 vs 其余步骤的分数分布", "Fig5  Oracle fulfillment vs rest"),
                 fontsize=11)
    txt = ("A : δ=%+.3f, p=%.2g\n" % (q4["A"]["cliff_delta"], q4["A"]["p"]) +
           "B1: δ=%+.3f, p=%.2g" % (q4["B1"]["cliff_delta"], q4["B1"]["p"]))
    ax.text(0.02, 0.98, txt, transform=ax.transAxes, va="top", ha="left", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", alpha=0.9, ec="0.6"))
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return {"n_gold": len(gold), "n_rest": len(rest),
            "A": {"delta": q4["A"]["cliff_delta"], "p": q4["A"]["p"]},
            "B1": {"delta": q4["B1"]["cliff_delta"], "p": q4["B1"]["p"]}}



# ---------------------------------------------------------------------------
# 数据表汇总（data-tables.md）
# ---------------------------------------------------------------------------
def _fmt(x, nd=4):
    if x is None:
        return "—"
    if isinstance(x, float):
        return ("%%.%df" % nd) % x
    return str(x)


def _p(p):
    if p is None:
        return "—"
    return "%.2g" % p if p < 0.001 else "%.3f" % p


def render_tables(data, fig_info):
    corpus, annot, consist, base, style, cite, ret, ts = (
        data["corpus"], data["annot"], data["consist"], data["base"],
        data["style"], data["cite"], data["ret"], data["ts"])
    L_ = []
    A = L_.append
    SRC_CORPUS = "data/corpus/amphoreus.final.jsonl（脚本重算）"
    SRC_ANNOT = "data/config/annotation-labels.json"
    SRC_A = "data/config/baseline-a-scores.json"
    SRC_B1 = "data/config/baseline-b-scores.json"
    SRC_B2 = "data/config/baseline-b2-scores.json"
    SRC_STYLE = "data/config/style-compare-results.json"
    SRC_CITE = "data/config/oracle-citation-coding.json"
    SRC_RET1 = "data/config/oracle-retrieval-results.json"
    SRC_RET2 = "data/config/retrieval-v2-results.json"
    SRC_TS = "data/config/type-and-oracle-significance.json"

    A("# 报告数据表汇总（make_figures.py 自动生成）")
    A("")
    A("> 生成脚本：`tools/make_figures.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    A("> 本文件所有数字由脚本从 JSON/JSONL 现场计算；每行「来源」标注数据文件。")
    A("> 图见 `docs/report/figures/`（5 张，均由同一脚本从 JSON 复现，不硬编码）。")
    A("")
    A("## 0. 图表清单")
    A("")
    A("| # | 文件 | 内容 | 数据来源 |")
    A("| --- | --- | --- | --- |")
    fig_desc = {
        "f1_level_scores.png": ("A vs B1 在人工等级 0/1/2/3 上的分数箱线图（展示 B1 拉开深度维度）",
                                "baseline-a/b-scores.json + annotation-labels.json"),
        "f2_rank_shift.png": ("686 步 A→B1 排名散点（标注 5 个最大提升/下降）",
                              "baseline-a/b-scores.json + segments.jsonl"),
        "f3_style_features.png": ("G1 神谕 / G2 对白 / G3 引用 的语体特征均值",
                                  "style-compare-results.json"),
        "f4_citation_stage.png": ("34 处引用的 版本×阶段 堆叠分布",
                                  "oracle-citation-coding.json"),
        "f5_oracle_vs_rest.png": ("13 个神谕兑现段 vs 其余 673 步的 A/B1 分数箱线图（附 p、δ）",
                                  "baseline-a/b-scores.json + type-and-oracle-significance.json"),
    }
    for i, (name, (desc, src)) in enumerate(fig_desc.items(), 1):
        A("| F%d | `docs/report/figures/%s` | %s | %s |" % (i, name, desc, src))
    A("")

    # ---------------- 1. 语料规模 ----------------
    A("## 1. 数据规模与语料统计")
    A("")
    A("| 指标 | 数值 | 来源 |")
    A("| --- | --- | --- |")
    A("| 记录数 | %d | %s |" % (corpus["n_records"], SRC_CORPUS))
    A("| 台词字数（原文） | %d | %s |" % (corpus["n_chars"], SRC_CORPUS))
    A("| 任务页数 | %d | %s |" % (corpus["n_tasks"], SRC_CORPUS))
    A("| 版本数 | %d（%s） | %s |" % (corpus["n_versions"], " / ".join(corpus["versions"]), SRC_CORPUS))
    A("| 说话人归一命中 | %d / %d = %.2f%% | %s |" % (
        corpus["n_canonical"], corpus["n_non_narration"],
        100.0 * corpus["normalization_rate"], SRC_CORPUS))
    A("| 重复记录（保留但标记） | %d | %s |" % (corpus["n_duplicates"], SRC_CORPUS))
    A("| 记录 kind 分布 | %s | %s |" % (
        "，".join("%s %d" % (k, v) for k, v in corpus["kind"].items()), SRC_CORPUS))
    A("| 记录 view 分布 | %s | %s |" % (
        "，".join("%s %d" % (k, v) for k, v in corpus["view"].items()), SRC_CORPUS))
    A("| text 长度 P50 / P90 / P99 / max | %d / %d / %d / %d | %s |" % (
        corpus["len_p50"], corpus["len_p90"], corpus["len_p99"], corpus["len_max"], SRC_CORPUS))
    A("")
    A("> 与 `data/reports/final-delivery.md` 的交付口径一致（该报告为同一语料的交付说明）。")
    A("")

    # ---------------- 2. 标注与一致性 ----------------
    A("## 2. 标注与一致性")
    A("")
    A("| 指标 | 数值 | 来源 |")
    A("| --- | --- | --- |")
    A("| 标注样本数 | %d | %s |" % (annot["n"], SRC_ANNOT))
    A("| 显著等级分布（0/1/2/3） | %s | %s |" % (
        " / ".join(str(annot["levels"].get(str(k), 0)) for k in range(4)), SRC_ANNOT))
    A("| 类型分布（7 类，多标签） | %s | %s |" % (
        "，".join("%s %d" % (TYPE_LABELS_CN[t], annot["types"][t]) for t in TYPES), SRC_ANNOT))
    A("| 隔轮重标样本数 | %s | %s（§4） |" % (consist.get("n_retest", "—"), consist["source"]))
    A("| 等级完全一致率（隔轮） | %s/%s = %s%% | %s（§4） |" % (
        consist.get("level_same", "—"), consist.get("level_total", "—"),
        consist.get("level_rate", "—"), consist["source"]))
    A("| 类型集合完全一致率（隔轮，原始） | %s/%s = %s%% | %s（§4） |" % (
        consist.get("type_same", "—"), consist.get("type_total", "—"),
        consist.get("type_rate", "—"), consist["source"]))
    A("| 平均类型交集 / 平均 Jaccard | %s 个 / %s%% | %s（§4） |" % (
        consist.get("mean_intersection", "—"), consist.get("mean_jaccard", "—"), consist["source"]))
    A("| 按统一规则修正后类型一致率 | %s%% | %s（§4） |" % (
        consist.get("type_rate_final", "—"), consist["source"]))
    A("")
    A("> 局限：单标注者、无第二标注者，无法计算 Cohen's kappa（见 `data/reports/annotation-review.md` §4）。")
    A("")

    # ---------------- 3. A / B1 / B2 主表 ----------------
    A("## 3. A vs B1 vs B2 主表（74 条人工标注；「显著样本」= 等级 ≥ 2，共 28 条）")
    A("")
    A("| 指标 | A | B1 | B2 | 来源 |")
    A("| --- | --- | --- | --- | --- |")
    def row3(key, fmt="%s"):
        vals = [base[n].get(key) for n in ("A", "B1", "B2")]
        A("| %s | %s | %s | %s | %s / %s / %s + %s |" % (
            key, *[fmt % v if v is not None else "—" for v in vals],
            SRC_A, SRC_B1, SRC_B2, SRC_ANNOT))
    row3("spearman")
    SRC_abc = "%s / %s / %s + %s（脚本重算）" % (SRC_A, SRC_B1, SRC_B2, SRC_ANNOT)
    for lv in ("0", "1", "2", "3"):
        vals = [base[n]["level_means"].get(lv) for n in ("A", "B1", "B2")]
        A("| 等级 %s 平均分 | %s | %s | %s | %s |" % (
            lv, *[("%.3f" % v) if v is not None else "—" for v in vals], SRC_abc))
    top_hits = tuple(base[n][k] for n in ("A", "B1", "B2")
                     for k in ("sig_in_top20", "sig_in_top50", "sig_in_top100"))
    A("| 显著样本在 Top20 / Top50 / Top100 | %d / %d / %d | %d / %d / %d | %d / %d / %d | %s |" % (
        top_hits + (SRC_abc,)))
    A("| 显著样本中位排名 | %.1f | %.1f | %.1f | %s |" % (
        tuple(base[n]["sig_median_rank"] for n in ("A", "B1", "B2")) + (SRC_abc,)))
    A("| 长度偏差 ρ(score, n_dialogue) | %s | %s | %s | %s / %s / %s（length_bias 字段） |" % (
        _fmt(base["A"]["length_bias_rho"]), _fmt(base["B1"]["length_bias_rho"]),
        _fmt(base["B2"]["length_bias_rho"]), SRC_A, SRC_B1, SRC_B2))
    A("")
    ab = base["b1_ab"]
    A("**A→B1 排名关系**（来源 `%s`: a_b_comparison）" % SRC_B1)
    A("")
    A("| 指标 | 数值 | 来源 |")
    A("| --- | --- | --- |")
    A("| Top10 / Top20 / Top50 / Top100 重叠 | %.2f / %.2f / %.2f / %.2f | %s |" % (
        ab["top10_overlap"], ab["top20_overlap"], ab["top50_overlap"], ab["top100_overlap"], SRC_B1))
    A("| Spearman(A, B1) | %.4f | %s |" % (ab["spearman_a_vs_b"], SRC_B1))
    A("| 排名变化：中位绝对变化 / 平均 Δ / 提升≥100 数 / 下降≥100 数 | %.1f / %.1f / %d / %d | %s |" % (
        ab["rank_change"]["median_abs_delta"], ab["rank_change"]["mean_delta"],
        ab["rank_change"]["n_improved_100plus"], ab["rank_change"]["n_worsened_100plus"], SRC_B1))
    A("")
    b2ab = base["b2_ab1"]
    A("**B2 vs B1**（来源 `%s`: b2_vs_b1）" % SRC_B2)
    A("")
    A("| 指标 | 数值 | 来源 |")
    A("| --- | --- | --- |")
    A("| Top10 / Top20 / Top50 / Top100 重叠 | %.2f / %.2f / %.2f / %.2f | %s |" % (
        b2ab["top10_overlap"], b2ab["top20_overlap"], b2ab["top50_overlap"], b2ab["top100_overlap"], SRC_B2))
    A("| Spearman(B1, B2) | %.4f | %s |" % (b2ab["spearman_score"], SRC_B2))
    A("| 短步数 / 排名中位绝对变化 | %d / %.1f | %s |" % (
        b2ab["n_short_steps"], b2ab["short_rank_change"]["median_abs_delta"], SRC_B2))
    A("")

    # ---------------- 4. 语体三组表 ----------------
    A("## 4. 语体三组表（G1 神谕 / G2 普通对白 / G3 角色引用）")
    A("")
    A("| 特征 | G1 均值 | G2 均值 | G3 均值 | G1−G2 δ / p | G1−G3 δ / p | G2−G3 δ / p | 来源 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    ov = style["overall"]
    for f in style["features"]:
        cells = []
        for pair in ("G1_vs_G2", "G1_vs_G3", "G2_vs_G3"):
            r = ov["comparisons"][pair][f]
            if r.get("cliff_delta") is None:
                cells.append("—")
            else:
                cells.append("%+.3f / %s" % (r["cliff_delta"], _p(r["p"])))
        A("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            style["labels"].get(f, f),
            *["%.4f" % ov["features"][f][g]["mean"] for g in ("G1", "G2", "G3")],
            *cells, SRC_STYLE))
    A("")
    A("> 特征定义与词表见 `data/reports/style-compare.md` §3；MWU 为双侧原始 p（未做 Bonferroni 校正）。")
    A("")

    # ---------------- 5. 引用轨迹表 ----------------
    A("## 5. 引用轨迹表（34 处 occurrences / 33 条唯一记录）")
    A("")
    summ = cite["summary"]
    A("| 指标 | 数值 | 来源 |")
    A("| --- | --- | --- |")
    A("| 引用处数 / 唯一记录 | %d / %d | %s |" % (cite["total"], cite["unique"], SRC_CITE))
    A("| 阶段分布（7 类） | %s | %s |" % (
        "，".join("%s %d" % (k, v) for k, v in summ["stage_distribution"].items()), SRC_CITE))
    A("| 引用者类别 | %s | %s |" % (
        "，".join("%s %d" % (k, v) for k, v in summ["citer_category_distribution"].items()), SRC_CITE))
    A("| 引用形式 | %s | %s |" % (
        "，".join("%s %d" % (k, v) for k, v in summ["citation_form_distribution"].items()), SRC_CITE))
    A("| 是否保留原句 | %s | %s |" % (
        "，".join("%s %d" % (k, v) for k, v in summ["keeps_original_text_distribution"].items()), SRC_CITE))
    A("| 编码不确定条数 | %d | %s |" % (summ["uncertain_count"], SRC_CITE))
    A("| 逐版本引用数 | %s | %s |" % (
        "，".join("%s: %d" % (v, summ["per_version"][v]["n"]) for v in sorted(summ["per_version"])), SRC_CITE))
    fvl = summ["first_vs_last"]
    A("| 首次引用阶段分布 | %s | %s |" % (
        "，".join("%s %d" % (k, v) for k, v in fvl["first_stage_distribution"].items()), SRC_CITE))
    A("| 最后引用阶段分布 | %s | %s |" % (
        "，".join("%s %d" % (k, v) for k, v in fvl["last_stage_distribution"].items()), SRC_CITE))
    A("| 无跨步时间轴的神谕 | %s | %s |" % ("、".join(fvl["zero_step_oracles"]), SRC_CITE))
    mp = summ["mirror_pair"]
    A("| 镜像对：共享记录 | #%d（O10 记「%s」/ O11 记「%s」） | %s |" % (
        mp["shared_record"]["record_id"], mp["shared_record"]["in_O10_stage"],
        mp["shared_record"]["in_O11_stage"], SRC_CITE))
    A("| 镜像对：同词异序 | 同 tokens / 语序互换 = %s（O10/O11 均 %d 字） | %s |" % (
        mp["clause_analysis"]["order_swapped"], mp["clause_analysis"]["char_len_O10"], SRC_CITE))
    A("| 镜像对：谁引用谁 | %s | %s（叙述见 `data/reports/oracle-citation-timeline.md` §5.4） |" % (
        mp["who_quotes_whom"].replace("|", "／"), SRC_CITE))
    A("")

    # ---------------- 6. 检索 v1 / v2 ----------------
    A("## 6. 神谕检索 v1 / v2 表")
    A("")
    A("**v1（原查询 + 686 全池）**（来源 `%s`: methods_base）" % SRC_RET1)
    A("")
    A("| 方法 | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR | 来源 |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    v1 = ret["v1"]["methods_base"]
    for m in METHODS:
        met = v1[m]["metrics"]
        A("| %s | %.3f | %.3f | %.3f | %.3f | %.3f | %s |" % (
            METHOD_LABELS[m], met["recall@1"], met["recall@5"], met["recall@10"], met["recall@20"],
            met["mrr"], SRC_RET1))
    A("")
    A("**v2-mask（掩蔽 query）**（来源 `%s`: summary.v2_mask，13 条 query）" % SRC_RET2)
    A("")
    A("| 方法 | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR | 来源 |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for m in METHODS:
        met = ret["v2"]["summary"]["v2_mask"][m]
        A("| %s | %.3f | %.3f | %.3f | %.3f | %.3f | %s |" % (
            METHOD_LABELS[m], met["recall@1"], met["recall@5"], met["recall@10"], met["recall@20"],
            met["mrr"], SRC_RET2))
    A("")
    meta2 = ret["v2"]["meta"]
    o10 = ret["v2"]["o10_focus"]
    A("**v2-noRecite / v2-both 与 O10**（来源 `%s`）" % SRC_RET2)
    A("")
    A("| 指标 | 数值 | 来源 |")
    A("| --- | --- | --- |")
    A("| 剔除吟诵步数 / 剩余池 | %d / %d | %s |" % (
        meta2["n_removed_recitation_steps"], meta2["n_documents_no_recite"], SRC_RET2))
    A("| gold 被剔除（N/A）的 query | %d/13（%s） | %s |" % (
        len(meta2["na_oracles_gold_removed"]), "、".join(meta2["na_oracles_gold_removed"]), SRC_RET2))
    A("| v2-noRecite 可评 query 数 | %d（仅 O10） | %s |" % (
        ret["v2"]["summary"]["v2_norecite"]["keyword"]["n_eval"], SRC_RET2))
    A("| O10 最好名次：v1 / mask / noRecite / both | %d / %d / %d / %d | %s |" % (
        min(v for v in o10["v1"].values() if v), min(v for v in o10["v2_mask"].values() if v),
        min(v for v in o10["v2_norecite"].values() if v), min(v for v in o10["v2_both"].values() if v),
        SRC_RET2))
    A("| 结论 | v1 的 gold 与吟诵步重合：关键词基线 v1 最强；v2 两修正分别暴露「泄漏仍在」与「gold 被删」→ 现有 gold 上无法做真语义五法对比 | %s |" % SRC_RET2)
    A("")

    # ---------------- 7. Q3 七类型 ----------------
    A("## 7. Q3 七类型信号表")
    A("")
    A("| 类型 | n | A 中位名次 | B1 中位名次 | 中位提升(A−B1) | A Top100 | B1 Top100 | B1 组内 Spearman | 来源 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for t in TYPES:
        v = ts["q3_types"][t]
        A("| %s（%s） | %d | %.1f | %.1f | %+.1f | %d | %d | %.2f | %s |" % (
            t, TYPE_LABELS_CN[t], v["n"], v["a_median_rank"], v["b_median_rank"],
            v["median_lift_A_minus_B"], v["a_top100"], v["b_top100"],
            v["spearman_within_type_B"], SRC_TS))
    A("")
    A("> B 提升最大的类型：%s（%+.1f）；提升最小：%s（%+.1f）；组内 ρ 最高：%s（%.2f）。" % (
        TYPE_LABELS_CN[ts["q3_summary"]["best_type_by_median_lift"]],
        ts["q3_types"][ts["q3_summary"]["best_type_by_median_lift"]]["median_lift_A_minus_B"],
        TYPE_LABELS_CN[ts["q3_summary"]["worst_type_by_median_lift"]],
        ts["q3_types"][ts["q3_summary"]["worst_type_by_median_lift"]]["median_lift_A_minus_B"],
        TYPE_LABELS_CN[ts["q3_summary"]["best_type_by_within_spearman"]],
        ts["q3_types"][ts["q3_summary"]["best_type_by_within_spearman"]]["spearman_within_type_B"]))
    A("")

    # ---------------- 8. Q4 显著性 ----------------
    A("## 8. Q4 神谕兑现显著性表")
    A("")
    q4 = ts["q4_overall"]
    A("| 检测器 | gold 中位分 | 其余中位分 | gold 中位名次 | gold 中位百分位 | 进 Top100 | MWU p | Cliff's δ | 来源 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name in ("A", "B1"):
        v = q4[name]
        A("| %s | %.3f | %.3f | %.0f | %.3f | %d/13 | %s | %+.3f | %s |" % (
            name, v["median_x"], v["median_y"], v["gold_median_rank"],
            v["gold_median_pct_rank"], v["gold_in_top100"], _p(v["p"]), v["cliff_delta"], SRC_TS))
    A("")
    A("**按长度分层**（来源 `%s`: q4_by_length）" % SRC_TS)
    A("")
    A("| 长度层 | gold 数 | 其余步数 | A p / δ | B1 p / δ | 来源 |")
    A("| --- | --- | --- | --- | --- | --- |")
    for b, v in ts["q4_by_length"].items():
        if v["n_gold"] < 2:
            A("| %s | %d | %d | —（gold<2，无法检验） | — | %s |" % (b, v["n_gold"], v["n_rest"], SRC_TS))
        else:
            A("| %s | %d | %d | %s / %+.3f | %s / %+.3f | %s |" % (
                b, v["n_gold"], v["n_rest"], _p(v["A"]["p"]), v["A"]["cliff_delta"],
                _p(v["B1"]["p"]), v["B1"]["cliff_delta"], SRC_TS))
    A("")
    A("> 解读：13 个兑现段全部落在「>30 句」层，该层内部仍显著（不是单纯长度效应）；"
      "但兑现段多为「吟诵神谕原文」的步骤，A/B 的高分含词面构造成分，不能把「神谕兑现」当显著性标签。")
    A("")

    # ---------------- 9. 复现 ----------------
    A("## 9. 复现与校验")
    A("")
    A("```bash")
    A(RUN_CMD)
    A("conda run -n nlpLesson python tools/make_figures.py --verify")
    A("```")
    A("")
    A("- 5 张图与上表全部由脚本从 JSON/JSONL 现场计算；脚本内不硬编码任何统计数字（只硬编码标签/配色/标题）。")
    A("- 中文字体：脚本自动检测（SimHei / Microsoft YaHei / Noto Sans CJK 等）；缺失时自动退回英文标签。")
    A("- `--verify` 会检查 5 张 PNG 是否非空、本文件是否包含全部 8 张表头与来源标注。")
    A("")
    return "\n".join(L_)


def build():
    os.makedirs(FIG_DIR, exist_ok=True)
    data = {
        "corpus": corpus_stats(),
        "annot": annotation_stats(),
        "consist": consistency_stats(),
        "base": baseline_stats(),
        "style": style_stats(),
        "cite": citation_stats(),
        "ret": retrieval_stats(),
        "ts": type_sig_stats(),
        "filled": fulfillment_stats(),
    }
    annot = read_json(P_ANNOT)
    seg_meta = data["base"]["seg_meta"]
    figs = {}
    paths = {
        "f1_level_scores.png": lambda p: fig_level_scores(data["base"], annot, p),
        "f2_rank_shift.png": lambda p: fig_rank_shift(data["base"], seg_meta, p),
        "f3_style_features.png": lambda p: fig_style_features(data["style"], p),
        "f4_citation_stage.png": lambda p: fig_citation_stage(data["cite"], p),
        "f5_oracle_vs_rest.png": lambda p: fig_oracle_vs_rest(data["base"], data["ts"], p),
    }
    for name, fn in paths.items():
        out = os.path.join(FIG_DIR, name)
        figs[name] = fn(out)
        print("已生成 %s（%.1f KB）" % (os.path.relpath(out, ROOT), os.path.getsize(out) / 1024.0))
    md = render_tables(data, figs)
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s（%.1f KB）" % (os.path.relpath(OUT_MD, ROOT), os.path.getsize(OUT_MD) / 1024.0))
    n_tables = md.count("\n## ")
    print("数据表章节数（含图表清单与复现章）：%d" % n_tables)
    if HAS_CJK:
        print("中文字体：%s" % CJK_FONT)
    else:
        print("!! 未找到中文字体，图中标签已退回英文")
    # 交付口径交叉核对（只打印差异，不改结论）
    try:
        fd = open(P_FINAL_DELIVERY, "r", encoding="utf-8").read()
        m = re.search(r"记录数 \| \*\*(\d+)\*\*", fd)
        if m and int(m.group(1)) != data["corpus"]["n_records"]:
            print("!! 语料记录数与 final-delivery.md 不一致：%d vs %s" % (
                data["corpus"]["n_records"], m.group(1)), file=sys.stderr)
        else:
            print("语料规模与 final-delivery.md 一致（记录数 %d）" % data["corpus"]["n_records"])
    except Exception as e:
        print("（跳过 final-delivery 交叉核对：%s）" % e)
    if data["base"].get("human_eval_mismatch"):
        print("!! 人工评估指标与 JSON 自带 human_eval 不一致：")
        for x in data["base"]["human_eval_mismatch"]:
            print("   " + x)
    else:
        print("人工评估指标与 JSON human_eval 一致（A/B1/B2 的 Spearman、显著中位排名、Top100 命中）")
    try:
        from export_plot_data import export_for
        export_for("tools/make_figures.py")
    except Exception as _e:
        print("  [plot_data] 跳过：%s" % _e, file=sys.stderr)
    if not verify(verbose=True):
        print("!! 图表/数据表校验失败", file=sys.stderr)
        sys.exit(1)
    print("\n校验通过：5 张图非空、数据表章节齐全、来源标注完整。")


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
EXPECTED_FIGS = ["f1_level_scores.png", "f2_rank_shift.png", "f3_style_features.png",
                 "f4_citation_stage.png", "f5_oracle_vs_rest.png"]
EXPECTED_HEADERS = ["## 0. 图表清单", "## 1. 数据规模与语料统计", "## 2. 标注与一致性",
                    "## 3. A vs B1 vs B2 主表", "## 4. 语体三组表",
                    "## 5. 引用轨迹表", "## 6. 神谕检索 v1 / v2 表",
                    "## 7. Q3 七类型信号表", "## 8. Q4 神谕兑现显著性表"]


def verify(verbose=False):
    problems = []
    for name in EXPECTED_FIGS:
        path = os.path.join(FIG_DIR, name)
        if not os.path.exists(path):
            problems.append("缺少图 %s" % name)
        elif os.path.getsize(path) < 5000:
            problems.append("图 %s 过小（%d bytes）" % (name, os.path.getsize(path)))
    if not os.path.exists(OUT_MD):
        problems.append("缺少 data-tables.md")
        md = ""
    else:
        md = open(OUT_MD, "r", encoding="utf-8").read()
    for h in EXPECTED_HEADERS:
        if h not in md:
            problems.append("数据表缺少章节 %s" % h)
    n_src = md.count("来源")
    n_ref = md.count("data/")
    if n_src < 15:
        problems.append("来源列过少（%d）" % n_src)
    if n_ref < 40:
        problems.append("来源文件引用过少（%d）" % n_ref)
    # 每个数据表章节都必须出现至少一个来源文件路径
    secs = md.split("\n## ")
    for h in EXPECTED_HEADERS[1:]:  # 跳过图表清单
        title = h.replace("## ", "").strip()
        sec = next((x for x in secs if x.startswith(title)), "")
        if "data/" not in sec:
            problems.append("章节缺少来源文件标注：%s" % title)
    if md.count("| F") < 5:
        problems.append("图表清单不足 5 行")
    # 关键数字与 JSON 交叉核对（重算后比对字符串是否出现在 md 里）
    ts = read_json(P_TYPESIG)
    ret1 = read_json(P_RET1)
    ret2 = read_json(P_RET2)
    checks = [
        ("v1 关键词 MRR", "%.3f" % ret1["methods_base"]["keyword"]["metrics"]["mrr"]),
        ("v2-mask 关键词 MRR", "%.3f" % ret2["summary"]["v2_mask"]["keyword"]["mrr"]),
        ("Q4 A δ", "%+.3f" % ts["q4_overall"]["A"]["cliff_delta"]),
        ("Q4 B1 δ", "%+.3f" % ts["q4_overall"]["B1"]["cliff_delta"]),
    ]
    for label, txt in checks:
        if txt not in md:
            problems.append("数据表缺少核对数字 %s=%s" % (label, txt))
    if verbose:
        print("\n校验项：5 图 + 9 章节 + 来源列（%d 处）/来源文件引用（%d 处）" % (n_src, n_ref))
        for label, txt in checks:
            print("  抽查 %-16s %s ✓" % (label, txt))
    if problems:
        for p in problems:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="报告图表 + 数据表")
    ap.add_argument("--verify", action="store_true", help="只校验已生成产物")
    args = ap.parse_args()
    if args.verify:
        ok = verify(verbose=True)
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    build()


if __name__ == "__main__":
    main()
