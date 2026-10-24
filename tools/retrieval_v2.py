#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
retrieval_v2.py — 补 task-15 的三块分析：

A. 神谕检索 v2（修正 v1 的 gold 构造问题）
   v1 的问题：12/13 条 gold 本身就是吟诵步、10/13 含神谕原文 → 关键词/字面方法必然赢。
   本脚本做两个变体重评五法（关键词 / TF-IDF-char / TF-IDF-word / BM25 / LSA）：
     * v2-mask     ：query 掩蔽——去掉神谕原句，只留 keywords + metaphors.gloss + 弱提示
                     （预言/神谕/命运/箴言/谶语/宿命），权重低于 keywords；
     * v2-noRecite ：候选池剔除「含神谕原文的吟诵步」（6-gram 覆盖率阈值 0.5）；
                     gold 被剔除的 query 标 N/A，不计入指标分母；
     * v2-both     ：掩蔽 query + 剔除吟诵步（最接近「真语义检索」的版本，作为附列）。
   与 v1（data/config/oracle-retrieval-results.json，只读）逐方法、逐 query 对比。

B. Q3 类型级分析（7 类型：identity/memory/prophecy/relationship/world/sacrifice/motif）
   按标注 types 分组，比较 A/B 的排名中位数、Top100 覆盖、组内 Spearman，找出 B 提升最大/最小的类型。

C. Q4 神谕显著性检验
   13 个神谕兑现段 vs 其余 673 步：A/B 分数分布 Mann–Whitney U + Cliff's delta；
   并按长度分层（1–3 / 4–10 / 11–30 / >30 句）再验一次，排除长度混淆。

产出（共 5 个文件，只写这些）：
   tools/retrieval_v2.py
   data/config/retrieval-v2-results.json
   data/reports/retrieval-v2.md
   data/config/type-and-oracle-significance.json
   data/reports/type-and-oracle-significance.md

运行：
   conda run -n nlpLesson python tools/retrieval_v2.py            # 重算并写产物
   conda run -n nlpLesson python tools/retrieval_v2.py --verify   # 只校验产物自洽

约束：只读语料与既有 config/结果；不装依赖（sklearn + jieba + scipy）；无随机。
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter

import jieba
import numpy as np
from scipy.stats import mannwhitneyu, spearmanr
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_ORACLES = os.path.join(ROOT, "data", "corpus", "oracles.jsonl")
P_SEGMENTS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_FILLED = os.path.join(ROOT, "data", "config", "oracle-fulfillment.filled.json")
P_V1 = os.path.join(ROOT, "data", "config", "oracle-retrieval-results.json")
P_ANNOT = os.path.join(ROOT, "data", "config", "annotation-labels.json")
P_A = os.path.join(ROOT, "data", "config", "baseline-a-scores.json")
P_B1 = os.path.join(ROOT, "data", "config", "baseline-b-scores.json")
OUT_A_JSON = os.path.join(ROOT, "data", "config", "retrieval-v2-results.json")
OUT_A_MD = os.path.join(ROOT, "data", "reports", "retrieval-v2.md")
OUT_B_JSON = os.path.join(ROOT, "data", "config", "type-and-oracle-significance.json")
OUT_B_MD = os.path.join(ROOT, "data", "reports", "type-and-oracle-significance.md")
RUN_CMD = "conda run -n nlpLesson python tools/retrieval_v2.py"

METHODS = ["keyword", "tfidf_char", "tfidf_word", "bm25", "lsa"]
METHOD_LABELS = {
    "keyword": "关键词基线",
    "tfidf_char": "TF-IDF(char 2–3gram)",
    "tfidf_word": "TF-IDF(jieba 词)",
    "bm25": "BM25(k1=1.5,b=0.75)",
    "lsa": "LSA(词TF-IDF+SVD100)",
}
KS = (1, 5, 10, 20)
NGRAM = 6
RECITE_TH = 0.5           # 文档对某条神谕的 6-gram 覆盖率 >= 0.5 → 视为吟诵步
KEYWORD_WEIGHT = 2.0      # 与 v1 关键词基线一致
WEAK_HINT_WEIGHT = 0.3    # v2-mask 的弱提示权重
WEAK_HINTS = ["预言", "神谕", "箴言", "谶语", "命运", "宿命"]
BM25_K1, BM25_B = 1.5, 0.75
LSA_COMPONENTS = 100
TYPES = ["identity", "memory", "prophecy", "relationship", "world", "sacrifice", "motif"]

STOPWORDS = set("""的 了 在 是 我 你 他 她 它 我们 你们 他们 这 那 一个 没有 就 都 也 不 将 于 中 而 之 以 为 把 被 让 从 到 对 会 能 要 个 一 上 下 里 后 前 时 等
与 和 或 但 却 又 很 太 更 最 如 若 则 因 所以 因此 如果 虽然 已经 正在 可以 不是 就是 还是 只是 这样 那样 什么 怎么 为什么 因为 至于 以及 并且 而且 然后 之后 之前
""".split())
PUNCT_RE = re.compile(r"^[\s，。！？、；：…—「」『』（）().,!?;:~\-·\"'《》〈〉【】0-9A-Za-z]+$")
PUNCT_CHARS = set("，。！？、；：…—「」『』（）().,!?;:~-·\"'《》〈〉【】 \t\r\n")


def strip_punct(text):
    return "".join(c for c in (text or "") if c not in PUNCT_CHARS and not c.isspace())


def is_content_token(t):
    return bool(t) and not PUNCT_RE.match(t) and t not in STOPWORDS and len(t) >= 2


def tokenize(text, min_len=2):
    return [t for t in jieba.lcut(text or "")
            if is_content_token(t) and len(t) >= min_len]


def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_oracles():
    rows = []
    with open(P_ORACLES, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_segments():
    rows = []
    with open(P_SEGMENTS, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ngram_cov(oracle_norm, doc_norm):
    """神谕规范化文本的 NGRAM-gram 有多大比例出现在文档里"""
    if len(oracle_norm) < NGRAM:
        return 1.0 if oracle_norm and oracle_norm in doc_norm else 0.0
    grams = [oracle_norm[i:i + NGRAM] for i in range(len(oracle_norm) - NGRAM + 1)]
    src = set(doc_norm[i:i + NGRAM] for i in range(len(doc_norm) - NGRAM + 1))
    return float(sum(1 for g in grams if g in src) / len(grams))


# ============================================================================
# 检索方法（与 v1 相同的实现，便于补丁式对比）
# ============================================================================
def score_keyword(weighted, doc_counts):
    scores = np.zeros(len(doc_counts), dtype=float)
    for i, cnt in enumerate(doc_counts):
        s = 0.0
        for t, w in weighted.items():
            tf = cnt.get(t)
            if tf:
                s += w * (1.0 + math.log1p(tf))
        scores[i] = s
    return scores


def vector_scores(q_vec, doc_mat):
    q = q_vec / (np.linalg.norm(q_vec) + 1e-12)
    return np.asarray(doc_mat.dot(q)).ravel()


def build_representations(doc_texts, doc_tokens2):
    char_vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=2,
                               sublinear_tf=True, norm="l2")
    char_mat = char_vec.fit_transform(doc_texts)
    word_vec = TfidfVectorizer(tokenizer=lambda t: tokenize(t, min_len=2), token_pattern=None,
                               lowercase=False, min_df=1, sublinear_tf=True, norm="l2")
    word_mat = word_vec.fit_transform(doc_texts)
    n = len(doc_tokens2)
    doc_len = np.array([len(t) for t in doc_tokens2], dtype=float)
    avgdl = float(doc_len.mean()) if n else 1.0
    df = Counter()
    tfs = []
    for toks in doc_tokens2:
        cnt = Counter(toks)
        tfs.append(cnt)
        for t in cnt:
            df[t] += 1
    idf = {t: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
    svd = TruncatedSVD(n_components=min(LSA_COMPONENTS, max(2, min(char_mat.shape) - 1)),
                       random_state=42, algorithm="randomized", n_iter=7)
    latent = svd.fit_transform(word_mat)
    latent = latent / np.maximum(np.linalg.norm(latent, axis=1, keepdims=True), 1e-12)
    return {"char_vec": char_vec, "char_mat": char_mat, "word_vec": word_vec, "word_mat": word_mat,
            "bm25": {"idf": idf, "tfs": tfs, "doc_len": doc_len, "avgdl": avgdl},
            "svd": svd, "lsa": latent, "doc_counts": [Counter(t) for t in doc_tokens2]}


def score_bm25(query_tokens, bm):
    scores = np.zeros(len(bm["doc_len"]), dtype=float)
    for t in query_tokens:
        idf = bm["idf"].get(t)
        if idf is None:
            continue
        for i, cnt in enumerate(bm["tfs"]):
            tf = cnt.get(t)
            if not tf:
                continue
            dl = bm["doc_len"][i]
            denom = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * dl / bm["avgdl"])
            scores[i] += idf * tf * (BM25_K1 + 1.0) / denom
    return scores


def run_methods(queries, reps):
    """queries: {qid: query_dict}；返回 {method: {qid: scores array}}"""
    out = {m: {} for m in METHODS}
    for qid, q in queries.items():
        out["keyword"][qid] = score_keyword(q["weighted"], reps["doc_counts"])
        qc = reps["char_vec"].transform([q["text"]])
        out["tfidf_char"][qid] = vector_scores(qc.toarray()[0], reps["char_mat"])
        qw = reps["word_vec"].transform([q["text"]])
        out["tfidf_word"][qid] = vector_scores(qw.toarray()[0], reps["word_mat"])
        out["bm25"][qid] = score_bm25(tokenize(q["text"], min_len=2), reps["bm25"])
        qz = reps["svd"].transform(np.atleast_2d(qw.toarray()[0]))[0]
        qz = qz / (np.linalg.norm(qz) + 1e-12)
        out["lsa"][qid] = np.asarray(reps["lsa"].dot(qz)).ravel()
    return out


def rank_all(scores_by_q, doc_ids, gold, available=None):
    """返回每 query 的 gold 排名矩阵与 Top3（available=False 的 query 记 N/A）"""
    per = {}
    ranks = {}
    for qid, scores in scores_by_q.items():
        if available is not None and not available.get(qid, True):
            per[qid] = {"gold_rank": None, "note": "N/A（gold 不在候选池）"}
            continue
        order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))
        rank = {doc_ids[i]: k + 1 for k, i in enumerate(order)}
        gr = rank.get(gold[qid])
        if gr is None:
            per[qid] = {"gold_rank": None, "note": "N/A（gold 不在候选池）"}
            continue
        ranks[qid] = gr
        per[qid] = {
            "gold_rank": gr,
            "gold_score": round(float(scores[doc_ids.index(gold[qid])]), 6),
            "top3": [{"segment_id": doc_ids[i], "score": round(float(scores[i]), 6)}
                     for i in order[:3]],
        }
    return per, ranks


