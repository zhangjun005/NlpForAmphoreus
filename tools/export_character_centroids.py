"""export_character_centroids.py — 导出每个角色的"角色向量"（向量质心）
- 基础向量是"每条台词"的（26,332 × 512 SBERT；TF-IDF 记录级）；
- 角色向量 = 该角色全部台词向量的质心（另给按版本质心）；
- 输出：data/models/character_centroids.npz + data/config/character-centroids.json
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
try:
    import tokenize_compat
    tokenize_compat.install()
except Exception:
    pass

MODELS = os.path.join(ROOT, "data", "models")


def main():
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

    # 角色名单：A 组 11 + B 组 3
    chars = ["白厄", "万敌", "阿格莱雅", "缇宝", "遐蝶", "那刻夏", "风堇", "赛飞儿",
             "海瑟音", "刻律德菈", "昔涟", "开拓者", "三月七", "丹恒"]
    out = {"note": "角色向量 = 该角色全部台词向量的质心（L2 归一）；per_version 为按版本质心",
           "n_records_total": len(rec_ids), "characters": {}}
    arrays = {}
    for c in chars:
        rows = [k for k, rid in enumerate(rec_ids) if (recs[rid].get("canonical_speaker") == c)]
        if not rows:
            continue
        sb = normalize(Z[rows].mean(axis=0).reshape(1, -1))[0]
        tf = normalize(np.asarray(X[rows].mean(axis=0)).reshape(1, -1))[0]
        per_ver = {}
        v_rows = {}
        for k in rows:
            v = recs[rec_ids[k]].get("version")
            v_rows.setdefault(v, []).append(k)
        for v, rr in sorted(v_rows.items()):
            per_ver[v] = {"n": len(rr),
                          "sbert": normalize(Z[rr].mean(axis=0).reshape(1, -1))[0]}
        out["characters"][c] = {
            "n_records": len(rows),
            "versions": sorted(v_rows.keys()),
            "per_version_n": {v: len(v_rows[v]) for v in sorted(v_rows)},
        }
        arrays[f"sbert_{c}"] = sb.astype(np.float32)
        arrays[f"tfidf_{c}"] = tf.astype(np.float32)
        for v, d in per_ver.items():
            arrays[f"sbert_{c}_{v}"] = d["sbert"].astype(np.float32)
    np.savez_compressed(os.path.join(MODELS, "character_centroids.npz"), **arrays)
    out["artifacts"] = {
        "npz": "data/models/character_centroids.npz",
        "keys": sorted(arrays.keys()),
        "sbert_dim": int(Z.shape[1]),
        "tfidf_dim": int(X.shape[1]),
    }
    json.dump(out, io.open(os.path.join(ROOT, "data/config/character-centroids.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("角色数 =", len(out["characters"]))
    print("npz keys =", len(arrays), "个（角色总质心 + 按版本质心）")
    print("sample:", chars[0], "n_records =", out["characters"].get(chars[0], {}).get("n_records"))


if __name__ == "__main__":
    main()
