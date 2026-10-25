"""lyric_query_report.py — 歌词 vs 全部角色质心 / 昔涟分版本质心 / 13 神谕，并过滤歌词自身后给最近台词"""
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
LYRICS = io.open(os.path.join(ROOT, "data/config/song-lyrics-xi.txt"), encoding="utf-8").read().strip()
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
qs = m.encode([LYRICS], normalize_embeddings=True)[0]
qt = normalize(vec.transform([LYRICS]))[0]

# 角色质心
cent = np.load(os.path.join(MODELS, "character_centroids.npz"))
char_rows = []
for k in cent.files:
    if k.startswith("sbert_") and k.count("_") == 1:
        c = k[len("sbert_"):]
        sb = float(np.dot(cent[k], qs))
        tf = float(np.dot(cent["tfidf_" + c], qt.toarray().ravel())) if hasattr(qt, "toarray") else float(np.dot(cent["tfidf_" + c], np.asarray(qt).ravel()))
        char_rows.append({"char": c, "sbert": round(sb, 4), "tfidf": round(tf, 4)})
char_rows.sort(key=lambda x: -x["sbert"])

# 昔涟按版本质心
xi_versions = []
for k in cent.files:
    if k.startswith("sbert_昔涟_") and k.count("_") == 2:
        v = k.split("_")[-1]
        xi_versions.append({"version": v, "sbert": round(float(np.dot(cent[k], qs)), 4)})
xi_versions.sort(key=lambda x: -x["sbert"])

# 歌词自身与语料块相似度（确认是否同一文本）
self_sims = []
for i, rid in enumerate(rec_ids):
    if 26218 <= rid <= 26241:
        r = recs[rid]
        s = float(np.dot(normalize(Z[i:i + 1])[0], qs))
        self_sims.append({"record_id": rid, "sbert": round(s, 4), "text": (r.get("text_clean") or "")[:40]})
self_sims.sort(key=lambda x: -x["sbert"])

# 最近的"非歌词"台词（按 SBERT）
sims_sb = (normalize(Z) @ qs.reshape(-1, 1)).ravel()
order = np.argsort(-sims_sb)
top_non_lyric = []
for k in order:
    rid = rec_ids[int(k)]
    if 26218 <= rid <= 26241:
        continue
    r = recs[rid]
    top_non_lyric.append({"record_id": int(rid), "score": round(float(sims_sb[int(k)]), 4),
                          "speaker": r.get("canonical_speaker") or r.get("speaker"),
                          "version": r.get("version"), "task": r.get("task"),
                          "step_idx": r.get("step_idx"),
                          "text": (r.get("text_clean") or r.get("text") or "")[:60]})
    if len(top_non_lyric) >= 15:
        break

# 神谕相似度
oracles = [json.loads(l) for l in io.open(os.path.join(ROOT, "data/corpus/oracles.jsonl"), encoding="utf-8") if l.strip()]
otexts = [o["text"] for o in oracles]
ot = normalize(vec.transform(otexts))
ot_sims = np.asarray((ot @ qt.reshape(-1, 1)).todense()).ravel()
osb = m.encode(otexts, normalize_embeddings=True)
o_sim = []
for i, o in enumerate(oracles):
    o_sim.append({"oracle_id": o["oracle_id"], "holder": o["holder"],
                  "tfidf": round(float(ot_sims[i]), 4),
                  "sbert": round(float(np.dot(osb[i], qs)), 4), "text": o["text"][:30]})
o_sim.sort(key=lambda x: -x["sbert"])

out = {"note": "歌词《昔涟》vs 角色质心 / 昔涟分版本质心 / 13 神谕 / 最近台词（已过滤歌词自身 24 条）",
       "lyrics_chars": len(LYRICS),
       "char_centroids": char_rows, "xi_version_centroids": xi_versions,
       "lyrics_self_block": {"n": len(self_sims), "max_sbert": self_sims[0]["sbert"] if self_sims else None,
                             "sample": self_sims[:3]},
       "top_non_lyric_lines": top_non_lyric, "oracle_similarity": o_sim}
json.dump(out, io.open(os.path.join(ROOT, "data/config/lyric-query-xi.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("=== 角色质心最接近（SBERT）===")
for r in char_rows[:6]:
    print(f"  {r['char']}: SBERT {r['sbert']} / TF-IDF {r['tfidf']}")
print("=== 昔涟按版本质心 ===")
for r in xi_versions:
    print(f"  {r['version']}: {r['sbert']}")
print("=== 歌词与语料歌词块 ===", out["lyrics_self_block"]["max_sbert"])
print("=== 最近的非歌词台词（SBERT）===")
for r in top_non_lyric[:8]:
    print(f"  {r['record_id']} {r['version']} {r['speaker']}: {r['text']} ({r['score']})")
print("=== 神谕相似度（SBERT 前 5）===")
for r in o_sim[:5]:
    print(f"  {r['oracle_id']} {r['holder']}: SBERT {r['sbert']} / TF-IDF {r['tfidf']}")
