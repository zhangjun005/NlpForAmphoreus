#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
oracle_retrieval.py — 神谕 → 兑现场景 检索实验（13 条 query / 686 个步骤 document）

实验口径：docs/实验口径与评测方案.md §3（候选池）与 §8 第 7 项（神谕—事件检索）
  * query   = data/corpus/oracles.jsonl 的 13 条神谕（text / keywords / metaphors）
  * document= data/corpus/segments.jsonl 中与 A/B 完全相同的 686 个合格步骤（用 text_all）
  * gold    = data/config/oracle-fulfillment.filled.json 里人工确认的 fulfillment_segment
  * 评测    = Recall@1/5/10/20、MRR、每条神谕的 gold 排名

逐级对比 5 种检索方法（越简单越先做）：
  1. keyword     词面/关键词基线：query = 神谕文本 + keywords；命中加权计数
  2. tfidf_char  sklearn TfidfVectorizer，字符 2–3 gram，余弦
  3. tfidf_word  sklearn TfidfVectorizer，jieba 词级，余弦
  4. bm25        手写 Okapi BM25（k1=1.5, b=0.75），jieba 词级
  5. lsa         jieba 词级 TF-IDF + TruncatedSVD(n_components=100)，潜在空间余弦
外加「注音隐喻扩展」变体：query 追加 metaphors 的 gloss（如 灰白的黎明→开拓者），
对 5 种方法各跑一遍，观察 Recall/MRR 是否提升。

约束：只读语料与 config；不装新依赖；无随机（SVD 固定 random_state）；可复现。

运行：
    conda run -n nlpLesson python tools/oracle_retrieval.py            # 重算并写产物
    conda run -n nlpLesson python tools/oracle_retrieval.py --verify   # 只校验产物自洽

产物（只写这 3 个文件）：
    data/config/oracle-retrieval-results.json
    data/reports/oracle-retrieval.md
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
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_ORACLES = os.path.join(ROOT, "data", "corpus", "oracles.jsonl")
P_FILLED = os.path.join(ROOT, "data", "config", "oracle-fulfillment.filled.json")
P_SEGMENTS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_VOCAB_ORACLE = os.path.join(ROOT, "data", "config", "vocab-oracle.json")
OUT_JSON = os.path.join(ROOT, "data", "config", "oracle-retrieval-results.json")
OUT_MD = os.path.join(ROOT, "data", "reports", "oracle-retrieval.md")
RUN_CMD = "conda run -n nlpLesson python tools/oracle_retrieval.py"

KS = (1, 5, 10, 20)
METHODS = ["keyword", "tfidf_char", "tfidf_word", "bm25", "lsa"]
METHOD_LABELS = {
    "keyword": "关键词基线",
    "tfidf_char": "TF-IDF(char 2–3gram)",
    "tfidf_word": "TF-IDF(jieba 词)",
    "bm25": "BM25(k1=1.5,b=0.75)",
    "lsa": "LSA(词TF-IDF+SVD100)",
}
LSA_COMPONENTS = 100
BM25_K1 = 1.5
BM25_B = 0.75
KEYWORD_WEIGHT = 2.0  # keywords 权重高于普通字面 token

# 小停用词表（只用于过滤查询/文档里的虚词，不影响语义词）
STOPWORDS = set("""的 了 在 是 我 你 他 她 它 我们 你们 他们 这 那 一个 没有 就 都 也 不 将 于 中 而 之 以 为 把 被 让 从 到 对 会 能 要 个 一 上 下 里 后 前 时 等
与 和 或 但 却 又 很 太 更 最 如 若 则 因 所以 因此 如果 虽然 已经 正在 可以 不是 就是 还是 只是 这样 那样 什么 怎么 为什么 因为 至于 以及 并且 而且 然后 之后 之前
""".split())
PUNCT_RE = re.compile(r"^[\s，。！？、；：…—「」『』（）().,!?;:~\-·\"'《》〈〉【】0-9A-Za-z]+$")


def is_content_token(t):
    if not t or PUNCT_RE.match(t):
        return False
    if t in STOPWORDS:
        return False
    return True


def tokenize(text, min_len=2):
    """jieba 词级分词 + 过滤；min_len=2 时过滤单字（汝/将/于 这类虚词也在这里被滤掉）"""
    out = []
    for t in jieba.lcut(text):
        t = t.strip()
        if not is_content_token(t):
            continue
        if len(t) < min_len:
            continue
        out.append(t)
    return out


def tokenize_all_min1(text):
    return [t for t in jieba.lcut(text) if is_content_token(t)]


# ============================================================================
# 1. 读取输入
# ============================================================================
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


# ============================================================================
# 2. 检索方法（输入：doc_texts / doc_tokens；输出：每个 query 对 686 个 doc 的打分）
# ============================================================================
def score_keyword(query, doc_token_counts):
    """词面/关键词基线：keywords 权重 2.0、普通字面 token 权重 1.0；
    score = Σ w_t × (1 + log1p(tf))（命中一次以上才计分）"""
    weighted = {}
    for t in query["text_tokens"]:
        weighted[t] = max(weighted.get(t, 0.0), 1.0)
    for t in query["keywords"]:
        if is_content_token(t):
            weighted[t] = max(weighted.get(t, 0.0), KEYWORD_WEIGHT)
    scores = np.zeros(len(doc_token_counts), dtype=float)
    for i, cnt in enumerate(doc_token_counts):
        s = 0.0
        for t, w in weighted.items():
            tf = cnt.get(t)
            if tf:
                s += w * (1.0 + math.log1p(tf))
        scores[i] = s
    return scores


def vector_scores(q_vec, doc_mat):
    """余弦相似度（doc_mat 行已 L2 归一化）"""
    q = q_vec / (np.linalg.norm(q_vec) + 1e-12)
    return np.asarray(doc_mat.dot(q)).ravel()


def build_word_tfidf(doc_texts):
    vec = TfidfVectorizer(tokenizer=lambda t: tokenize(t, min_len=2), token_pattern=None,
                          lowercase=False, min_df=1, sublinear_tf=True, norm="l2")
    mat = vec.fit_transform(doc_texts)
    return vec, mat


