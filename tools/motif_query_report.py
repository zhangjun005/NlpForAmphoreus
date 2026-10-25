"""motif_query_report.py — 把"短文本/母题"（角色曲、明天见、再见面）当作查询，跑与角色质心/神谕/最近台词的对照
用法：python tools/motif_query_report.py --text "明天见"
"""
import argparse
import io
import json
import os
import sys

import joblib
import numpy as np
from sklearn.preprocessing import normalize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tokenize_compat
tokenize_compat.install()
from sentence_transformers import SentenceTransformer

MODELS = os.path.join(ROOT, "data", "models")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--topk", type=int, default=12)
    args = ap.parse_args()
    text = args.text

    ids = json.load(io.open(os.path.join(MODELS, "ids.json"), encoding="utf-8"))
    recs = {}
    for line in io.open(os.path.join(ROOT, "data/corpus/amphoreus.final.jsonl"), encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            recs[r["id"]] = r
    rec_ids = ids["records"]
    Z = np.load(os.path.join(MODELS, "Z_sbert_rec.npy"))
    vec = joblib.load(os.path.join(MODELS, "vec_rec.joblib"))
    X = vec.transform([recs[i].get("text_clean") or "" for i in rec_ids])
    m = SentenceTransformer(os.path.join(MODELS, "sbert_model"), device="cpu")
    qs = m.encode([text], normalize_embeddings=True)[0]
    qt = normalize(vec.transform([text]))

    # 角色质心
    cent = np.load(os.path.join(MODELS, "character_centroids.npz"))
    chars = []
    for k in cent.files:
        if k.startswith("sbert_") and k.count("_") == 1:
            c = k[len("sbert_"):]
            chars.append({"char": c,
                          "sbert": round(float(np.dot(cent[k], qs)), 4),
                          "tfidf": round(float((cent["tfidf_" + c] @ np.asarray(qt.todense()).ravel())), 4)})
    chars.sort(key=lambda x: -x["sbert"])

    # 神谕
    oracles = [json.loads(l) for l in io.open(os.path.join(ROOT, "data/corpus/oracles.jsonl"), encoding="utf-8") if l.strip()]
    otexts = [o["text"] for o in oracles]
    ot = normalize(vec.transform(otexts))
    ot_sims = np.asarray((ot @ qt.T).todense()).ravel()
    osb = m.encode(otexts, normalize_embeddings=True)
    osim = [{"oracle_id": o["oracle_id"], "holder": o["holder"], "sbert": round(float(np.dot(osb[i], qs)), 4),
             "tfidf": round(float(ot_sims[i]), 4)} for i, o in enumerate(oracles)]
    osim.sort(key=lambda x: -x["sbert"])

    # 包含该短语的记录（承载句）
    occ = []
    for rid in rec_ids:
        r = recs[rid]
        if text in (r.get("text_clean") or ""):
            occ.append({"record_id": int(rid), "version": r.get("version"), "task": r.get("task"),
                        "speaker": r.get("canonical_speaker") or r.get("speaker"), "text": r.get("text_clean")})
    by_ver = {}
    for o in occ:
        by_ver[o["version"]] = by_ver.get(o["version"], 0) + 1

    # 最接近、但不含该短语的台词
    sims = (normalize(Z) @ qs.reshape(-1, 1)).ravel()
    order = np.argsort(-sims)
    near = []
    for k in order:
        rid = rec_ids[int(k)]
        r = recs[rid]
        if text in (r.get("text_clean") or ""):
            continue
        near.append({"record_id": int(rid), "score": round(float(sims[int(k)]), 4),
                     "version": r.get("version"), "speaker": r.get("canonical_speaker") or r.get("speaker"),
                     "text": (r.get("text_clean") or "")[:60]})
        if len(near) >= args.topk:
            break

    out = {"query": text, "n_occurrences": len(occ), "by_version": by_ver, "occurrences": occ,
           "char_centroids": chars, "oracle_similarity": osim, "nearest_lines_without_phrase": near,
           "note": "短语被当作查询文本；角色质心=该角色全部台词向量平均；相似度不是含义强度"}
    outpath = args.out or os.path.join(ROOT, "data/config/motif-query.json")
    json.dump(out, io.open(outpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("query =", text)
    print("occurrences =", len(occ), "by_version =", by_ver)
    print("char centroids top5:", " | ".join(f"{c['char']}:{c['sbert']}" for c in chars[:5]))
    print("oracles top5:", " | ".join(f"{o['oracle_id']}({o['holder']}):{o['sbert']}" for o in osim[:5]))
    print("nearest (no phrase):", " | ".join(f"{n['record_id']}:{n['score']}" for n in near[:5]))
    print("written:", outpath)


if __name__ == "__main__":
    main()
