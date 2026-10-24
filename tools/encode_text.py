"""encode_text.py — 把任意文本（如角色曲歌词）编码进已归档的向量空间，并做相似度检索。

用法：
  conda run -n nlpLesson python tools/encode_text.py --text "要编码的文本" [--out data/plot_data/query_x.json]
  conda run -n nlpLesson python tools/encode_text.py --file lyrics.txt --char 白厄

输出：
  - 两种空间（TF-IDF / SBERT）的向量与元信息
  - 与目标角色全部台词（记录级）的 Top-k
  - 与 13 条神谕的相似度矩阵
  - （--char 指定时）与目标角色自己的神谕、以及 14 条角色曲线的近似位置
口径：歌词是篇外语料，只能给"向量接近程度"，不能当"含义证明"。
"""
from __future__ import annotations

import sys
sys.path.insert(0, __file__.rsplit(chr(92),1)[0])
try:
    import tokenize_compat
except Exception:
    from tools import tokenize_compat
tokenize_compat.install()

import argparse
import json
import os

import joblib
import numpy as np
from sklearn.preprocessing import normalize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "data", "models")


def read_jsonl(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--char", default="")
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    text = args.text
    if args.file:
        text = open(args.file, encoding="utf-8").read().strip()
    if not text:
        raise SystemExit("需要 --text 或 --file")

    ids = json.load(open(os.path.join(MODELS, "ids.json"), encoding="utf-8"))
    recs = read_jsonl("data/corpus/amphoreus.final.jsonl")
    oracles = read_jsonl("data/corpus/oracles.jsonl")
    rec_by_id = {r["id"]: r for r in recs}

    # TF-IDF
    vec = joblib.load(os.path.join(MODELS, "vec_rec.joblib"))
    q_tf = normalize(vec.transform([text]))
    X_tf = vec.transform([r.get("text_clean") or "" for r in recs])
    sim_tf = (normalize(X_tf) @ q_tf.T).toarray().ravel()

    # SBERT（优先本地模型）
    local_model = os.path.join(MODELS, "sbert_model")
    model_path = local_model if os.path.isdir(local_model) else "BAAI/bge-small-zh-v1.5"
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(model_path, device="cpu")
    q_sb = m.encode([text], normalize_embeddings=True)[0].astype(np.float32)
    Z = np.load(os.path.join(MODELS, "Z_sbert_rec.npy"))
    sim_sb = (normalize(Z) @ q_sb.reshape(1, -1).T).ravel()

    # 记录级 Top-k
    def topk(sim, k):
        idx = np.argsort(-sim)[:k]
        out = []
        for i in idx:
            rid = ids["records"][int(i)]
            r = rec_by_id.get(rid, {})
            out.append({
                "record_id": int(rid),
                "score": round(float(sim[int(i)]), 6),
                "speaker": r.get("canonical_speaker") or r.get("speaker"),
                "version": r.get("version"),
                "task": r.get("task"),
                "step_idx": r.get("step_idx"),
                "text": (r.get("text_clean") or r.get("text") or "")[:80],
            })
        return out

    # 神谕相似度
    oracle_texts = [o["text"] for o in oracles]
    o_tf = normalize(vec.transform(oracle_texts))
    oracle_sim_tf = (o_tf @ q_tf.T).toarray().ravel()
    o_sb = m.encode(oracle_texts, normalize_embeddings=True)
    oracle_sim_sb = (normalize(np.asarray(o_sb)) @ q_sb.reshape(1, -1).T).ravel()

    char_result = None
    if args.char:
        rec_ids = ids["records"]
        char_rows = [i for i, rid in enumerate(rec_ids) if (rec_by_id.get(rid, {}).get("canonical_speaker") == args.char)]
        if char_rows:
            char_tf = normalize(np.asarray(X_tf[char_rows].todense()))
            char_sb = normalize(Z[char_rows])
            centroid_tf = normalize(np.asarray(char_tf.mean(axis=0)).reshape(1, -1))
            centroid_sb = normalize(char_sb.mean(axis=0).reshape(1, -1))
            own_map = {"白厄": "O09", "万敌": "O03", "阿格莱雅": "O01", "缇宝": "O02", "遐蝶": "O04",
                       "那刻夏": "O06", "风堇": "O07", "赛飞儿": "O08", "海瑟音": "O10",
                       "刻律德菈": "O11", "昔涟": "O13", "丹恒": "O12"}
            own_id = own_map.get(args.char)
            own_sim = None
            if own_id:
                for i, o in enumerate(oracles):
                    if o["oracle_id"] == own_id:
                        own_sim = {"oracle_id": own_id, "tfidf": round(float(oracle_sim_tf[i]), 6),
                                   "sbert": round(float(oracle_sim_sb[i]), 6)}
                        break

            def char_topk(sim, k):
                order_ = np.argsort(-sim)[:k]
                out = []
                for j in order_:
                    rid = rec_ids[char_rows[int(j)]]
                    r = rec_by_id.get(rid, {})
                    out.append({
                        "record_id": int(rid),
                        "score": round(float(sim[int(j)]), 6),
                        "version": r.get("version"),
                        "task": r.get("task"),
                        "step_idx": r.get("step_idx"),
                        "text": (r.get("text_clean") or r.get("text") or "")[:80],
                    })
                return out

            char_result = {
                "char": args.char,
                "n_records": len(char_rows),
                "centroid_similarity": {"tfidf": round(float((centroid_tf @ q_tf.T).ravel()[0]), 6),
                                        "sbert": round(float((centroid_sb @ q_sb.reshape(-1, 1)).ravel()[0]), 6)},
                "own_oracle": own_sim,
                "char_topk_tfidf": char_topk(sim_tf[char_rows], args.topk),
                "char_topk_sbert": char_topk(sim_sb[char_rows], args.topk),
            }
        else:
            char_result = {"char": args.char, "n_records": 0, "note": "该角色无记录（检查 canonical_speaker 拼写）"}

    result = {
        "char_target": char_result,
        "input": {"chars": len(text), "charset_sample": text[:80]},
        "spaces": {"tfidf_dim": int(vec.transform([text]).shape[1]), "sbert_dim": int(q_sb.shape[0])},
        "tfidf_topk": topk(sim_tf, args.topk),
        "sbert_topk": topk(sim_sb, args.topk),
        "oracle_similarity": [
            {"oracle_id": o["oracle_id"], "holder": o["holder"], "text": o["text"][:40],
             "tfidf": round(float(oracle_sim_tf[i]), 6), "sbert": round(float(oracle_sim_sb[i]), 6)}
            for i, o in enumerate(oracles)
        ],
        "method_note": "TF-IDF=词面相似；SBERT=句子级语义相似；均非“含义证明”。篇外语料与游戏台词分布不同，仅作探索性对照。",
    }
    out = args.out or os.path.join(ROOT, "data", "plot_data", "query_result.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("written:", out)
    print("TF-IDF top1:", result["tfidf_topk"][0]["speaker"], result["tfidf_topk"][0]["text"])
    print("SBERT  top1:", result["sbert_topk"][0]["speaker"], result["sbert_topk"][0]["text"])


if __name__ == "__main__":
    main()
