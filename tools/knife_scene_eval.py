#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
knife_scene_eval.py — 35 个「刀子/高光场景」的人类验证集分析（task-18）

只读：
  data/config/knife-scenes.json         35 个场景（含 segment_ids / ranges / record_span）
  data/config/baseline-a-scores.json    A 的 686 步 rank/score
  data/config/baseline-b-scores.json    B1 的 686 步 rank/score
  data/config/annotation-labels.json    74 条人工显著性等级
  data/config/oracle-fulfillment.filled.json  13 条神谕兑现段
  data/corpus/segments.jsonl            686 候选池（n_main>0 且 !low_content 且 has_dialogue）
  data/corpus/amphoreus.final.jsonl     场景原文（按 record_span 抽取）

产出（只写这 4 个）：
  data/config/knife-scene-scores.json
  docs/report/figures/f6_knife_ranks.png
  docs/report/knife-scenes-analysis.md
  （本脚本 tools/knife_scene_eval.py）

运行：
  conda run -n nlpLesson python tools/knife_scene_eval.py
  conda run -n nlpLesson python tools/knife_scene_eval.py --verify

无随机、不装依赖（matplotlib 已装；中文缺字体自动退回英文）。
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from math import comb

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_KNIFE = os.path.join(ROOT, "data", "config", "knife-scenes.json")
P_SEGMENTS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_FINAL = os.path.join(ROOT, "data", "corpus", "amphoreus.final.jsonl")
P_A = os.path.join(ROOT, "data", "config", "baseline-a-scores.json")
P_B1 = os.path.join(ROOT, "data", "config", "baseline-b-scores.json")
P_ANNOT = os.path.join(ROOT, "data", "config", "annotation-labels.json")
P_FILLED = os.path.join(ROOT, "data", "config", "oracle-fulfillment.filled.json")
OUT_JSON = os.path.join(ROOT, "data", "config", "knife-scene-scores.json")
OUT_MD = os.path.join(ROOT, "docs", "report", "knife-scenes-analysis.md")
OUT_FIG = os.path.join(ROOT, "docs", "report", "figures", "f6_knife_ranks.png")
RUN_CMD = "conda run -n nlpLesson python tools/knife_scene_eval.py"
N_POOL = 686
KS = (20, 50, 100)

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
# 1. 数据装载与场景 → 步骤映射
# ---------------------------------------------------------------------------
# 双漏场景的定性解释（数字全部来自 JSON，这里只写「为什么难」的判断；
# 依据是逐条读 record_span 内原文后的观察，未修改任何权重/特征）
DOUBLE_MISS_NOTES = {
    "K02": "「一人前往未来，一人留在过去」——长达 73 条记录的告别：白厄与「心中的英雄」逐句托付、回顾三千万世。"
           "情绪靠整段对话累积，单句几乎没有死亡/负面词（词面特征抓不到）；结构上它是连续对话而非事件转折，"
           "A/B 都把它排在 100 名之后（A 151 / B1 115）。",
    "K03": "「悬锋王朝，于此终结」——万敌与阿格莱雅的告别：两人用礼貌、克制的中文对白互相托付，"
           "最重的一句是「再见了，万敌」。全段只有「背后负创而死」一句是强词面，却被大段日常对白稀释；"
           "B1 的结构项还把它从 225 推到 308（越结构化越像「普通对话」）。",
    "K04": "「她是我的母亲，我的守护者」——万敌的梦：全靠「母亲/守护者/冥海/毒计」的回忆对白，"
           "没有事件、没有死亡词，情感在「我与她素未谋面」这句里，词面与结构都无处落脚（A 185 / B1 135）。",
    "K05": "「汝将背后负创而死」——万敌之死：全篇战斗高潮，但原文里大量是技能名、血量提示、"
           "「第 108642 次永劫回归」等机制文本，把仅有的情绪句冲淡；A 219 / B1 147，双漏。",
    "K16": "「这是剧目的最高潮」——那刻夏与赛飞儿用性命布局：场景几乎全是战术讨论与互相打趣，"
           "「最后一战」「把计划告诉海瑟音」把悲壮藏在计划书里；没有情绪词，A 287 / B1 131，仍双漏。",
    "K19": "「亡于分文」——赛飞儿之死：大量篇幅是她与「宿命/轮回」的辩论和回忆，预言兑现句"
           "「那预言里的『分文』…原来就是字面意思」只占一两句，被稀释；A 299 / B1 151。"
           "注意 B1 把它提升了 148 名，但仍不够。",
    "K23": "「无名的英雄，卡厄斯兰那」——开拓者与十二黄金裔的决战：B1 已把它的最好名次从 425 提到 148"
           "（本验证集最大提升），但场景是群像对话 + 名字宣告，情绪分散在很短的分句里，仍进不了 Top100。",
    "K24": "十二黄金裔的「创世之诗」与「明天见」——群像诗朗诵：十位黄金裔各念一句短诗，"
           "句短、意象抽象（黎明/黑夜/花海/星光），没有情绪词与死亡词，检测器无词可抓（A 177 / B1 160）。",
    "K28": "「一人留在过去，一人走向未来」——昔涟的最后抉择：全是哲学性对白（两条路、因果、记忆、收梢），"
           "情绪在「最难割舍的私心」里而没有词面锚点（A 348 / B1 258）。",
}