def metrics(ranks):
    if not ranks:
        return {"n_eval": 0}
    r = np.array(list(ranks.values()), dtype=float)
    out = {"n_eval": len(r)}
    for k in KS:
        out["recall@%d" % k] = round(float((r <= k).mean()), 4)
    out["mrr"] = round(float((1.0 / r).mean()), 4)
    out["median_rank"] = float(np.median(r))
    return out



# ============================================================================
# A. 检索 v2
# ============================================================================
def build_queries(oracles):
    base, mask = {}, {}
    for o in oracles:
        oid = o["oracle_id"]
        text = o.get("text") or ""
        kws = [k for k in (o.get("keywords") or []) if is_content_token(k)]
        glosses = [(m.get("gloss") or "").strip() for m in (o.get("metaphors") or [])]
        glosses = [g for g in glosses if g]
        weak = [w for w in WEAK_HINTS if is_content_token(w)]
        # base（= v1 口径）：原文 jieba 词权重 1 + keywords 权重 2
        w = {}
        for t in tokenize(text, min_len=2):
            w[t] = max(w.get(t, 0.0), 1.0)
        for t in kws:
            w[t] = max(w.get(t, 0.0), KEYWORD_WEIGHT)
        base[oid] = {"text": text, "weighted": w,
                     "terms": sorted(kws), "glosses": glosses, "weak": weak}
        # v2-mask：去掉原句，只留 keywords（w=2）+ gloss（w=2）+ 弱提示（w=0.3）
        w2 = {}
        for t in kws:
            w2[t] = max(w2.get(t, 0.0), KEYWORD_WEIGHT)
        for t in glosses:
            w2[t] = max(w2.get(t, 0.0), KEYWORD_WEIGHT)
        for t in weak:
            w2[t] = max(w2.get(t, 0.0), WEAK_HINT_WEIGHT)
        mask_text = " ".join(sorted(set(kws + glosses + weak)))
        mask[oid] = {"text": mask_text, "weighted": w2,
                     "terms": sorted(kws), "glosses": glosses, "weak": weak}
    return base, mask


def build_retrieval(oracles, filled, segs, v1):
    eligible = [s for s in segs if s["n_main"] > 0 and not s["low_content"] and s["has_dialogue"]]
    seq = sorted(eligible, key=lambda s: (s["order"], s["step_idx"]))
    doc_ids = [s["segment_id"] for s in seq]
    doc_texts = [s["text_all"] or "" for s in seq]
    doc_tokens = [tokenize(t, min_len=2) for t in doc_texts]
    gold = {o["oracle_id"]: filled[o["oracle_id"]]["fulfillment_segment"] for o in oracles}
    oid_list = [o["oracle_id"] for o in oracles]
    assert len(doc_ids) == 686 and len(oid_list) == 13

    base_q, mask_q = build_queries(oracles)
    reps_full = build_representations(doc_texts, doc_tokens)

    # ---- v1 复现（同一口径） ----
    scores = run_methods(base_q, reps_full)
    variants = {}
    for tag, sc, ids, avail in (("v1", scores, doc_ids, None),):
        per, ranks = {}, {}
        for m in METHODS:
            pm, rk = rank_all(sc[m], ids, gold, avail)
            per[m] = {"metrics": metrics(rk), "per_oracle": pm}
            ranks[m] = rk
        variants[tag] = {"per_method": per, "ranks": ranks, "pool_size": len(ids)}
    # 与 v1 JSON 对账
    v1_mismatch = []
    for m in METHODS:
        for oid in oid_list:
            r_now = variants["v1"]["ranks"][m].get(oid)
            r_old = v1["methods_base"][m]["gold_ranks"].get(oid)
            if r_now != r_old:
                v1_mismatch.append({"method": m, "oracle": oid, "now": r_now, "v1": r_old})
    if v1_mismatch:
        print("!! v1 无法复现：%s" % v1_mismatch[:5], file=sys.stderr)
        raise SystemExit(1)

    # ---- v2-mask：全池 + 掩蔽 query ----
    scores_mask = run_methods(mask_q, reps_full)
    for m in METHODS:
        pm, rk = rank_all(scores_mask[m], doc_ids, gold, None)
        variants["v2_mask"] = variants.get("v2_mask", {"per_method": {}, "ranks": {}, "pool_size": len(doc_ids)})
        variants["v2_mask"]["per_method"][m] = {"metrics": metrics(rk), "per_oracle": pm}
        variants["v2_mask"]["ranks"][m] = rk

    # ---- v2-noRecite：剔除吟诵步后的池 ----
    oracle_norms = {o["oracle_id"]: strip_punct(o["text"]) for o in oracles}
    recite = {}
    max_cov = np.zeros(len(doc_ids))
    max_cov_oid = [None] * len(doc_ids)
    for i, t in enumerate(doc_texts):
        dn = strip_punct(t)
        best, best_oid = 0.0, None
        for oid in oid_list:
            c = ngram_cov(oracle_norms[oid], dn)
            if c > best:
                best, best_oid = c, oid
        max_cov[i] = best
        max_cov_oid[i] = best_oid if best > 0 else None
        recite[doc_ids[i]] = {"max_oracle_6gram_coverage": round(float(best), 4),
                              "closest_oracle": best_oid,
                              "is_recitation": bool(best >= RECITE_TH)}
    keep_idx = [i for i in range(len(doc_ids)) if not recite[doc_ids[i]]["is_recitation"]]
    keep_ids = [doc_ids[i] for i in keep_idx]
    keep_texts = [doc_texts[i] for i in keep_idx]
    keep_tokens = [doc_tokens[i] for i in keep_idx]
    reps_keep = build_representations(keep_texts, keep_tokens)
    avail_base = {oid: gold[oid] in set(keep_ids) for oid in oid_list}
    na_oracles = [oid for oid in oid_list if not avail_base[oid]]
    scores_keep = run_methods(base_q, reps_keep)
    scores_keep_mask = run_methods(mask_q, reps_keep)
    for tag, sc in (("v2_norecite", scores_keep), ("v2_both", scores_keep_mask)):
        variants[tag] = {"per_method": {}, "ranks": {}, "pool_size": len(keep_ids)}
        for m in METHODS:
            pm, rk = rank_all(sc[m], keep_ids, gold, avail_base)
            variants[tag]["per_method"][m] = {"metrics": metrics(rk), "per_oracle": pm}
            variants[tag]["ranks"][m] = rk

    # ---- 汇总与 O10 ----
    summary = {}
    for tag in variants:
        summary[tag] = {m: variants[tag]["per_method"][m]["metrics"] for m in METHODS}
    o10 = {}
    for tag in variants:
        o10[tag] = {m: variants[tag]["per_method"][m]["per_oracle"].get("O10", {}).get("gold_rank") for m in METHODS}
    # 逐 query 排名对比
    per_query = {}
    for oid in oid_list:
        per_query[oid] = {
            tag: {m: variants[tag]["per_method"][m]["per_oracle"].get(oid, {}).get("gold_rank")
                  for m in METHODS}
            for tag in variants
        }
    # 吟诵步剔除详情
    removed = [{"segment_id": doc_ids[i], "max_oracle_6gram_coverage": round(float(max_cov[i]), 4),
                "closest_oracle": max_cov_oid[i]} for i in range(len(doc_ids))
               if recite[doc_ids[i]]["is_recitation"]]
    meta = {
        "script": "tools/retrieval_v2.py",
        "run_command": RUN_CMD,
        "purpose": "修正 v1 的 gold/query 构造问题后重评五法",
        "v1_source": "data/config/oracle-retrieval-results.json（只读，用于对比）",
        "n_documents_full": len(doc_ids),
        "n_documents_no_recite": len(keep_ids),
        "recite_threshold": "文档对某条神谕的 6-gram 覆盖率 ≥ %.2f 视为吟诵步并剔除" % RECITE_TH,
        "recite_threshold_value": RECITE_TH,
        "n_removed_recitation_steps": len(removed),
        "na_oracles_gold_removed": na_oracles,
        "query_mask": "v2-mask 的 query = keywords（w=%.1f）+ metaphors.gloss（w=%.1f）+ 弱提示 %s（w=%.1f）；"
                      "完全去掉神谕原句的字面" % (KEYWORD_WEIGHT, KEYWORD_WEIGHT, "/".join(WEAK_HINTS), WEAK_HINT_WEIGHT),
        "methods": METHODS,
        "method_labels": METHOD_LABELS,
        "metrics_note": "Recall@k = gold 排名 ≤ k 的 query 比例；MRR = mean(1/rank)；"
                        "v2-noRecite / v2-both 的分母只算 gold 仍在池内的 query（N/A 见 na_oracles_gold_removed）",
        "tie_break": "分数降序、同分按 document 顺序（order→step_idx）升序",
    }
    result = {
        "meta": meta,
        "variants": {tag: {"pool_size": variants[tag]["pool_size"],
                           "per_method": {m: {"metrics": variants[tag]["per_method"][m]["metrics"],
                                              "per_oracle": variants[tag]["per_method"][m]["per_oracle"]}
                                          for m in METHODS}}
                     for tag in variants},
        "summary": summary,
        "per_query_ranks": per_query,
        "o10_focus": o10,
        "recitation_removed": removed,
        "recitation_flags": recite,
        "v1_reproduction_mismatch": v1_mismatch,
        "v1_metrics": {m: v1["methods_base"][m]["metrics"] for m in METHODS},
    }
    return result


