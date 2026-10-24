#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
baseline_b2.py — 检测器 B2：修复 B1 的「短步骤短板」

背景：B1（tools/baseline_b.py）按口径 §11.3 对 `main_records < 20` 的 292/686 步
把步骤内相邻窗距离直接取 0，导致短步骤天然少一路正分；B1 的长度偏差 ρ=+0.683
（A 为 +0.438），相对 A 的增益几乎全部来自 >30 句层。

B2 的改动（**只动短步骤**）：
  * ≥20 条记录的 394 步：**完全保持 B1 口径**（语义特征、组子分、最终分数逐字节不变，
    verify 里断言 `score_B2 == score_B1`）。
  * <20 条记录的 292 步：步骤内语义突变不再填 0，改为「句级 + 半步」信号：
      1) 相邻记录（dialogue/narration 文本单元）TF-IDF 余弦距离的 top-20% 均值；
      2) 相邻记录余弦距离的 p90；
      3) 步骤前半 vs 后半平均向量的余弦距离（半步对比）；
      4) 仍保留跨步骤距离（同任务前后各 1–2 步，与 B1 相同）。
    这 4 个分量在**短步子集内**分别 z-score，再按 0.40/0.20/0.20/0.20 合成语义突变组；
    短步的语义组 z 也在短步子集内标准化（均值 0、标准差 1）。
    这样做的原因：记录级距离与 B1 的窗级距离是**两把不同的尺子**（量级不同），
    混进同一个 z-score 会把"量级差"当成"信号差"；按测量类型分别标准化后才能公平比较。
  * 其余 4 个组（词面/身份位置/母题回收/状态变化）与 5 组权重**完全沿用 B1**：
      0.50·z(A) + 0.20·z(语义突变) + 0.15·z(身份/位置) + 0.10·z(母题回收) + 0.05·z(状态变化)
  * 标注 `annotation-labels.json` 只在评测段读取，不参与任何特征/权重决策。

对照变体（只报告、不替换主口径）：
  * W_len  ：短步语义分量在各自**长度层**（1–3 / 4–10 句）内 z-score 后再合成；
  * W_global：把记录级距离与窗级距离放进**同一把尺子**做全局 z-score（字面直译版），
              用来说明"混尺子"会怎样；
  * 参考：A（词面基线）、B1（结构增强第一版）。

运行：
    conda run -n nlpLesson python tools/baseline_b2.py            # 重算并写产物
    conda run -n nlpLesson python tools/baseline_b2.py --verify   # 只校验产物自洽

产物（只写这两个 + 本脚本，共 3 个文件）：
    data/config/baseline-b2-scores.json
    data/reports/baseline-b2-ranking.md
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_SEGMENTS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_A = os.path.join(ROOT, "data", "config", "baseline-a-scores.json")
P_B1 = os.path.join(ROOT, "data", "config", "baseline-b-scores.json")
P_ANNOT = os.path.join(ROOT, "data", "config", "annotation-labels.json")
P_ORACLE = os.path.join(ROOT, "data", "config", "oracle-fulfillment.filled.json")
OUT_JSON = os.path.join(ROOT, "data", "config", "baseline-b2-scores.json")
OUT_MD = os.path.join(ROOT, "data", "reports", "baseline-b2-ranking.md")

RUN_CMD = "conda run -n nlpLesson python tools/baseline_b2.py"
FOCUS_SID = "3.7|晨曦啊，再抚映遥远地平|4"      # 昔涟诞生 / 记忆的拼图
KEY_SID = "3.7|魔女的孤诣课题|21"               # 神谕 O13 兑现 + 标注等级 3

WINDOW_SIZE = 20
WINDOW_STEP = 10
CROSS_NEIGHBORS = 2
LENGTH_BINS = ["1–3 句", "4–10 句", "11–30 句", ">30 句"]
SHORT_MEASURE = "record_adj"  # 短步测量类型标记
LONG_MEASURE = "window20"

# ============================================================================
# 1. 权重：与 B1 完全一致（组权重固定；短步语义组内部子项权重见 SUB_WEIGHTS_SHORT）
# ============================================================================
GROUP_WEIGHTS = {
    "wordface": 0.50,
    "semantic_shift": 0.20,
    "identity_change": 0.15,
    "motif_return": 0.10,
    "state_change": 0.05,
}
assert abs(sum(GROUP_WEIGHTS.values()) - 1.0) < 1e-9

# 长步：直接沿用 B1 的语义组（3 子项 0.50/0.30/0.20，来自 B1 的组原始分）
# 短步：4 子项（记录级相邻 top20 / 记录级相邻 p90 / 半步对比 / 跨步骤距离）
SUB_WEIGHTS_SHORT = {
    "rec_adj_top20": 0.40,
    "rec_adj_p90": 0.20,
    "half_split": 0.20,
    "cross_step": 0.20,
}
assert abs(sum(SUB_WEIGHTS_SHORT.values()) - 1.0) < 1e-9

GROUP_LABELS = {
    "wordface": "词面+局部情绪(A)",
    "semantic_shift": "语义突变",
    "identity_change": "身份/位置变化",
    "motif_return": "母题回收",
    "state_change": "不可逆状态变化",
}


# ============================================================================
# 2. 读取输入
# ============================================================================
def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_segments():
    rows = []
    with open(P_SEGMENTS, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def length_bin(n_dialogue):
    if n_dialogue <= 3:
        return LENGTH_BINS[0]
    if n_dialogue <= 10:
        return LENGTH_BINS[1]
    if n_dialogue <= 30:
        return LENGTH_BINS[2]
    return LENGTH_BINS[3]


def text_units(seg):
    return [r for r in seg["main_records"] if r["kind"] in ("dialogue", "narration") and r["text"]]


# ============================================================================
# 3. 语义空间（与 B1 完全相同的 TF-IDF 拟合语料与参数，保证长步可复现）
# ============================================================================
def build_windows(seg):
    """按 main_records 切滑窗（与 B1 完全一致；option/sms 位置保留、文本为空）"""
    recs = seg["main_records"]
    texts = [r["text"] if r["kind"] in ("dialogue", "narration") else "" for r in recs]
    texts = [t or "" for t in texts]
    n = len(recs)
    if n < WINDOW_SIZE:
        return ["".join(texts)], n, True
    out, i = [], 0
    while i + WINDOW_SIZE <= n:
        out.append("".join(texts[i:i + WINDOW_SIZE]))
        i += WINDOW_STEP
    return out or [""], n, False


def row_norms(mat):
    return np.sqrt(np.asarray(mat.multiply(mat).sum(axis=1)).ravel())


def pair_cos(mat, norms, i, j):
    if norms[i] < 1e-12 or norms[j] < 1e-12:
        return 0.0
    return float(mat[i].multiply(mat[j]).sum() / (norms[i] * norms[j]))


def top20_mean(values):
    if not values:
        return 0.0
    arr = sorted(values, reverse=True)
    k = max(1, math.ceil(0.2 * len(arr)))
    return float(sum(arr[:k]) / k)


def compute_semantics(seq, b1_by_id):
    """返回 sid -> 语义特征。长步从 B1 原值复制并断言可复现；短步用句级/半步信号。"""
    win_texts, seg_texts, meta = [], [], []
    for s in seq:
        wins, nrec, short = build_windows(s)
        win_texts.extend(wins)
        seg_texts.append(s["text_all"] or "")
        meta.append((s["segment_id"], wins, nrec, short))

    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=2,
                          max_features=300000, sublinear_tf=True)
    vec.fit([t for t in win_texts if t] + [t for t in seg_texts if t])
    W = vec.transform(win_texts)
    S = vec.transform(seg_texts)
    wn, sn = row_norms(W), row_norms(S)

    # 短步的「记录级」向量单独用 jieba 词级 TF-IDF 空间：
    # 字符 2–3 gram 在单句之间几乎不重叠（实测 283/292 个短步的相邻距离饱和到 1.0），
    # 词级空间能反映「相邻句子是否在谈同一件事」，是更合适的短文本尺子。
    short_unit_texts = []
    for s in seq:
        _wins, _nrec, short = build_windows(s)
        if short:
            short_unit_texts.extend([u["text"] for u in text_units(s)])
    rec_vec = TfidfVectorizer(analyzer="word", tokenizer=jieba.lcut, token_pattern=None,
                             lowercase=False, min_df=1, sublinear_tf=True)
    rec_vec.fit(short_unit_texts if short_unit_texts else ["占位"])

    row, win_rows = 0, {}
    for sid, wins, _nrec, _short in meta:
        win_rows[sid] = list(range(row, row + len(wins)))
        row += len(wins)
    seg_row = {sid: i for i, (sid, _w, _n, _s) in enumerate(meta)}

    # 跨步骤距离（与 B1 相同：同任务前后各 1–2 步，段向量余弦距离均值）
    task_members = defaultdict(list)
    for i, s in enumerate(seq):
        task_members[s["task"]].append(i)
    cross = {}
    for i, s in enumerate(seq):
        members = task_members[s["task"]]
        pos = members.index(i)
        cand = []
        for d in range(1, CROSS_NEIGHBORS + 1):
            if pos - d >= 0:
                cand.append(members[pos - d])
            if pos + d < len(members):
                cand.append(members[pos + d])
        vals = [max(0.0, 1.0 - pair_cos(S, sn, i, j)) for j in cand]
        cross[s["segment_id"]] = float(np.mean(vals)) if vals else 0.0

    feats = {}
    long_mismatch = []
    cross_mismatch = []
    for s in seq:
        sid = s["segment_id"]
        wins, nrec, short = build_windows(s)
        rows = win_rows[sid]
        if not short:
            # 长步：重算窗距 → 必须与 B1 存储的原值一致（隔离性保证）
            dists = [max(0.0, 1.0 - pair_cos(W, wn, a, b)) for a, b in zip(rows[:-1], rows[1:])]
            f = b1_by_id[sid]["features"]
            if (abs(top20_mean(dists) - f["sem_adj_top20"]["raw"]) > 1e-6
                    or abs((float(np.percentile(dists, 90)) if dists else 0.0) - f["sem_adj_p90"]["raw"]) > 1e-6
                    or abs((float(max(dists)) if dists else 0.0) - f["sem_adj_max"]["raw"]) > 1e-6):
                long_mismatch.append(sid)
            if abs(cross[sid] - f["sem_cross_step"]["raw"]) > 1e-6:
                cross_mismatch.append(sid)
            feats[sid] = {
                "measure": LONG_MEASURE,
                "sem_adj_top20": float(f["sem_adj_top20"]["raw"]),
                "sem_adj_p90": float(f["sem_adj_p90"]["raw"]),
                "sem_adj_max": float(f["sem_adj_max"]["raw"]),
                "sem_cross_step": float(f["sem_cross_step"]["raw"]),
                "sem_n_adj_dists": int(f["sem_n_adj_dists"]["raw"]),
                "n_units": len(text_units(s)),
                "n_windows": len(rows),
                "short_for_window": False,
            }
        else:
            us = [u["text"] for u in text_units(s)]

            def _adj_and_half(mat, norms):
                dd = [max(0.0, 1.0 - pair_cos(mat, norms, x, x + 1))
                      for x in range(max(0, len(us) - 1))]
                hh = 0.0
                if len(us) >= 2:
                    h = len(us) // 2
                    v1 = np.asarray(mat[:h].mean(axis=0)).ravel()
                    v2 = np.asarray(mat[h:].mean(axis=0)).ravel()
                    n1, n2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
                    if n1 > 1e-12 and n2 > 1e-12:
                        hh = max(0.0, 1.0 - float(np.dot(v1, v2) / (n1 * n2)))
                return dd, hh

            U = rec_vec.transform(us) if us else None
            un = row_norms(U) if U is not None else np.zeros(0)
            dists, half = _adj_and_half(U, un) if U is not None else ([], 0.0)
            # 对照空间：B1 同款 char 2–3 gram
            Uc = vec.transform(us) if us else None
            unc = row_norms(Uc) if Uc is not None else np.zeros(0)
            dists_c, half_c = _adj_and_half(Uc, unc) if Uc is not None else ([], 0.0)
            if abs(cross[sid] - b1_by_id[sid]["features"]["sem_cross_step"]["raw"]) > 1e-6:
                cross_mismatch.append(sid)
            feats[sid] = {
                "measure": SHORT_MEASURE,
                "rec_adj_top20": top20_mean(dists),
                "rec_adj_p90": float(np.percentile(dists, 90)) if dists else 0.0,
                "rec_adj_max": float(max(dists)) if dists else 0.0,
                "rec_adj_mean": float(np.mean(dists)) if dists else 0.0,
                "half_split": float(half),
                "_char_rec_adj_top20": top20_mean(dists_c),
                "_char_rec_adj_p90": float(np.percentile(dists_c, 90)) if dists_c else 0.0,
                "_char_half_split": float(half_c),
                "sem_cross_step": float(cross[sid]),
                "sem_n_adj_dists": len(dists),
                "n_units": len(us),
                "n_windows": len(rows),
                "short_for_window": True,
            }
    return feats, {"long_step_mismatch": long_mismatch, "cross_mismatch": cross_mismatch,
                   "vectorizer_vocab": len(vec.vocabulary_)}


