"""
export_sbert.py — 导出中文句向量（sentence-transformers, CPU）
模型：BAAI/bge-small-zh-v1.5（512 维，约 95 MB；首次运行会下载）
输出（data/models/）：
  Z_sbert_seg.npy   686×512  步骤级句向量（text_all）
  Z_sbert_rec.npy   26332×512 记录级句向量（text_clean）；如内存/时间紧张可只跑需要子集
  S_sbert_seg.npy   686×686  句向量余弦相似度
  S_sbert_oracle_seg.npy 13×686（神谕文本向量 vs 步骤）
  S_sbert_anchor_seg.npy 14×686（概念锚点）
  manifest_sbert.json
对齐：行顺序与 data/models/ids.json 完全一致（segments / records / oracles / anchors）。
运行：conda run -n nlpLesson python tools/export_sbert.py [--records]
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "models")
os.makedirs(OUT, exist_ok=True)

ids = json.load(open(os.path.join(OUT, "ids.json"), encoding="utf-8"))
segs = [json.loads(x) for x in open(os.path.join(ROOT, "data/corpus/segments.jsonl"), encoding="utf-8") if x.strip()]
recs = [json.loads(x) for x in open(os.path.join(ROOT, "data/corpus/amphoreus.final.jsonl"), encoding="utf-8") if x.strip()]
oracles = [json.loads(x) for x in open(os.path.join(ROOT, "data/corpus/oracles.jsonl"), encoding="utf-8") if x.strip()]
filled = json.load(open(os.path.join(ROOT, "data/config/oracle-fulfillment.v2.json"), encoding="utf-8"))
knife = json.load(open(os.path.join(ROOT, "data/config/knife-scenes.json"), encoding="utf-8"))

from sentence_transformers import SentenceTransformer  # noqa: E402

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
model = SentenceTransformer(MODEL_NAME, device="cpu")
print("model loaded:", MODEL_NAME, "dim:", model.get_sentence_embedding_dimension(), flush=True)

seg_docs = [s.get("text_all") or "" for s in segs if s["segment_id"] in set(ids["segments"])]
order = {sid: i for i, sid in enumerate(ids["segments"])}
seg_docs = [""] * len(ids["segments"])
for s in segs:
    if s["segment_id"] in order:
        seg_docs[order[s["segment_id"]]] = s.get("text_all") or ""
Z_seg = model.encode(seg_docs, batch_size=32, show_progress_bar=True, normalize_embeddings=True).astype(np.float32)
np.save(os.path.join(OUT, "Z_sbert_seg.npy"), Z_seg)

from sklearn.preprocessing import normalize  # noqa: E402
S_seg = (normalize(Z_seg) @ normalize(Z_seg).T).astype(np.float32)
np.save(os.path.join(OUT, "S_sbert_seg.npy"), S_seg)

q_oracle = model.encode([o["text"] for o in oracles], normalize_embeddings=True).astype(np.float32)
np.save(os.path.join(OUT, "S_sbert_oracle_seg.npy"), (normalize(q_oracle) @ normalize(Z_seg).T).astype(np.float32))

anchors = ids["anchors"]
q_anchor = model.encode(anchors, normalize_embeddings=True).astype(np.float32)
np.save(os.path.join(OUT, "S_sbert_anchor_seg.npy"), (normalize(q_anchor) @ normalize(Z_seg).T).astype(np.float32))

# 记录级（可选，慢；--records 开启）
if "--records" in sys.argv:
    order_r = {rid: i for i, rid in enumerate(ids["records"])}
    rec_docs = [""] * len(ids["records"])
    for r in recs:
        if r.get("id") in order_r:
            rec_docs[order_r[r["id"]]] = r.get("text_clean") or ""
    Z_rec = model.encode(rec_docs, batch_size=64, show_progress_bar=True, normalize_embeddings=True).astype(np.float32)
    np.save(os.path.join(OUT, "Z_sbert_rec.npy"), Z_rec)
    print("Z_sbert_rec:", Z_rec.shape, flush=True)

manifest = {
    "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    "script": "tools/export_sbert.py",
    "model": MODEL_NAME,
    "dim": int(Z_seg.shape[1]),
    "device": "cpu",
    "artifacts": [],
}
for f in ["Z_sbert_seg.npy", "S_sbert_seg.npy", "S_sbert_oracle_seg.npy", "S_sbert_anchor_seg.npy"] + (["Z_sbert_rec.npy"] if os.path.exists(os.path.join(OUT, "Z_sbert_rec.npy")) else []):
    p = os.path.join(OUT, f)
    manifest["artifacts"].append({
        "file": f,
        "size_bytes": os.path.getsize(p),
        "sha256_16": hashlib.sha256(open(p, "rb").read()).hexdigest()[:16],
        "shape": list(np.load(p, mmap_mode="r").shape),
    })
json.dump(manifest, open(os.path.join(OUT, "manifest_sbert.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("done:", [(a["file"], a["shape"]) for a in manifest["artifacts"]])