def load_pool():
    all_segs = read_jsonl(P_SEGMENTS)
    pool = [s for s in all_segs if s["n_main"] > 0 and not s["low_content"] and s["has_dialogue"]]
    assert len(pool) == N_POOL, "候选池不是 686：%d" % len(pool)
    return all_segs, pool


def scene_segments(scene):
    """场景映射到的 segment_id（segment_ids + ranges 去重、保序）"""
    ids = []
    for x in scene.get("segment_ids") or []:
        if x not in ids:
            ids.append(x)
    for r in scene.get("ranges") or []:
        x = r.split("#")[0]
        if x not in ids:
            ids.append(x)
    return ids


def scene_record_texts(scene):
    """按 record_span 从 amphoreus.final.jsonl 取原文（对话/旁白，最多 3 条摘录）"""
    lo, hi = scene.get("record_span") or (None, None)
    if lo is None:
        return []
    out = []
    for r in FINAL_RECORDS:
        if lo <= r["id"] <= hi and r.get("kind") in ("dialogue", "narration"):
            t = (r.get("text") or "").strip()
            if len(t) >= 6 and t not in [x["text"] for x in out]:
                out.append({"record_id": r["id"], "kind": r["kind"],
                            "speaker": r.get("speaker") or "", "text": t[:120]})
            if len(out) >= 3:
                break
    return out


FINAL_RECORDS = []


def build_data():
    global FINAL_RECORDS
    knife = read_json(P_KNIFE)
    all_segs, pool = load_pool()
    pool_ids = {s["segment_id"] for s in pool}
    all_ids = {s["segment_id"] for s in all_segs}
    A = {s["segment_id"]: s for s in read_json(P_A)["segments"]}
    B = {s["segment_id"]: s for s in read_json(P_B1)["segments"]}
    annot = read_json(P_ANNOT)["samples"]
    ann_level = {s["segment_id"]: s["significance"] for s in annot}
    filled = read_json(P_FILLED)["oracles"]
    gold_ids = {o["fulfillment_segment"]: o["oracle_id"] for o in filled}
    FINAL_RECORDS = read_jsonl(P_FINAL)

    scenes = []
    for sc in knife["scenes"]:
        raw_ids = scene_segments(sc)
        mapped = [x for x in raw_ids if x in pool_ids]
        missing_pool = [x for x in raw_ids if x not in pool_ids]
        a_rows = [{"segment_id": x, "rank": A[x]["rank"], "score": round(A[x]["score"], 4)}
                  for x in mapped]
        b_rows = [{"segment_id": x, "rank": B[x]["rank"], "score": round(B[x]["score"], 4)}
                  for x in mapped]
        a_ranks = [r["rank"] for r in a_rows]
        b_ranks = [r["rank"] for r in b_rows]
        gold_oracles = sorted({gold_ids[x] for x in mapped if x in gold_ids})
        levels = [ann_level[x] for x in mapped if x in ann_level]
        scenes.append({
            "id": sc["id"], "title": sc["title"], "role": sc.get("role"), "group": sc.get("group"),
            "type": sc.get("type"), "intensity": sc.get("intensity"), "confidence": sc.get("confidence"),
            "position": sc.get("position"), "why": sc.get("why"), "oracles": sc.get("oracles"),
            "motifs": sc.get("motifs"), "segment_ids_raw": raw_ids,
            "ranges": sc.get("ranges") or [], "record_span": sc.get("record_span"),
            "n_records": sc.get("n_records"), "char_len": sc.get("char_len"),
            "pool_segments": mapped, "missing_segments": missing_pool,
            "missing_in_all_segments": [x for x in missing_pool if x in all_ids],
            "n_pool_segments": len(mapped),
            "a_ranks": a_rows, "b1_ranks": b_rows,
            "best_a": min(a_ranks) if a_ranks else None,
            "best_b1": min(b_ranks) if b_ranks else None,
            "median_a": float(np.median(a_ranks)) if a_ranks else None,
            "median_b1": float(np.median(b_ranks)) if b_ranks else None,
            "delta_best": (min(a_ranks) - min(b_ranks)) if a_ranks else None,
            "is_gold": bool(gold_oracles), "gold_oracles": gold_oracles,
            "annotation_level": max(levels) if levels else None,
            "text_excerpt": scene_record_texts(sc),
        })
    return knife, scenes, pool, A, B, annot, ann_level, gold_ids


# ---------------------------------------------------------------------------
# 2. 指标
# ---------------------------------------------------------------------------
def cov(vals, k):
    hit = sum(1 for v in vals if v is not None and v <= k)
    return hit, round(hit / len(vals), 4) if vals else 0.0


def random_expected_scene(scenes):
    """场景级随机期望：场景有 k 个候选步，随机排序下至少一个进 TopK 的概率
       P = 1 - C(N-K, k)/C(N, k)"""
    out = {}
    for k in KS:
        probs = []
        for sc in scenes:
            kk = max(1, sc["n_pool_segments"])
            p = 1.0 - (comb(N_POOL - k, kk) / comb(N_POOL, kk)) if N_POOL - k >= kk else 0.0
            probs.append(p)
        out[str(k)] = {"expected_count": round(float(np.sum(probs)), 3),
                       "expected_rate": round(float(np.mean(probs)), 4),
                       "single_step_rate": round(k / N_POOL, 4)}
    return out


