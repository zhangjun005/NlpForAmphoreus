"""crystal_flower_analysis.py — 水晶花寓言的向量分析
1) 三个版本（原版 / 昔涟第一改 / 终局第二改）两两相似度；
2) 每版与 14 角色质心、13 神谕的接近程度；
3) 整个 K36 故事作为 query：最像的角色/神谕/非本段台词。
"""
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
recs = {}
for line in io.open(os.path.join(ROOT, "data/corpus/amphoreus.final.jsonl"), encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        recs[r["id"]] = r
ids = json.load(io.open(os.path.join(MODELS, "ids.json"), encoding="utf-8"))
rec_ids = ids["records"]
Z = np.load(os.path.join(MODELS, "Z_sbert_rec.npy"))
vec = joblib.load(os.path.join(MODELS, "vec_rec.joblib"))
X = vec.transform([recs[i].get("text_clean") or "" for i in rec_ids])
m = SentenceTransformer(os.path.join(MODELS, "sbert_model"), device="cpu")
cent = np.load(os.path.join(MODELS, "character_centroids.npz"))
oracles = [json.loads(l) for l in io.open(os.path.join(ROOT, "data/corpus/oracles.jsonl"), encoding="utf-8") if l.strip()]
otexts = [o["text"] for o in oracles]
ot = normalize(vec.transform(otexts))
osb = m.encode(otexts, normalize_embeddings=True)


def text_of(rng):
    return "\n".join((recs[i].get("text_clean") or "") for i in rng if i in recs)


versions = {
    "v0_original": text_of(range(23888, 23901)),   # 德谬歌原版故事
    "v1_xi_rewrite": text_of(range(23901, 23914)), # 昔涟第一改
    "v2_final_rewrite": text_of(range(25226, 25231)),  # 终局第二改
}
full_story = text_of(range(23885, 23914))

# 编码
names = list(versions.keys())
texts = [versions[n] for n in names]
qs = m.encode(texts, normalize_embeddings=True)
qt = normalize(vec.transform(texts))
pairwise = {}
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        pairwise[names[i] + " vs " + names[j]] = {
            "sbert": round(float(np.dot(qs[i], qs[j])), 4),
            "tfidf": round(float((qt[i] @ qt[j].T).toarray()[0, 0] if hasattr(qt[i] @ qt[j].T, "toarray") else 0), 4),
        }

# 每版 vs 角色质心 / 神谕
per_version = {}
for idx, nm in enumerate(names):
    chars = []
    for k in cent.files:
        if k.startswith("sbert_") and k.count("_") == 1:
            c = k[len("sbert_"):]
            chars.append({"char": c, "sbert": round(float(np.dot(cent[k], qs[idx])), 4)})
    chars.sort(key=lambda x: -x["sbert"])
    o_sims = [{"oracle_id": o["oracle_id"], "holder": o["holder"], "sbert": round(float(np.dot(osb[i], qs[idx])), 4)}
              for i, o in enumerate(oracles)]
    o_sims.sort(key=lambda x: -x["sbert"])
    per_version[nm] = {"n_chars": len(versions[nm]), "top_char_centroids": chars[:5], "top_oracles": o_sims[:5]}

# 整个故事作 query
fs = m.encode([full_story], normalize_embeddings=True)[0]
ft = normalize(vec.transform([full_story]))
chars_full = []
for k in cent.files:
    if k.startswith("sbert_") and k.count("_") == 1:
        c = k[len("sbert_"):]
        chars_full.append({"char": c, "sbert": round(float(np.dot(cent[k], fs)), 4)})
chars_full.sort(key=lambda x: -x["sbert"])
o_full = [{"oracle_id": o["oracle_id"], "holder": o["holder"], "sbert": round(float(np.dot(osb[i], fs)), 4)}
          for i, o in enumerate(oracles)]
o_full.sort(key=lambda x: -x["sbert"])
sims = (normalize(Z) @ fs.reshape(-1, 1)).ravel()
order = np.argsort(-sims)
near = []
for k in order:
    rid = rec_ids[int(k)]
    if 23885 <= rid <= 23913 or 25224 <= rid <= 25232:
        continue
    r = recs[rid]
    near.append({"record_id": int(rid), "score": round(float(sims[int(k)]), 4),
                 "version": r.get("version"), "speaker": r.get("canonical_speaker") or r.get("speaker"),
                 "text": (r.get("text_clean") or "")[:60]})
    if len(near) >= 12:
        break

out = {"note": "水晶花寓言的向量分析：三版本两两相似 + 每版最像的角色/神谕 + 整段故事的最近邻",
       "versions": {k: {"chars": len(v), "preview": v[:80]} for k, v in versions.items()},
       "pairwise": pairwise, "per_version": per_version,
       "full_story": {"top_char_centroids": chars_full[:5], "top_oracles": o_full[:5], "nearest_lines": near}}
json.dump(out, io.open(os.path.join(ROOT, "data/config/crystal-flower-analysis.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("=== 三版本两两相似 ===")
for k, v in pairwise.items():
    print(" ", k, v)
print("=== 每版最像的角色（前3）===")
for nm in names:
    print(" ", nm, "|", " , ".join(f"{c['char']}:{c['sbert']}" for c in per_version[nm]["top_char_centroids"][:3]),
          "| 神谕:", " , ".join(f"{o['oracle_id']}:{o['sbert']}" for o in per_version[nm]["top_oracles"][:3]))
print("=== 整个故事 ===")
print(" 角色:", " , ".join(f"{c['char']}:{c['sbert']}" for c in chars_full[:5]))
print(" 神谕:", " , ".join(f"{o['oracle_id']}({o['holder']}):{o['sbert']}" for o in o_full[:5]))
print(" 最近邻:", " , ".join(f"{n['record_id']}:{n['score']}" for n in near[:6]))