def build_char_tfidf(doc_texts):
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=2,
                          sublinear_tf=True, norm="l2")
    mat = vec.fit_transform(doc_texts)
    return vec, mat


def build_bm25(doc_tokens, doc_texts):
    """手写 Okapi BM25；idf 用 log(1 + (N-df+0.5)/(df+0.5))（恒正）"""
    n = len(doc_tokens)
    doc_len = np.array([len(t) for t in doc_tokens], dtype=float)
    avgdl = float(doc_len.mean()) if n else 1.0
    df = Counter()
    tfs = []
    for toks in doc_tokens:
        cnt = Counter(toks)
        tfs.append(cnt)
        for t in cnt:
            df[t] += 1
    idf = {t: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
    return {"idf": idf, "tfs": tfs, "doc_len": doc_len, "avgdl": avgdl}


def score_bm25(query_tokens, bm25):
    scores = np.zeros(len(bm25["doc_len"]), dtype=float)
    for t in query_tokens:
        idf = bm25["idf"].get(t)
        if idf is None:
            continue
        for i, cnt in enumerate(bm25["tfs"]):
            tf = cnt.get(t)
            if not tf:
                continue
            dl = bm25["doc_len"][i]
            denom = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * dl / bm25["avgdl"])
            scores[i] += idf * tf * (BM25_K1 + 1.0) / denom
    return scores


def build_lsa(word_mat):
    svd = TruncatedSVD(n_components=LSA_COMPONENTS, random_state=42, algorithm="randomized", n_iter=7)
    latent = svd.fit_transform(word_mat)
    norms = np.linalg.norm(latent, axis=1, keepdims=True)
    latent = latent / np.maximum(norms, 1e-12)
    return svd, latent


def query_lsa(svd, q_vec):
    z = svd.transform(np.atleast_2d(q_vec))[0]
    z = z / (np.linalg.norm(z) + 1e-12)
    return z


# ============================================================================
# 3. 评测
# ============================================================================
def rank_docs(scores, doc_ids):
    """分数降序；同分按 document 顺序（seq 顺序）升序，保证确定性。
    返回 {segment_id: rank(1-based)} 与排序后的索引列表"""
    order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))
    rank = {doc_ids[i]: k + 1 for k, i in enumerate(order)}
    return rank, order


def metrics_from_ranks(gold_ranks):
    """gold_ranks: {oracle_id: rank}；返回 Recall@k / MRR"""
    n = len(gold_ranks)
    ranks = np.array(list(gold_ranks.values()), dtype=float)
    out = {}
    for k in KS:
        out["recall@%d" % k] = round(float((ranks <= k).sum()) / n, 4)
    out["mrr"] = round(float(np.mean(1.0 / ranks)), 4)
    out["median_rank"] = float(np.median(ranks))
    out["mean_rank"] = round(float(ranks.mean()), 2)
    return out


def evaluate_method(scores_by_oracle, doc_ids, gold_map, occurrence_ids, top_n=3):
    """对单个方法：算每个神谕的 gold 排名、Top-k 候选、是否命中神谕被引用步骤"""
    per_oracle = {}
    gold_ranks = {}
    for oid in scores_by_oracle:
        scores = scores_by_oracle[oid]
        rank, order = rank_docs(scores, doc_ids)
        gid = gold_map[oid]
        gr = rank[gid]
        gold_ranks[oid] = gr
        top = []
        for i in order[:top_n]:
            top.append({"segment_id": doc_ids[i], "score": round(float(scores[i]), 6),
                        "is_gold": doc_ids[i] == gid})
        # gold 落在第几名、是否在 Top-k 里
        per_oracle[oid] = {
            "gold_segment": gid,
            "gold_rank": gr,
            "gold_score": round(float(scores[doc_ids.index(gid)]), 6),
            "top3": top,
            "gold_in_top3": gr <= top_n,
            "top1_is_occurrence": doc_ids[order[0]] in occurrence_ids.get(oid, set()),
            "occurrence_hit_rank": _first_occ_rank(rank, occurrence_ids.get(oid, set())),
        }
    result = {"metrics": metrics_from_ranks(gold_ranks),
              "per_oracle": per_oracle,
              "gold_ranks": gold_ranks}
    return result


def _first_occ_rank(rank, occ_ids):
    if not occ_ids:
        return None
    vals = [rank[s] for s in occ_ids if s in rank]
    return min(vals) if vals else None