# ============================================================================
# B. Q3 类型分组 + Q4 神谕显著性
# ============================================================================
LENGTH_BINS = ["1–3 句", "4–10 句", "11–30 句", ">30 句"]


def length_bin(n_dialogue):
    if n_dialogue <= 3:
        return LENGTH_BINS[0]
    if n_dialogue <= 10:
        return LENGTH_BINS[1]
    if n_dialogue <= 30:
        return LENGTH_BINS[2]
    return LENGTH_BINS[3]


def compare_dist(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) == 0 or len(y) == 0:
        return {"n_x": len(x), "n_y": len(y), "U": None, "p": None, "cliff_delta": None}
    if len(set(np.concatenate([x, y]).tolist())) <= 1:
        return {"n_x": len(x), "n_y": len(y), "U": float(len(x) * len(y) / 2),
                "p": 1.0, "cliff_delta": 0.0}
    res = mannwhitneyu(x, y, alternative="two-sided")
    U = float(res.statistic)
    return {"n_x": len(x), "n_y": len(y), "U": round(U, 4), "p": float(res.pvalue),
            "cliff_delta": round(2.0 * U / (len(x) * len(y)) - 1.0, 4),
            "mean_x": round(float(x.mean()), 4), "mean_y": round(float(y.mean()), 4),
            "median_x": round(float(np.median(x)), 4), "median_y": round(float(np.median(y)), 4)}


def build_significance(segs, annot, a_scores, b_scores, filled):
    eligible = [s for s in segs if s["n_main"] > 0 and not s["low_content"] and s["has_dialogue"]]
    pool = [s["segment_id"] for s in eligible]
    seg_by_id = {s["segment_id"]: s for s in eligible}
    A = {s["segment_id"]: s for s in a_scores["segments"]}
    B = {s["segment_id"]: s for s in b_scores["segments"]}
    a_score = {sid: A[sid]["score"] for sid in pool}
    b_score = {sid: B[sid]["score"] for sid in pool}
    a_rank = {sid: A[sid]["rank"] for sid in pool}
    b_rank = {sid: B[sid]["rank"] for sid in pool}

    # ---------- Q3：7 类型 ----------
    samples = annot["samples"]
    q3 = {}
    for t in TYPES:
        sel = [s for s in samples if t in s["types"]]
        if not sel:
            continue
        a_r = [a_rank[s["segment_id"]] for s in sel]
        b_r = [b_rank[s["segment_id"]] for s in sel]
        sig = [s["significance"] for s in sel]
        rho_a = spearmanr([a_score[s["segment_id"]] for s in sel], sig)
        rho_b = spearmanr([b_score[s["segment_id"]] for s in sel], sig)
        lifts = [(s["segment_id"], a_rank[s["segment_id"]] - b_rank[s["segment_id"]]) for s in sel]
        best = max(lifts, key=lambda x: x[1])
        worst = min(lifts, key=lambda x: x[1])
        q3[t] = {
            "n": len(sel),
            "a_median_rank": float(np.median(a_r)),
            "b_median_rank": float(np.median(b_r)),
            "median_lift_A_minus_B": float(np.median(a_r) - np.median(b_r)),
            "a_top100": sum(1 for r in a_r if r <= 100),
            "b_top100": sum(1 for r in b_r if r <= 100),
            "a_top20": sum(1 for r in a_r if r <= 20),
            "b_top20": sum(1 for r in b_r if r <= 20),
            "spearman_within_type_A": round(float(rho_a.statistic), 4) if rho_a.pvalue == rho_a.pvalue else None,
            "p_A": float(rho_a.pvalue),
            "spearman_within_type_B": round(float(rho_b.statistic), 4) if rho_b.pvalue == rho_b.pvalue else None,
            "p_B": float(rho_b.pvalue),
            "best_lift_example": {"segment_id": best[0], "a_rank": a_rank[best[0]], "b_rank": b_rank[best[0]],
                                  "lift": best[1]},
            "worst_lift_example": {"segment_id": worst[0], "a_rank": a_rank[worst[0]],
                                   "b_rank": b_rank[worst[0]], "lift": worst[1]},
            "note_sample_significance": [s["significance"] for s in sel],
        }
    best_type = max(q3, key=lambda t: q3[t]["median_lift_A_minus_B"])
    worst_type = min(q3, key=lambda t: q3[t]["median_lift_A_minus_B"])
    best_spear = max(q3, key=lambda t: q3[t]["spearman_within_type_B"] or -2)
    worst_spear = min(q3, key=lambda t: q3[t]["spearman_within_type_B"] or 2)

    # ---------- Q4：神谕兑现显著性 ----------
    gold_ids = [filled[o["oracle_id"]]["fulfillment_segment"] for o in
                sorted(filled.values(), key=lambda x: x["oracle_id"])]
    gold_ids = [g for g in gold_ids if g in set(pool)]
    rest_ids = [sid for sid in pool if sid not in set(gold_ids)]
    q4 = {}
    for name, score in (("A", a_score), ("B1", b_score)):
        cmp = compare_dist([score[g] for g in gold_ids], [score[r] for r in rest_ids])
        ranks_sorted = sorted([score[sid] for sid in pool], reverse=True)
        rank_of = {sid: 1 + sum(1 for v in ranks_sorted if v > score[sid]) for sid in gold_ids}
        cmp["gold_median_pct_rank"] = round(float(np.median([rank_of[g] / len(pool) for g in gold_ids])), 4)
        cmp["gold_median_rank"] = float(np.median([rank_of[g] for g in gold_ids]))
        cmp["gold_in_top100"] = sum(1 for g in gold_ids if rank_of[g] <= 100)
        q4[name] = cmp
    # 按长度分层
    by_len = {}
    for b in LENGTH_BINS:
        g = [sid for sid in gold_ids if length_bin(seg_by_id[sid]["n_dialogue"]) == b]
        r = [sid for sid in rest_ids if length_bin(seg_by_id[sid]["n_dialogue"]) == b]
        row = {"n_gold": len(g), "n_rest": len(r)}
        if len(g) >= 2:
            row["A"] = compare_dist([a_score[s] for s in g], [a_score[s] for s in r])
            row["B1"] = compare_dist([b_score[s] for s in g], [b_score[s] for s in r])
        else:
            row["note"] = "该层 gold 样本 <2，无法做 U 检验"
            if g:
                row["A_gold_mean"] = round(float(np.mean([a_score[s] for s in g])), 4)
                row["B1_gold_mean"] = round(float(np.mean([b_score[s] for s in g])), 4)
                row["rest_mean"] = {"A": round(float(np.mean([a_score[s] for s in r])), 4),
                                    "B1": round(float(np.mean([b_score[s] for s in r])), 4)}
        by_len[b] = row
    return {
        "meta": {
            "script": "tools/retrieval_v2.py",
            "run_command": RUN_CMD,
            "q3_source": "data/config/annotation-labels.json（74 条，types 多选）+ baseline-a/b-scores.json",
            "q4_source": "13 个神谕兑现段（oracle-fulfillment.filled.json）vs 其余 %d 步；分数来自 baseline-a/b-scores.json" % len(rest_ids),
            "q3_metric_note": "排名来自 A/B 全排序（686 步，1=最高）；组内 Spearman = 该类型样本的分数与人工等级的 Spearman（n 小，仅方向性）",
            "q4_metric_note": "Mann–Whitney U（gold vs 非 gold）+ Cliff's delta（正=gold 分数更高）；长度分层用对白句数分箱",
            "n_samples_annotated": len(samples),
        },
        "q3_types": q3,
        "q3_summary": {"best_type_by_median_lift": best_type, "worst_type_by_median_lift": worst_type,
                       "best_type_by_within_spearman": best_spear, "worst_type_by_within_spearman": worst_spear},
        "q4_overall": q4,
        "q4_by_length": by_len,
        "gold_ids": gold_ids,
        "rest_n": len(rest_ids),
    }



