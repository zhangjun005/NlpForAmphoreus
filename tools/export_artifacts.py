"""
export_artifacts.py — 导出可复用的语义中间产物（供后续「意义变化」分析）

设计原则
- 复现：所有向量空间、分词器、LSA 模型、相似度矩阵都落盘；后续分析不必重算。
- 对齐：所有矩阵都附带 id 顺序文件，行/列可回查。
- 可核对：manifest 记录 shape/dtype/sha256/来源脚本。
- 不含原始语料（合规）：只存派生向量与 id。

运行：conda run -n nlpLesson python tools/export_artifacts.py
输出目录：data/models/（本地，不入 git；manifest 另行记录在 docs/中间产物清单.md）
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone

import joblib
import jieba
import numpy as np
import scipy.sparse as sp
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "models")
os.makedirs(OUT, exist_ok=True)

# ---------------- 数据读取 ----------------
def read_jsonl(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


SEGS = read_jsonl("data/corpus/segments.jsonl")
RECS = read_jsonl("data/corpus/amphoreus.final.jsonl")
ORACLES = read_jsonl("data/corpus/oracles.jsonl")
KNIFE = json.load(open(os.path.join(ROOT, "data/config/knife-scenes.json"), encoding="utf-8"))
FILLED = json.load(open(os.path.join(ROOT, "data/config/oracle-fulfillment.v2.json"), encoding="utf-8"))

ELIG = [s for s in SEGS if s.get("has_dialogue") and not s.get("low_content") and s.get("n_main", 0) > 0]
SEG_IDS = [s["segment_id"] for s in ELIG]
SEG_DOCS = [s.get("text_all") or "" for s in ELIG]

# ---------------- 分词 ----------------
STOP = set("""
的 了 是 在 我 你 他 她 它 我们 你们 他们 这 那 这个 那个 一个 一种 什么 怎么 为什么 不 也 都 就 而 与 和 或
但 却 又 很 更 最 非常 已经 还是 因为 所以 如果 虽然 但是 然后 可以 没有 不是 自己 这样 那样 一些 这些 那些
啊 吧 呢 吗 呀 哦 唉 嗯 唔 诶 哈 呵 诶 之 其 者 也 矣 焉 哉
""".split())
KEEP_SINGLE = set("汝 吾 尔 她 他 我 你 花 海 火 光 梦 死 生 爱 痛 刀 剑 星 月 日 夜 风 雨 雪 冰 雷".split())

TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+")

def tokenize(text: str):
    toks = []
    for w in jieba.cut(text or ""):
        w = w.strip()
        if not w:
            continue
        if w in STOP:
            continue
        if len(w) == 1 and w not in KEEP_SINGLE and not w.isdigit() and not w.isascii():
            continue
        toks.append(w)
    return toks


VEC_PARAMS = dict(analyzer=tokenize, ngram_range=(1, 2), min_df=1, sublinear_tf=True, dtype=np.float32)
vec_word = TfidfVectorizer(**VEC_PARAMS)
X_word = vec_word.fit_transform(SEG_DOCS)          # 686 × V
vec_char = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=2, sublinear_tf=True, dtype=np.float32)
X_char = vec_char.fit_transform(SEG_DOCS)          # 686 × Vc

svd = TruncatedSVD(n_components=100, random_state=42)
Z_seg = svd.fit_transform(X_word).astype(np.float32)   # 686 × 100

# 记录级空间（26,332 条）
REC_DOCS = [r.get("text_clean") or "" for r in RECS]
REC_IDS = [r.get("id") for r in RECS]
vec_rec = TfidfVectorizer(analyzer=tokenize, ngram_range=(1, 2), min_df=2, sublinear_tf=True, dtype=np.float32)
X_rec = vec_rec.fit_transform(REC_DOCS)
svd_rec = TruncatedSVD(n_components=100, random_state=42)
Z_rec = svd_rec.fit_transform(X_rec).astype(np.float32)  # 26332 × 100

# ---------------- 相似度 ----------------
def cosm(A, B=None):
    A = normalize(A)
    if B is None:
        return (A @ A.T).toarray().astype(np.float32)
    return (normalize(B) @ A.T).toarray().astype(np.float32)

S_seg = cosm(X_word)                     # 686×686
ORACLE_TEXTS = [o["text"] for o in ORACLES]
ORACLE_Q = vec_word.transform(ORACLE_TEXTS)
S_oracle_seg = cosm(X_word, ORACLE_Q)    # 13×686
KNIFE_TEXTS = [f"{k['title']} {k.get('why','')}" for k in KNIFE["scenes"]]
KNIFE_Q = vec_word.transform(KNIFE_TEXTS)
S_knife_seg = cosm(X_word, KNIFE_Q)      # 35×686

ANCHORS = ["英雄", "救世主", "记忆", "明天", "毁灭", "花", "海", "黎明", "讲述者", "听众", "预言", "神谕", "命运", "牺牲"]
ANCHOR_Q = vec_word.transform(ANCHORS)
S_anchor_seg = cosm(X_word, ANCHOR_Q)    # 14×686

# 神谕→记录级相似度（供意义履历在记录粒度上定位）
ORACLE_Q_REC = vec_rec.transform(ORACLE_TEXTS)
S_oracle_rec = cosm(X_rec, ORACLE_Q_REC).astype(np.float32)   # 13×26332

# ---------------- 落盘 ----------------
def save(path, obj):
    p = os.path.join(OUT, path)
    if path.endswith(".npz"):
        sp.save_npz(p, obj, compressed=True)
    elif path.endswith(".npy"):
        np.save(p, obj)
    elif path.endswith(".joblib"):
        joblib.dump(obj, p, compress=3)
    elif path.endswith(".json"):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    return p

files = []
files.append(save("vec_word.joblib", vec_word))
files.append(save("vec_char.joblib", vec_char))
files.append(save("vec_rec.joblib", vec_rec))
files.append(save("X_word.npz", X_word))
files.append(save("X_char.npz", X_char))
files.append(save("svd_seg.joblib", svd))
files.append(save("svd_rec.joblib", svd_rec))
files.append(save("Z_seg.npy", Z_seg))
files.append(save("Z_rec.npy", Z_rec))
files.append(save("S_seg.npy", S_seg))
files.append(save("S_oracle_seg.npy", S_oracle_seg))
files.append(save("S_knife_seg.npy", S_knife_seg))
files.append(save("S_anchor_seg.npy", S_anchor_seg))
files.append(save("S_oracle_rec.npy", S_oracle_rec))
files.append(save("ids.json", {
    "segments": SEG_IDS,
    "records": REC_IDS,
    "oracles": [o["oracle_id"] for o in ORACLES],
    "oracle_texts": ORACLE_TEXTS,
    "knife_scenes": [k["id"] for k in KNIFE["scenes"]],
    "knife_titles": KNIFE_TEXTS,
    "anchors": ANCHORS,
    "knife_segment_ids": [k.get("segment_ids", []) for k in KNIFE["scenes"]],
    "note": "所有矩阵行/列顺序与这里一致",
}))
files.append(save("tokens_segments.json", [tokenize(d) for d in SEG_DOCS]))
files.append(save("vocab_word.json", {k: int(v) for k, v in vec_word.vocabulary_.items()}))
files.append(save("vocab_rec.json", {k: int(v) for k, v in vec_rec.vocabulary_.items()}))

# 基线特征矩阵（从既有结论 JSON 导出，供后续建模/对照）
def feat_matrix(scores_path):
    d = json.load(open(os.path.join(ROOT, scores_path), encoding="utf-8"))
    segs = d.get("segments") or []
    ids = [s["segment_id"] for s in segs]
    feats = segs[0]["features"] if segs else {}
    names = list(feats.keys())
    M = np.array([[s["features"][n].get("raw", s["features"][n].get("raw_value", 0)) for n in names] for s in segs], dtype=np.float32)
    return ids, names, M

def save_feat(out_name, rel):
    try:
        ids, names, M = feat_matrix(rel)
        np.save(os.path.join(OUT, out_name + ".npy"), M)
        with open(os.path.join(OUT, out_name + ".json"), "w", encoding="utf-8") as f:
            json.dump({"ids": ids, "feature_names": names}, f, ensure_ascii=False)
        files.append(os.path.join(OUT, out_name + ".npy"))
        files.append(os.path.join(OUT, out_name + ".json"))
    except Exception as e:  # noqa: BLE001
        print("skip", out_name, e)

save_feat("feat_A", "data/config/baseline-a-scores.json")
save_feat("feat_B", "data/config/baseline-b-scores.json")

# ---------------- manifest ----------------
manifest = {
    "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    "script": "tools/export_artifacts.py",
    "run_command": "conda run -n nlpLesson python tools/export_artifacts.py",
    "python": __import__("sys").version.split()[0],
    "jieba": jieba.__version__ if hasattr(jieba, "__version__") else "unknown",
    "spaces": {
        "seg_word": {"n_docs": len(SEG_IDS), "n_features": int(X_word.shape[1]), "params": "analyzer=jieba, ngram=(1,2), min_df=1, sublinear_tf, stopwords+单字过滤"},
        "seg_char": {"n_docs": len(SEG_IDS), "n_features": int(X_char.shape[1]), "params": "char(2,3), min_df=2"},
        "rec_word": {"n_docs": len(REC_IDS), "n_features": int(X_rec.shape[1]), "params": "analyzer=jieba, ngram=(1,2), min_df=2"},
        "lsa": {"n_components": 100, "random_state": 42},
    },
    "artifacts": [],
}
for p in files:
    p = p if os.path.isabs(p) else os.path.join(OUT, p)
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    manifest["artifacts"].append({
        "file": os.path.basename(p),
        "size_bytes": os.path.getsize(p),
        "sha256_16": h,
        "shape": list(np.load(p).shape) if p.endswith(".npy") else None,
    })
with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print("== 导出完成 ==")
print(f"segment 空间: {X_word.shape} / char {X_char.shape} / LSA {Z_seg.shape}")
print(f"record 空间: {X_rec.shape} / LSA {Z_rec.shape}")
print(f"相似度: S_seg {S_seg.shape}, oracle×seg {S_oracle_seg.shape}, knife×seg {S_knife_seg.shape}, anchor×seg {S_anchor_seg.shape}, oracle×rec {S_oracle_rec.shape}")
print(f"输出目录: {OUT}")
total = sum(a["size_bytes"] for a in manifest["artifacts"])
print(f"文件数 {len(manifest['artifacts'])}，总量 {total/1024/1024:.1f} MB")