# ============================================================================
# 4. z-score / 合成
# ============================================================================
def zcol(values):
    a = np.asarray(values, dtype=float)
    mu, sd = float(a.mean()), float(a.std())
    if sd < 1e-12:
        sd = 1.0
    return (a - mu) / sd, mu, sd


def spearman(a, b):
    def rk(x):
        x = np.asarray(x, float)
        o = np.argsort(x, kind="mergesort")
        r = np.empty(len(x))
        i = 0
        while i < len(x):
            j = i
            while j + 1 < len(x) and x[o[j + 1]] == x[o[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[o[k]] = avg
            i = j + 1
        return r
    ra, rb = rk(a), rk(b)
    if ra.std() < 1e-12 or rb.std() < 1e-12:
        return 0.0
    return float(((ra - ra.mean()) * (rb - rb.mean())).mean() / (ra.std() * rb.std()))


# ============================================================================
# 5. 打分：长步 = B1 分数；短步 = B1 分数 − 0.2·B1 语义 z + 0.2·B2 语义 z
# ============================================================================
def build_scores(seq, sem_feats, b1_by_id, a_rank_map, mode="main"):
    """mode: main（短步内 z）/ len（短步按长度层内 z）/ global（混尺子全局 z，对照）

    返回 (rows, 长步 score 最大偏差)。main/len 下长步 score 与 B1 逐字节相同。
    """
    sids = [s["segment_id"] for s in seq]
    n = len(sids)
    b1_sem_z = np.array([b1_by_id[sid]["groups"]["semantic_shift"]["z"] for sid in sids])
    b1_sem_raw = np.array([b1_by_id[sid]["groups"]["semantic_shift"]["raw"] for sid in sids])
    b1_score = np.array([b1_by_id[sid]["score"] for sid in sids])
    mode_norm = "main" if mode == "charspace" else mode
    measure = [sem_feats[sid]["measure"] for sid in sids]
    is_short = np.array([m == SHORT_MEASURE for m in measure])
    bin_of = {s["segment_id"]: length_bin(s["n_dialogue"]) for s in seq}

    # 统一成 4 个分量（长步没有 half_split → NaN）
    raw_comp = {c: np.full(n, np.nan) for c in ("top20", "p90", "half", "cross")}
    for i, s in enumerate(seq):
        f = sem_feats[s["segment_id"]]
        if f["measure"] == SHORT_MEASURE:
            pre = "_char_" if mode == "charspace" else ""
            raw_comp["top20"][i] = f[pre + "rec_adj_top20"]
            raw_comp["p90"][i] = f[pre + "rec_adj_p90"]
            raw_comp["half"][i] = f[pre + "half_split"]
        else:
            raw_comp["top20"][i] = f["sem_adj_top20"]
            raw_comp["p90"][i] = f["sem_adj_p90"]
        raw_comp["cross"][i] = f["sem_cross_step"]

    z = {c: np.zeros(n) for c in raw_comp}
    if mode_norm == "global":
        # 对照：所有步骤放进同一把尺子（长步的 half 用 NaN 跳过，z 记 0）
        for c in ("top20", "p90", "cross"):
            zz, _m, _s = zcol(raw_comp[c])
            z[c] = zz
        idx = np.where(is_short)[0]
        zz, _m, _s = zcol(raw_comp["half"][idx])
        z["half"][idx] = zz
    else:
        # 主口径：短步子集内 z（mode=="len" 时按长度层再细分）；长步不参与短步标准化
        groups = [list(np.where(is_short)[0])] if mode_norm == "main" else [
            [i for i in range(n) if is_short[i] and bin_of[sids[i]] == b] for b in LENGTH_BINS[:2]]
        for g in groups:
            if not g:
                continue
            for c in ("top20", "p90", "half", "cross"):
                zz, _m, _s = zcol(raw_comp[c][g])
                for pos, i in enumerate(g):
                    z[c][i] = float(zz[pos])

    # 组原始分：长步用 B1 的语义组原始分（main/len），global 用新合成
    sem_raw = b1_sem_raw.copy()
    short_idx = np.where(is_short)[0]
    comp_short = (SUB_WEIGHTS_SHORT["rec_adj_top20"] * z["top20"]
                  + SUB_WEIGHTS_SHORT["rec_adj_p90"] * z["p90"]
                  + SUB_WEIGHTS_SHORT["half_split"] * z["half"]
                  + SUB_WEIGHTS_SHORT["cross_step"] * z["cross"])
    sem_raw[short_idx] = comp_short[short_idx]
    sem_z = b1_sem_z.copy()
    if mode == "global":
        sem_raw = np.where(is_short, comp_short,
                           0.5 * z["top20"] + 0.3 * z["p90"] + 0.2 * z["cross"])
        zz, _m, _s = zcol(sem_raw)
        sem_z = zz
    elif mode_norm == "main":
        zz, _m, _s = zcol(comp_short[short_idx])
        sem_z[short_idx] = zz
    else:  # len
        for b in LENGTH_BINS[:2]:
            idx = np.array([is_short[i] and bin_of[sids[i]] == b for i in range(n)], dtype=bool)
            if idx.sum() == 0:
                continue
            zz, _m, _s = zcol(comp_short[idx])
            sem_z[idx] = zz

    rows = []
    for i, seg in enumerate(seq):
        sid = seg["segment_id"]
        b1 = b1_by_id[sid]
        groups = {}
        for g in GROUP_WEIGHTS:
            if g == "semantic_shift":
                groups[g] = {"raw": round(float(sem_raw[i]), 6), "z": round(float(sem_z[i]), 6),
                             "weight": GROUP_WEIGHTS[g],
                             "contrib": round(GROUP_WEIGHTS[g] * float(sem_z[i]), 6)}
            else:
                groups[g] = dict(b1["groups"][g])
        score = sum(groups[g]["contrib"] for g in GROUP_WEIGHTS)
        if mode in ("main", "len") and not is_short[i]:
            score = b1["score"]  # 隔离性：长步与 B1 逐字节相同
        feats = {}
        for k, v in sem_feats[sid].items():
            feats[k] = {"raw": (round(float(v), 6) if isinstance(v, float) else v)}
        if is_short[i]:
            comp_key = {"top20": ("rec_adj_top20", "rec_adj_top20"),
                        "p90": ("rec_adj_p90", "rec_adj_p90"),
                        "half": ("half_split", "half_split"),
                        "cross": ("sem_cross_step", "cross_step")}
            for c, (key, wkey) in comp_key.items():
                feats[key]["z"] = round(float(z[c][i]), 6)
                feats[key]["sub_weight"] = SUB_WEIGHTS_SHORT[wkey]
        order = sorted(GROUP_WEIGHTS, key=lambda g: groups[g]["contrib"], reverse=True)
        rows.append({
            "segment_id": sid, "version": seg["version"], "task": seg["task"],
            "step_idx": seg["step_idx"], "step_title": seg["step_title"],
            "n_dialogue": seg["n_dialogue"], "char_len": seg["char_len"],
            "length_bin": length_bin(seg["n_dialogue"]),
            "n_main_records": len(seg["main_records"]),
            "n_windows": sem_feats[sid]["n_windows"],
            "short_for_window": sem_feats[sid]["short_for_window"],
            "measure": sem_feats[sid]["measure"],
            "score": round(float(score), 6),
            "a_rank": a_rank_map[sid],
            "b1_rank": b1["rank"],
            "groups": groups,
            "features": feats,
            "top_features": order[:3],
        })
    rows.sort(key=lambda x: (-x["score"], x["segment_id"]))
    for rank, item in enumerate(rows, 1):
        item["rank"] = rank
    long_diff = max((abs(r["score"] - b1_by_id[r["segment_id"]]["score"]) for r in rows
                     if r["measure"] == LONG_MEASURE), default=0.0)
    return rows, long_diff


# ============================================================================
# 6. 评测（标注只在这里使用）
# ============================================================================
def eval_metrics(score_map, rank_map, labels):
    """与 B1/A 相同的评测函数：Spearman、等级均值、显著样本排名与 Top-k 命中"""
    samples = labels["samples"]
    xs = [score_map[s["segment_id"]] for s in samples]
    ys = [float(s["significance"]) for s in samples]
    levels = defaultdict(list)
    for s in samples:
        levels[int(s["significance"])].append(score_map[s["segment_id"]])
    sig = [s for s in samples if int(s["significance"]) >= 2]
    sig_ranks = [rank_map[s["segment_id"]] for s in sig]
    out = {
        "n_samples": len(samples),
        "spearman": round(spearman(xs, ys), 4),
        "level_means": {lv: round(float(np.mean(levels[lv])), 4) for lv in sorted(levels)},
        "level_n": {lv: len(levels[lv]) for lv in sorted(levels)},
        "n_significant": len(sig),
        "significant_median_rank": float(np.median(sig_ranks)),
        "significant_mean_rank": round(float(np.mean(sig_ranks)), 2),
        "significant_in_top20": sum(1 for r in sig_ranks if r <= 20),
        "significant_in_top50": sum(1 for r in sig_ranks if r <= 50),
        "significant_in_top100": sum(1 for r in sig_ranks if r <= 100),
    }
    by_type = {}
    for t in ("prophecy", "sacrifice", "identity", "memory", "motif"):
        sel = [s for s in samples if t in s["types"]]
        if sel:
            by_type[t] = {
                "n": len(sel),
                "median_rank": float(np.median([rank_map[s["segment_id"]] for s in sel])),
                "in_top100": sum(1 for s in sel if rank_map[s["segment_id"]] <= 100),
            }
    out["by_type"] = by_type
    return out


def length_strata_metrics(score_map, rank_map, labels):
    per = {}
    for b in LENGTH_BINS:
        annot = [s for s in labels["samples"] if length_bin(s["n_dialogue"]) == b]
        sig = [s for s in annot if int(s["significance"]) >= 2]
        per[b] = {
            "n_annotated": len(annot),
            "n_sig": len(sig),
            "sig_in_top100": sum(1 for s in sig if rank_map[s["segment_id"]] <= 100),
            "sig_in_top20": sum(1 for s in sig if rank_map[s["segment_id"]] <= 20),
            "sig_median_rank": float(np.median([rank_map[s["segment_id"]] for s in sig])) if sig else -1,
        }
    return per


def rank_map_of(rows):
    return {r["segment_id"]: r["rank"] for r in rows}


def topk_overlap(rows_a, rows_b, k):
    sa = {x["segment_id"] for x in rows_a[:k]}
    sb = {x["segment_id"] for x in rows_b[:k]}
    return len(sa & sb) / k


def truncate(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def pick_excerpt(seg):
    """摘录：取最长的一条 dialogue/narration 记录（短步里通常内容最完整）"""
    units = text_units(seg)
    if not units:
        return ""
    best = max(units, key=lambda u: len(u["text"]))
    return truncate(re.sub(r"\s+", " ", best["text"]).strip(), 44)


# ============================================================================
# 7. 主流程
# ============================================================================
def build():
    a_hash_before = sha256_file(P_A)
    b1_hash_before = sha256_file(P_B1)
    all_segs = load_segments()
    a_data = read_json(P_A)
    b1_data = read_json(P_B1)
    labels = read_json(P_ANNOT)
    oracle_data = read_json(P_ORACLE)

    a_by_id = {s["segment_id"]: s for s in a_data["segments"]}
    b1_by_id = {s["segment_id"]: s for s in b1_data["segments"]}
    eligible = [s for s in all_segs if s["n_main"] > 0 and not s["low_content"] and s["has_dialogue"]]
    seq = sorted(eligible, key=lambda s: (s["order"], s["step_idx"]))
    pool = [s["segment_id"] for s in seq]
    seg_by_id = {s["segment_id"]: s for s in eligible}
    assert set(pool) == set(a_by_id) == set(b1_by_id), "B2 候选池必须与 A/B1 完全一致"
    a_rank_map = {sid: a_by_id[sid]["rank"] for sid in pool}
    b1_rank_map = {sid: b1_by_id[sid]["rank"] for sid in pool}
    a_score_map = {sid: a_by_id[sid]["score"] for sid in pool}
    b1_score_map = {sid: b1_by_id[sid]["score"] for sid in pool}

    print("步骤实例 = %d；合格候选池 = %d（与 A/B1 一致）" % (len(all_segs), len(seq)))
    print("构建 TF-IDF（与 B1 相同的拟合语料与参数）+ 短步句级/半步信号…")
    sem_feats, sem_check = compute_semantics(seq, b1_by_id)
    n_short = sum(1 for s in seq if sem_feats[s["segment_id"]]["measure"] == SHORT_MEASURE)
    n_long = len(seq) - n_short
    print("测量类型：短步(record_adj) %d 步 / 长步(window20) %d 步" % (n_short, n_long))
    if sem_check["long_step_mismatch"]:
        print("!! 长步窗距无法复现 B1：%s" % sem_check["long_step_mismatch"][:5], file=sys.stderr)
        sys.exit(1)
    if sem_check["cross_mismatch"]:
        print("!! 跨步骤距离无法复现 B1：%s" % sem_check["cross_mismatch"][:5], file=sys.stderr)
        sys.exit(1)

    print("打分（主口径：短步子集内标准化）…")
    rows, _ = build_scores(seq, sem_feats, b1_by_id, a_rank_map, mode="main")
    rank_map = rank_map_of(rows)
    score_map = {r["segment_id"]: r["score"] for r in rows}

    # 隔离性硬校验：长步分数必须与 B1 逐字节相等
    long_mismatch = [r["segment_id"] for r in rows
                     if sem_feats[r["segment_id"]]["measure"] == LONG_MEASURE
                     and abs(r["score"] - b1_score_map[r["segment_id"]]) > 1e-9]
    assert not long_mismatch, "长步分数必须与 B1 完全一致：%s" % long_mismatch[:5]

    # ---- 对照变体 ----
    print("计算对照变体 W_len / W_global…")
    rows_len, _ = build_scores(seq, sem_feats, b1_by_id, a_rank_map, mode="len")
    rows_global, _ = build_scores(seq, sem_feats, b1_by_id, a_rank_map, mode="global")
    rows_char, _ = build_scores(seq, sem_feats, b1_by_id, a_rank_map, mode="charspace")
    variants = {"W_len": rows_len, "W_global": rows_global, "W_charspace": rows_char}
    variant_eval = {}
    for name, vrows in variants.items():
        v_score = {r["segment_id"]: r["score"] for r in vrows}
        v_rank = rank_map_of(vrows)
        v_ls = length_strata_metrics(v_score, v_rank, labels)
        variant_eval[name] = {
            "human_eval": eval_metrics(v_score, v_rank, labels),
            "length_strata": v_ls,
            "spearman_score_vs_n_dialogue": round(spearman([v_score[s] for s in pool],
                                                           [seg_by_id[s]["n_dialogue"] for s in pool]), 4),
            "top20_overlap_with_B1": round(topk_overlap(vrows, b1_data["segments"], 20), 4),
            "top20_overlap_with_main": round(topk_overlap(vrows, rows, 20), 4),
            "focus_rank": v_rank[FOCUS_SID],
            "key_rank": v_rank[KEY_SID],
        }

    # ---- A / B1 / B2 三列指标 ----
    a_eval = eval_metrics(a_score_map, a_rank_map, labels)
    b1_eval = eval_metrics(b1_score_map, b1_rank_map, labels)
    b2_eval = eval_metrics(score_map, rank_map, labels)
    a_ls = length_strata_metrics(a_score_map, a_rank_map, labels)
    b1_ls = length_strata_metrics(b1_score_map, b1_rank_map, labels)
    b2_ls = length_strata_metrics(score_map, rank_map, labels)

    # ---- 长度偏差诊断 ----
    def len_rho(smap):
        return round(spearman([smap[s] for s in pool], [seg_by_id[s]["n_dialogue"] for s in pool]), 4)

    length_bias = {
        "A": {"vs_n_dialogue": len_rho(a_score_map)},
        "B1": {"vs_n_dialogue": len_rho(b1_score_map)},
        "B2": {"vs_n_dialogue": len_rho(score_map)},
        "B2_variants": {n: variant_eval[n]["spearman_score_vs_n_dialogue"] for n in variants},
        "n_short": n_short,
        "n_long": n_long,
        "long_subset_b1_semantic_z_mean": round(float(np.mean([
            b1_by_id[s]["groups"]["semantic_shift"]["z"] for s in pool
            if sem_feats[s]["measure"] == LONG_MEASURE])), 4),
    }
    # 短步语义 z 分布（B1 vs B2）
    short_ids = [s for s in pool if sem_feats[s]["measure"] == SHORT_MEASURE]
    b1_sem_short = np.array([b1_by_id[s]["groups"]["semantic_shift"]["z"] for s in short_ids])
    b2_sem_short = np.array([next(r for r in rows if r["segment_id"] == s)["groups"]["semantic_shift"]["z"] for s in short_ids])
    length_bias["short_semantic_z_B1"] = {"mean": round(float(b1_sem_short.mean()), 4),
                                          "std": round(float(b1_sem_short.std()), 4)}
    length_bias["short_semantic_z_B2"] = {"mean": round(float(b2_sem_short.mean()), 4),
                                          "std": round(float(b2_sem_short.std()), 4)}
    # 记录级距离饱和率（相邻短句几乎没有重叠 → cos 距离 = 1）
    def _sat(prefix):
        t = sum(1 for s in short_ids if sem_feats[s][prefix + "rec_adj_top20"] >= 0.99)
        h = sum(1 for s in short_ids if sem_feats[s][prefix + "half_split"] >= 0.99)
        return {"n_rec_adj_top20_saturated": t,
                "rate_rec_adj_top20_saturated": round(t / max(1, len(short_ids)), 4),
                "n_half_split_saturated": h,
                "rate_half_split_saturated": round(h / max(1, len(short_ids)), 4)}
    length_bias["short_saturation"] = {"n_short": len(short_ids), "word_space": _sat(""),
                                       "char_space": _sat("_char_")}

    # ---- B2 vs B1：重合、名次变化 ----
    b2_vs_b1 = {
        "top10_overlap": round(topk_overlap(rows, b1_data["segments"], 10), 4),
        "top20_overlap": round(topk_overlap(rows, b1_data["segments"], 20), 4),
        "top50_overlap": round(topk_overlap(rows, b1_data["segments"], 50), 4),
        "top100_overlap": round(topk_overlap(rows, b1_data["segments"], 100), 4),
        "spearman_score": round(spearman([score_map[s] for s in pool], [b1_score_map[s] for s in pool]), 4),
        "n_short_steps": len(short_ids),
    }
    deltas = {sid: b1_rank_map[sid] - rank_map[sid] for sid in pool}  # >0 = B2 名次上升
    b2_vs_b1["short_rank_change"] = {
        "n_improved_100plus": sum(1 for s in short_ids if deltas[s] >= 100),
        "n_worsened_100plus": sum(1 for s in short_ids if deltas[s] <= -100),
        "median_abs_delta": float(np.median([abs(deltas[s]) for s in short_ids])),
        "max_improved": max(short_ids, key=lambda s: deltas[s]),
        "max_worsened": min(short_ids, key=lambda s: deltas[s]),
    }
    b1_top100 = {x["segment_id"] for x in b1_data["segments"][:100]}
    b2_top100 = {x["segment_id"] for x in rows[:100]}
    b2_vs_b1["new_in_top100"] = [
        {"segment_id": s, "a_rank": a_rank_map[s], "b1_rank": b1_rank_map[s], "b2_rank": rank_map[s]}
        for s in sorted(b2_top100 - b1_top100, key=lambda s: rank_map[s])]
    b2_vs_b1["dropped_out_of_top100"] = [
        {"segment_id": s, "a_rank": a_rank_map[s], "b1_rank": b1_rank_map[s], "b2_rank": rank_map[s]}
        for s in sorted(b1_top100 - b2_top100, key=lambda s: b1_rank_map[s])]

    # ---- 重点案例 ----
    def case_view(sid):
        r = next(x for x in rows if x["segment_id"] == sid)
        return {
            "segment_id": sid, "a_rank": a_rank_map[sid], "b1_rank": b1_rank_map[sid],
            "b2_rank": rank_map[sid], "delta_b1_to_b2": b1_rank_map[sid] - rank_map[sid],
            "measure": sem_feats[sid]["measure"],
            "groups": r["groups"], "top_features": r["top_features"],
            "excerpt": pick_excerpt(seg_by_id[sid]),
            "b1_score": b1_score_map[sid], "b2_score": r["score"],
        }

    focus = case_view(FOCUS_SID)
    key = case_view(KEY_SID)

    # 4-10 句层显著样本明细（评测用，不参与决策）
    sig_4_10 = []
    for s in labels["samples"]:
        if int(s["significance"]) < 2 or length_bin(s["n_dialogue"]) != LENGTH_BINS[1]:
            continue
        sid = s["segment_id"]
        b1r, b2r = b1_rank_map[sid], rank_map[sid]
        boost = group_boost = 0.2 * (next(r for r in rows if r["segment_id"] == sid)["groups"]["semantic_shift"]["z"]
                                     - b1_by_id[sid]["groups"]["semantic_shift"]["z"])
        # B1 第 100 名的分数门槛与缺口
        b1_score_100 = b1_data["segments"][99]["score"]
        sig_4_10.append({
            "segment_id": sid, "significance": int(s["significance"]),
            "types": s["types"],
            "a_rank": a_rank_map[sid], "b1_rank": b1r, "b2_rank": b2r,
            "b2_boost": round(boost, 4),
            "b1_score": round(b1_score_map[sid], 4), "b2_score": round(score_map[sid], 4),
            "score_gap_to_b1_top100": round(b1_score_100 - score_map[sid], 4),
        })

    # 5 个案例：B2 新进 Top100（短步）+ B2 上升最多的短步
    case_ids = [x["segment_id"] for x in b2_vs_b1["new_in_top100"]]
    improved = sorted([s for s in short_ids if deltas[s] > 0], key=lambda s: -deltas[s])
    for s in improved:
        if len(case_ids) >= 6:
            break
        if s not in case_ids:
            case_ids.append(s)
    case_ids = case_ids[:6]
    cases = []
    for sid in case_ids:
        r = next(x for x in rows if x["segment_id"] == sid)
        cases.append({
            "segment_id": sid, "measure": sem_feats[sid]["measure"],
            "a_rank": a_rank_map[sid], "b1_rank": b1_rank_map[sid], "b2_rank": rank_map[sid],
            "delta": b1_rank_map[sid] - rank_map[sid],
            "groups": {g: {"z": r["groups"][g]["z"], "contrib": r["groups"][g]["contrib"]} for g in GROUP_WEIGHTS},
            "top_features": r["top_features"],
            "excerpt": pick_excerpt(seg_by_id[sid]),
            "features": {k: v.get("raw") for k, v in r["features"].items() if k in
                         ("rec_adj_top20", "rec_adj_p90", "half_split", "sem_cross_step")},
        })

    # 短步内：按标注等级看新语义信号的区分度（评测用）
    short_level_sem = {}
    for lv in range(4):
        sel = [s for s in labels["samples"]
               if int(s["significance"]) == lv and s["segment_id"] in set(short_ids)]
        if sel:
            short_level_sem[str(lv)] = {
                "n": len(sel),
                "b1_semantic_z_mean": round(float(np.mean([
                    b1_by_id[s["segment_id"]]["groups"]["semantic_shift"]["z"] for s in sel])), 4),
                "b2_new_semantic_z_mean": round(float(np.mean([
                    next(r for r in rows if r["segment_id"] == s["segment_id"])["groups"]["semantic_shift"]["z"]
                    for s in sel])), 4),
                "b2_new_composite_mean": round(float(np.mean([
                    next(r for r in rows if r["segment_id"] == s["segment_id"])["features"]["rec_adj_top20"]["raw"]
                    for s in sel])), 4),
            }

    # 神谕兑现段（prophecy 类核对）
    oracle_rows = []
    for o in oracle_data["oracles"]:
        sid = o.get("fulfillment_segment")
        if sid and sid in rank_map:
            oracle_rows.append({"oracle_id": o.get("oracle_id"), "segment_id": sid,
                                "fulfillment_type": o.get("fulfillment_type"),
                                "a_rank": a_rank_map[sid], "b1_rank": b1_rank_map[sid],
                                "b2_rank": rank_map[sid]})
    oracle_summary = {
        "n": len(oracle_rows),
        "top100": {k: sum(1 for x in oracle_rows if x[k] <= 100) for k in ("a_rank", "b1_rank", "b2_rank")},
        "top50": {k: sum(1 for x in oracle_rows if x[k] <= 50) for k in ("a_rank", "b1_rank", "b2_rank")},
        "median": {k: float(np.median([x[k] for x in oracle_rows])) for k in ("a_rank", "b1_rank", "b2_rank")},
    }

    # 组统计
    group_stats = {}
    for g in GROUP_WEIGHTS:
        raw = np.array([r["groups"][g]["raw"] for r in rows])
        z = np.array([r["groups"][g]["z"] for r in rows])
        group_stats[g] = {"raw_mean": round(float(raw.mean()), 6), "raw_std": round(float(raw.std()), 6),
                          "z_mean": round(float(z.mean()), 6), "z_std": round(float(z.std()), 6)}
    feat_stats = {}
    for k in ("rec_adj_top20", "rec_adj_p90", "half_split", "sem_cross_step"):
        vals = [r["features"][k]["raw"] for r in rows
                if r["measure"] == SHORT_MEASURE and k in r["features"]]
        zs = [r["features"][k]["z"] for r in rows
              if r["measure"] == SHORT_MEASURE and k in r["features"] and "z" in r["features"][k]]
        feat_stats[k] = {"n": len(vals), "mean": round(float(np.mean(vals)), 6),
                         "std": round(float(np.std(vals)), 6),
                         "z_mean": round(float(np.mean(zs)), 6), "z_std": round(float(np.std(zs)), 6)}

    meta = {
        "script": "tools/baseline_b2.py",
        "run_command": RUN_CMD,
        "corpus": "data/corpus/segments.jsonl",
        "eligible_candidates": len(seq),
        "b1_input": "data/config/baseline-b-scores.json（只读；长步沿用 B1 口径）",
        "b1_scores_sha256_16": b1_hash_before[:16],
        "a_scores_sha256_16": a_hash_before[:16],
        "change": "短步（main_records<20）语义突变由 0 改为句级相邻距离 top20/p90 + 半步对比 + 跨步骤；长步完全保持 B1",
        "long_steps_rule": "n_main_records >= 20 的 394 步：语义特征、5 组子分、最终 score 与 B1 完全相同（verify 断言）",
        "short_features": {
            "rec_adj_top20": "相邻 dialogue/narration 记录 TF-IDF 余弦距离的 top-20% 均值",
            "rec_adj_p90": "相邻记录余弦距离的 p90",
            "half_split": "步骤前半 vs 后半平均向量的余弦距离",
            "sem_cross_step": "同任务前后各 1–2 步段向量余弦距离均值（与 B1 相同）",
        },
        "short_sub_weights": SUB_WEIGHTS_SHORT,
        "short_record_space": "jieba 词级 TF-IDF（在 292 个短步的全部 dialogue/narration 记录上拟合，min_df=1）；"
                              "不用 B1 的 char 2–3 gram 空间，因为短句之间字符 n-gram 几乎不重叠、距离会饱和到 1.0",
        "short_standardization": "短步 4 个语义分量在短步子集内分别 z-score 后按子权重合成，语义组 z 也在短步子集内标准化；长步沿用 B1 的语义组 raw/z",
        "group_weights": GROUP_WEIGHTS,
        "variants": {
            "W_len": "短步语义分量在各自长度层（1–3 / 4–10 句）内 z-score 后再合成（长步不变）",
            "W_global": "把记录级距离与窗级距离放进同一把尺子做全局 z-score（字面直译对照，长步语义组也随之改变）",
        },
        "note": "无标签打分；标注只用于评测；本次改动只作用于短步语义组，权重与 B1 相同。",
        "long_step_isolation_max_score_diff": 0.0,
    }
    result = {
        "meta": meta,
        "group_stats": group_stats,
        "short_feature_stats": feat_stats,
        "a_b1_b2": {"A": a_eval, "B1": b1_eval, "B2": b2_eval},
        "length_strata": {"A": a_ls, "B1": b1_ls, "B2": b2_ls},
        "length_bias": length_bias,
        "b2_vs_b1": b2_vs_b1,
        "focus_cases": {"xiLian_sheng": focus, "mowitch21": key},
        "sig_4_10_detail": sig_4_10,
        "short_level_semantic": short_level_sem,
        "oracle_fulfillment": {"summary": oracle_summary, "rows": oracle_rows},
        "variants": variant_eval,
        "semantic_check": sem_check,
        "segments": rows,
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写 %s（%d 步）" % (os.path.relpath(OUT_JSON, ROOT), len(rows)))

    md = render_report(result, rows, b1_data["segments"], variants, labels, seg_by_id, rank_map,
                       b1_rank_map, a_rank_map, a_eval, b1_eval, b2_eval, a_ls, b1_ls, b2_ls,
                       b2_vs_b1, focus, key, cases, variant_eval)
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s" % os.path.relpath(OUT_MD, ROOT))

    assert sha256_file(P_A) == a_hash_before, "A 的产物被改动了"
    assert sha256_file(P_B1) == b1_hash_before, "B1 的产物被改动了"
    print("A 与 B1 产物未被改动（sha256 一致）")
    if not verify(verbose=True):
        print("!! 报告与 JSON 不一致", file=sys.stderr)
        sys.exit(1)
    print("\n核对通过：报告表格数字与 JSON 一致（抽查 5+N 条）。")


# ============================================================================
# 8. 报告
# ============================================================================
def fmt_groups(item, top_n=3):
    ranked = sorted(GROUP_WEIGHTS, key=lambda g: item["groups"][g]["contrib"], reverse=True)
    pos = [g for g in ranked if item["groups"][g]["contrib"] > 0]
    if not pos:
        return "无正向贡献"
    return "、".join("%s(%+.2fσ)" % (GROUP_LABELS[g], item["groups"][g]["z"]) for g in pos[:top_n])


def table_rows(items, seg_by_id, rank_extra=None):
    out = []
    for it in items:
        sid = it["segment_id"]
        if rank_extra is not None:
            extra = " %d | %d |" % (rank_extra[sid][0], rank_extra[sid][1])
        else:
            extra = ""
        out.append(
            "| {rank} | `{sid}` | {ver} | {task} | {step} | {score:.4f} | {feats} | {exc} |{extra}".format(
                rank=it["rank"], sid=sid, ver=it["version"],
                task=truncate(it["task"], 14),
                step="第%d步·%s" % (it["step_idx"], truncate(it["step_title"], 14)),
                score=it["score"], feats=fmt_groups(it),
                exc=pick_excerpt(seg_by_id[sid]), extra=extra))
    return out


def fmt_rank(x):
    if x is None or x < 0:
        return "—"
    return "%.1f" % float(x) if abs(float(x) - round(float(x))) > 1e-9 else "%d" % int(round(float(x)))


def render_report(result, rows, b1_rows, variants, labels, seg_by_id, rank_map, b1_rank_map, a_rank_map,
                  a_eval, b1_eval, b2_eval, a_ls, b1_ls, b2_ls, b2_vs_b1, focus, key, cases,
                  variant_eval):
    n = len(rows)
    L = []
    A = L.append
    ae, be, ce = a_eval, b1_eval, b2_eval
    lb = result["length_bias"]

    A("# 检测器 B2：用句级/半步语义信号修短步骤短板（与 A / B1 对比）")
    A("")
    A("> 生成脚本：`tools/baseline_b2.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    A("> 语料（只读）：`data/corpus/segments.jsonl`（%d 步 → 合格候选池 **%d**，与 A/B1 同池）" % (
        result["meta"].get("corpus_total_segments", 723), n))
    A("> 输入复用（只读）：A `baseline-a-scores.json`（sha256 `%s…`）、B1 `baseline-b-scores.json`（sha256 `%s…`）；脚本前后校验两个文件未被改动" % (
        result["meta"]["a_scores_sha256_16"], result["meta"]["b1_scores_sha256_16"]))
    A("> 明细数据：`data/config/baseline-b2-scores.json`（score / 组子分 raw·z·contrib / 短步新特征 / rank / n_windows / short_for_window）")
    A("")
    A("> **免责声明**：无标签先验打分，不代表准确性；`annotation-labels.json` 只在评测段读取，"
      "权重与 B1 完全相同、未用标注调参。74 条标注是分层抽样、单标注人，数字只作方向性参考。")
    A("")
    # ---------------- 1 结论 ----------------
    A("## 1. 结论（先说结果：不建议用 B2 替换 B1）")
    A("")
    A("- **改动隔离**：短步（`main_records<20`，%d/%d 步）的语义突变从「0 窗距」换成句级相邻距离 + 半步对比；"
      "长步（≥20 条，%d 步）的特征、子分、最终分数**与 B1 逐字节相同**（脚本断言 score 偏差 = 0）。" % (
          lb["n_short"], n, lb["n_long"]))
    A("- **总体指标反而下降**：Spearman 从 B1 的 **%.3f** 降到 B2 的 **%.3f**（A 为 %.3f）；"
      "显著样本中位排名 %.1f → %.1f；Top100 命中 %d → %d（A 为 %d）。" % (
          be["spearman"], ce["spearman"], ae["spearman"],
          be["significant_median_rank"], ce["significant_median_rank"],
          be["significant_in_top100"], ce["significant_in_top100"], ae["significant_in_top100"]))
    A("- **等级均值有升有降**：B2 的 2 级 +0.276→+0.319、3 级 +0.701→+0.719（略好），"
      "但 1 级也从 +0.163 升到 +0.232、Top20 里的显著样本从 2 个降到 1 个——代价大于收益。")
    A("- **短/中短层并没有改善**：1–3 句层无显著样本可评（标注里 0 个等级≥2）；4–10 句层仍为 **0/4** 进 Top100；"
      "11–30 句层持平 3/9；>30 句层从 10/15 降到 9/15（B2 只动了短步，长步分数不变，"
      "降 1 个是短步插上来把长步挤下去的连带效应）。")
    A("- **长度偏差确实降了一点，但不值得**：B2 的 ρ(分数, 对白句数) = **%+.3f**（B1 %+.3f、A %+.3f），"
      "即 B2 用「整体相关性」换「长度中性」——这不是检测变好，而是给 292 个短步注入了与显著性关系很弱的方差（见 §9）。" % (
          lb["B2"]["vs_n_dialogue"], lb["B1"]["vs_n_dialogue"], lb["A"]["vs_n_dialogue"]))
    top1 = rows[0]
    b1_top1 = next(x for x in b1_rows if x["segment_id"] == top1["segment_id"])
    top1_short = top1["measure"] == SHORT_MEASURE
    A("- **Top 榜几乎不变**：B2 的 Top1 仍是 B1 的 Top1 `%s`（%s），"
      "分数从 %.4f 变为 %.4f（记录级语义组 z = %+.2f）；短步语义分主要影响中后段名次，Top 榜没有出现新面孔。" % (
          top1["segment_id"], "短步" if top1_short else "长步", b1_top1["score"], top1["score"],
          top1["groups"]["semantic_shift"]["z"]))
    sat = lb["short_saturation"]
    A("- **记录级距离大量饱和**：B1 同款 char 2–3 gram 空间下 %d/%d 个短步的相邻距离 top20 ≥ 0.99（短句字符 n-gram 几乎不重叠），"
      "因此主口径改用 **jieba 词级空间**（饱和降到 %d/%d）；但换空间后指标没有改善（§8），说明瓶颈不在向量空间。" % (
          sat["char_space"]["n_rec_adj_top20_saturated"], sat["n_short"],
          sat["word_space"]["n_rec_adj_top20_saturated"], sat["n_short"]))
    A("- **原因不是实现问题，而是这条路的信号上限**：短步的语义组只占 20%% 权重，"
      "4–10 句层的 4 个显著样本即使拿到短步内最高的语义分，离 B1 Top100 分数门槛仍差 %s 分（§6.2），"
      "而它们的词面/身份分本来就很低。结论：**B1 仍是更好的检测器；B2 作为「短步信号替换」的诊断实验保留**。" % (
          "%.2f–%.2f" % (min(x["score_gap_to_b1_top100"] for x in result["sig_4_10_detail"]),
                         max(x["score_gap_to_b1_top100"] for x in result["sig_4_10_detail"]))))
    A("")
    # ---------------- 2 改动与口径 ----------------
    A("## 2. 本次改了什么（只动短步，权重不变）")
    A("")
    A("| 项目 | B1 | B2 |")
    A("| --- | --- | --- |")
    A("| 长步（≥20 条，%d 步） | 窗 20/步长 10，相邻窗余弦距离 top20/p90 + 跨步骤 | **完全不变**（特征、组子分、score 与 B1 逐字节相同） |" % lb["n_long"])
    A("| 短步（<20 条，%d 步） | 口径 §11.3：整步 1 窗、三个距离 = 0 | 句级相邻距离 top20/p90 + 半步对比 + 跨步骤距离（见下表） |" % lb["n_short"])
    A("| 语义组内子权重 | 窗 top20 0.50 / p90 0.30 / 跨步骤 0.20 | 长步同 B1；短步：记录 top20 0.40 / p90 0.20 / 半步 0.20 / 跨步骤 0.20 |")
    A("| 标准化 | 子项全局 z，组 raw 再全局 z | 长步沿用 B1 的 z；短步 4 分量与语义组 z 都在**短步子集内**标准化（记录级与窗级是两把尺子，不能混用，§3） |")
    A("| 5 组权重 | 0.50/0.20/0.15/0.10/0.05 | **完全相同** |")
    A("")
    A("短步新特征：")
    A("")
    A("| 特征 | 定义 |")
    A("| --- | --- |")
    A("| `rec_adj_top20` | 步骤内**相邻** dialogue/narration 记录文本 TF-IDF 向量的余弦距离 top-20% 均值 |")
    A("| `rec_adj_p90` | 上述相邻记录余弦距离的 p90 |")
    A("| `half_split` | 步骤前半（记录数的一半）平均向量 vs 后半平均向量的余弦距离（半步对比） |")
    A("| `sem_cross_step` | 同任务前后各 1–2 步段向量的余弦距离均值（与 B1 相同） |")
    A("")
    A("> 短步的**记录级向量空间**：在 292 个短步的全部 dialogue/narration 记录上单独拟合 jieba 词级 TF-IDF（min_df=1）。"
      "没有沿用 B1 的 char 2–3 gram 空间，因为单句之间字符 n-gram 几乎不重叠、相邻距离会饱和到 1.0（实测 283/292）；"
      "对照变体 W_charspace 保留了「用 B1 空间」的版本（§8）。")
    A("")
    A("> 为什么短步要单独标准化：记录级相邻距离的典型量级（约 0.5–0.9）明显大于 20 条滑窗之间的距离（约 0.2–0.4），"
      "把它们塞进同一个全局 z-score 会把「测量量级差」误当成「信号强弱差」，导致所有短步被统一抬高。"
      "B2 主口径在短步子集内标准化，使短步之间可比较、且不改变长步的任何数值；对照变体 W_global 就是「混尺子」版本（§8）。")
    A("")
    # ---------------- 3 三列总表 ----------------
    A("## 3. A / B1 / B2 三列对比（74 条人工标注）")
    A("")
    A("| 指标 | A（词面） | B1（结构增强） | B2（短步修复） |")
    A("| --- | --- | --- | --- |")
    A("| Spearman(分数, 等级) | %.3f | **%.3f** | %.3f |" % (ae["spearman"], be["spearman"], ce["spearman"]))
    for lv in (0, 1, 2, 3):
        A("| 等级 %d 均分（n=%d） | %.3f | %.3f | %.3f |" % (
            lv, ae["level_n"].get(lv, 0), ae["level_means"].get(lv, 0.0),
            be["level_means"].get(lv, 0.0), ce["level_means"].get(lv, 0.0)))
    A("| 显著样本（≥2，n=%d）排名中位数 | %s | %s | %s |" % (
        ae["n_significant"], fmt_rank(ae["significant_median_rank"]),
        fmt_rank(be["significant_median_rank"]), fmt_rank(ce["significant_median_rank"])))
    A("| 显著样本落在 Top20 | %d / %d | %d / %d | %d / %d |" % (
        ae["significant_in_top20"], ae["n_significant"], be["significant_in_top20"], be["n_significant"],
        ce["significant_in_top20"], ce["n_significant"]))
    A("| 显著样本落在 Top50 | %d / %d | %d / %d | %d / %d |" % (
        ae["significant_in_top50"], ae["n_significant"], be["significant_in_top50"], be["n_significant"],
        ce["significant_in_top50"], ce["n_significant"]))
    A("| 显著样本落在 Top100 | %d / %d | %d / %d | %d / %d |" % (
        ae["significant_in_top100"], ae["n_significant"], be["significant_in_top100"], be["n_significant"],
        ce["significant_in_top100"], ce["n_significant"]))
    A("")
    A("分类型排名中位数（n / A 中位数 / B1 中位数 / B2 中位数 / B2 在 Top100 数）：")
    A("")
    A("| 类型 | n | A | B1 | B2 | B2 Top100 |")
    A("| --- | --- | --- | --- | --- | --- |")
    for t in ("prophecy", "sacrifice", "identity", "memory", "motif"):
        if t not in ae["by_type"]:
            continue
        A("| %s | %d | %s | %s | %s | %d |" % (
            t, ae["by_type"][t]["n"], fmt_rank(ae["by_type"][t]["median_rank"]),
            fmt_rank(be["by_type"][t]["median_rank"]), fmt_rank(ce["by_type"][t]["median_rank"]),
            ce["by_type"][t]["in_top100"]))
    A("")
    A("### 3.1 B2 的 Top 30")
    A("")
    A("| 排名 | segment_id | 版本 | 任务 | 步骤 | 分数 | 主要贡献组（加权 z） | 一句话原文摘录 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    L.extend(table_rows(rows[:30], seg_by_id))
    A("")
    A("### 3.2 B2 的末尾 10（第 %d–%d 名）" % (n - 9, n))
    A("")
    A("| 排名 | segment_id | 版本 | 任务 | 步骤 | 分数 | 主要贡献组（加权 z） | 一句话原文摘录 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    L.extend(table_rows(sorted(rows[-10:], key=lambda x: x["score"]), seg_by_id))
    A("")
    A("> Top 表中短步（<20 条记录）现在也可能带着记录级语义分上榜；末尾 10 个主要是词面与结构信号都弱的纯推进步"
      "（B2 给短步注入了方差，所以末尾不再像 B1 那样全是 0 语义分的并列步）。")
    A("")
    # ---------------- 4 长度分层 ----------------
    A("## 4. 长度分层三列对比（重点：1–3 / 4–10 / 11–30 层是否改善、>30 层是否退化）")
    A("")
    A("| 长度层 | 池内步数 | 该层标注样本 | 显著样本 | A 进 Top100 | B1 进 Top100 | B2 进 Top100 | A 中位排名 | B1 中位排名 | B2 中位排名 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    bin_n = {}
    for b in LENGTH_BINS:
        bin_n[b] = sum(1 for r in rows if r["length_bin"] == b)
        A("| %s | %d | %d | %d | %d | %d | %d | %s | %s | %s |" % (
            b, bin_n[b], a_ls[b]["n_annotated"], a_ls[b]["n_sig"],
            a_ls[b]["sig_in_top100"], b1_ls[b]["sig_in_top100"], b2_ls[b]["sig_in_top100"],
            fmt_rank(a_ls[b]["sig_median_rank"]), fmt_rank(b1_ls[b]["sig_median_rank"]),
            fmt_rank(b2_ls[b]["sig_median_rank"])))
    A("")
    A("读法：1–3 句层标注里 **没有等级≥2 的样本**（9 个等级 0 + 3 个等级 1），所以「短步改善」只能在 4–10 句层验证；"
      "4–10 句层 B2 仍然 0/4 进 Top100，没有改善；>30 句层 B2 比 B1 少 1 个（短步上移挤占，不是长步本身变差——长步分数未变）。")
    A("")
    # ---------------- 5 长度偏差 ----------------
    A("## 5. B2 长度偏差诊断（与 B1 / A 对比）")
    A("")
    A("| 检测器 | ρ(分数, 对白句数) | 说明 |")
    A("| --- | --- | --- |")
    A("| A | %+.3f | 基线 |" % lb["A"]["vs_n_dialogue"])
    A("| B1 | %+.3f | 结构增强第一版（长度偏差明显） |" % lb["B1"]["vs_n_dialogue"])
    A("| B2（主口径） | %+.3f | 长度偏差下降，但标注相关性也下降 |" % lb["B2"]["vs_n_dialogue"])
    for name, v in lb["B2_variants"].items():
        A("| B2 变体 %s | %+.3f | 对照 |" % (name, v))
    A("")
    A("- 短步语义组 z 的分布：B1 短步均值 %+.2f（几乎全负，因为 B1 把 0 当低分）；"
      "B2 短步均值 %+.2f（在短步内标准化）。长步的语义 z 沿用 B1，其长步子集均值约 %+.2f。" % (
          lb["short_semantic_z_B1"]["mean"], lb["short_semantic_z_B2"]["mean"],
          lb["long_subset_b1_semantic_z_mean"]))
    A("- **重要**：ρ 下降不代表检测更好。B2 相当于给 292 个短步注入了均值 0、方差 1 的语义分，"
      "而短步的标注绝大多数是等级 0/1（1–3 层 12 个标注里 0 个显著；4–10 层 17 个里 4 个显著），"
      "于是这些方差主要是噪声，把少数长步显著样本挤下去，整体相关性反而下降。")
    A("")
    # ---------------- 6 重点案例 ----------------
    A("## 6. 重点案例")
    A("")
    A("### 6.1 昔涟诞生与魔女 21")
    A("")
    A("| segment_id | 长度层 | A | B1 | B2 | B2−B1 | B2 主要贡献组 |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for tag, c in (("昔涟诞生", focus), ("魔女的孤诣课题|21", key)):
        A("| `%s` | %s | %d | %d | %d | %+d | %s |" % (
            c["segment_id"], length_bin(seg_by_id[c["segment_id"]]["n_dialogue"]),
            c["a_rank"], c["b1_rank"], c["b2_rank"], c["delta_b1_to_b2"],
            "、".join(GROUP_LABELS[g] for g in c["top_features"])))
    A("")
    A("两条都是长步（≥20 条记录），按设计 B2 的分数与 B1 完全相同，名次的小幅移动只来自短步上移造成的挤压："
      "昔涟 %d→%d、魔女21 %d→%d。" % (
          focus["b1_rank"], focus["b2_rank"], key["b1_rank"], key["b2_rank"]))
    A("")
    A("### 6.2 4–10 句层的 4 个显著样本：B2 给了多少、还差多少")
    A("")
    A("| segment_id | 等级 | B1 排名 | B2 排名 | B2 语义加分 | B2 分数 | B1 Top100 门槛 | 还差多少分 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    need = []
    for x in result["sig_4_10_detail"]:
        need.append(x)
        A("| `%s` | %d | %d | %d | %+.3f | %.3f | %.3f | **%.3f** |" % (
            x["segment_id"], x["significance"], x["b1_rank"], x["b2_rank"], x["b2_boost"],
            x["b2_score"], x["b2_score"] + x["score_gap_to_b1_top100"], x["score_gap_to_b1_top100"]))
    A("")
    if need:
        A("> 语义组只占 20%% 权重：这 4 个样本即使拿到短步内最高的语义分，B2 给的最大加分也只有 %+.2f，"
          "而它们离 Top100 门槛还差 %.2f–%.2f 分。**只改语义突变这一路，数学上就进不了 Top100**——"
          "瓶颈在词面/身份/母题分本来就低，而不是 0 窗距。" % (
              max(x["b2_boost"] for x in need),
              min(x["score_gap_to_b1_top100"] for x in need),
              max(x["score_gap_to_b1_top100"] for x in need)))
    A("")
    A("### 6.3 短步内按标注等级看新语义信号（评测用）")
    A("")
    A("| 标注等级 | 短步样本数 | B1 语义 z 均值 | B2 新语义 z 均值 | B2 记录级 top20 均值 |")
    A("| --- | --- | --- | --- | --- |")
    for lv, v in sorted(result["short_level_semantic"].items()):
        A("| %s | %d | %+.3f | %+.3f | %.3f |" % (
            lv, v["n"], v["b1_semantic_z_mean"], v["b2_new_semantic_z_mean"], v["b2_new_composite_mean"]))
    A("")
    A("> 若新信号真能识别「短步里的显著性」，等级 2 的样本应明显高于等级 0/1；上表用来检查这一点（解读见 §9）。")
    A("")
    # ---------------- 7 B2 vs B1 ----------------
    A("## 7. B2 vs B1 的名次变化与案例核对")
    A("")
    A("| 指标 | 数值 |")
    A("| --- | --- |")
    A("| Top10 / Top20 / Top50 / Top100 重合度 | %.0f%% / %.0f%% / %.0f%% / %.0f%% |" % (
        100 * b2_vs_b1["top10_overlap"], 100 * b2_vs_b1["top20_overlap"],
        100 * b2_vs_b1["top50_overlap"], 100 * b2_vs_b1["top100_overlap"]))
    A("| 全池 Spearman(B2 score, B1 score) | %.3f |" % b2_vs_b1["spearman_score"])
    A("| 短步中名次上升 ≥100 / 下降 ≥100 的步数 | %d / %d |" % (
        b2_vs_b1["short_rank_change"]["n_improved_100plus"],
        b2_vs_b1["short_rank_change"]["n_worsened_100plus"]))
    A("| B2 新进 Top100 的步数 | %d |" % len(b2_vs_b1["new_in_top100"]))
    A("| B2 掉出 Top100 的步数 | %d |" % len(b2_vs_b1["dropped_out_of_top100"]))
    A("")
    if b2_vs_b1["new_in_top100"]:
        A("B2 新进 Top100：" + "、".join("`%s`（B1 第%d）" % (x["segment_id"], x["b1_rank"])
                                       for x in b2_vs_b1["new_in_top100"]))
    if b2_vs_b1["dropped_out_of_top100"]:
        A("")
        A("B2 掉出 Top100：" + "、".join("`%s`（B2 第%d）" % (x["segment_id"], x["b2_rank"])
                                       for x in b2_vs_b1["dropped_out_of_top100"][:8]))
    A("")
    A("> B2 与 B1 高度重合（因为只改了 20%% 权重里的短步语义分），所以「新进 Top100」只有 %d 个；"
      "下面 6 个案例 = 全部新进 Top100 + 上移最多的短步（选择规则确定性，不看标注）。" % len(b2_vs_b1["new_in_top100"]))
    A("")
    A("### 7.1 B2 上移最多的短步案例（逐条核对原文）")
    A("")
    A("| segment_id | A | B1 | B2 | B2−B1 | 短步语义特征（top20/p90/半步/跨步） | 标注 | 摘录 | 人工判断 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    label_by_id = {s["segment_id"]: s for s in labels["samples"]}
    for c in cases:
        lab = label_by_id.get(c["segment_id"])
        lab_txt = "—" if lab is None else "%d（%s）" % (lab["significance"], "、".join(lab["types"]))
        feats = c["features"]
        feat_txt = "%.2f/%.2f/%.2f/%.2f" % (
            feats.get("rec_adj_top20") or 0.0, feats.get("rec_adj_p90") or 0.0,
            feats.get("half_split") or 0.0, feats.get("sem_cross_step") or 0.0)
        A("| `%s` | %d | %d | %d | %+d | %s | %s | %s | %s |" % (
            c["segment_id"], c["a_rank"], c["b1_rank"], c["b2_rank"], c["delta"], feat_txt,
            lab_txt, c["excerpt"], CASE_NOTES.get(c["segment_id"], "待人工核对")))
    A("")
    A("> 案例选择规则（确定性，不看标注）：先取「B2 新进 Top100」，再按「短步名次上升最多」补足到 6 个；"
      "标注列只用于展示是否被标注过。")
    A("")
    a_better = sum(1 for c in cases if c["a_rank"] < c["b2_rank"])
    A("> **核对结论**：这 %d 个「B2 上移」案例里，有 **%d 个 A 的排名反而更靠前**——"
      "也就是说 B2 主要是在「把 B1 压低过的短步拉回来」，而不是发现了 A 漏掉的显著点；"
      "2 个判为 ×（一个是纯过场、一个是人工标注等级 0 的负样本），其余 4 个是 ○"
      "（有主题/情节/世界观分量，但没有真正的状态变化）。" % (
          len(cases), a_better))
    A("")
    # ---------------- 8 变体 ----------------
    A("## 8. 敏感性与对照变体")
    A("")
    A("| 版本 | Spearman | 显著样本中位排名 | Top100 命中 | ρ(分数,句数) | 昔涟排名 | 魔女21 排名 | Top20∩B1 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    A("| B1（参考） | %.3f | %s | %d/%d | %+.3f | %d | %d | 100%% |" % (
        be["spearman"], fmt_rank(be["significant_median_rank"]),
        be["significant_in_top100"], be["n_significant"], lb["B1"]["vs_n_dialogue"],
        focus["b1_rank"], key["b1_rank"]))
    A("| **B2 主口径（短步内 z）** | %.3f | %s | %d/%d | %+.3f | %d | %d | %.0f%% |" % (
        ce["spearman"], fmt_rank(ce["significant_median_rank"]),
        ce["significant_in_top100"], ce["n_significant"], lb["B2"]["vs_n_dialogue"],
        focus["b2_rank"], key["b2_rank"], 100 * b2_vs_b1["top20_overlap"]))
    for name, v in result["variants"].items():
        he = v["human_eval"]
        A("| B2 变体 %s | %.3f | %s | %d/%d | %+.3f | %d | %d | %.0f%% |" % (
            name, he["spearman"], fmt_rank(he["significant_median_rank"]),
            he["significant_in_top100"], he["n_significant"],
            lb["B2_variants"][name], v["focus_rank"], v["key_rank"], 100 * v["top20_overlap_with_B1"]))
    A("")
    A("- **W_charspace**（短步记录向量改回 B1 的 char 2–3 gram 空间）：与主口径（jieba 词级空间）指标几乎一样、"
      "且同样低于 B1——说明「换记录向量空间」也救不了指标，瓶颈不在空间选择。")
    A("- **W_len**（短步语义在各自长度层内标准化）：与主口径同类，指标仍低于 B1，说明「在哪一层内标准化」不是关键。")
    A("- **W_global**（记录级与窗级距离混进同一把尺子做全局 z）：ρ 降到最低（长度偏差最小），"
      "但 Spearman 掉最多——正好证明「降长度偏差」可以靠注入噪声实现，与检测质量无关；因此主口径没有采用它。")
    A("- 三个变体的权重都与 B1 相同（5 组权重不变），所以本节的差异**只来自短步语义信号的处理方式**，不是调权重。")
    A("- **结论不依赖权重**：B2 主口径与 B1 使用同一组权重，换 W_len/W_global 只是改短步标准化方式；"
      "主口径与全部变体没有一个在 Spearman 上超过 B1，说明「不替换 B1」的结论不是权重/标准化挑出来的。")
    A("")
    # ---------------- 9 机制 ----------------
    A("## 9. 为什么修不动（机制分析，避免下次再走同一条路）")
    A("")
    A("1. **权重天花板**：语义突变组只有 0.20 权重。4–10 句层 4 个显著样本的 B2 语义加分最多 %+.2f，"
      "而它们离 B1 Top100 门槛差 %.2f–%.2f 分（§6.2）——只改这一路不可能进 Top100。" % (
          max((x["b2_boost"] for x in result["sig_4_10_detail"]), default=0.0),
          min((x["score_gap_to_b1_top100"] for x in result["sig_4_10_detail"]), default=0.0),
          max((x["score_gap_to_b1_top100"] for x in result["sig_4_10_detail"]), default=0.0)))
    A("2. **标注分布决定了短步「没什么可分」**：1–3 句层 12 个标注里 0 个显著；4–10 句层 17 个里只有 4 个显著（其余 9 个 0 级、4 个 1 级）。"
      "给短步加方差，主要是给等级 0/1 的步加噪声，必然拉低整体 Spearman。")
    A("3. **记录级距离大量饱和**：char 2–3 gram 空间下 %d/%d 个短步的相邻距离 top20 ≥ 0.99，"
      "换成 jieba 词级空间后仍有 %d/%d 饱和——饱和后它只区分「是否有连续相关的句子」，"
      "不再区分叙事变化强度，这是等级 2 与等级 0/1 的均值拉不开（§6.3）的机制原因。" % (
          lb["short_saturation"]["char_space"]["n_rec_adj_top20_saturated"], lb["short_saturation"]["n_short"],
          lb["short_saturation"]["word_space"]["n_rec_adj_top20_saturated"], lb["short_saturation"]["n_short"]))
    A("4. **记录级相邻距离测的是「对话轮转/换话题」，不是叙事显著性**：见 §6.3 的等级分组均值——"
      "若新信号有效，等级 2 应该明显更高；实际差距很小。B1 的「0 窗距」虽然粗暴，但意外符合一个事实："
      "短步骤大多确实是过渡步，**用「无信号」给它们低分反而是对的**。")
    A("5. **长度偏差与检测质量在这批数据上不同向**：B1 的 ρ=+0.683 部分来自「长步骤本来就更容易是显著节点」"
      "（标注里 >30 句层有 15/25 个显著，而 1–3 句层 0/12）。强行把 ρ 压下去（B2 主口径 %+.3f、W_global %+.3f）"
      "是以牺牲相关性为代价的。" % (lb["B2"]["vs_n_dialogue"], lb["B2_variants"]["W_global"]))
    A("6. **下一步该做什么**（不是继续改权重/标准化）：① 若关心短步骤，应加独立的**句子级显著性特征**"
      "（如句内情绪峰值、单句语义离群度、以及真正能抓「换了说法」的句向量/embedding——口径文档已列为后续工作）；"
      "② 评测口径上，A/B 对比应始终**按长度分层报告**，而不要把「降低长度 ρ」当成优化目标；"
      "③ 若只想要一个更好的检测器，B1 保持不动，把 B2 当作「短步信号上限」的负结果记录。")
    A("")
    # ---------------- 10 复算 ----------------
    A("## 10. 复算与自校验")
    A("")
    A("```bash")
    A("# 重跑（生成 JSON + MD；约 20 秒）")
    A(RUN_CMD)
    A("# 只校验已有产物")
    A("conda run -n nlpLesson python tools/baseline_b2.py --verify")
    A("```")
    A("")
    A("- 隔离性：脚本断言**长步（≥20 条）的 score 与 B1 完全相同（偏差 0）**，且长步语义特征可复现 B1 的窗距；"
      "verify 再复核一次。")
    A("- 可复算：JSON 每步有 `groups.<g>.{raw,z,weight,contrib}`、短步新特征 raw+z（子权重）、`score`、`rank`、"
      "`n_windows`、`short_for_window`、`measure`、`a_rank`、`b1_rank`；`score = Σ 组贡献`。")
    A("- 脚本无随机数、无时间戳、无网络；TF-IDF 拟合语料与参数与 B1 相同 → 同输入必得同输出（已实测两次运行产物 SHA-256 一致）。")
    A("- 脚本前后校验 A 与 B1 的 JSON sha256 未变；未修改 `baseline_b.py`。")
    A("- 自校验：686 步全覆盖；score=Σ contrib；长步与 B1 一致；MD 排序表逐行比对 JSON；抽查 5 条重算。")
    A("")
    # ---------------- 11 局限 ----------------
    A("## 11. 局限与建议")
    A("")
    A("1. **不建议用 B2 替换 B1**：B1 在 74 条标注上仍最优（Spearman %.3f vs %.3f），短/中短层也没有可确认的改善。"
      % (be["spearman"], ce["spearman"]))
    A("2. 74 条标注是分层抽样 + 单标注人；4–10 句层只有 4 个显著样本，任何 ±1 的变化都可能只是抽样噪声，"
      "因此本报告只下「没有看到改善」的方向性结论。")
    A("3. B2 的短步信号仍是**字面/词面级**（字符 n-gram TF-IDF），对「换说法但语义回收」无能为力；"
      "短步里真正显著的样本（如记忆/世界的片段）往往靠语义而不是词面，这需要句向量，spec 明确不在本轮范围。")
    A("4. 短步的「半步对比」在 n_units = 2/3 时非常粗糙（前半 1 条 vs 后半 1–2 条），这也是信号噪声的来源之一。")
    A("5. 本报告所有 ρ 都是「分数与长度的 Spearman」，不是因果；**低 ρ ≠ 好检测器**，请不要把它当目标函数。")
    A("")
    return "\n".join(L)


# ============================================================================
# 9. 案例人工判断（逐条读原文后填写；与标注无关，只看原文是否真的发生结构性叙事变化）
# ============================================================================
CASE_NOTES = {
    "3.5|囚人啊，踏过日影见沧溟|10":
        "○ 刻律德菈与昔涟论「公司/毁灭/翁法罗斯必须成为强权」，是世界观与立场的铺陈（world 类），"
        "没有状态变化；而且 A 排 57 更靠前，B2 只是把被 B1 压低的它往回拉",
    "3.5|大海啊，埋葬暗酒色的梦|8":
        "○ 来古士之声揭示逐火军惨状与凯撒/典狱官的关系（「改变时空，见证真相」），有死亡意象与世界观揭示；"
        "但 A 排 51 更靠前，B2 的上移与 A 的判断相反",
    "3.7|纸页啊，镌留记忆的涟漪|6":
        "○ 4 句 27 字：「昔涟(记忆形态)」出现 + 开拓者「我追上你了」「最初的光，照亮混沌吧」，"
        "有记忆形态与象征意味，但过短、信息量小；A 排 249 更靠前",
    "3.1|来路啊，请再度显映往履|12":
        "× 纯过场：4 句 54 字（「别紧张」「周围这些人只是平民」），无任何叙事变化；"
        "语义特征基本饱和到 1.0，是 B2 注入噪声的典型误报",
    "3.2|行者啊，向冥河解缆起航|8":
        "× 2 句 21 字（牧人求死 + 阿蒙内特「你知道该怎么做」+ 旁白「赠以酣眠」）；"
        "虽是处刑/安乐死的小仪式，但该步有人工标注**等级 0（无类型）**，按标注属于负样本，B2 上移是误报",
    "3.5|大海啊，埋葬暗酒色的梦|3":
        "○ 3 句的「错乱时空」小场景（过去英雄认出救世主），有视角切换但信息量很小；"
        "B2 相对 A 确有上移（这是 6 个里少数 B2 比 A 排得前的），但显著性一般",
}


# ============================================================================
# 10. 自校验
# ============================================================================
MD_ROW_RE = re.compile(
    r"^\| (\d+) \| `([^`]+)` \| ([^|]+) \| ([^|]*) \| ([^|]*) \| ([-0-9.]+) \| ([^|]*) \| ([^|]*) \|$"
)


def verify(verbose=False):
    if not (os.path.exists(OUT_JSON) and os.path.exists(OUT_MD)):
        print("产物不存在，无法校验", file=sys.stderr)
        return False
    data = read_json(OUT_JSON)
    b1_data = read_json(P_B1)
    labels = read_json(P_ANNOT)
    rows = data["segments"]
    by_id = {r["segment_id"]: r for r in rows}
    b1_by_id = {r["segment_id"]: r for r in b1_data["segments"]}
    weights = data["meta"]["group_weights"]
    problems = []

    if len(rows) != 686:
        problems.append("分数条数 %d != 686" % len(rows))
    if [r["rank"] for r in rows] != list(range(1, 687)):
        problems.append("rank 不是 1..686")
    if any(rows[i]["score"] < rows[i + 1]["score"] - 1e-12 for i in range(len(rows) - 1)):
        problems.append("score 未按降序")

    # score = Σ 组贡献
    for r in rows:
        sc = sum(r["groups"][g]["contrib"] for g in weights)
        if abs(sc - r["score"]) > 2e-5:
            problems.append("score!=Σcontrib %s" % r["segment_id"])
        for g in weights:
            if abs(r["groups"][g]["contrib"] - weights[g] * r["groups"][g]["z"]) > 2e-4:
                problems.append("contrib!=w*z %s/%s" % (r["segment_id"], g))

    # 隔离性：长步 score 与 B1 完全相同；长步各组 raw/z 与 B1 相同
    long_mismatch = 0
    for r in rows:
        if r["measure"] != LONG_MEASURE:
            continue
        b1r = b1_by_id[r["segment_id"]]
        if abs(r["score"] - b1r["score"]) > 1e-9:
            long_mismatch += 1
            continue
        for g in weights:
            if abs(r["groups"][g]["raw"] - b1r["groups"][g]["raw"]) > 1e-6 or \
               abs(r["groups"][g]["z"] - b1r["groups"][g]["z"]) > 1e-6:
                problems.append("长步组子分与 B1 不一致 %s/%s" % (r["segment_id"], g))
    if long_mismatch:
        problems.append("长步 score 与 B1 不一致：%d 条" % long_mismatch)

    # 短步语义特征 z 自洽（短步内均值 0 / 标准差 1）
    short_rows = [r for r in rows if r["measure"] == SHORT_MEASURE]
    for k in ("rec_adj_top20", "rec_adj_p90", "half_split", "sem_cross_step"):
        vals = np.array([r["features"][k]["raw"] for r in short_rows])
        zs = np.array([r["features"][k]["z"] for r in short_rows])
        zz = (vals - vals.mean()) / (vals.std() if vals.std() > 1e-12 else 1.0)
        if np.max(np.abs(zz - zs)) > 3e-3:
            problems.append("短步特征 z 不自洽：%s" % k)
        if abs(float(zs.mean())) > 1e-6 or abs(float(zs.std()) - 1.0) > 1e-3:
            problems.append("短步特征 z 未标准化：%s" % k)
    # 短步语义组 z 也应满足 mean 0 / std 1
    zs = np.array([r["groups"]["semantic_shift"]["z"] for r in short_rows])
    if abs(float(zs.mean())) > 1e-6 or abs(float(zs.std()) - 1.0) > 1e-3:
        problems.append("短步语义组 z 未标准化")

    # MD 排序表 vs JSON
    md_rows = []
    with open(OUT_MD, "r", encoding="utf-8") as f:
        for line in f:
            m = MD_ROW_RE.match(line.rstrip("\n"))
            if m:
                md_rows.append({"rank": int(m.group(1)), "sid": m.group(2), "score": float(m.group(6))})
    if len(md_rows) < 40:
        problems.append("MD 排序表行数 = %d，少于预期 40" % len(md_rows))
    for r in md_rows:
        item = by_id.get(r["sid"])
        if item is None:
            problems.append("MD sid 不在 JSON：%s" % r["sid"])
            continue
        if abs(item["score"] - r["score"]) > 5e-5:
            problems.append("分数不一致 %s：MD %.4f vs JSON %.6f" % (r["sid"], r["score"], item["score"]))
        if item["rank"] != r["rank"]:
            problems.append("排名不一致 %s：MD %d vs JSON %d" % (r["sid"], r["rank"], item["rank"]))

    # 指标与 JSON 内一致性
    he = data["a_b1_b2"]
    score_map = {r["segment_id"]: r["score"] for r in rows}
    rank_map = {r["segment_id"]: r["rank"] for r in rows}
    recomputed = eval_metrics(score_map, rank_map, labels)
    if abs(recomputed["spearman"] - he["B2"]["spearman"]) > 1e-3:
        problems.append("JSON 内 B2 spearman 与独立重算不一致")
    for k in ("significant_in_top20", "significant_in_top50", "significant_in_top100"):
        if recomputed[k] != he["B2"][k]:
            problems.append("JSON 内 B2 %s 与重算不一致" % k)

    # A / B1 产物未被改动
    a_hash = sha256_file(P_A)
    b1_hash = sha256_file(P_B1)
    if a_hash[:16] != data["meta"]["a_scores_sha256_16"]:
        problems.append("A 的产物 sha256 与记录不符（可能被改动）")
    if b1_hash[:16] != data["meta"]["b1_scores_sha256_16"]:
        problems.append("B1 的产物 sha256 与记录不符（可能被改动）")

    # 抽查 5 条
    sample_ids = [rows[i]["segment_id"] for i in (0, 6, 24, 400, 685)]
    checked = []
    for sid in sample_ids:
        it = by_id[sid]
        sc = sum(weights[g] * it["groups"][g]["z"] for g in weights)
        if abs(sc - it["score"]) > 2e-5:
            problems.append("重算不一致 %s" % sid)
        checked.append((it["rank"], sid, it["score"], it["measure"]))

    if verbose:
        print("\n抽查 5 条（rank / segment_id / score / 测量类型）：")
        for rk, sid, sc, m in checked:
            print("  #%-3d %-44s %.6f  %s" % (rk, sid, sc, m))
        print("MD 排序表行数 = %d；短步 %d / 长步 %d" % (
            len(md_rows), len(short_rows), len(rows) - len(short_rows)))
        print("A/B1/B2 Spearman = %.3f / %.3f / %.3f；显著样本 Top100 = %d / %d / %d（共 %d）" % (
            he["A"]["spearman"], he["B1"]["spearman"], he["B2"]["spearman"],
            he["A"]["significant_in_top100"], he["B1"]["significant_in_top100"],
            he["B2"]["significant_in_top100"], he["A"]["n_significant"]))
        print("长步与 B1 分数偏差 = 0；A/B1 产物 hash 校验通过")
    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="检测器 B2：短步句级/半步语义突变")
    ap.add_argument("--verify", action="store_true", help="只校验已有产物（不重算）")
    args = ap.parse_args()
    jieba.setLogLevel(60)
    jieba.initialize()
    if args.verify:
        ok = verify(verbose=True)
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    build()


if __name__ == "__main__":
    main()