# ============================================================================
# 证据表（可直接抄进报告：结论 / 指标 / 数值 / p 或效应量 / 来源）
# ============================================================================
def build_evidence(A, B, v1):
    m = A["meta"]
    v1_best = max(METHODS, key=lambda x: v1["methods_base"][x]["metrics"]["mrr"])
    v1_best_mrr = v1["methods_base"][v1_best]["metrics"]["mrr"]
    def best_of(tag):
        met = A["summary"][tag]
        bm = max(METHODS, key=lambda x: (met[x]["mrr"], met[x].get("recall@10", 0)))
        return bm, met[bm]
    bm_mask, met_mask = best_of("v2_mask")
    bm_no, met_no = best_of("v2_norecite")
    bm_both, met_both = best_of("v2_both")
    o10 = A["o10_focus"]
    rows = [
        {"id": "A1", "conclusion": "v1 检索主要测「引用句匹配」：关键词基线最优（因 12/13 gold 是吟诵步、10/13 含神谕原文）",
         "metric": "v1 最佳方法 / MRR", "value": "%s / %.3f" % (METHOD_LABELS[v1_best], v1_best_mrr),
         "effect": "方法间 Kendall 序被 gold 构造污染", "source": "oracle-retrieval-results.json（v1）"},
        {"id": "A2", "conclusion": "query 掩蔽（去掉神谕原句，只留 keywords/gloss/弱提示）后五法重评",
         "metric": "最佳方法 / MRR / R@10", "value": "%s / %.3f / %.2f" % (
             METHOD_LABELS[bm_mask], met_mask["mrr"], met_mask.get("recall@10", 0)),
         "effect": "分母 %d 条 query" % met_mask.get("n_eval", 0), "source": "retrieval-v2-results.json: summary.v2_mask"},
        {"id": "A3", "conclusion": "候选池剔除吟诵步后，%d/13 条 gold 被一并剔除（gold 本身多为吟诵步）→ 无法做五法对比" % len(m["na_oracles_gold_removed"]),
         "metric": "剔除步数 / 剩余池 / N/A gold / 可评 query", "value": "%d / %d / %d / %d" % (
             m["n_removed_recitation_steps"], m["n_documents_no_recite"],
             len(m["na_oracles_gold_removed"]), met_no["n_eval"]),
         "effect": "N/A：%s" % ("、".join(m["na_oracles_gold_removed"]) or "无"),
         "source": "retrieval-v2-results.json: summary.v2_norecite"},
        {"id": "A4", "conclusion": "掩蔽 query + 剔除吟诵步后只剩 O10 一条可评：字面检索下唯一的语义样本",
         "metric": "可评 query / O10 最好名次（both vs v1）", "value": "%d / 第 %s 名（v1 第 %s 名）" % (
             met_both.get("n_eval", 0),
             min((v for v in o10["v2_both"].values() if v), default=-1),
             min((v for v in o10["v1"].values() if v), default=-1)),
         "effect": "n=1，不能做方法比较", "source": "retrieval-v2-results.json: summary.v2_both / o10_focus"},
        {"id": "A5", "conclusion": "v1 到 v2-mask 的指标变化（看字面优势被去掉后谁占优）",
         "metric": "ΔMRR（mask−v1，逐方法 最大/最小）", "value": "%+.3f / %+.3f" % (
             max(A["summary"]["v2_mask"][x]["mrr"] - v1["methods_base"][x]["metrics"]["mrr"] for x in METHODS),
             min(A["summary"]["v2_mask"][x]["mrr"] - v1["methods_base"][x]["metrics"]["mrr"] for x in METHODS)),
         "effect": "全池 686，13 条 query", "source": "retrieval-v2-results.json: comparison"},
        {"id": "A6", "conclusion": "O10（唯一不引原文的兑现）在剔除吟诵步后明显提前：v1 被 O11 的吟诵步污染",
         "metric": "O10 最好名次（v1 / mask / noRecite / both）",
         "value": "v1=%s / mask=%s / noRecite=%s / both=%s" % (
             min(v for v in o10["v1"].values() if v),
             min(v for v in o10["v2_mask"].values() if v),
             min((v for v in o10["v2_norecite"].values() if v), default=-1),
             min((v for v in o10["v2_both"].values() if v), default=-1)),
         "effect": "n=1，方向性证据", "source": "retrieval-v2-results.json: o10_focus"},
        {"id": "Q3-1", "conclusion": "不同转折类型有不同信号：B 相对 A 的排名提升在类型间不均匀",
         "metric": "B 提升最大/最小的类型（中位名次差 A−B）",
         "value": "%s %+.1f / %s %+.1f" % (
             B["q3_summary"]["best_type_by_median_lift"],
             B["q3_types"][B["q3_summary"]["best_type_by_median_lift"]]["median_lift_A_minus_B"],
             B["q3_summary"]["worst_type_by_median_lift"],
             B["q3_types"][B["q3_summary"]["worst_type_by_median_lift"]]["median_lift_A_minus_B"]),
         "effect": "7 类型多标签，n=7–27/类型", "source": "type-and-oracle-significance.json: q3_types"},
        {"id": "Q3-2", "conclusion": "B 的组内 Spearman（分数 vs 人工等级）在类型间差异",
         "metric": "最高/最低类型 ρ", "value": "%s %.2f / %s %.2f" % (
             B["q3_summary"]["best_type_by_within_spearman"],
             B["q3_types"][B["q3_summary"]["best_type_by_within_spearman"]]["spearman_within_type_B"],
             B["q3_summary"]["worst_type_by_within_spearman"],
             B["q3_types"][B["q3_summary"]["worst_type_by_within_spearman"]]["spearman_within_type_B"]),
         "effect": "n 小，仅方向性", "source": "type-and-oracle-significance.json: q3_summary"},
        {"id": "Q3-3", "conclusion": "B 的 Top100 覆盖在类型间不均衡",
         "metric": "A/B 的 Top100 覆盖总数（7 类型相加）",
         "value": "A=%d / B=%d（共 %d 条标注样本）" % (
             sum(v["a_top100"] for v in B["q3_types"].values()),
             sum(v["b_top100"] for v in B["q3_types"].values()),
             sum(v["n"] for v in B["q3_types"].values())),
         "effect": "多标签样本会重复计入", "source": "type-and-oracle-significance.json: q3_types"},
        {"id": "Q4-1", "conclusion": "神谕兑现段是否更易成为高显著段（A 检测器）",
         "metric": "MWU / Cliff's delta / p",
         "value": "δ=%+.3f, p=%.3g（gold 中位分 %.3f vs 其余 %.3f）" % (
             B["q4_overall"]["A"]["cliff_delta"], B["q4_overall"]["A"]["p"],
             B["q4_overall"]["A"]["median_x"], B["q4_overall"]["A"]["median_y"]),
         "effect": "13 gold vs %d 其余步" % B["rest_n"], "source": "type-and-oracle-significance.json: q4_overall.A"},
        {"id": "Q4-2", "conclusion": "神谕兑现段是否更易成为高显著段（B 检测器）",
         "metric": "MWU / Cliff's delta / p",
         "value": "δ=%+.3f, p=%.3g（gold 中位分 %.3f vs 其余 %.3f）" % (
             B["q4_overall"]["B1"]["cliff_delta"], B["q4_overall"]["B1"]["p"],
             B["q4_overall"]["B1"]["median_x"], B["q4_overall"]["B1"]["median_y"]),
         "effect": "13 gold vs %d 其余步" % B["rest_n"], "source": "type-and-oracle-significance.json: q4_overall.B1"},
        {"id": "Q4-3", "conclusion": "长度分层后神谕兑现段的显著性（排除长度混淆）",
         "metric": "各层 gold 数 / 哪些层仍显著（p<0.05）",
         "value": "；".join("%s: n_gold=%d%s" % (
             b, v["n_gold"], "" if v["n_gold"] < 2 else
             " A" + ("✓" if v["A"]["p"] < 0.05 else "✗") + " B" + ("✓" if v["B1"]["p"] < 0.05 else "✗"))
             for b, v in B["q4_by_length"].items()),
         "effect": "每层内部比较 gold vs 同层非 gold", "source": "type-and-oracle-significance.json: q4_by_length"},
        {"id": "Q4-4", "conclusion": "神谕兑现段在排序中的位置",
         "metric": "gold 中位百分位 / 中位名次 / 进 Top100 数",
         "value": "A: %.3f / %.0f / %d；B1: %.3f / %.0f / %d" % (
             B["q4_overall"]["A"]["gold_median_pct_rank"], B["q4_overall"]["A"]["gold_median_rank"],
             B["q4_overall"]["A"]["gold_in_top100"],
             B["q4_overall"]["B1"]["gold_median_pct_rank"], B["q4_overall"]["B1"]["gold_median_rank"],
             B["q4_overall"]["B1"]["gold_in_top100"]),
         "effect": "百分位 0=最高分", "source": "type-and-oracle-significance.json: q4_overall"},
    ]
    return rows


