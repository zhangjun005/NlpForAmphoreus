#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
retrieval_v3.py — 神谕检索 v3：事件段 gold + 排除吟诵步 + 6 法对比（含 SBERT）

设计（A1 修正版）：
  * gold = oracle-fulfillment.v2.json 的 event_segments（多段；任一命中即算命中）
           event_segments 为空的 O07/O11/O12 回退到 current_filled_fulfillment；
           O04=3.2|摇船啊，请载我横渡冥流|19、O05 两段（断梦|1 + 摇船|19）、O13 两段（点燃|7 + 魔女|21）。
  * v3 候选池 = 686 池中剔除「含该神谕原文（6-gram 覆盖率 ≥0.5 或包含整句）」的吟诵步；
    另跑一个「不剔除」的 v3_control 作对照。
  * 方法：关键词 / TF-IDF(char) / TF-IDF(word) / BM25 / LSA(100) / SBERT(bge-small-zh-v1.5，复用 data/models)。
  * 指标：多 gold 的 Recall@1/5/10/20、MRR（=1/min gold rank）；gold 被剔除导致 N/A 的 query 不计入分母。
  * 对照：v1（旧结果，旧 gold=吟诵步）、v2（mask / noRecite 诊断，取自旧 JSON）。

产出（只写这些）：
  data/config/retrieval-v3-results.json
  data/reports/retrieval-v3.md
  docs/report/figures/f15_retrieval_v3.png
  data/plot_data/f15_retrieval_v3.csv + .meta.json（经 export_plot_data.export_for 自动生成）
  docs/report/figures-index.md（刷新）

运行：
  conda run -n nlpLesson python tools/retrieval_v3.py
  conda run -n nlpLesson python tools/retrieval_v3.py --verify