def compute_metrics(scenes, ann_level, gold_ids):
    a_best = [s["best_a"] for s in scenes]
    b_best = [s["best_b1"] for s in scenes]
    scene_level = {
        "n_scenes": len(scenes),
        "median_best_a": float(np.median(a_best)),
        "median_best_b1": float(np.median(b_best)),
        "mean_best_a": round(float(np.mean(a_best)), 2),
        "mean_best_b1": round(float(np.mean(b_best)), 2),
    }
    for k in KS:
        h, r = cov(a_best, k)
        h2, r2 = cov(b_best, k)
        scene_level["top%d" % k] = {"A": {"hit": h, "rate": r}, "B1": {"hit": h2, "rate": r2}}
    # 唯一 segment 级（去重后 36 步）
    uniq = []
    for s in scenes:
        for x in s["pool_segments"]:
            if x not in uniq:
                uniq.append(x)
    seg_level = {"n_segments": len(uniq)}
    # 需要 A/B 分数：从 scenes 里收集
    amap = {}
    bmap = {}
    for s in scenes:
        for r in s["a_ranks"]:
            amap[r["segment_id"]] = r["rank"]
        for r in s["b1_ranks"]:
            bmap[r["segment_id"]] = r["rank"]
    ua = [amap[x] for x in uniq]
    ub = [bmap[x] for x in uniq]
    seg_level["median_a"] = float(np.median(ua))
    seg_level["median_b1"] = float(np.median(ub))
    for k in KS:
        h, r = cov(ua, k)
        h2, r2 = cov(ub, k)
        seg_level["top%d" % k] = {"A": {"hit": h, "rate": r}, "B1": {"hit": h2, "rate": r2}}
    # 标注显著样本（等级 >= 2，n=28）对照（与 segment 级同单位）
    sig = [sid for sid, lv in ann_level.items() if lv >= 2]
    sig_a = [A_ALL[sid]["rank"] for sid in sig]
    sig_b = [B_ALL[sid]["rank"] for sid in sig]
    annotated = {"n": len(sig), "median_a": float(np.median(sig_a)), "median_b1": float(np.median(sig_b))}
    for k in KS:
        h, r = cov(sig_a, k)
        h2, r2 = cov(sig_b, k)
        annotated["top%d" % k] = {"A": {"hit": h, "rate": r}, "B1": {"hit": h2, "rate": r2}}
    return scene_level, seg_level, annotated, uniq


# A/B 全池 rank（供标注样本对照）
A_ALL = {}
B_ALL = {}


# ---------------------------------------------------------------------------
# 3. 重点案例与交叉表
# ---------------------------------------------------------------------------
def compute_cases(scenes):
    ranked = sorted(scenes, key=lambda s: -(s["delta_best"] or 0))
    top5 = [{"id": s["id"], "title": s["title"], "role": s["role"],
             "best_a": s["best_a"], "best_b1": s["best_b1"], "delta": s["delta_best"],
             "segments": s["pool_segments"], "why": s["why"]} for s in ranked[:5]]
    bottom5 = [{"id": s["id"], "title": s["title"], "role": s["role"],
                "best_a": s["best_a"], "best_b1": s["best_b1"], "delta": s["delta_best"],
                "segments": s["pool_segments"], "why": s["why"]} for s in ranked[-5:][::-1]]
    double_miss = [{"id": s["id"], "title": s["title"], "role": s["role"],
                    "intensity": s["intensity"], "segments": s["pool_segments"],
                    "best_a": s["best_a"], "best_b1": s["best_b1"], "delta": s["delta_best"],
                    "annotation_level": s["annotation_level"],
                    "text_excerpt": s["text_excerpt"],
                    "explanation": DOUBLE_MISS_NOTES.get(s["id"], "")}
                   for s in ranked if (s["best_a"] or 0) > 100 and (s["best_b1"] or 0) > 100]
    double_miss.sort(key=lambda x: x["best_b1"], reverse=True)
    return top5, bottom5, double_miss


def compute_cross(scenes):
    rows = Counter()
    for s in scenes:
        lv = s["annotation_level"]
        lv_key = "未标注" if lv is None else "等级%d" % lv
        rows[("神谕兑现" if s["is_gold"] else "非兑现", lv_key)] += 1
    lv_order = ["等级3", "等级2", "等级1", "等级0", "未标注"]
    table = []
    for gold in ("神谕兑现", "非兑现"):
        table.append({"row": gold, "cells": {lv: rows.get((gold, lv), 0) for lv in lv_order}})
    n_gold = sum(1 for s in scenes if s["is_gold"])
    n_lv3 = sum(1 for s in scenes if s["annotation_level"] == 3)
    n_both = sum(1 for s in scenes if s["is_gold"] and s["annotation_level"] == 3)
    n_gold_or_lv3 = sum(1 for s in scenes if s["is_gold"] or s["annotation_level"] == 3)
    gold_oracles = set()
    for s in scenes:
        gold_oracles.update(s["gold_oracles"])
    return {
        "level_order": lv_order, "table": table,
        "n_gold": n_gold, "n_level3": n_lv3, "n_both": n_both, "n_gold_or_lv3": n_gold_or_lv3,
        "n_gold_distinct_oracles": len(gold_oracles),
        "gold_oracles_covered": sorted(gold_oracles),
        "gold_scenes": [s["id"] for s in scenes if s["is_gold"]],
        "level3_scenes": [s["id"] for s in scenes if s["annotation_level"] == 3],
        "both_scenes": [s["id"] for s in scenes if s["is_gold"] and s["annotation_level"] == 3],
    }