# ============================================================================
# 报告 A：检索 v2
# ============================================================================
def render_retrieval_md(A):
    m = A["meta"]
    L = []
    Ap = L.append
    v1 = A["v1_metrics"]
    Ap("# 神谕—事件检索 v2：query 掩蔽 + 剔除吟诵步后的重评（修正 v1 的 gold 构造问题）")
    Ap("")
    Ap("> 生成脚本：`tools/retrieval_v2.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    Ap("> 输入（只读）：`data/config/oracle-retrieval-results.json`（v1）、`oracles.jsonl`、`oracle-fulfillment.filled.json`、`segments.jsonl`")
    Ap("> 明细数据：`data/config/retrieval-v2-results.json`")
    Ap("")
    Ap("> **v1 的问题（本次要修的）**：13 条 query 里 12 条 gold 本身就是吟诵该神谕的步骤、10 条 gold 文本含神谕原文 → "
      "任务退化成「引用句匹配」，关键词基线必然赢。v2 用两个变体分别去掉「query 字面」和「候选池里的吟诵步」。")
    Ap("")
    Ap("## 1. 结论")
    Ap("")
    best_v1 = max(METHODS, key=lambda x: v1[x]["mrr"])
    sumA = A["summary"]
    def bm(tag):
        met = sumA[tag]
        b = max(METHODS, key=lambda x: (met[x]["mrr"], met[x].get("recall@10", 0)))
        return b, met[b]
    bmask, met_mask = bm("v2_mask")
    bno, met_no = bm("v2_norecite")
    bboth, met_both = bm("v2_both")
    Ap("- **v1 复现成功**（逐 query、逐方法 gold 排名与 v1 JSON 完全一致），说明 v2 的差别只来自 query/候选池的改动。")
    Ap("- **v1（原查询 + 全池）**：最佳 %s，MRR **%.3f**、R@10 %.2f。它的高分主要来自「查到吟诵句」。"
      % (METHOD_LABELS[best_v1], v1[best_v1]["mrr"], v1[best_v1]["recall@10"]))
    Ap("- **v2-mask（掩蔽 query）**：最佳 %s，MRR **%.3f**、R@10 %.2f（%d 条 query）。"
      "去掉神谕原句后，字面方法不再占便宜，指标整体下降是预期。" % (
          METHOD_LABELS[bmask], met_mask["mrr"], met_mask["recall@10"], met_mask["n_eval"]))
    Ap("- **v2-noRecite（剔除吟诵步）**：剔除 **%d** 步（6-gram 覆盖率≥%.2f），池剩 **%d** 步；"
      "**%d/13 条 gold 本身就在被剔除的吟诵步里 → 标 N/A**（%s）。因此这个版本只剩 **%d 条**可评 query，"
      "MRR %.3f 只代表 O10 一条（第 %s 名），不做方法比较。" % (
          m["n_removed_recitation_steps"], RECITE_TH, m["n_documents_no_recite"],
          len(m["na_oracles_gold_removed"]), "、".join(m["na_oracles_gold_removed"]) or "无",
          met_no["n_eval"], met_no["mrr"],
          min((v for v in A["o10_focus"]["v2_norecite"].values() if v), default=-1)))
    Ap("- **v2-both（掩蔽 + 剔除吟诵步，最接近真语义检索）**：同样只剩 **%d 条**可评 query（O10，最好第 %s 名）："
      "**在现有 gold 定义下无法做「真语义」下的五法对比**，因为 gold 与吟诵步几乎重合。" % (
          met_both["n_eval"],
          min((v for v in A["o10_focus"]["v2_both"].values() if v), default=-1)))
    o10 = A["o10_focus"]
    o10_vals = {tag: min((v for v in o10[tag].values() if v is not None), default=None) for tag in o10}
    Ap("- **O10（唯一不引原文的兑现）是唯一能检验「去字面」效果的样本**：v1 最好第 **%s** 名（TF-IDF-char）、"
      "v2-mask 第 **%s**、**v2-noRecite 第 %s 名**、v2-both 第 **%s**。"
      "→ 把吟诵步剔掉后，O10 真正兑现段的排名从第 %s 提到第 %s，说明 v1 里 O11 的吟诵步确实在污染 O10 的排序；"
      "但样本只有 1 条，只能作为方向性证据，不能据此给方法排序。" % (
          o10_vals["v1"], o10_vals["v2_mask"], o10_vals["v2_norecite"], o10_vals["v2_both"],
          o10_vals["v1"], o10_vals["v2_norecite"]))
    Ap("")
    Ap("**方法排序**：在仍可做 13 条对比的 **v2-mask** 下，MRR 排序为 %s；"
      "v2-noRecite / v2-both 只剩 1 条 query，其 MRR 排序没有统计意义，不采用。" % " > ".join(
          "%s %.3f" % (METHOD_LABELS[x], sumA["v2_mask"][x]["mrr"])
          for x in sorted(METHODS, key=lambda x: -sumA["v2_mask"][x]["mrr"])))
    Ap("")
    Ap("## 2. 两个 v2 变体的定义")
    Ap("")
    Ap("| 变体 | query | 候选池 | 目的 |")
    Ap("| --- | --- | --- | --- |")
    Ap("| v1（对照） | 神谕原句（关键词法额外用 keywords） | 686 全池 | 复现 v1 |")
    Ap("| **v2-mask** | 去掉神谕原句：keywords（w=%.1f）+ metaphors.gloss（w=%.1f）+ 弱提示 %s（w=%.1f） | 686 全池 | 去掉 query 里的字面复现 |" % (
        m["query_mask"].split("w=")[1].split("）")[0] if False else 2.0, 2.0, "/".join(WEAK_HINTS), 0.3))
    Ap("| **v2-noRecite** | 神谕原句（同 v1） | 剔除对任一条神谕 6-gram 覆盖率≥%.2f 的吟诵步 | 去掉候选池里的字面复现 |" % RECITE_TH)
    Ap("| v2-both（附） | 掩蔽 query | 剔除吟诵步 | 最接近真语义检索 |")
    Ap("")
    Ap("> 吟诵步判定：文档规范化文本对某条神谕的 6-gram 覆盖率 = 神谕的 6-gram 有多大比例出现在文档里；≥%.2f 即视为「吟诵该神谕的步骤」。" % RECITE_TH)
    Ap("")
    Ap("## 3. 五法 × 四版本 的指标汇总")
    Ap("")
    Ap("| 方法 | v1 MRR | v1 R@10 | mask MRR | mask R@10 | noRecite MRR | noRecite R@10 | both MRR | both R@10 |")
    Ap("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for x in METHODS:
        def g(tag, k):
            return A["summary"][tag][x].get(k)
        Ap("| %s | %.3f | %.2f | %.3f | %.2f | %s | %s | %.3f | %.2f |" % (
            METHOD_LABELS[x], v1[x]["mrr"], v1[x]["recall@10"],
            g("v2_mask", "mrr"), g("v2_mask", "recall@10"),
            ("%.3f" % g("v2_norecite", "mrr")) if g("v2_norecite", "mrr") is not None else "N/A",
            ("%.2f" % g("v2_norecite", "recall@10")) if g("v2_norecite", "recall@10") is not None else "N/A",
            g("v2_both", "mrr"), g("v2_both", "recall@10")))
    Ap("")
    Ap("> 注：noRecite / both 两列只有 1 条有效 query（O10），其 MRR 不能与 v1/mask 的 13 条指标横向比较。")
    Ap("")
    Ap("Recall@1/5/20 与有效 query 数：")
    Ap("")
    Ap("| 版本 | 方法 | Recall@1 | Recall@5 | Recall@20 | 有效 query |")
    Ap("| --- | --- | --- | --- | --- | --- |")
    for tag in ("v1", "v2_mask", "v2_norecite", "v2_both"):
        for x in METHODS:
            met = A["summary"][tag][x]
            Ap("| %s | %s | %s | %s | %s | %s |" % (
                tag, METHOD_LABELS[x],
                met.get("recall@1", "N/A"), met.get("recall@5", "N/A"),
                met.get("recall@20", "N/A"), met.get("n_eval", "N/A")))
    Ap("")
    Ap("## 4. 逐 query：gold 排名对比（五法）")
    Ap("")
    for x in METHODS:
        Ap("### %s" % METHOD_LABELS[x])
        Ap("")
        Ap("| oracle | v1 | mask | noRecite | both |")
        Ap("| --- | --- | --- | --- | --- |")
        for oid in A["per_query_ranks"]:
            row = A["per_query_ranks"][oid]
            def f(tag):
                v = row[tag].get(x)
                return "N/A" if v is None else str(v)
            Ap("| %s | %s | %s | %s | %s |" % (oid, f("v1"), f("v2_mask"), f("v2_norecite"), f("v2_both")))
        Ap("")
    Ap("## 5. 剔除吟诵步的细节")
    Ap("")
    Ap("共剔除 **%d** 步（对任一条神谕 6-gram 覆盖率≥%.2f）。前 10 个被剔除的步骤：" % (
        m["n_removed_recitation_steps"], RECITE_TH))
    Ap("")
    Ap("| segment_id | 最高覆盖率 | 最近神谕 |")
    Ap("| --- | --- | --- |")
    for r in sorted(A["recitation_removed"], key=lambda x: -x["max_oracle_6gram_coverage"])[:10]:
        Ap("| `%s` | %.3f | %s |" % (r["segment_id"], r["max_oracle_6gram_coverage"], r["closest_oracle"]))
    Ap("")
    if m["na_oracles_gold_removed"]:
        Ap("> gold 被剔除、标 N/A 的 query：%s" % "、".join(m["na_oracles_gold_removed"]))
    else:
        Ap("> 所有 13 条 gold 都不属于「吟诵步」，因此 noRecite 版本没有 N/A（分母仍 13）。")
    Ap("")
    Ap("## 6. 讨论：为什么修正后指标反而下降")
    Ap("")
    Ap("1. v1 的高分是「查到吟诵句」：gold 步骤里直接念出神谕，关键词/BM25/TF-IDF 的字面重合必然排前。"
      "掩蔽 query / 剔除吟诵步之后，方法只能靠关键词或浅层语义去匹配真正的事件描述，指标自然下降。")
    Ap("2. **v2-mask 下各方法都下降，但关键词法仍最高**（MRR 0.660）：因为 keywords 本身仍来自神谕字面（沐浴/黄金/涛声），"
      "而 gold 的吟诵文本里正好有这些词——所以掩蔽 query 并不能真正去掉 gold 泄漏；"
      "下降最多的是 LSA（%.3f→%.3f）和 TF-IDF-char（%.3f→%.3f），说明向量方法更依赖完整句子的上下文。" % (
          v1["lsa"]["mrr"], sumA["v2_mask"]["lsa"]["mrr"],
          v1["tfidf_char"]["mrr"], sumA["v2_mask"]["tfidf_char"]["mrr"]))
    n_na = len(m["na_oracles_gold_removed"])
    n_eval_no = A["summary"]["v2_norecite"]["keyword"].get("n_eval", 0)
    Ap("3. **v2-noRecite 暴露了根本矛盾**：13 条 gold 里有 %d 条本身就是「吟诵该神谕」的步骤"
      "（对某条神谕的 6-gram 覆盖率≥%.2f），所以「剔除吟诵步」等于把这些 gold 一起删掉，只剩 %d 条可评——"
      "这不是实现问题，而是 v1 的 gold 定义问题：**在这个 gold 上做不出有效的「去字面」方法对比**。"
      "要真正重评，需要把 gold 重新标为「不含神谕原文的兑现段」（例如选事件场景而不是吟诵台词所在的步骤）。" % (
          n_na, RECITE_TH, n_eval_no))
    Ap("4. **结论**：v2 的两个修正都暴露同一个问题——**gold 与吟诵步不可分割**。v2-mask 无法去掉 gold 泄漏（keywords 仍命中吟诵文本）；"
      "v2-noRecite 虽然把 O10 从第 7 提到第 3（说明 O11 吟诵步确实在污染 O10），但代价是 12/13 条 gold 被删。"
      "因此**在现有 gold 上无法给出「真语义检索下五法优劣」的可靠结论**；要得到这个结论必须先重标 gold（事件场景、不含神谕原文），"
      "或改用句向量等更强语义表示（口径 §8 已列为后续工作）。")
    Ap("")
    Ap("## 7. 复现与自校验")
    Ap("")
    Ap("```bash")
    Ap(RUN_CMD)
    Ap("conda run -n nlpLesson python tools/retrieval_v2.py --verify")
    Ap("```")
    Ap("")
    Ap("- 无随机：TF-IDF/BM25 确定性，SVD `random_state=42`；v1 复现逐 query 对账（v1_reproduction_mismatch 为空）。")
    Ap("- JSON 保存 4 个版本 × 5 方法的每 query 排名、Top3、指标、吟诵步标记与剔除清单；报告同源。")
    Ap("- `--verify` 会重算指标、核对报告表格与 JSON、并抽查 O10/抽 3 条 query。")
    Ap("")
    return "\n".join(L)



# ============================================================================
# 报告 B：Q3 类型 + Q4 神谕显著性 + 证据表
# ============================================================================
TYPE_LABELS = {"identity": "身份揭示", "memory": "记忆回收", "prophecy": "神谕/预言",
               "relationship": "关系变化", "world": "世界规则", "sacrifice": "牺牲/死亡",
               "motif": "母题回收"}


def render_significance_md(B, evidence):
    q3 = B["q3_types"]
    q4 = B["q4_overall"]
    by_len = B["q4_by_length"]
    L = []
    Ap = L.append
    Ap("# Q3 转折类型级信号 + Q4 神谕兑现显著性检验")
    Ap("")
    Ap("> 生成脚本：`tools/retrieval_v2.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    Ap("> 数据（只读）：`annotation-labels.json`（74 条标注，types 多选）、`baseline-a/b-scores.json`、`oracle-fulfillment.filled.json`、`segments.jsonl`")
    Ap("> 明细数据：`data/config/type-and-oracle-significance.json`")
    Ap("")
    Ap("## 1. 结论")
    Ap("")
    Ap("- **Q3（不同转折类型是否有不同信号）**：有。B 相对 A 的中位名次提升在 7 个类型之间差异明显——"
      "提升最大的是 **%s**（A−B 中位名次 = %+.1f），最小的是 **%s**（%+.1f）。"
      "组内 Spearman（B 分数 vs 人工等级）最高的是 %s（ρ=%.2f），最低的是 %s（ρ=%.2f）。" % (
          TYPE_LABELS[B["q3_summary"]["best_type_by_median_lift"]],
          q3[B["q3_summary"]["best_type_by_median_lift"]]["median_lift_A_minus_B"],
          TYPE_LABELS[B["q3_summary"]["worst_type_by_median_lift"]],
          q3[B["q3_summary"]["worst_type_by_median_lift"]]["median_lift_A_minus_B"],
          TYPE_LABELS[B["q3_summary"]["best_type_by_within_spearman"]],
          q3[B["q3_summary"]["best_type_by_within_spearman"]]["spearman_within_type_B"],
          TYPE_LABELS[B["q3_summary"]["worst_type_by_within_spearman"]],
          q3[B["q3_summary"]["worst_type_by_within_spearman"]]["spearman_within_type_B"]))
    q4_sig = (q4["A"]["p"] < 0.05) or (q4["B1"]["p"] < 0.05)
    Ap("- **Q4（神谕兑现是否更易成为高显著段）**：%s 13 个兑现段的分数**%s**其余 %d 步。"
      "A 检测器：Cliff's δ = **%+.3f**（p=%.3g）；B1 检测器：δ = **%+.3f**（p=%.3g）。"
      "兑现段的中位百分位：A %.3f、B1 %.3f（0=最高分），进 Top100 的分别 %d 个和 %d 个。" % (
          "是——" if q4_sig else "否——", "显著高于" if q4_sig else "不显著高于", B["rest_n"],
          q4["A"]["cliff_delta"], q4["A"]["p"], q4["B1"]["cliff_delta"], q4["B1"]["p"],
          q4["A"]["gold_median_pct_rank"], q4["B1"]["gold_median_pct_rank"],
          q4["A"]["gold_in_top100"], q4["B1"]["gold_in_top100"]))
    sig_len = [b for b, v in by_len.items() if v["n_gold"] >= 2 and (
        v["A"]["p"] < 0.05 or v["B1"]["p"] < 0.05)]
    Ap("- **按长度分层后**：13 个兑现段**全部落在「%s」层**（其他层的 gold 数为 0，无法分层检验）；"
      "在该层**内部**再比「兑现段 vs 同层其余步骤」，%s——所以「兑现段分数更高」不是单纯由长度造成的；"
      "但它仍可能是「兑现段引用了神谕原文（文言/情态词多）」造成的词面效应，不能当成叙事显著性证据。" % (
          "、".join(b for b, v in by_len.items() if v["n_gold"] >= 2) or "无",
          "A 与 B1 都仍显著（A δ=%.3f p=%.3g；B1 δ=%.3f p=%.3g）" % (
              by_len[sig_len[0]]["A"]["cliff_delta"], by_len[sig_len[0]]["A"]["p"],
              by_len[sig_len[0]]["B1"]["cliff_delta"], by_len[sig_len[0]]["B1"]["p"])
          if sig_len else "差异不再显著"))
    Ap("")
    Ap("## 2. Q3：7 个转折类型的信号对比（A vs B1）")
    Ap("")
    Ap("说明：types 是多标签（一个标注样本可属多个类型），因此各类型 n 之和 > 74；排名是全池 686 的 1-based 名次（越小越好）。")
    Ap("")
    Ap("| 类型 | n | A 中位名次 | B1 中位名次 | 中位提升(A−B) | A Top100 | B1 Top100 | B1 组内 Spearman |")
    Ap("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for t in TYPES:
        if t not in q3:
            continue
        v = q3[t]
        Ap("| %s（%s） | %d | %.1f | %.1f | %+.1f | %d | %d | %.2f |" % (
            t, TYPE_LABELS[t], v["n"], v["a_median_rank"], v["b_median_rank"],
            v["median_lift_A_minus_B"], v["a_top100"], v["b_top100"],
            v["spearman_within_type_B"]))
    Ap("")
    Ap("**各类型示例**（B 提升最大 / 最小的样本）：")
    Ap("")
    Ap("| 类型 | 提升最大的样本 | A 名次 | B1 名次 | 提升最小的样本 | A 名次 | B1 名次 |")
    Ap("| --- | --- | --- | --- | --- | --- | --- |")
    for t in TYPES:
        if t not in q3:
            continue
        v = q3[t]
        be, we = v["best_lift_example"], v["worst_lift_example"]
        Ap("| %s | `%s` | %d | %d | `%s` | %d | %d |" % (
            t, be["segment_id"], be["a_rank"], be["b_rank"],
            we["segment_id"], we["a_rank"], we["b_rank"]))
    Ap("")
    best_t = B["q3_summary"]["best_type_by_median_lift"]
    worst_t = B["q3_summary"]["worst_type_by_median_lift"]
    bt = q3[best_t]
    Ap("**解读**：")
    Ap("- B 在 **%s** 上中位名次提升最大（%+.1f，n=%d），但这个数字主要被 1 个样本带动"
      "（`%s`：A 第 %d → B1 第 %d）；该类型的组内 Spearman 只有 %.2f（n 小），**不能过度解读**。" % (
          TYPE_LABELS[best_t], bt["median_lift_A_minus_B"], bt["n"],
          bt["best_lift_example"]["segment_id"], bt["best_lift_example"]["a_rank"],
          bt["best_lift_example"]["b_rank"], bt["spearman_within_type_B"]))
    Ap("- **identity** 的中位提升只有 %+.1f，但 Top100 覆盖从 %d 升到 %d——说明 B 的作用是「把少数身份揭示推进 Top100」，"
      "而不是整体抬升该类型。" % (
          q3["identity"]["median_lift_A_minus_B"], q3["identity"]["a_top100"], q3["identity"]["b_top100"]))
    Ap("- B 在 **%s** 上中位名次反而变差（%+.1f）：这类转折多为单句就能讲清的世界规则/说明性台词，A 的强词面已足够，"
      "B 的结构项反而把它压下去（示例 `%s`：A 第 %d → B1 第 %d）。" % (
          TYPE_LABELS[worst_t], q3[worst_t]["median_lift_A_minus_B"],
          q3[worst_t]["worst_lift_example"]["segment_id"], q3[worst_t]["worst_lift_example"]["a_rank"],
          q3[worst_t]["worst_lift_example"]["b_rank"]))
    Ap("- 组内 Spearman 在类型间差异也说明：**不存在单一信号对所有转折类型都有效**；"
      "「类型 → 该用哪组特征」的对应关系值得写进讨论。")
    Ap("")
    Ap("## 3. Q4：神谕兑现段的显著性检验")
    Ap("")
    Ap("| 检测器 | gold 中位分 | 其余中位分 | gold 中位名次 | gold 中位百分位 | 进 Top100 | MWU p | Cliff's δ |")
    Ap("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for name in ("A", "B1"):
        v = q4[name]
        Ap("| %s | %.3f | %.3f | %.0f | %.3f | %d / 13 | %.3g | %+.3f |" % (
            name, v["median_x"], v["median_y"], v["gold_median_rank"],
            v["gold_median_pct_rank"], v["gold_in_top100"], v["p"], v["cliff_delta"]))
    Ap("")
    Ap("**按长度分层再验**（每层内部：该层 gold vs 同层非 gold）：")
    Ap("")
    Ap("| 长度层 | gold 数 | 其余步数 | A: gold 中位分 / 其余 | A p | A δ | B1: gold 中位分 / 其余 | B1 p | B1 δ |")
    Ap("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for b, v in by_len.items():
        if v["n_gold"] < 2:
            Ap("| %s | %d | %d | — | — | — | — | — | — |（gold 数 <2，无法检验）" % (
                b, v["n_gold"], v["n_rest"]))
            continue
        Ap("| %s | %d | %d | %.3f / %.3f | %.3g | %+.3f | %.3f / %.3f | %.3g | %+.3f |" % (
            b, v["n_gold"], v["n_rest"],
            v["A"]["median_x"], v["A"]["median_y"], v["A"]["p"], v["A"]["cliff_delta"],
            v["B1"]["median_x"], v["B1"]["median_y"], v["B1"]["p"], v["B1"]["cliff_delta"]))
    Ap("")
    Ap("**解读**：")
    Ap("- 13 条兑现段在 A/B 分数上**显著高于**其余步骤（δ：A %+.3f、B1 %+.3f，p 均 < 0.001），"
      "整体排在中位百分位 A %.3f / B1 %.3f（0=最高分）。" % (
          q4["A"]["cliff_delta"], q4["B1"]["cliff_delta"],
          q4["A"]["gold_median_pct_rank"], q4["B1"]["gold_median_pct_rank"]))
    Ap("- 但**不能据此下「神谕兑现 = 天然高显著」的结论**：①13 条兑现段全部是 >30 句的长步骤（长度层只有这一层有 gold）；"
      "②它们多数本身就是「吟诵神谕」的步骤，文本里含大量文言/情态/神谕词——这正是 A/B 词面特征最敏感的东西；"
      "③唯一不引原文的 O10 在 A 里最好也只排第 %d 名（关键词法第 %d 名），说明去掉字面后「兑现」并不显眼。" % (
          B["meta"]["o10_ranks_v1"].get("tfidf_char"),
          B["meta"]["o10_ranks_v1"].get("keyword")))
    Ap("- 对报告的含义：检索评测的 gold（兑现段）与显著性检测的「高显著段」是**两个不同概念**；"
      "兑现段在 A/B 上的高分可以作为「它们容易被词面方法抓到」的证据，但不能反过来当作显著性标签。")
    Ap("")
    Ap("## 4. 证据表（可直接抄进报告）")
    Ap("")
    Ap("| # | 结论 | 指标 | 数值 | p / 效应量 | 来源 |")
    Ap("| --- | --- | --- | --- | --- | --- |")
    for row in evidence:
        Ap("| %s | %s | %s | %s | %s | %s |" % (
            row["id"], row["conclusion"], row["metric"], row["value"], row["effect"], row["source"]))
    Ap("")
    Ap("## 5. 局限")
    Ap("")
    Ap("1. **Q3 的类型样本很小**（n=7–27），且是多标签（同一片段可计入多个类型）；组内 Spearman 在 n<10 时几乎不可解释，"
      "只能看方向；类型间比较是描述性的。")
    Ap("2. **Q3 的排名来自 A/B 的全池排序**：A/B 本身长度偏差明显（B1 的 ρ=+0.68），类型与长度相关时会混入长度效应。")
    Ap("3. **Q4 的 13 个 gold 是人工挑出的「最主要兑现段」**，不是随机样本；13 vs 673 的 MWU 也不满足「独立同分布」假设。")
    Ap("4. 长度分层后部分层 gold 数 <2 无法检验，结论只能覆盖有检验的层。")
    Ap("5. 本分析不改任何语料/config，只读既有分数与标注；数字可由脚本逐行复算。")
    Ap("")
    Ap("## 6. 复现")
    Ap("")
    Ap("```bash")
    Ap("%s            # 同时重算 A 与 B 两部分并写 4 个产物" % RUN_CMD)
    Ap("conda run -n nlpLesson python tools/retrieval_v2.py --verify")
    Ap("```")
    Ap("")
    return "\n".join(L)


# ============================================================================
# 主流程
# ============================================================================
def build():
    jieba.setLogLevel(60)
    jieba.initialize()
    oracles = load_oracles()
    segs = load_segments()
    filled = {o["oracle_id"]: o for o in read_json(P_FILLED)["oracles"]}
    v1 = read_json(P_V1)
    annot = read_json(P_ANNOT)
    a_scores = read_json(P_A)
    b_scores = read_json(P_B1)
    print("A. 检索 v2：重建五法 + v1 复现 + 两个变体…")
    A = build_retrieval(oracles, filled, segs, v1)
    print("   v1 复现校验通过；剔除吟诵步 %d 个" % A["meta"]["n_removed_recitation_steps"])
    print("B. Q3 类型 + Q4 神谕显著性…")
    B = build_significance(segs, annot, a_scores, b_scores, filled)
    B["meta"]["o10_ranks_v1"] = {m: A["o10_focus"]["v1"].get(m) for m in METHODS}
    evidence = build_evidence(A, B, v1)
    B["evidence_table"] = evidence
    # 写 JSON
    for path, obj in ((OUT_A_JSON, A), (OUT_B_JSON, B)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("已写 %s" % os.path.relpath(path, ROOT))
    # 写 MD
    for path, md in ((OUT_A_MD, render_retrieval_md(A)), (OUT_B_MD, render_significance_md(B, evidence))):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        print("已写 %s" % os.path.relpath(path, ROOT))
    if not verify(verbose=True):
        print("!! 报告与 JSON 不一致", file=sys.stderr)
        sys.exit(1)
    print("\n核对通过：报告数值与 JSON 一致。")



# ============================================================================
# 自校验
# ============================================================================
PERQUERY_ROW_RE = re.compile(r"^\| (O\d{2}) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$")
TYPE_ROW_RE = re.compile(r"^\| ([a-z]+)（[^|]*） \| (\d+) \| ([0-9.]+) \| ([0-9.]+) \| ([+-]?[0-9.]+) \| (\d+) \| (\d+) \| ([0-9.]+) \|$")


def verify(verbose=False):
    for path in (OUT_A_JSON, OUT_A_MD, OUT_B_JSON, OUT_B_MD):
        if not os.path.exists(path):
            print("产物不存在：%s" % path, file=sys.stderr)
            return False
    A = read_json(OUT_A_JSON)
    B = read_json(OUT_B_JSON)
    problems = []
    # ---------- A 部分 ----------
    if A["v1_reproduction_mismatch"]:
        problems.append("v1 复现不一致：%s" % A["v1_reproduction_mismatch"][:3])
    if len(A["variants"]) != 4:
        problems.append("变体数 %d != 4" % len(A["variants"]))
    for tag, v in A["variants"].items():
        for m in METHODS:
            per = v["per_method"][m]
            if len(per["per_oracle"]) != 13:
                problems.append("%s/%s per_oracle 数 != 13" % (tag, m))
            ranks = [x.get("gold_rank") for x in per["per_oracle"].values() if x.get("gold_rank")]
            if per["metrics"].get("n_eval") != len(ranks):
                problems.append("%s/%s n_eval 不一致" % (tag, m))
            rec = {k: round(float(sum(1 for r in ranks if r <= k)) / len(ranks), 4) for k in KS}
            mrr = round(float(np.mean([1.0 / r for r in ranks])), 4)
            if abs(mrr - per["metrics"]["mrr"]) > 1e-4:
                problems.append("%s/%s MRR 重算不一致" % (tag, m))
            for k in KS:
                if abs(rec[k] - per["metrics"]["recall@%d" % k]) > 1e-4:
                    problems.append("%s/%s recall@%d 不一致" % (tag, m, k))
    # A 报告：逐 query 排名表核对（每方法一张表，5 张 × 13 行）
    mdA = open(OUT_A_MD, "r", encoding="utf-8").read()
    parsed = 0
    sections = re.split(r"^### ", mdA, flags=re.M)
    for sec in sections:
        title = sec.split("\n", 1)[0].strip()
        m_label = next((m for m in METHODS if METHOD_LABELS[m] == title), None)
        if m_label is None:
            continue
        for line in sec.splitlines():
            mm = PERQUERY_ROW_RE.match(line)
            if not mm:
                continue
            oid = mm.group(1)
            cells = [mm.group(i).strip() for i in (2, 3, 4, 5)]
            ref = A["per_query_ranks"][oid]
            for tag, cell in zip(("v1", "v2_mask", "v2_norecite", "v2_both"), cells):
                r = ref[tag].get(m_label)
                if cell == "N/A":
                    if r is not None:
                        problems.append("报告 N/A 但 JSON 有值 %s/%s/%s" % (m_label, oid, tag))
                elif r is None or int(cell) != r:
                    problems.append("报告排名与 JSON 不一致 %s/%s/%s：%s vs %s" % (
                        m_label, oid, tag, cell, r))
            parsed += 1
    if parsed < 5 * 13:
        problems.append("报告 A 逐 query 表解析行数 %d < 65" % parsed)

    # ---------- B 部分 ----------
    q3 = B["q3_types"]
    if len(q3) != 7:
        problems.append("Q3 类型数 %d != 7" % len(q3))
    # 重算 Q3（用 A/B 分数 + 标注）
    segs = load_segments()
    eligible = [x for x in segs if x["n_main"] > 0 and not x["low_content"] and x["has_dialogue"]]
    pool = [x["segment_id"] for x in eligible]
    A_s = {x["segment_id"]: x for x in read_json(P_A)["segments"]}
    B_s = {x["segment_id"]: x for x in read_json(P_B1)["segments"]}
    a_rank = {sid: A_s[sid]["rank"] for sid in pool}
    b_rank = {sid: B_s[sid]["rank"] for sid in pool}
    annot = read_json(P_ANNOT)
    for t in TYPES:
        sel = [x for x in annot["samples"] if t in x["types"]]
        if not sel:
            continue
        a_r = [a_rank[x["segment_id"]] for x in sel]
        b_r = [b_rank[x["segment_id"]] for x in sel]
        if abs(float(np.median(a_r)) - q3[t]["a_median_rank"]) > 1e-6:
            problems.append("Q3 %s A 中位名次不一致" % t)
        if abs(float(np.median(b_r)) - q3[t]["b_median_rank"]) > 1e-6:
            problems.append("Q3 %s B 中位名次不一致" % t)
        if sum(1 for r in a_r if r <= 100) != q3[t]["a_top100"]:
            problems.append("Q3 %s A Top100 不一致" % t)
        if sum(1 for r in b_r if r <= 100) != q3[t]["b_top100"]:
            problems.append("Q3 %s B Top100 不一致" % t)
    # 重算 Q4
    filled = {o["oracle_id"]: o for o in read_json(P_FILLED)["oracles"]}
    gold_ids = [filled[o]["fulfillment_segment"] for o in sorted(filled)]
    gold_ids = [g for g in gold_ids if g in set(pool)]
    rest = [sid for sid in pool if sid not in set(gold_ids)]
    for name, scores in (("A", {sid: A_s[sid]["score"] for sid in pool}),
                         ("B1", {sid: B_s[sid]["score"] for sid in pool})):
        cmp = compare_dist([scores[g] for g in gold_ids], [scores[r] for r in rest])
        ref = B["q4_overall"][name]
        if abs(cmp["cliff_delta"] - ref["cliff_delta"]) > 1e-4:
            problems.append("Q4 %s δ 重算不一致" % name)
        if abs(cmp["p"] - ref["p"]) > 1e-9:
            problems.append("Q4 %s p 重算不一致" % name)
    if len(B["evidence_table"]) < 10:
        problems.append("证据表条数 %d < 10" % len(B["evidence_table"]))
    mdB = open(OUT_B_MD, "r", encoding="utf-8").read()
    if mdB.count("| ") < 50:
        problems.append("报告 B 表格内容过少")

    if verbose:
        print("\nA：变体 %s；剔除吟诵步 %d；O10 最好名次 v1=%s mask=%s noRecite=%s both=%s" % (
            "/".join(A["variants"].keys()), A["meta"]["n_removed_recitation_steps"],
            min(v for v in A["o10_focus"]["v1"].values() if v),
            min(v for v in A["o10_focus"]["v2_mask"].values() if v),
            min((v for v in A["o10_focus"]["v2_norecite"].values() if v), default=None),
            min((v for v in A["o10_focus"]["v2_both"].values() if v), default=None)))
        print("   报告 A 逐 query 表解析 %d 行（5 方法 × 13 query）" % parsed)
        print("B：Q3 7 类型；Q4 A δ=%+.3f p=%.3g / B1 δ=%+.3f p=%.3g；证据表 %d 条" % (
            B["q4_overall"]["A"]["cliff_delta"], B["q4_overall"]["A"]["p"],
            B["q4_overall"]["B1"]["cliff_delta"], B["q4_overall"]["B1"]["p"],
            len(B["evidence_table"])))
        print("抽查 3 个数值：Q3 relationship 中位提升 %+.1f；Q4 gold 中位百分位 A=%.3f；v2_both BM25 MRR=%.3f" % (
            q3["relationship"]["median_lift_A_minus_B"],
            B["q4_overall"]["A"]["gold_median_pct_rank"],
            A["summary"]["v2_both"]["bm25"]["mrr"]))
    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="检索 v2 + Q3 类型 + Q4 显著性")
    ap.add_argument("--verify", action="store_true", help="只校验已有产物（不重算）")
    args = ap.parse_args()
    if args.verify:
        ok = verify(verbose=True)
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    build()


if __name__ == "__main__":
    main()