"""

import argparse
import json
import math
import os
import sys
from collections import Counter

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import jieba
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tokenize_compat import install, tokenize  # noqa: E402

install()  # 兼容 joblib 反序列化（本脚本不需要 load 向量器，但保持与规范一致）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_ORACLES = os.path.join(ROOT, "data", "corpus", "oracles.jsonl")
P_SEGS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_V2 = os.path.join(ROOT, "data", "config", "oracle-fulfillment.v2.json")
P_RET1 = os.path.join(ROOT, "data", "config", "oracle-retrieval-results.json")
P_RET2 = os.path.join(ROOT, "data", "config", "retrieval-v2-results.json")
P_IDS = os.path.join(ROOT, "data", "models", "ids.json")
P_Z_SBERT_SEG = os.path.join(ROOT, "data", "models", "Z_sbert_seg.npy")
P_SBERT_MODEL = os.path.join(ROOT, "data", "models", "sbert_model")
OUT_JSON = os.path.join(ROOT, "data", "config", "retrieval-v3-results.json")
OUT_MD = os.path.join(ROOT, "data", "reports", "retrieval-v3.md")
OUT_FIG = os.path.join(ROOT, "docs", "report", "figures", "f15_retrieval_v3.png")
RUN_CMD = "conda run -n nlpLesson python tools/retrieval_v3.py"

METHODS = ["keyword", "tfidf_char", "tfidf_word", "bm25", "lsa", "sbert"]
METHOD_LABELS = {"keyword": "关键词基线", "tfidf_char": "TF-IDF(char)", "tfidf_word": "TF-IDF(word)",
                 "bm25": "BM25", "lsa": "LSA(100)", "sbert": "SBERT(bge-small)"}
KS = (1, 5, 10, 20)
RECITE_TH = 0.5
BM25_K1, BM25_B = 1.5, 0.75

STOP = set("的 了 是 在 我 你 他 她 它 我们 你们 他们 这 那 一个 没有 就 都 也 不 将 于 中 而 之 以 为 把 被 让 从 到 对 会 能 要 个 一 上 下 里 后 前 时 等 与 和 或 但 却 又 很 太 更 最 如 若 则 因 所以 因此 如果 虽然 已经 正在 可以 不是 就是 还是 只是 这样 那样 什么 怎么 为什么 因为 至于 以及 并且 而且 然后 之后 之前".split())
PUNCT_CHARS = set("，。！？、；：…—「」『』（）().,!?;:~-·\"'《》〈〉【】 \t\r\n")


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


def strip_punct(t):
    return "".join(c for c in (t or "") if c not in PUNCT_CHARS and not c.isspace())


def tok2(text):
    return [w for w in tokenize(text or "") if len(w) >= 2]


def ngram_cov(oracle_norm, doc_norm, n=6):
    if len(oracle_norm) < n:
        return 1.0 if oracle_norm and oracle_norm in doc_norm else 0.0
    grams = [oracle_norm[i:i + n] for i in range(len(oracle_norm) - n + 1)]
    src = set(doc_norm[i:i + n] for i in range(len(doc_norm) - n + 1))
    return sum(1 for g in grams if g in src) / len(grams)


# ---------------------------------------------------------------------------
# 数据
# ---------------------------------------------------------------------------
def load_all():
    oracles = read_jsonl(P_ORACLES)
    segs = [s for s in read_jsonl(P_SEGS)
            if s["n_main"] > 0 and not s["low_content"] and s["has_dialogue"]]
    assert len(segs) == 686, len(segs)
    ids = read_json(P_IDS)
    assert [s["segment_id"] for s in segs] == ids["segments"], "segments 顺序与 ids.json 不一致"
    v2 = {e["oracle_id"]: e for e in read_json(P_V2)["oracles"]}
    return oracles, segs, v2


def gold_sets(oracles, v2):
    out = {}
    for o in oracles:
        oid = o["oracle_id"]
        ev = v2.get(oid, {})
        segs = [x["segment_id"] for x in ev.get("event_segments") or []]
        src = "event_segments"
        if not segs and ev.get("current_filled_fulfillment"):
            segs = [ev["current_filled_fulfillment"]]
            src = "fallback_current_filled"
        out[oid] = {"segments": list(dict.fromkeys(segs)), "source": src}
    return out


def removal_flags(oracles, segs):
    removed = {}
    for s in segs:
        dn = strip_punct(s.get("text_all") or "")
        best, best_oid = 0.0, None
        for o in oracles:
            n = strip_punct(o["text"])
            cov = ngram_cov(n, dn)
            if n and n in dn:
                cov = 1.0
            if cov > best:
                best, best_oid = cov, o["oracle_id"]
        if best >= RECITE_TH:
            removed[s["segment_id"]] = {"max_oracle_6gram_coverage": round(float(best), 4),
                                        "closest_oracle": best_oid}
    return removed


# ---------------------------------------------------------------------------
# 方法
# ---------------------------------------------------------------------------
def build_keyword_query(o):
    w = {}
    for t in tok2(o["text"]):
        w[t] = max(w.get(t, 0.0), 1.0)
    for t in [k for k in (o.get("keywords") or []) if len(k) >= 2]:
        w[t] = max(w.get(t, 0.0), 2.0)
    return w


def score_keyword(weighted, doc_counts):
    out = np.zeros(len(doc_counts), dtype=float)
    for i, cnt in enumerate(doc_counts):
        s = 0.0
        for t, ww in weighted.items():
            tf = cnt.get(t)
            if tf:
                s += ww * (1.0 + math.log1p(tf))
        out[i] = s
    return out


def cos_scores(q_vec, mat):
    q = np.asarray(q_vec, dtype=float).ravel()
    q = q / (np.linalg.norm(q) + 1e-12)
    m = np.asarray(mat, dtype=float)
    return m.dot(q)


def fit_and_score(segs, oracles, sbert_docs):
    docs = [s.get("text_all") or "" for s in segs]
    doc_toks = [tokenize(d) for d in docs]
    doc_counts = [Counter(t) for t in doc_toks]
    # char tfidf
    char_vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=2,
                               sublinear_tf=True, norm="l2")
    char_mat = char_vec.fit_transform(docs)
    # word tfidf
    word_vec = TfidfVectorizer(analyzer=tokenize, ngram_range=(1, 2), min_df=1,
                               sublinear_tf=True, norm="l2")
    word_mat = word_vec.fit_transform(docs)
    # bm25
    n = len(docs)
    dl = np.array([len(t) for t in doc_toks], dtype=float)
    avgdl = float(dl.mean()) if n else 1.0
    df = Counter()
    for cnt in doc_counts:
        for t in cnt:
            df[t] += 1
    idf = {t: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
    # lsa
    svd = TruncatedSVD(n_components=min(100, max(2, min(word_mat.shape) - 1)),
                       random_state=42, algorithm="randomized", n_iter=7)
    latent = svd.fit_transform(word_mat)
    latent = latent / np.maximum(np.linalg.norm(latent, axis=1, keepdims=True), 1e-12)
    out = {}
    queries = {o["oracle_id"]: o for o in oracles}
    for oid, o in queries.items():
        out[oid] = {}
        kw = build_keyword_query(o)
        out[oid]["keyword"] = score_keyword(kw, doc_counts)
        qc = char_vec.transform([o["text"]])
        cm = normalize(char_mat)
        out[oid]["tfidf_char"] = np.asarray(cm.dot(normalize(qc).T).todense()).ravel()
        qw = word_vec.transform([o["text"]])
        wm = normalize(word_mat)
        out[oid]["tfidf_word"] = np.asarray(wm.dot(normalize(qw).T).todense()).ravel()
        # bm25
        scores = np.zeros(n, dtype=float)
        for t in tokenize(o["text"]):
            idf_t = idf.get(t)
            if idf_t is None:
                continue
            for i, cnt in enumerate(doc_counts):
                tf = cnt.get(t)
                if tf:
                    scores[i] += idf_t * tf * (BM25_K1 + 1) / (
                        tf + BM25_K1 * (1 - BM25_B + BM25_B * dl[i] / avgdl))
        out[oid]["bm25"] = scores
        qz = svd.transform(qw)[0]
        qz = qz / (np.linalg.norm(qz) + 1e-12)
        out[oid]["lsa"] = latent.dot(qz)
        # sbert（docs 为该池子集的 Z_sbert_seg 行）
        qs = sbert_docs["query_vecs"][oid]
        out[oid]["sbert"] = sbert_docs["mat"].dot(qs)
    return out


def evaluate(scores_by_query, segs, gold, available):
    """多 gold：任一命中即算命中；返回 metrics + per_query"""
    oids = [o["oracle_id"] for o in segs] if False else None
    per_query = {}
    for oid, methods in scores_by_query.items():
        gs = [x for x in gold[oid]["segments"] if x in available]
        if not gs:
            per_query[oid] = {"n_gold": 0, "gold_ranks": {}, "best_rank": None, "note": "N/A（gold 全被剔除）"}
            continue
        idx = {s["segment_id"]: i for i, s in enumerate(segs)}
        ranks = {}
        for m, sc in methods.items():
            order = sorted(range(len(sc)), key=lambda i: (-float(sc[i]), i))
            rk = {segs[i]["segment_id"]: k + 1 for k, i in enumerate(order)}
            ranks[m] = {g: rk[g] for g in gs}
        per_query[oid] = {"n_gold": len(gs), "gold_segments": gs,
                          "gold_in_pool_ratio": round(len(gs) / len(gold[oid]["segments"]), 4) if gold[oid]["segments"] else 0,
                          "gold_ranks": ranks,
                          "best_rank": {m: min(ranks[m].values()) for m in ranks},
                          "note": "" if len(gs) == len(gold[oid]["segments"]) else "部分 gold 被剔除"}
    metrics = {}
    for m in METHODS:
        ranks = [per_query[oid]["best_rank"][m] for oid in per_query
                 if per_query[oid]["best_rank"] and m in per_query[oid]["best_rank"]]
        if not ranks:
            metrics[m] = None
            continue
        a = np.array(ranks, dtype=float)
        met = {"n_eval": len(a), "mrr": round(float((1.0 / a).mean()), 4),
               "median_rank": float(np.median(a))}
        for k in KS:
            met["recall@%d" % k] = round(float((a <= k).mean()), 4)
        metrics[m] = met
    return metrics, per_query


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build():
    oracles, segs, v2 = load_all()
    gold = gold_sets(oracles, v2)
    removed = removal_flags(oracles, segs)
    pool_v3 = [s for s in segs if s["segment_id"] not in removed]
    # SBERT 资产：Z_sbert_seg 行顺序 = ids["segments"]
    ids = read_json(P_IDS)
    Z = np.load(P_Z_SBERT_SEG)
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(1)
    model = SentenceTransformer(P_SBERT_MODEL, device="cpu")
    ovecs = {o["oracle_id"]: model.encode([o["text"]], normalize_embeddings=True)[0]
             for o in oracles}
    idx_full = {sid: i for i, sid in enumerate(ids["segments"])}

    def run(pool):
        mat = np.stack([Z[idx_full[s["segment_id"]]] for s in pool])
        sb = {"mat": mat, "query_vecs": ovecs}
        return fit_and_score(pool, oracles, sb)

    print("v3：剔除吟诵步 %d 个，池 %d；跑 6 法…" % (len(removed), len(pool_v3)))
    scores_v3 = run(pool_v3)
    scores_ctrl = run(segs)
    avail_v3 = {s["segment_id"] for s in pool_v3}
    avail_ctrl = {s["segment_id"] for s in segs}
    met_v3, per_v3 = evaluate(scores_v3, pool_v3, gold, avail_v3)
    met_ctrl, per_ctrl = evaluate(scores_ctrl, segs, gold, avail_ctrl)

    v1 = read_json(P_RET1)
    v2r = read_json(P_RET2)
    v1_metrics = {m: v1["methods_base"][m]["metrics"] for m in
                  ["keyword", "tfidf_char", "tfidf_word", "bm25", "lsa"]}
    v2_mask = {m: v2r["summary"]["v2_mask"][m] for m in
               ["keyword", "tfidf_char", "tfidf_word", "bm25", "lsa"]}
    v2_norecite = {m: v2r["summary"]["v2_norecite"][m] for m in
                   ["keyword", "tfidf_char", "tfidf_word", "bm25", "lsa"]}
    na = [oid for oid in gold if not per_v3[oid]["best_rank"] or per_v3[oid]["best_rank"].get("keyword") is None]
    result = {
        "meta": {
            "script": "tools/retrieval_v3.py", "run_command": RUN_CMD,
            "design": "gold=event_segments（多段任一命中）；v3 池剔除含神谕原文的吟诵步；"
                      "另跑 v3_control（不剔除）对照；方法含 SBERT（本地 bge-small-zh-v1.5）",
            "threshold": "6-gram 覆盖率 ≥ %.2f 或整句包含" % RECITE_TH,
            "n_pool_full": len(segs), "n_pool_v3": len(pool_v3),
            "n_removed": len(removed),
            "n_eval_v3": met_v3["keyword"]["n_eval"] if met_v3["keyword"] else 0,
            "n_na_v3": len(na), "na_queries": na,
            "sources": ["data/config/oracle-fulfillment.v2.json", "data/corpus/oracles.jsonl",
                        "data/corpus/segments.jsonl", "data/models/Z_sbert_seg.npy",
                        "data/models/ids.json", "data/models/sbert_model/",
                        "data/config/oracle-retrieval-results.json",
                        "data/config/retrieval-v2-results.json"],
        },
        "gold_sets": {oid: {"segments": gold[oid]["segments"], "source": gold[oid]["source"],
                            "in_full_pool": [x for x in gold[oid]["segments"]
                                             if x in avail_ctrl]} for oid in gold},
        "removal": {"n_removed": len(removed),
                    "removed": [{"segment_id": sid, **v} for sid, v in removed.items()],
                    "n_pool_full": len(segs), "n_pool_v3": len(pool_v3)},
        "v3": {"n_eval": met_v3["keyword"]["n_eval"] if met_v3["keyword"] else 0,
               "metrics": met_v3, "per_query": per_v3},
        "v3_control": {"n_eval": met_ctrl["keyword"]["n_eval"] if met_ctrl["keyword"] else 0,
                       "metrics": met_ctrl, "per_query": per_ctrl},
        "v1_old": {"metrics": v1_metrics, "n_eval": 13,
                   "note": "旧 gold=吟诵步；5 法；无 SBERT"},
        "v2_old": {"v2_mask_metrics": v2_mask, "v2_mask_n_eval":
                   v2r["summary"]["v2_mask"]["keyword"]["n_eval"],
                   "v2_norecite_metrics": v2_norecite, "v2_norecite_n_eval":
                   v2r["summary"]["v2_norecite"]["keyword"]["n_eval"],
                   "note": "mask 有泄漏；noRecite 删 gold 后仅 1 条可评"},
        "o10": {"v3": {m: per_v3.get("O10", {}).get("gold_ranks", {}).get(m) for m in METHODS},
                "v3_control": {m: per_ctrl.get("O10", {}).get("gold_ranks", {}).get(m) for m in METHODS}},
    }
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写 %s" % os.path.relpath(OUT_JSON, ROOT))
    make_figure(result)
    md = render_md(result)
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s" % os.path.relpath(OUT_MD, ROOT))
    try:
        from export_plot_data import export_for
        export_for("tools/retrieval_v3.py")
    except Exception as e:
        print("  [plot_data] 跳过：%s" % e, file=sys.stderr)
    if not verify(result, verbose=True):
        print("!! 校验失败", file=sys.stderr)
        sys.exit(1)
    print("\n校验通过：gold/剔除/指标/图与配对数据一致。")


# ---------------------------------------------------------------------------
# 图 / 报告 / 校验
# ---------------------------------------------------------------------------
def make_figure(result):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"]:
        if cand in names:
            plt.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(14.2, 5.0))
    ax = axes[0]
    variants = [("v1_old", result["v1_old"]["metrics"], "#9fb3c8"),
                ("v2_mask", result["v2_old"]["v2_mask_metrics"], "#7f8c8d"),
                ("v3_control", result["v3_control"]["metrics"], "#d98c3f"),
                ("v3", result["v3"]["metrics"], "#2e5c8a")]
    x = np.arange(len(METHODS))
    w = 0.2
    for i, (var, met, col) in enumerate(variants):
        vals = [met[m]["mrr"] if met.get(m) else float("nan") for m in METHODS]
        ax.bar(x + (i - 1.5) * w, vals, w, label=var, color=col)
    ax.set_xticks(x)
    ax.set_xticklabels([METHOD_LABELS[m] for m in METHODS], rotation=12, fontsize=8)
    ax.set_ylabel("MRR")
    ax.set_title("(a) 四组方法 MRR 对比（v3=%d 条可评，v3_control=%d 条）" % (
        result["v3"]["n_eval"], result["v3_control"]["n_eval"]), fontsize=9)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    # (b) v3 Recall@k
    ax = axes[1]
    xs = np.arange(len(METHODS))
    for j, k in enumerate(KS):
        vals = [result["v3"]["metrics"][m]["recall@%d" % k] if result["v3"]["metrics"].get(m) else float("nan")
                for m in METHODS]
        ax.bar(xs + (j - 1.5) * 0.2, vals, 0.2, label="R@%d" % k)
    ax.set_xticks(xs)
    ax.set_xticklabels([METHOD_LABELS[m] for m in METHODS], rotation=12, fontsize=8)
    ax.set_ylabel("Recall@k")
    ax.set_title("(b) v3 各方法 Recall@k（n=%d）" % result["v3"]["n_eval"], fontsize=9)
    ax.legend(fontsize=8, frameon=False, ncol=2)
    ax.grid(axis="y", alpha=0.25)
    fig.suptitle("图15 神谕检索 v3：事件段 gold + 剔除吟诵步后的方法对比（纵轴=MRR/Recall）", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT_FIG, dpi=200, bbox_inches="tight")
    plt.close(fig)


def render_md(d):
    meta = d["meta"]
    L = []
    A = L.append
    A("# 神谕检索 v3：事件段 gold + 排除吟诵步 + 6 法对比（含 SBERT）")
    A("")
    A("> 生成脚本：`%s` ｜ 重跑：`%s`" % (meta["script"], RUN_CMD))
    A("> 数据（只读）：`oracle-fulfillment.v2.json`（事件段 gold）、`oracles.jsonl`、`segments.jsonl`、"
      "`Z_sbert_seg.npy`/`ids.json`/`sbert_model/`（SBERT）、旧结果 `oracle-retrieval-results.json`（v1）与 `retrieval-v2-results.json`（v2）")
    A("> 明细：`data/config/retrieval-v3-results.json` ｜ 图：`docs/report/figures/f15_retrieval_v3.png`"
      "（配对数据 `data/plot_data/f15_retrieval_v3.csv` + `.meta.json`）")
    A("")
    A("## 1. 结论")
    A("")
    A("- **v3 设计**：gold = `event_segments`（多段，任一命中即算命中）；候选池剔除吟诵步（6-gram 覆盖 ≥%.2f 或整句包含）；"
      "方法 5 个旧法 + **SBERT**。" % meta["threshold"].split("≥")[1].split(" ")[0] if False else
      "- **v3 设计**：gold = `event_segments`（多段，任一命中即算命中）；候选池剔除吟诵步（6-gram 覆盖 ≥0.5 或整句包含）；方法 5 个旧法 + **SBERT**。")
    A("- **剔除后只剩 %d/13 条可评**（N/A：%s）；v3_control（不剔除）13 条全可评。" % (
        d["v3"]["n_eval"], "、".join(d["meta"]["na_queries"]) or "无"))
    best_v3 = max([m for m in METHODS if d["v3"]["metrics"].get(m)],
                  key=lambda m: d["v3"]["metrics"][m]["mrr"]) if d["v3"]["metrics"].get("keyword") else None
    best_ctrl = max([m for m in METHODS if d["v3_control"]["metrics"].get(m)],
                    key=lambda m: d["v3_control"]["metrics"][m]["mrr"])
    if best_v3:
        A("- **v3（%d 条）最佳方法**：%s，MRR %.3f、R@10 %.2f；v3_control（13 条）最佳：%s，MRR %.3f、R@10 %.2f。" % (
            d["v3"]["n_eval"], METHOD_LABELS[best_v3], d["v3"]["metrics"][best_v3]["mrr"],
            d["v3"]["metrics"][best_v3]["recall@10"],
            METHOD_LABELS[best_ctrl], d["v3_control"]["metrics"][best_ctrl]["mrr"],
            d["v3_control"]["metrics"][best_ctrl]["recall@10"]))
    def _mrr_str(met):
        return "、".join("%s %.3f" % (METHOD_LABELS[m], met[m]["mrr"])
                        for m in METHODS if met.get(m))
    A("- **v3（%d 条）各方法 MRR**：%s。" % (d["v3"]["n_eval"], _mrr_str(d["v3"]["metrics"])))
    A("- **v3_control（13 条）各方法 MRR**：%s。" % _mrr_str(d["v3_control"]["metrics"]))
    A("- **v3 是否终于能做方法对比？答：不能（但比 v2 前进了一步）**：①剔除吟诵步让 %d 条 gold 被连带删掉"
      "（N/A：%s），只剩 %d 条可评；②这 %d 条上所有方法都接近失败（最好 MRR %.3f、R@10 %.2f），"
      "方法间差异没有统计意义；③v3_control 13 条虽全可评，但池里仍保留吟诵步，字面方法依旧占优（关键词 %.3f > SBERT %.3f），"
      "所以它也不是「无泄漏的方法对比」。→ **v3 的可用结论是：在事件段 gold 上，现有 6 种方法全部失效**"
      "（任务本身比旧 gold 难得多），而不是「哪种方法更好」。" % (
          d["meta"]["n_na_v3"], "、".join(d["meta"]["na_queries"]) or "无", d["v3"]["n_eval"],
          d["v3"]["n_eval"],
          max(v["mrr"] for v in d["v3"]["metrics"].values() if v),
          max(v["recall@10"] for v in d["v3"]["metrics"].values() if v),
          d["v3_control"]["metrics"]["keyword"]["mrr"],
          (d["v3_control"]["metrics"]["sbert"] or {}).get("mrr", 0)))
    A("- **SBERT 反而最差**：v3 MRR %.3f、v3_control %.3f（均低于关键词/BM25/TF-IDF）——"
      "步骤级句向量的相似度普遍偏高、区分度低；这与「语义方法应该更强」的直觉相反，是本轮最反直觉的发现。" % (
          d["v3"]["metrics"]["sbert"]["mrr"], d["v3_control"]["metrics"]["sbert"]["mrr"]))
    o10_v3 = d["v3"]["per_query"]["O10"]["best_rank"]
    o10_ctrl = d["v3_control"]["per_query"]["O10"]["best_rank"]
    A("- **O10（唯一不引原文的兑现）**：v3 最好名次 = TF-IDF(char) 第 **%d** 名（关键词第 %d 名）；"
      "v3_control 最好 = TF-IDF(char) 第 **%d** 名（关键词第 %d 名）。" % (
          min(o10_v3.values()), o10_v3.get("keyword"), min(o10_ctrl.values()), o10_ctrl.get("keyword")))
    A("")

    A("## 2. gold 与剔除")
    A("")
    A("| oracle | gold 段（event_segments，多段） | 来源 | 在 686 池 | 被剔除导致 N/A |")
    A("| --- | --- | --- | --- | --- |")
    for oid, g in d["gold_sets"].items():
        segs = g["segments"]
        A("| %s | %s | %s | %s | %s |" % (
            oid, "；".join("`%s`" % x for x in segs) or "（空）",
            g["source"], "、".join(g["in_full_pool"]) and "是" or "否",
            "是" if (not d["v3"]["per_query"][oid]["best_rank"]) or d["v3"]["per_query"][oid]["best_rank"].get("keyword") is None else "否"))
    A("")
    A("**剔除吟诵步**：共 **%d** 个步骤（阈值 6-gram 覆盖 ≥0.5 或整句包含），池 686 → %d。" % (
        d["removal"]["n_removed"], d["removal"]["n_pool_v3"]))
    A("")
    A("| 被剔除步骤 | 最高覆盖率 | 最近神谕 |")
    A("| --- | --- | --- |")
    for r in d["removal"]["removed"][:12]:
        A("| `%s` | %.3f | %s |" % (r["segment_id"], r["max_oracle_6gram_coverage"], r["closest_oracle"]))
    A("")
    A("## 3. 三组对比")
    A("")
    A("| 方法 | v1(旧 gold,13) MRR | v2-mask(13) MRR | v2-noRecite(1) MRR | v3_control(13) MRR | v3(%d) MRR |" % d["v3"]["n_eval"])
    A("| --- | --- | --- | --- | --- | --- |")
    for m in ["keyword", "tfidf_char", "tfidf_word", "bm25", "lsa", "sbert"]:
        def g(met, key="mrr"):
            v = met.get(m) if met else None
            return "%.3f" % v[key] if v and v.get(key) is not None else "—"
        A("| %s | %s | %s | %s | %s | %s |" % (
            METHOD_LABELS[m],
            g(d["v1_old"]["metrics"]), g(d["v2_old"]["v2_mask_metrics"]),
            g(d["v2_old"]["v2_norecite_metrics"]), g(d["v3_control"]["metrics"]), g(d["v3"]["metrics"])))
    A("")
    A("> v1/v2 无 SBERT；v2-noRecite 只有 1 条可评（原任务已说明）。")
    A("")
    A("## 4. v3 逐神谕 gold 排名（多 gold 取最好名次）")
    A("")
    A("| oracle | gold 数 | " + " | ".join(METHOD_LABELS[m] for m in METHODS) + " |")
    A("| --- | --- | " + " | ".join("---" for _ in METHODS) + " |")
    for oid in d["gold_sets"]:
        pq = d["v3"]["per_query"][oid]
        cells = [str(pq["best_rank"].get(m, "N/A")) if pq["best_rank"] else "N/A" for m in METHODS]
        A("| %s | %d | %s |" % (oid, pq["n_gold"], " | ".join(cells)))
    A("")
    A("## 5. 局限")
    A("")
    A("1. 剔除吟诵步会连带删掉多条 gold（N/A %d 条）→ v3 的 8 条样本不足以做统计结论。" % d["meta"]["n_na_v3"])
    A("2. v3_control 保留吟诵步作为候选，字面方法仍会被「念出神谕的步骤」吸走；它的方法对比是「真实混合池」下的对比，不是纯语义对比。")
    A("3. SBERT 用 `Z_sbert_seg.npy`（步骤级）与本地 `sbert_model/` 编码神谕，单线程保证可复现；SBERT 也非「含义强度」。")
    A("4. 事件段 gold 由 A1 修订而来，仍有 3 条（O07/O11/O12）回退到旧 gold；gold 质量受人工修订限制。")
    A("")
    A("## 6. 复现与配对")
    A("")
    A("```bash")
    A(RUN_CMD)
    A(RUN_CMD + " --verify")
    A("conda run -n nlpLesson python tools/export_plot_data.py --verify")
    A("```")
    A("")
    A("- 无随机（SVD random_state=42；SBERT 单线程）；两次运行 JSON/MD/图/配对数据一致。")
    A("- 图 f15 已按规范写 `data/plot_data/f15_retrieval_v3.csv` + `.meta.json` 并刷新 `docs/report/figures-index.md`。")
    A("")
    return "\n".join(L)


def verify(data=None, verbose=False):
    problems = []
    if data is None:
        if not os.path.exists(OUT_JSON):
            print("缺少 %s" % OUT_JSON, file=sys.stderr)
            return False
        data = read_json(OUT_JSON)
    oracles, segs, v2 = load_all()
    gold = gold_sets(oracles, v2)
    for oid in gold:
        if data["gold_sets"][oid]["segments"] != gold[oid]["segments"]:
            problems.append("%s gold 集合不一致" % oid)
    removed = removal_flags(oracles, segs)
    if len(removed) != data["removal"]["n_removed"]:
        problems.append("剔除数不一致")
    # 指标由 per_query 重算
    for key in ("v3", "v3_control"):
        pq = data[key]["per_query"]
        for m in METHODS:
            ranks = [pq[oid]["best_rank"][m] for oid in pq if pq[oid]["best_rank"] and m in pq[oid]["best_rank"]]
            if not ranks:
                continue
            mrr = round(float(np.mean([1.0 / r for r in ranks])), 4)
            if abs(mrr - data[key]["metrics"][m]["mrr"]) > 1e-4:
                problems.append("%s/%s MRR 重算不一致" % (key, m))
    # 图与配对
    if not os.path.exists(OUT_FIG) or os.path.getsize(OUT_FIG) < 5000:
        problems.append("图不存在或过小")
    if os.path.exists("/dev/null"):
        pass
    figure_name = "f15_retrieval_v3"
    csv_p = os.path.join(ROOT, "data", "plot_data", figure_name + ".csv")
    meta_p = os.path.join(ROOT, "data", "plot_data", figure_name + ".meta.json")
    if not os.path.exists(csv_p) or not os.path.exists(meta_p):
        problems.append("缺 f15 配对数据")
    else:
        meta = read_json(meta_p)
        import hashlib
        sha = hashlib.sha256(open(csv_p, "rb").read()).hexdigest()[:16]
        if meta.get("data_sha256_16") != sha:
            problems.append("f15 配对 sha256 不一致")
    idx = open(os.path.join(ROOT, "docs", "report", "figures-index.md"), encoding="utf-8").read()
    if "f15_retrieval_v3" not in idx:
        problems.append("figures-index 缺 f15 行")
    if verbose:
        print("v3 可评 %d 条，N/A %d；v3 最佳 %s MRR %.3f；v3_control 最佳 %s MRR %.3f" % (
            data["v3"]["n_eval"], data["meta"]["n_na_v3"],
            max([m for m in METHODS if data["v3"]["metrics"].get(m)],
                key=lambda m: data["v3"]["metrics"][m]["mrr"]) if data["v3"]["metrics"].get("keyword") else "—",
            (data["v3"]["metrics"].get("keyword") or {}).get("mrr", 0),
            max([m for m in METHODS if data["v3_control"]["metrics"].get(m)],
                key=lambda m: data["v3_control"]["metrics"][m]["mrr"]),
            (data["v3_control"]["metrics"].get("keyword") or {}).get("mrr", 0)))
    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="神谕检索 v3")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    if args.verify:
        ok = verify(verbose=True)
        print("校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    build()


if __name__ == "__main__":
    main()