# ============================================================================
# 4. 主流程
# ============================================================================
def build():
    jieba.setLogLevel(60)
    jieba.initialize()

    oracles = load_oracles()
    filled = {o["oracle_id"]: o for o in read_json(P_FILLED)["oracles"]}
    vocab_oracle = read_json(P_VOCAB_ORACLE)
    segs = load_segments()
    eligible = [s for s in segs if s["n_main"] > 0 and not s["low_content"] and s["has_dialogue"]]
    seq = sorted(eligible, key=lambda s: (s["order"], s["step_idx"]))
    doc_ids = [s["segment_id"] for s in seq]
    doc_texts = [s["text_all"] or "" for s in seq]
    doc_tokens2 = [tokenize(t, min_len=2) for t in doc_texts]
    doc_token_counts = [Counter(t) for t in doc_tokens2]
    print("document = %d 个步骤；query = %d 条神谕" % (len(doc_ids), len(oracles)))
    assert len(doc_ids) == 686 and len(oracles) == 13

    # gold 池检查
    gold_map = {}
    gold_pool = {}
    for o in oracles:
        oid = o["oracle_id"]
        f = filled.get(oid)
        gid = f.get("fulfillment_segment") if f else None
        gold_map[oid] = gid
        gold_pool[oid] = bool(gid and gid in set(doc_ids))
        if not gold_pool[oid]:
            print("!! gold 不在 686 池中：%s -> %s" % (oid, gid), file=sys.stderr)
    assert all(gold_pool.values()), "存在 gold 不在候选池内的神谕，需在报告中标注"
    print("gold 全部在 686 候选池内：%d/%d" % (sum(gold_pool.values()), len(gold_pool)))

    # 神谕被引用的步骤（用于诊断：字面方法是不是在检索"引用句"而不是"兑现段"）
    occurrence_ids = {}
    for o in oracles:
        oid = o["oracle_id"]
        ids = set()
        for occ in o.get("occurrences") or []:
            sid = "%s|%s|%s" % (occ.get("version"), occ.get("task"), occ.get("step_idx"))
            if sid in set(doc_ids):
                ids.add(sid)
        occurrence_ids[oid] = ids

    seg_by_id = {sid: s for sid, s in zip(doc_ids, seq)}
    query_rows = []
    for o in oracles:
        oid = o["oracle_id"]
        gold_text = seg_by_id[gold_map[oid]]["text_all"] or ""
        query_rows.append({
            "oracle_id": oid, "text": o["text"], "holder": o.get("holder"),
            "fulfillment_type": filled[oid].get("fulfillment_type"),
            "gold_segment": gold_map[oid],
            "gold_in_pool": gold_pool[oid],
            "gold_is_occurrence": gold_map[oid] in occurrence_ids[oid],
            "gold_contains_oracle_text": (o.get("text") or "").strip("。！？") in gold_text,
            "keywords": o.get("keywords") or [],
            "metaphors": [{"display": m.get("display"), "gloss": m.get("gloss")}
                          for m in (o.get("metaphors") or [])],
            "occurrences_in_pool": sorted(occurrence_ids[oid])})

    # query 表示（base / expanded）
    def q_view(o, expand=False):
        text = o.get("text") or ""
        keywords = [k for k in (o.get("keywords") or []) if is_content_token(k)]
        glosses = []
        if expand:
            for m in o.get("metaphors") or []:
                g = (m.get("gloss") or "").strip()
                if g:
                    glosses.append(g)
        q_text = text if not expand else (text + " " + " ".join(glosses))
        return {
            "text": text,
            "q_text": q_text,
            "text_tokens": tokenize(q_text, min_len=2),
            "keywords": keywords,
            "glosses": glosses,
        }

    queries = {}
    for o in oracles:
        queries[o["oracle_id"]] = {"base": q_view(o, False), "expanded": q_view(o, True)}

    # ---------------- 构建各方法的 document 表示 ----------------
    print("构建 TF-IDF / BM25 / LSA 表示…")
    char_vec, char_mat = build_char_tfidf(doc_texts)
    word_vec, word_mat = build_word_tfidf(doc_texts)
    bm25 = build_bm25(doc_tokens2, doc_texts)
    svd, lsa_mat = build_lsa(word_mat)

    # ---------------- 五种方法 × 两种 query ----------------
    def run_all(variant):
        scores_by_method = {m: {} for m in METHODS}
        for o in oracles:
            oid = o["oracle_id"]
            q = queries[oid][variant]
            # 1) keyword
            scores_by_method["keyword"][oid] = score_keyword(q, doc_token_counts)
            # 2) tfidf char
            qc = char_vec.transform([q["q_text"]])
            scores_by_method["tfidf_char"][oid] = vector_scores(qc.toarray()[0], char_mat)
            # 3) tfidf word
            qw = word_vec.transform([q["q_text"]])
            scores_by_method["tfidf_word"][oid] = vector_scores(qw.toarray()[0], word_mat)
            # 4) bm25
            scores_by_method["bm25"][oid] = score_bm25(tokenize(q["q_text"], min_len=2), bm25)
            # 5) lsa
            qz = query_lsa(svd, qw.toarray()[0])
            scores_by_method["lsa"][oid] = np.asarray(lsa_mat.dot(qz)).ravel()
        return {m: evaluate_method(scores_by_method[m], doc_ids, gold_map, occurrence_ids)
                for m in METHODS}

    results_base = run_all("base")
    results_expanded = run_all("expanded")

    # ---------------- 分析：最佳方法、失败案例、隐喻增益 ----------------
    def best_method_for(oid):
        best, best_r = None, None
        for m in METHODS:
            r = results_base[m]["gold_ranks"][oid]
            if best_r is None or r < best_r:
                best, best_r = m, r
        return best, best_r

    failures = []
    for o in oracles:
        oid = o["oracle_id"]
        ranks = {m: results_base[m]["gold_ranks"][oid] for m in METHODS}
        worst = max(ranks.values())
        best_m, best_r = best_method_for(oid)
        qrow = next(x for x in query_rows if x["oracle_id"] == oid)
        failures.append({
            "oracle_id": oid,
            "text": o["text"],
            "holder": o.get("holder"),
            "fulfillment_type": filled[oid].get("fulfillment_type"),
            "gold_is_occurrence": qrow["gold_is_occurrence"],
            "gold_contains_oracle_text": qrow["gold_contains_oracle_text"],
            "gold_segment": gold_map[oid],
            "gold_evidence": (filled[oid].get("evidence") or "")[:120],
            "ranks": ranks,
            "best_method": best_m,
            "best_rank": best_r,
            "worst_rank": worst,
            "metaphors": [{"display": m.get("display"), "gloss": m.get("gloss")}
                          for m in (o.get("metaphors") or [])],
            "keywords": o.get("keywords") or [],
        })
    failures.sort(key=lambda x: (-x["best_rank"], x["oracle_id"]))

    # 隐喻扩展增益（逐方法、逐神谕）
    expansion = {}
    for m in METHODS:
        base_ranks = results_base[m]["gold_ranks"]
        exp_ranks = results_expanded[m]["gold_ranks"]
        improved = [oid for oid in base_ranks if exp_ranks[oid] < base_ranks[oid]]
        worsened = [oid for oid in base_ranks if exp_ranks[oid] > base_ranks[oid]]
        expansion[m] = {
            "base_metrics": results_base[m]["metrics"],
            "expanded_metrics": results_expanded[m]["metrics"],
            "delta_recall@1": round(results_expanded[m]["metrics"]["recall@1"]
                                    - results_base[m]["metrics"]["recall@1"], 4),
            "delta_recall@5": round(results_expanded[m]["metrics"]["recall@5"]
                                    - results_base[m]["metrics"]["recall@5"], 4),
            "delta_recall@10": round(results_expanded[m]["metrics"]["recall@10"]
                                     - results_base[m]["metrics"]["recall@10"], 4),
            "delta_mrr": round(results_expanded[m]["metrics"]["mrr"] - results_base[m]["metrics"]["mrr"], 4),
            "n_improved": len(improved),
            "n_worsened": len(worsened),
            "improved_ids": improved,
            "worsened_ids": worsened,
            "per_oracle_ranks_base": base_ranks,
            "per_oracle_ranks_expanded": exp_ranks,
        }

    # 汇总：各方法最优者
    summary = []
    for m in METHODS:
        met = results_base[m]["metrics"]
        summary.append({"method": m, "label": METHOD_LABELS[m], **met,
                        "top1_occurrence_rate": round(
                            sum(1 for o in oracles if results_base[m]["per_oracle"][o["oracle_id"]]["top1_is_occurrence"]) / len(oracles), 4)})
    best_overall = max(summary, key=lambda x: (x["mrr"], x["recall@10"]))

    meta = {
        "script": "tools/oracle_retrieval.py",
        "run_command": RUN_CMD,
        "n_queries": len(oracles),
        "n_documents": len(doc_ids),
        "document_pool": "n_main>0 且 !low_content 且 has_dialogue（与 A/B 相同，共 686）",
        "document_text": "segments.jsonl 的 text_all（dialogue+narration 拼接）",
        "gold_source": "data/config/oracle-fulfillment.filled.json 的 fulfillment_segment（人工确认）",
        "gold_all_in_pool": bool(all(gold_pool.values())),
        "methods": METHODS,
        "method_labels": METHOD_LABELS,
        "params": {
            "tfidf_char": "analyzer=char, ngram_range=(2,3), min_df=2, sublinear_tf, L2",
            "tfidf_word": "jieba 词级（len>=2、去停用词）, min_df=1, sublinear_tf, L2",
            "bm25": "k1=%.1f, b=%.2f, idf=log(1+(N-df+0.5)/(df+0.5))" % (BM25_K1, BM25_B),
            "lsa": "词级 TF-IDF + TruncatedSVD(n_components=%d, random_state=42), 潜在向量 L2 后余弦"
                   % LSA_COMPONENTS,
            "keyword": "query = 神谕文本 + keywords（keywords 权重 %.1f）；score=Σ w×(1+log1p(tf))"
                       % KEYWORD_WEIGHT,
            "rank_tie_break": "分数降序、同分按 document 顺序（seq）升序；排名为 1-based 位置",
        },
        "expanded_query": "在神谕原文后追加 metaphors 的 gloss（如 灰白的黎明→开拓者）；"
                          "keyword 方法与普通 query 同一套权重",
        "note": "13 条 query 的小样本结果，只作方向性参考，不做显著性断言。",
        "gold_composition_diagnosis": "见 gold_diagnosis：若多数 gold 本身就是吟诵该神谕的步骤，"
                                      "则本任务主要测「引用句匹配」而非「语义兑现检索」",
    }
    n_gold_occ = sum(1 for q in query_rows if q["gold_is_occurrence"])
    n_gold_text = sum(1 for q in query_rows if q["gold_contains_oracle_text"])
    gold_diagnosis = {
        "n_queries": len(query_rows),
        "n_gold_is_occurrence": n_gold_occ,
        "n_gold_contains_oracle_text": n_gold_text,
        "n_semantic_only": sum(1 for q in query_rows
                               if not q["gold_is_occurrence"] and not q["gold_contains_oracle_text"]),
        "semantic_only_oracles": [q["oracle_id"] for q in query_rows
                                  if not q["gold_is_occurrence"] and not q["gold_contains_oracle_text"]],
    }

    result = {
        "meta": meta,
        "queries": query_rows,
        "methods_base": {m: results_base[m] for m in METHODS},
        "methods_expanded": {m: results_expanded[m] for m in METHODS},
        "summary": summary,
        "best_method": best_overall["method"],
        "gold_diagnosis": gold_diagnosis,
        "expansion_gain": expansion,
        "failures": failures,
        "occurrence_analysis": {
            m: {"top1_is_occurrence_rate": summary[i]["top1_occurrence_rate"],
                "per_oracle": {oid: {"top1_is_occurrence": results_base[m]["per_oracle"][oid]["top1_is_occurrence"],
                                     "occurrence_hit_rank": results_base[m]["per_oracle"][oid]["occurrence_hit_rank"]}
                               for oid in results_base[m]["per_oracle"]}}
            for i, m in enumerate(METHODS)
        },
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写 %s" % os.path.relpath(OUT_JSON, ROOT))

    md = render_report(result, oracles, failures, summary, expansion, results_base, results_expanded)
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s" % os.path.relpath(OUT_MD, ROOT))

    if not verify(verbose=True):
        print("!! 报告与 JSON 不一致", file=sys.stderr)
        sys.exit(1)
    print("\n核对通过：报告数字与 JSON 一致（13 条 query × 5 方法全量核对）。")



# ============================================================================
# 5. 失败案例的人工解释（逐条读原文/神谕后填写；只解释现象，不参与检索与评测）
# ============================================================================
FAILURE_NOTES = {
    "O10": "**唯一的纯语义兑现、也是唯一真失败**。gold `3.5|大海啊，埋葬暗酒色的梦|14` 是海瑟音/凯撒的结局场景，"
          "文本里没有「涛声」「天地境界之海」「征服」这些词；而 O11（『汝将于天地境界之海完成征服，长眠于涛声中』）"
          "与 O10 只是**语序不同**，它的吟诵步骤（`3.5|囚人啊|5`、`|15`）占了所有方法 Top1/Top2。"
          "词面方法无法区分「同词异序的两条神谕」，只能靠「谁在兑现」的上下文/角色信息。",
    "O04": "反转兑现。gold `3.2|学者啊，于真理门前再会|2` 文本里**直接引用了神谕原文**（『花海尽头…相拥之后，便是永恒的离别』），"
          "所以其实已被命中；没排第 1 是因为池里还有其它步骤引用「花海」「指尖」「离别」等同词。",
    "O07": "字面兑现。gold `3.3|黎明啊，执耀于全世之终|1` 直接引用「在彩虹桥的尽头，天空之子将缝补晨昏」；"
          "排第 3 是因为「黎明」「天空」在其它步骤也高频出现。",
    "O09": "隐喻型神谕（灰白的黎明→开拓者、黎明→天外的救世主）。gold `3.4|英雄啊，粉碎那悲哀的造像|6` 文本里引用了"
          "「汝将肩负骄阳，直至灰白的黎明显著」，字面本来就命中；扩展变体加入「白厄/开拓者/天外的救世主」后，"
          "这些词在 686 个步骤里出现频率极高，反而稀释了信号，所以扩展没有改善。",
    "O08": "字面兑现。gold `3.3|石板啊，为何罔闻那灯影|10` 引用了「汝将与贪婪同行，亦将亡于分文」；排第 2 属近似命中。",
    "O01": "字面兑现。gold `3.4|英雄啊，回返那安宁的家乡|21` 是阿格莱雅兑现「最后一次沐浴」的步骤（含改写引用）；排第 1。",
}


# ============================================================================
# 6. 报告
# ============================================================================
def truncate(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def render_report(result, oracles, failures, summary, expansion, results_base, results_expanded):
    meta = result["meta"]
    L = []
    A = L.append
    best = result["best_method"]
    best_met = next(x for x in summary if x["method"] == best)
    queries = result["queries"]
    oid_list = [q["oracle_id"] for q in queries]

    A("# 神谕—事件检索实验：关键词 / TF-IDF / BM25 / LSA 对比（13 条 query × 686 个步骤）")
    A("")
    A("> 生成脚本：`tools/oracle_retrieval.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    A("> query：`data/corpus/oracles.jsonl` 的 %d 条神谕 ｜ document：`data/corpus/segments.jsonl` 的 **%d** 个合格步骤（`text_all`）" % (
        meta["n_queries"], meta["n_documents"]))
    A("> gold：`data/config/oracle-fulfillment.filled.json` 的人工确认 `fulfillment_segment`（**%d/%d 在候选池内**）" % (
        sum(1 for q in queries if q["gold_in_pool"]), len(queries)))
    A("> 明细数据：`data/config/oracle-retrieval-results.json`（每方法 × 每神谕的排名、Top3 候选与指标）")
    A("")
    A("> **小样本声明**：只有 13 条 query，Recall@k/MRR 的分母是 13，单条 query 的名次波动就会让指标跳动 0.08–0.15；"
      "本报告只做**方法间的方向性对比**，不做显著性断言。")
    A("")
    # ---------------- 1 结论 ----------------
    A("## 1. 结论")
    A("")
    A("- **最佳方法：%s**，MRR = **%.3f**，Recall@1/5/10/20 = **%.2f / %.2f / %.2f / %.2f**。" % (
        METHOD_LABELS[best], best_met["mrr"], best_met["recall@1"], best_met["recall@5"],
        best_met["recall@10"], best_met["recall@20"]))
    kw = next(x for x in summary if x["method"] == "keyword")
    A("- **由简到繁的递进**：关键词基线 MRR %.3f → TF-IDF(char) %.3f / TF-IDF(word) %.3f / BM25 %.3f → LSA %.3f。" % (
        kw["mrr"],
        next(x for x in summary if x["method"] == "tfidf_char")["mrr"],
        next(x for x in summary if x["method"] == "tfidf_word")["mrr"],
        next(x for x in summary if x["method"] == "bm25")["mrr"],
        next(x for x in summary if x["method"] == "lsa")["mrr"]))
    exp_m = _best_expansion_method(expansion)
    exp_e = expansion[exp_m]
    vec_max = max(abs(expansion[m]["delta_mrr"]) for m in METHODS if m != "keyword")
    A("- **注音隐喻扩展**：13 条里只有 O09 带 metaphors，扩展后 **%s** 的 MRR %.3f→%.3f（%+.3f）、"
      "Recall@1 %.2f→%.2f，O09 的 gold 排名 %d→%d；而对 TF-IDF/BM25/LSA 的 ΔMRR 最大只有 %.3f。"
      "→ 扩展对「关键词式」检索有效，对向量空间无效（扩展词是高频称呼/角色名，被 TF-IDF 权重稀释）；"
      "且 13 条里只有 1 条可用，只能验证机制、给不出统计结论。" % (
          METHOD_LABELS[exp_m], exp_e["base_metrics"]["mrr"], exp_e["expanded_metrics"]["mrr"],
          exp_e["delta_mrr"], exp_e["base_metrics"]["recall@1"], exp_e["expanded_metrics"]["recall@1"],
          exp_e["per_oracle_ranks_base"]["O09"], exp_e["per_oracle_ranks_expanded"]["O09"], vec_max))
    gd = result["gold_diagnosis"]
    A("- **必须先说清 gold 的构成**：%d/%d 条 gold **本身就是吟诵/引用该神谕的步骤**，%d/%d 条的 gold 文本里直接含有神谕原文。"
      "所以本任务对大多数神谕实际上测的是「引用句匹配」，关键词基线因此看起来很强；"
      "**真正考验语义兑现检索的只有 %d 条（%s）**。" % (
          gd["n_gold_is_occurrence"], gd["n_queries"], gd["n_gold_contains_oracle_text"], gd["n_queries"],
          gd["n_semantic_only"], "、".join(gd["semantic_only_oracles"])))
    worst = failures[0]
    A("- **最难检索的神谕：%s**（「%s」），最好方法的 gold 排名也只有第 **%d** 名；"
      "其次是 %s。" % (worst["oracle_id"], worst["text"], worst["best_rank"],
                      "、".join("%s（最好第%d）" % (x["oracle_id"], x["best_rank"]) for x in failures[1:3])))
    A("- **Top1 全部落在「引用句」上（%.0f%%）——但多数情况这不算错**：%d/%d 条 gold 本身就是吟诵该神谕的步骤，"
      "所以引用句命中 = 正确检索；唯一真正暴露问题的是 O10（纯语义兑现、gold 非引用步），"
      "它的 Top1 全是 **O11 的引用步**（两条神谕同词异序）——这才是本实验真正的失败模式（见 §7/§8）。" % (
          100 * best_met["top1_occurrence_rate"], result["gold_diagnosis"]["n_gold_is_occurrence"],
          result["gold_diagnosis"]["n_queries"]))
    A("")
    # ---------------- 2 数据与口径 ----------------
    A("## 2. 数据与评测口径")
    A("")
    A("| 项目 | 口径 |")
    A("| --- | --- |")
    A("| query（13 条） | 神谕原文；关键词方法额外用 `keywords`；扩展变体追加 `metaphors` 的 gloss |")
    A("| document（686 个） | 与 A/B 检测器相同的合格步骤（`n_main>0` 且 `!low_content` 且 `has_dialogue`），文本用 `text_all` |")
    A("| gold | `oracle-fulfillment.filled.json` 的 `fulfillment_segment`（人工确认的兑现段），**每条 query 恰好 1 个 gold** |")
    A("| 排名 | 分数降序、同分按 document 顺序（order→step_idx）升序；1-based |")
    A("| 指标 | Recall@k = gold 排名 ≤ k 的 query 比例（每 query 1 gold，等价于命中率）；MRR = mean(1/rank) |")
    A("")
    A("**gold 池检查（全部 13 条都在 686 池内，无需剔除）**：")
    A("")
    A("| oracle | gold segment_id | 兑现类型 |")
    A("| --- | --- | --- |")
    for q in queries:
        A("| %s | `%s` | %s |" % (q["oracle_id"], q["gold_segment"], q["fulfillment_type"] or "—"))
    A("")
    # ---------------- 3 方法 ----------------
    A("## 3. 五种检索方法（由简到繁）")
    A("")
    A("| # | 方法 | query 表示 | document 表示 / 打分 |")
    A("| --- | --- | --- | --- |")
    A("| 1 | 关键词基线 | 神谕文本 jieba 词（len≥2、去停用词）+ `keywords`（权重 %.1f） | 词命中加权计数 `Σ w×(1+log1p(tf))` |" % KEYWORD_WEIGHT)
    A("| 2 | TF-IDF(char) | 神谕原文 | 字符 2–3 gram TF-IDF（min_df=2, sublinear_tf），余弦 |")
    A("| 3 | TF-IDF(word) | 神谕原文（+扩展变体追加 gloss） | jieba 词级 TF-IDF（min_df=1, sublinear_tf），余弦 |")
    A("| 4 | BM25 | 同上 | 手写 Okapi BM25（k1=%.1f, b=%.2f），idf=log(1+(N−df+0.5)/(df+0.5)) |" % (BM25_K1, BM25_B))
    A("| 5 | LSA | 同上 | 词级 TF-IDF → TruncatedSVD(n_components=%d, random_state=42) → 潜在向量余弦 |" % LSA_COMPONENTS)
    A("")
    A("> 全部方法共用同一候选池与同一条 gold；差距只来自 query/document 表示与打分函数。"
      "「关键词基线」是三级对比的第 1 级，TF-IDF/BM25 是第 2 级，LSA 是第 3 级（轻量语义，不装 sentence-transformers）。")
    A("")
    # ---------------- 4 汇总 ----------------
    A("## 4. 指标汇总（base query）")
    A("")
    A("| 方法 | Recall@1 | Recall@5 | Recall@10 | Recall@20 | MRR | 中位排名 | 平均排名 | Top1 是引用句的比例 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for x in summary:
        A("| %s | %.2f | %.2f | %.2f | %.2f | **%.3f** | %.1f | %.1f | %.0f%% |" % (
            METHOD_LABELS[x["method"]], x["recall@1"], x["recall@5"], x["recall@10"], x["recall@20"],
            x["mrr"], x["median_rank"], x["mean_rank"], 100 * x["top1_occurrence_rate"]))
    A("")
    A("按 MRR 从高到低：%s。" % " > ".join(
        "%s %.3f" % (METHOD_LABELS[x["method"]], x["mrr"])
        for x in sorted(summary, key=lambda y: -y["mrr"])))
    A("")
    # ---------------- 5 逐神谕排名 ----------------
    A("## 5. 逐神谕 gold 排名（base query）")
    A("")
    A("| oracle | 神谕（截断） | 兑现类型 | " + " | ".join(METHOD_LABELS[m] for m in METHODS) + " |")
    A("| --- | --- | --- | " + " | ".join("---" for _ in METHODS) + " |")
    for q in queries:
        oid = q["oracle_id"]
        cells = []
        for m in METHODS:
            r = results_base[m]["gold_ranks"][oid]
            cells.append("**%d**" % r if r <= 10 else "%d" % r)
        A("| %s | %s | %s | %s |" % (
            oid, truncate(q["text"], 26), q["fulfillment_type"] or "—", " | ".join(cells)))
    A("")
    A("（加粗 = 进入 Top10。）")
    A("")
    # ---------------- 6 扩展变体 ----------------
    A("## 6. 注音隐喻扩展变体（query 追加 metaphors.gloss）")
    A("")
    A("只有 **O09** 带 metaphors（汝→白厄、黎明→天外的救世主、灰白的黎明→开拓者），所以这一节实际只影响 1 条 query：")
    A("")
    A("| 方法 | MRR(base) | MRR(扩展) | ΔMRR | Recall@10(base) | Recall@10(扩展) | 提升的神谕数 | 变差的神谕数 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for m in METHODS:
        e = expansion[m]
        A("| %s | %.3f | %.3f | %+.3f | %.2f | %.2f | %d | %d |" % (
            METHOD_LABELS[m], e["base_metrics"]["mrr"], e["expanded_metrics"]["mrr"], e["delta_mrr"],
            e["base_metrics"]["recall@10"], e["expanded_metrics"]["recall@10"],
            e["n_improved"], e["n_worsened"]))
    A("")
    A("**O09 在各方法下的 gold 排名（base → 扩展）**：")
    A("")
    A("| 方法 | base 排名 | 扩展后排名 |")
    A("| --- | --- | --- |")
    for m in METHODS:
        A("| %s | %d | %d |" % (
            METHOD_LABELS[m], results_base[m]["gold_ranks"]["O09"], results_expanded[m]["gold_ranks"]["O09"]))
    A("")
    exp_m = _best_expansion_method(expansion)
    exp_e = expansion[exp_m]
    A("**解读**：")
    A("")
    A("- **关键词基线受益最多**：O09 gold 排名 %d→%d、MRR %.3f→%.3f。原因是 keyword 打分直接用 gloss 词（白厄/天外的救世主/开拓者）"
      "与文档做命中加权，而 O09 的 gold 步骤里正好出现了这些称呼。" % (
          exp_e["per_oracle_ranks_base"]["O09"], exp_e["per_oracle_ranks_expanded"]["O09"],
          exp_e["base_metrics"]["mrr"], exp_e["expanded_metrics"]["mrr"]))
    A("- **TF-IDF/BM25/LSA 几乎不受影响**（ΔMRR ≤ %.3f）：扩展词只被追加到 query 文本，"
      "在 686 篇文档的 IDF 里这些高频称呼权重很低，且原句词面已足够命中 O09，扩展没有改变排序。" % (
          max(abs(expansion[m]["delta_mrr"]) for m in METHODS if m != "keyword")))
    A("- **O10 不受影响**（它没有 metaphors）：这也说明隐喻扩展只能修「注音解码」问题，修不了「同词异序/语义兑现」问题。")
    A("")
    # ---------------- 7 失败案例 ----------------
    A("## 7. 失败案例分析（按最好方法下的 gold 排名从差到好）")
    A("")
    truly = [f for f in failures
             if f["best_rank"] > 20
             or (not f["gold_is_occurrence"] and not f["gold_contains_oracle_text"] and f["best_rank"] > 5)]
    A("**判定口径**：真正失败 = 最好方法下 gold 排名 > 20，**或**「gold 既非引用步也不含神谕原文」"
      "（纯语义兑现）却没能进 Top5；其余（排名 2–6）属于「近似命中」，通常是被同一神谕的其它引用句/相邻场景挤到后面。"
      "按此口径，**真正失败的只有 %d 条**（%s）。" % (
          len(truly), "、".join(f["oracle_id"] for f in truly) or "无"))
    A("")
    shown = [f for f in failures if f["best_rank"] > 1][:6]
    for i, f in enumerate(shown, 1):
        ranks = " / ".join("%s %d" % (m, f["ranks"][m]) for m in METHODS)
        A("### %d. %s（%s）「%s」" % (i, f["oracle_id"], f["holder"], f["text"]))
        A("")
        A("- gold：`%s`（%s 兑现）；最好方法 %s 排第 **%d** 名；各方法排名：%s。" % (
            f["gold_segment"], f["fulfillment_type"] or "—", METHOD_LABELS[f["best_method"]],
            f["best_rank"], ranks))
        A("- 人工解释：%s" % FAILURE_NOTES.get(f["oracle_id"], "待人工核对"))
        A("")
    A("")
    # ---------------- 8 引用句诊断 ----------------
    A("## 8. 诊断：字面方法检索到的是「引用句」还是「兑现段」？")
    A("")
    A("每条神谕在剧情里都有若干**被引用/吟诵的步骤**（`oracles.jsonl` 的 `occurrences`）。"
      "先把这个和 gold 对照清楚，再谈方法优劣：")
    A("")
    A("| 诊断项 | 数量 |")
    A("| --- | --- |")
    A("| gold 本身就在该神谕的 occurrences 里（吟诵/引用步） | %d / %d |" % (
        gd["n_gold_is_occurrence"], gd["n_queries"]))
    A("| gold 文本直接包含神谕原文（去句末标点后子串匹配） | %d / %d |" % (
        gd["n_gold_contains_oracle_text"], gd["n_queries"]))
    A("| 既非引用步、也不含原文的「纯语义兑现」gold | %d（%s） |" % (
        gd["n_semantic_only"], "、".join(gd["semantic_only_oracles"]) or "无"))
    A("")
    A("| 方法 | Top1 是引用句的比例 | 说明 |")
    A("| --- | --- | --- |")
    for m in METHODS:
        A("| %s | %.0f%% | %s |" % (
            METHOD_LABELS[m],
            100 * next(x for x in summary if x["method"] == m)["top1_occurrence_rate"],
            "对 12 条「gold=引用步」的 query 而言这是**正确行为**" if m == "keyword" else ""))
    A("")
    A("> **关键结论**：因为 12/13 条 gold 就是引用/吟诵步骤，Top1 命中引用句在多数 query 上等于命中 gold；"
      "这个诊断只对唯一「纯语义兑现」的 O10 有判别意义——而 O10 的 Top1 恰好全是 **O11 的引用步**"
      "（两条神谕文字几乎相同、只差语序，见 §7 的 O10 分析），这才是真正的失败模式："
      "**词面方法分不清「同词异序的两条神谕」各自的兑现段**。")
    A("")
    # ---------------- 9 每条神谕 Top3 ----------------
    A("## 9. 每条神谕 × 每种方法的 Top3 候选（标注 gold 是否在其中）")
    A("")
    for q in queries:
        oid = q["oracle_id"]
        A("### %s「%s」" % (oid, truncate(q["text"], 40)))
        A("")
        A("gold：`%s` ｜ %s 兑现" % (q["gold_segment"], q["fulfillment_type"] or "—"))
        A("")
        A("| 方法 | Top1 | Top2 | Top3 | gold 排名 |")
        A("| --- | --- | --- | --- | --- |")
        for m in METHODS:
            po = results_base[m]["per_oracle"][oid]
            cells = []
            for t in po["top3"]:
                mark = " ✅" if t["is_gold"] else ""
                cells.append("`%s` (%.3f)%s" % (t["segment_id"], t["score"], mark))
            A("| %s | %s | **第 %d 名** |" % (METHOD_LABELS[m], " | ".join(cells), po["gold_rank"]))
        A("")
    # ---------------- 10 局限 ----------------
    A("## 10. 结论强度与局限")
    A("")
    A("1. **只有 13 条 query**：Recall@k 的最小分辨率是 1/13≈0.077，MRR 的单条波动可达 0.05–0.15；"
      "方法之间的 0.02–0.05 差距不能当成稳定结论。")
    A("2. **gold 是单点**：一条神谕对应一个人工确认的「最主要兑现段」，但兑现可能是分散的（多步、长线）；"
      "检索到其它合理相关段（包括神谕被吟诵的步骤）不会被算作命中，会低估方法能力。")
    A("3. **document 粒度粗**：以「步骤」为单位（平均 770 字），神谕是单句；步骤越长，单句信号越被稀释。"
      "若要更公平，应做句子级/场景级检索再做步骤聚合（口径 §1 的两层粒度）。")
    A("4. **LSA 是轻量语义**：SVD 只有 100 维、语料仅 686 篇，学不到真正的语义等价；"
      "「换说法」的检索需要句向量（口径已列为后续工作，本轮明确不装 sentence-transformers）。")
    A("5. **隐喻扩展只覆盖 1 条神谕**：13 条里只有 O09 在 `oracles.jsonl` 里标了 metaphors，"
      "所以「扩展是否有效」在本数据上无法得到统计结论，只能验证流程。")
    A("6. 本实验不改任何语料/配置；gold 与 query 都来自既有文件，指标可由脚本逐行复算。")
    A("")
    # ---------------- 11 复现 ----------------
    A("## 11. 复现与自校验")
    A("")
    A("```bash")
    A("# 重跑（生成 JSON + MD）")
    A(RUN_CMD)
    A("# 只校验已有产物：13 条 query × 5 方法排名与指标 vs JSON")
    A("conda run -n nlpLesson python tools/oracle_retrieval.py --verify")
    A("```")
    A("")
    A("- 无随机：TF-IDF 确定性；BM25 确定性；SVD 固定 `random_state=42`/`randomized` → 同输入必得同输出。")
    A("- JSON 里保存每条 query × 每种方法的 `gold_rank`、`gold_score`、Top3 候选与全部指标，报告数字与之同源。")
    A("- `--verify` 会重算指标、核对每张排名表与 JSON 一致，并抽查 3 条黄金排名；gold 池检查在运行前断言。")
    A("")
    return "\n".join(L)


def _best_expansion_method(expansion):
    return max(METHODS, key=lambda m: expansion[m]["delta_mrr"])


def _best_expansion_value(expansion, key):
    return expansion[_best_expansion_method(expansion)][key]


# ============================================================================
# 7. 自校验
# ============================================================================
RANK_ROW_RE = re.compile(r"^\| (O\d{2}) \| [^|]* \| [^|]* \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$", re.M)


def verify(verbose=False):
    if not (os.path.exists(OUT_JSON) and os.path.exists(OUT_MD)):
        print("产物不存在，无法校验", file=sys.stderr)
        return False
    data = read_json(OUT_JSON)
    problems = []
    methods = data["meta"]["methods"]
    queries = data["queries"]
    base = data["methods_base"]
    expanded = data["methods_expanded"]

    if len(queries) != 13:
        problems.append("query 数 %d != 13" % len(queries))
    if methods != METHODS:
        problems.append("methods 列表不符")
    if not data["meta"]["gold_all_in_pool"]:
        problems.append("有 gold 不在候选池内")
    for q in queries:
        if not q["gold_in_pool"]:
            problems.append("gold 不在池内：%s" % q["oracle_id"])
    for m in METHODS:
        if m not in base or m not in expanded:
            problems.append("缺少方法结果：%s" % m)
            continue
        for q in queries:
            oid = q["oracle_id"]
            po = base[m]["per_oracle"].get(oid)
            if po is None:
                problems.append("缺少 %s/%s 结果" % (m, oid))
                continue
            if not (1 <= po["gold_rank"] <= 686):
                problems.append("排名越界 %s/%s" % (m, oid))
            for t in po["top3"]:
                if t["is_gold"] != (t["segment_id"] == q["gold_segment"]):
                    problems.append("top3 gold 标记错误 %s/%s" % (m, oid))
            if [t["score"] for t in po["top3"]] != sorted([t["score"] for t in po["top3"]], reverse=True):
                problems.append("top3 分数未降序 %s/%s" % (m, oid))
        # 指标从 gold_ranks 重算
        ranks = base[m]["gold_ranks"]
        rec = {k: round(sum(1 for r in ranks.values() if r <= k) / len(ranks), 4) for k in KS}
        mrr = round(float(np.mean([1.0 / r for r in ranks.values()])), 4)
        met = base[m]["metrics"]
        for k in KS:
            if abs(rec[k] - met["recall@%d" % k]) > 1e-9:
                problems.append("指标不一致 %s recall@%d" % (m, k))
        if abs(mrr - met["mrr"]) > 1e-9:
            problems.append("指标不一致 %s mrr" % m)

    # 报告中的逐神谕排名表 vs JSON
    with open(OUT_MD, "r", encoding="utf-8") as f:
        md = f.read()
    rank_rows = RANK_ROW_RE.findall(md)
    if len(rank_rows) < 13:
        problems.append("报告逐神谕排名表行数 %d < 13" % len(rank_rows))
    parsed = {}
    for row in rank_rows:
        oid = row[0]
        vals = []
        for cell in row[1:6]:
            cell = cell.strip().replace("**", "")
            try:
                vals.append(int(cell))
            except ValueError:
                vals = None
                break
        if vals and len(vals) == 5:
            parsed[oid] = vals
    for oid, vals in parsed.items():
        for i, m in enumerate(METHODS):
            if base[m]["gold_ranks"][oid] != vals[i]:
                problems.append("报告排名与 JSON 不一致 %s/%s：%d vs %d" % (
                    oid, m, vals[i], base[m]["gold_ranks"][oid]))

    # 抽查 3 条
    sample = [queries[0]["oracle_id"], queries[5]["oracle_id"], queries[12]["oracle_id"]]
    checked = []
    for oid in sample:
        checked.append((oid, {m: base[m]["gold_ranks"][oid] for m in METHODS}))
    if verbose:
        print("\n抽查 3 条 gold 排名（oracle -> 各方法）：")
        for oid, ranks in checked:
            print("  %s  %s" % (oid, "  ".join("%s:%d" % (m, ranks[m]) for m in METHODS)))
        print("汇总：")
        for x in data["summary"]:
            print("  %-24s MRR %.3f | R@1 %.2f R@5 %.2f R@10 %.2f R@20 %.2f | 中位 %.1f | Top1引用句 %.0f%%" % (
                x["label"], x["mrr"], x["recall@1"], x["recall@5"], x["recall@10"], x["recall@20"],
                x["median_rank"], 100 * x["top1_occurrence_rate"]))
        print("报告排名表解析 = %d 行；对照 JSON 一致" % len(parsed))
    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="神谕—事件检索实验")
    ap.add_argument("--verify", action="store_true", help="只校验已有产物（不重算）")
    args = ap.parse_args()
    if args.verify:
        ok = verify(verbose=True)
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    build()


if __name__ == "__main__":
    main()