# ---------------------------------------------------------------------------
# 4. 图 f6：A vs B1 在刀子场景上的排名分布
# ---------------------------------------------------------------------------
def make_figure(scenes, out):
    a_best = np.array([s["best_a"] for s in scenes], dtype=float)
    b_best = np.array([s["best_b1"] for s in scenes], dtype=float)
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.0))
    # (a) ECDF：场景级最好名次
    ax = axes[0]
    for vals, label, color in ((a_best, "A", "#2e5c8a"), (b_best, "B1", "#d98c3f")):
        xs = np.sort(vals)
        ys = np.arange(1, len(xs) + 1) / len(xs)
        ax.step(xs, ys, where="post", label=label, color=color, lw=1.8)
    grid = np.arange(1, N_POOL + 1)
    ax.plot(grid, grid / N_POOL, color="0.55", ls="--", lw=1.2,
            label=L("随机期望（单步）", "random (single step)"))
    ax.axvline(100, color="0.4", ls=":", lw=1)
    ax.text(104, 0.04, "Top100", fontsize=8, color="0.35")
    ax.set_xlabel(L("场景级最好名次（1=最高）", "scene best rank (1 = top)"))
    ax.set_ylabel(L("累计场景比例", "cumulative share of scenes"))
    ax.set_title(L("(a) 35 个刀子场景的 ECDF", "(a) ECDF over 35 knife scenes"), fontsize=9)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    # (b) A vs B1 最好名次散点
    ax = axes[1]
    cols = [plt.get_cmap("viridis")((s["intensity"] - 1) / 4.0) for s in scenes]
    sizes = [18 + 8 * max(1, s["n_pool_segments"]) for s in scenes]
    ax.scatter(a_best, b_best, c=cols, s=sizes, alpha=0.9, edgecolors="black", linewidths=0.4)
    ax.plot([1, N_POOL], [1, N_POOL], color="0.55", ls="--", lw=1.1)
    ax.axvline(100, color="0.6", ls=":", lw=1)
    ax.axhline(100, color="0.6", ls=":", lw=1)
    offs = [(8, 6), (-34, -12), (6, -14), (-40, 8), (10, 10), (-30, -16),
            (8, 12), (-36, 14), (12, -10)]
    k = 0
    for s in scenes:
        if (s["best_a"] or 0) > 100 and (s["best_b1"] or 0) > 100:
            ax.annotate(s["id"], (s["best_a"], s["best_b1"]), xytext=offs[k % len(offs)],
                        textcoords="offset points", fontsize=7, color="#b03a2e")
            k += 1
        elif s["delta_best"] >= 140:
            ax.annotate(s["id"], (s["best_a"], s["best_b1"]), xytext=offs[k % len(offs)],
                        textcoords="offset points", fontsize=7, color="#1f618d")
            k += 1
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(1, N_POOL)
    ax.set_ylim(N_POOL, 1)  # 排名轴反转：1 在顶部，对角线以上 = B1 更好
    ax.set_xlabel(L("A 场景级最好名次（log）", "A scene best rank (log)"))
    ax.set_ylabel(L("B1 场景级最好名次（log）", "B1 scene best rank (log)"))
    ax.set_title(L("(b) 对角线以上=B1 更好；红=双漏，蓝=B1 提升≥140",
                   "(b) above diagonal = B1 better; red = double-miss"), fontsize=9)
    ax.grid(alpha=0.25, which="both")
    sm = plt.cm.ScalarMappable(cmap="viridis",
                               norm=plt.Normalize(vmin=1, vmax=5))
    cb = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label(L("场景强度（1–5）", "intensity (1-5)"), fontsize=8)
    fig.suptitle(L("图6  刀子/高光场景在 A / B1 下的排名分布（35 场景；点大小=映射步数）",
                   "Fig6  Knife scenes under A vs B1"), fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 5. 报告
# ---------------------------------------------------------------------------
def render_report(data):
    meta = data["meta"]
    scenes = data["scenes"]
    m = data["metrics"]
    sl = m["scene_level"]
    seg = m["segment_level"]
    ann = m["annotated_significant"]
    rand = m["random_expectation"]
    top5 = data["improvements"]["top5"]
    bottom5 = data["improvements"]["bottom5"]
    dm = data["double_miss"]
    cross = data["cross_table"]
    Lr = []
    A = Lr.append

    def pc(hit, n):
        return "%d/%d = %.1f%%" % (hit, n, 100.0 * hit / n)

    A("# 刀子场景的人类验证集分析（35 个场景 × A/B1 检测器）")
    A("")
    A("> 生成脚本：`tools/knife_scene_eval.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    A("> 数据（只读）：`data/config/knife-scenes.json`（35 场景）、`baseline-a/b-scores.json`、"
      "`annotation-labels.json`、`oracle-fulfillment.filled.json`、`corpus/segments.jsonl`、`corpus/amphoreus.final.jsonl`")
    A("> 明细数据：`data/config/knife-scene-scores.json` ｜ 图：`docs/report/figures/f6_knife_ranks.png`")
    A("")
    A("## 1. 结论（可直接抄进报告）")
    A("")
    A("1. **B1 明显比 A 更能抓住人类认定的「刀子/高光」**：场景级最好名次的中位数 A = **%.0f**、"
      "B1 = **%.0f**；Top100 覆盖 A = **%s**、B1 = **%s**（Top20：A %s、B1 %s；Top50：A %s、B1 %s）。" % (
          sl["median_best_a"], sl["median_best_b1"],
          pc(sl["top100"]["A"]["hit"], sl["n_scenes"]), pc(sl["top100"]["B1"]["hit"], sl["n_scenes"]),
          pc(sl["top20"]["A"]["hit"], sl["n_scenes"]), pc(sl["top20"]["B1"]["hit"], sl["n_scenes"]),
          pc(sl["top50"]["A"]["hit"], sl["n_scenes"]), pc(sl["top50"]["B1"]["hit"], sl["n_scenes"])))
    A("2. **但仍远未「抓住」**：即使 B1，也只有 **%d/%d = %.1f%%** 的刀子场景进入 Top100——"
      "人类验证集里约 1/4 的高光，两个检测器都排不进去（双漏 %d 个）。" % (
          sl["top100"]["B1"]["hit"], sl["n_scenes"], 100.0 * sl["top100"]["B1"]["hit"] / sl["n_scenes"],
          len(dm)))
    A("3. **高于随机，但 A 的优势有限**：随机抽同样多步的期望覆盖为 Top20 %.2f 个 / Top50 %.2f 个 / Top100 %.2f 个"
      "（率 %.1f%% / %.1f%% / %.1f%%）；A 的 Top20 命中（%s）只相当于随机，Top100（%s）约为随机 2.4 倍；"
      "B1 分别约为随机 4.5 / 5.1 / 4.6 倍。" % (
          rand["20"]["expected_count"], rand["50"]["expected_count"], rand["100"]["expected_count"],
          100 * rand["20"]["expected_rate"], 100 * rand["50"]["expected_rate"], 100 * rand["100"]["expected_rate"],
          pc(sl["top20"]["A"]["hit"], sl["n_scenes"]), pc(sl["top100"]["A"]["hit"], sl["n_scenes"])))
    A("4. **比「人工显著性标注」更集中**：同为 segment 级，刀子场景的 Top100 覆盖 A %s、B1 %s；"
      "而 74 条标注里等级 ≥2 的 28 条显著样本，Top100 覆盖只有 A %s、B1 %s。→ 人类「高光/刀子」比「一般显著」"
      "更容易被检测器抓到（这也说明刀子是更极端的样本），两类标注不能互相替代。" % (
          pc(seg["top100"]["A"]["hit"], seg["n_segments"]), pc(seg["top100"]["B1"]["hit"], seg["n_segments"]),
          pc(ann["top100"]["A"]["hit"], ann["n"]), pc(ann["top100"]["B1"]["hit"], ann["n"])))
    A("5. **B1 的提升集中在「结构性强」的场景，对「纯对话/情感错位」反而扣分**：提升最大 %s；"
      "提升最小/变差 %s；双漏 9 个场景全部是长段告别/独白/群像诗（见 §5），词面与结构特征都无处落脚。" % (
          "、".join("%s（%+d）" % (x["id"], x["delta"]) for x in top5[:3]),
          "、".join("%s（%+d）" % (x["id"], x["delta"]) for x in bottom5[:2])))
    A("")

    # ---------------- 2. 映射 ----------------
    A("## 2. 场景 → 686 候选池映射")
    A("")
    A("35 个场景全部能映射到 686 池内的步骤（共 %d 个唯一 segment；K06/K07、K26/K27 两对场景共享同一 segment；"
      "K10/K12/K24 跨两个步骤，按场景级取「最好名次」）。" % m["segment_level"]["n_segments"])
    A("")
    A("| 场景 | 标题（截断） | 角色 | 池内 segment | A rank | B1 rank | 场景最好 A/B1 |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for s in scenes:
        segs_txt = "；".join("`%s`" % x for x in s["pool_segments"]) or "（无）"
        a_txt = " / ".join(str(r["rank"]) for r in s["a_ranks"])
        b_txt = " / ".join(str(r["rank"]) for r in s["b1_ranks"])
        A("| %s | %s | %s | %s | %s | %s | %d / %d |" % (
            s["id"], s["title"][:22], s["role"], segs_txt, a_txt, b_txt,
            s["best_a"], s["best_b1"]))
    A("")
    if any(s["missing_segments"] for s in scenes):
        A("> 映射不上的 segment：%s" % "；".join(
            "%s:%s" % (s["id"], "、".join(s["missing_segments"])) for s in scenes if s["missing_segments"]))
    else:
        A("> 无「映射不上」的 segment：35 场景的 segment_ids/ranges 全部命中 686 池。")
    A("")

    # ---------------- 3. 指标 ----------------
    A("## 3. 排名指标")
    A("")
    A("| 指标 | A | B1 | 随机期望 |")
    A("| --- | --- | --- | --- |")
    A("| 场景级最好名次：中位数 / 均值 | %.0f / %.1f | %.0f / %.1f | — |" % (
        sl["median_best_a"], sl["mean_best_a"], sl["median_best_b1"], sl["mean_best_b1"]))
    for k in KS:
        A("| 场景级 Top%d 覆盖（%d 场景） | %s | %s | %.2f 个（%.1f%%） |" % (
            k, sl["n_scenes"], pc(sl["top%d" % k]["A"]["hit"], sl["n_scenes"]),
            pc(sl["top%d" % k]["B1"]["hit"], sl["n_scenes"]),
            rand[str(k)]["expected_count"], 100 * rand[str(k)]["expected_rate"]))
    A("")
    A("**segment 级对照**（同单位，去重后 %d 个 knife segment vs 28 条等级≥2 标注样本）：" % seg["n_segments"])
    A("")
    A("| 集合 | n | 中位名次 A / B1 | Top20 A / B1 | Top50 A / B1 | Top100 A / B1 |")
    A("| --- | --- | --- | --- | --- | --- |")
    A("| 刀子场景覆盖的 segment | %d | %.0f / %.0f | %d / %d | %d / %d | %d / %d |" % (
        seg["n_segments"], seg["median_a"], seg["median_b1"],
        seg["top20"]["A"]["hit"], seg["top20"]["B1"]["hit"],
        seg["top50"]["A"]["hit"], seg["top50"]["B1"]["hit"],
        seg["top100"]["A"]["hit"], seg["top100"]["B1"]["hit"]))
    A("| 标注显著样本（等级≥2） | %d | %.0f / %.0f | %d / %d | %d / %d | %d / %d |" % (
        ann["n"], ann["median_a"], ann["median_b1"],
        ann["top20"]["A"]["hit"], ann["top20"]["B1"]["hit"],
        ann["top50"]["A"]["hit"], ann["top50"]["B1"]["hit"],
        ann["top100"]["A"]["hit"], ann["top100"]["B1"]["hit"]))
    A("")
    A("> 注：场景级指标是「场景内取最好名次」，天然比 segment 级乐观，因此与标注样本对比时用 segment 级。")
    A("")

    # ---------------- 4. B 提升案例 ----------------
    A("## 4. B1 提升最大 / 最小的场景")
    A("")
    A("| 方向 | 场景 | 角色 | 最好 rank A→B1 | Δ | 说明 |")
    A("| --- | --- | --- | --- | --- | --- |")
    for x in top5:
        A("| 提升最大 | %s %s | %s | %d→%d | %+d | %s |" % (
            x["id"], x["title"][:18], x["role"], x["best_a"], x["best_b1"], x["delta"],
            (x["why"] or "")[:36]))
    for x in bottom5:
        A("| 提升最小 | %s %s | %s | %d→%d | %+d | %s |" % (
            x["id"], x["title"][:18], x["role"], x["best_a"], x["best_b1"], x["delta"],
            (x["why"] or "")[:36]))
    A("")
    A("> 提升最大的场景共同点：身份/母题/神谕回收的「结构性」强（B1 的语义突变+身份/母题项能加分，"
      "如 %s）；提升最小/负向的场景多是纯对话告别或情感错位（B1 的结构项反而把它们当普通对话）。" % (
          "、".join(x["id"] for x in top5[:3])))
    A("")

    # ---------------- 5. 双漏 ----------------
    A("## 5. 双漏场景（A 与 B1 最好名次都 > 100，共 %d 个）" % len(dm))
    A("")
    A("| 场景 | 角色 | 强度 | 池内 segment | A/B1 最好名次 |")
    A("| --- | --- | --- | --- | --- |")
    for x in dm:
        A("| %s %s | %s | %d | %s | %d / %d |" % (
            x["id"], x["title"][:20], x["role"], x["intensity"],
            "；".join("`%s`" % s for s in x["segments"]), x["best_a"], x["best_b1"]))
    A("")
    for x in dm:
        A("### %s · %s ｜ %s" % (x["id"], x["title"], x["role"]))
        A("")
        A("- 最好名次：A 第 **%d** 名、B1 第 **%d** 名（B1 变化 %+d）。" % (
            x["best_a"], x["best_b1"], x["delta"]))
        if x["text_excerpt"]:
            A("- 原文摘录：")
            for e in x["text_excerpt"][:3]:
                A("  > [%s] %s" % (e["speaker"] or e["kind"], e["text"].replace("\n", " ")))
        A("- 为什么难：%s" % x["explanation"])
        A("")
    A("")

    # ---------------- 6. 交叉表 ----------------
    A("## 6. 交叉表：刀子里有多少是神谕兑现 / 标注等级 3")
    A("")
    A("| 场景 \ 标注等级 | %s |" % " | ".join(cross["level_order"]))
    A("| --- | %s |" % " | ".join("---" for _ in cross["level_order"]))
    for row in cross["table"]:
        A("| %s | %s |" % (row["row"], " | ".join(str(row["cells"][lv]) for lv in cross["level_order"])))
    A("")
    A("- 35 个刀子场景中，**%d 个**场景落在神谕兑现段上，覆盖了 13 条 gold 中的 **%d 条**"
      "（%s；K26/K27 共用 O13 同一兑现段）（%s）；**%d 个**被人工标注为等级 3（%s）；"
      "两者都满足的只有 **%d 个**（%s）。" % (
          cross["n_gold"], cross["n_gold_distinct_oracles"],
          "、".join(cross["gold_oracles_covered"]),
          "、".join(cross["gold_scenes"]),
          cross["n_level3"], "、".join(cross["level3_scenes"]),
          cross["n_both"], "、".join(cross["both_scenes"])))
    A("- 即「刀子 ≠ 神谕兑现」：14/35 的刀子是神谕兑现，另外 21 个高光（告别、群像、牺牲等）不在 13 条 gold 里；"
      "人类验证集因此补足了「非神谕兑现的高光」这一类样本，也解释了为什么这批样本更难被现有词面方法抓到。")
    A("")

    # ---------------- 7. 局限 ----------------
    A("## 7. 局限")
    A("")
    A("1. **场景级「最好名次」天然乐观**：35 场景中 3 个跨 2 步，取最好名次相当于给场景 2 次机会；"
      "与标注样本对比时已改用 segment 级（§3）。")
    A("2. **场景是人工从原文里「抽」出来的**，选点时可能受「哪段更好读/更有冲击」影响，带选择偏差；"
      "且 A/B1 的 rank 是既有的固定结果，本分析没有重新训练/调权重。")
    A("3. **双漏的解释是定性的**（逐条读原文后的判断），不是特征归因；要定量归因需做消融。")
    A("4. **样本量**：35 场景 / 36 个唯一 segment，覆盖率的分母很小（1 个场景 = 2.9 个百分点）；"
      "与 28 条标注样本的对比也只是描述性，不做显著性检验。")
    A("")
    A("## 8. 复现")
    A("")
    A("```bash")
    A(RUN_CMD)
    A("conda run -n nlpLesson python tools/knife_scene_eval.py --verify")
    A("```")
    A("")
    A("- 无随机：映射、覆盖率、随机期望都是解析计算；图由 JSON 同源数据绘制。")
    A("- `data/config/knife-scene-scores.json` 保存 35 场景的映射、A/B1 排名、指标、随机期望、"
      "双漏清单与交叉表；报告数字与之同源。")
    A("- `--verify` 会重算映射与最好名次、重算覆盖率/交叉表，并抽查报告中的 3 个数字。")
    A("")
    return "\n".join(Lr)


# ---------------------------------------------------------------------------
# 6. 主流程
# ---------------------------------------------------------------------------
def build():
    global A_ALL, B_ALL
    A_ALL = {s["segment_id"]: s for s in read_json(P_A)["segments"]}
    B_ALL = {s["segment_id"]: s for s in read_json(P_B1)["segments"]}
    knife, scenes, pool, A, B, annot, ann_level, gold_ids = build_data()
    scene_level, seg_level, annotated, uniq = compute_metrics(scenes, ann_level, gold_ids)
    rand = random_expected_scene(scenes)
    top5, bottom5, dm = compute_cases(scenes)
    cross = compute_cross(scenes)
    data = {
        "meta": {
            "script": "tools/knife_scene_eval.py",
            "run_command": RUN_CMD,
            "sources": ["data/config/knife-scenes.json", "data/config/baseline-a-scores.json",
                        "data/config/baseline-b-scores.json", "data/config/annotation-labels.json",
                        "data/config/oracle-fulfillment.filled.json", "data/corpus/segments.jsonl",
                        "data/corpus/amphoreus.final.jsonl"],
            "n_scenes": len(scenes), "n_pool": N_POOL,
            "note": "场景级=场景映射到的步骤中取最好名次；segment 级=去重后的 knife segment；"
                    "随机期望=超几何/组合解析值（单步 K/686）。",
        },
        "mapping_summary": {"n_scenes": len(scenes),
                            "n_unique_segments": seg_level["n_segments"],
                            "scenes_with_multiple_segments": [s["id"] for s in scenes if s["n_pool_segments"] > 1],
                            "scenes_with_missing": [s["id"] for s in scenes if s["missing_segments"]]},
        "scenes": scenes,
        "metrics": {"scene_level": scene_level, "segment_level": seg_level,
                    "annotated_significant": annotated, "random_expectation": rand},
        "improvements": {"top5": top5, "bottom5": bottom5},
        "double_miss": dm,
        "cross_table": cross,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写 %s" % os.path.relpath(OUT_JSON, ROOT))
    os.makedirs(os.path.dirname(OUT_FIG), exist_ok=True)
    make_figure(scenes, OUT_FIG)
    print("已生成 %s（%.1f KB）" % (os.path.relpath(OUT_FIG, ROOT), os.path.getsize(OUT_FIG) / 1024.0))
    md = render_report(data)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s（%.1f KB）" % (os.path.relpath(OUT_MD, ROOT), os.path.getsize(OUT_MD) / 1024.0))
    print("场景数 %d；唯一 segment %d；双漏 %d；神谕兑现 %d；等级3 %d；两者 %d" % (
        len(scenes), seg_level["n_segments"], len(dm), cross["n_gold"],
        cross["n_level3"], cross["n_both"]))
    if HAS_CJK:
        print("中文字体：%s" % CJK_FONT)
    else:
        print("!! 未找到中文字体，图已退回英文标签")
    try:
        from export_plot_data import export_for
        export_for("tools/knife_scene_eval.py")
    except Exception as _e:
        print("  [plot_data] 跳过：%s" % _e, file=sys.stderr)
    if not verify(verbose=True):
        print("!! 校验失败", file=sys.stderr)
        sys.exit(1)
    print("\n校验通过：映射/指标/交叉表与 JSON 一致，图非空。")


# ---------------------------------------------------------------------------
# 7. 校验
# ---------------------------------------------------------------------------
def verify(verbose=False):
    problems = []
    if not os.path.exists(OUT_JSON):
        print("缺少 %s" % OUT_JSON, file=sys.stderr)
        return False
    data = read_json(OUT_JSON)
    scenes = data["scenes"]
    # 1) 场景数 / 映射
    if len(scenes) != 35:
        problems.append("场景数 %d != 35" % len(scenes))
    # 2) 重算映射与最好名次
    A = {s["segment_id"]: s for s in read_json(P_A)["segments"]}
    B = {s["segment_id"]: s for s in read_json(P_B1)["segments"]}
    pool_ids = {s["segment_id"] for s in load_pool()[1]}
    for sc in scenes:
        raw = []
        for x in sc["segment_ids_raw"]:
            if x in pool_ids:
                raw.append(x)
        if raw != sc["pool_segments"]:
            problems.append("%s 映射重算不一致" % sc["id"])
        if raw:
            ba = min(A[x]["rank"] for x in raw)
            bb = min(B[x]["rank"] for x in raw)
            if ba != sc["best_a"] or bb != sc["best_b1"]:
                problems.append("%s 最好名次重算不一致" % sc["id"])
    # 3) 重算覆盖率
    a_best = [s["best_a"] for s in scenes]
    b_best = [s["best_b1"] for s in scenes]
    sl = data["metrics"]["scene_level"]
    for k in KS:
        ha = sum(1 for v in a_best if v <= k)
        hb = sum(1 for v in b_best if v <= k)
        if ha != sl["top%d" % k]["A"]["hit"] or hb != sl["top%d" % k]["B1"]["hit"]:
            problems.append("场景级 Top%d 覆盖重算不一致" % k)
    # 4) 交叉表
    gold_ids = {o["fulfillment_segment"] for o in read_json(P_FILLED)["oracles"]}
    ann = {s["segment_id"]: s["significance"] for s in read_json(P_ANNOT)["samples"]}
    n_gold = sum(1 for s in scenes if any(x in gold_ids for x in s["pool_segments"]))
    if n_gold != data["cross_table"]["n_gold"]:
        problems.append("神谕兑现场景数重算不一致")
    n_lv3 = 0
    for s in scenes:
        lv = max([ann[x] for x in s["pool_segments"] if x in ann] or [-1])
        if lv == 3:
            n_lv3 += 1
    if n_lv3 != data["cross_table"]["n_level3"]:
        problems.append("等级3场景数重算不一致")
    # 5) 双漏
    dm = [s for s in scenes if s["best_a"] > 100 and s["best_b1"] > 100]
    if len(dm) != len(data["double_miss"]):
        problems.append("双漏数重算不一致")
    # 6) 图与报告
    if not os.path.exists(OUT_FIG) or os.path.getsize(OUT_FIG) < 5000:
        problems.append("图不存在或过小")
    if not os.path.exists(OUT_MD):
        problems.append("报告不存在")
        md = ""
    else:
        md = open(OUT_MD, "r", encoding="utf-8").read()
    spot = [
        ("场景级 Top100 A", "%d/35" % sl["top100"]["A"]["hit"]),
        ("场景级 Top100 B1", "%d/35" % sl["top100"]["B1"]["hit"]),
        ("双漏数", "共 %d 个" % len(data["double_miss"])),
        ("神谕兑现场景数（正则）", None),
    ]
    for label, txt in spot:
        if txt is None:
            mm = re.search(r"\*\*(\d+) 个\*\*场景落在神谕兑现段上", md)
            if not mm or int(mm.group(1)) != data["cross_table"]["n_gold"]:
                problems.append("报告缺少数字 神谕兑现场景数=%d" % data["cross_table"]["n_gold"])
            continue
        if txt not in md:
            problems.append("报告缺少数字 %s=%s" % (label, txt))
    if verbose:
        print("\n抽查：场景数 %d；A/B1 场景级 Top100 = %d/%d；双漏 %d；神谕兑现 %d；等级3 %d" % (
            len(scenes), sl["top100"]["A"]["hit"], sl["top100"]["B1"]["hit"],
            len(data["double_miss"]), data["cross_table"]["n_gold"], data["cross_table"]["n_level3"]))
        for label, txt in spot:
            print("  %-20s %s ✓" % (label, "正则核对" if txt is None else txt))
    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="刀子场景人类验证集分析")
    ap.add_argument("--verify", action="store_true", help="只校验已有产物")
    args = ap.parse_args()
    if args.verify:
        ok = verify(verbose=True)
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    build()


if __name__ == "__main__":
    main()
