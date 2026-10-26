"""character_oracle_similarity.py — 角色向量 × 神谕向量 相似度矩阵（f16）

问题：之前只做了「单个出场步 vs 神谕」的曲线（语言层的局部动作），没回答
「每个角色的整体语言习惯，离哪条神谕最近」——这正是角色向量（质心）该做的事。

做法：
- 角色向量 = data/models/character_centroids.npz 的 tfidf_<角色> / sbert_<角色>
  （该角色全部台词向量的质心，L2 归一）
- 神谕向量 = 13 条神谕原文，分别用 data/models/vec_word.joblib（TF-IDF，11,737 维）
  与本地 bge-small-zh-v1.5（512 维，离线）编码，L2 归一
- 两种表示各算一遍 14×13 余弦矩阵（同一表示内可比，跨表示不可比）

输出：
- docs/report/figures/f16_char_oracle_similarity.png（左右两联热图，自有神谕加框）
- data/plot_data/f16_char_oracle_similarity.csv + .meta.json（经 export_for 配对）
- data/config/character-oracle-similarity.json（矩阵、排名、发现）
"""
import io
import json
import os
import sys

import numpy as np
import joblib
from sklearn.preprocessing import normalize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
# vec_word.joblib 反序列化依赖 __main__.tokenize；以本脚本作为 __main__ 运行时导入即可
from export_plot_data import tokenize  # noqa: F401

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

MODELS = os.path.join(ROOT, "data", "models")
FIG_DIR = os.path.join(ROOT, "docs", "report", "figures")
DATA_DIR = os.path.join(ROOT, "data", "plot_data")
CFG = os.path.join(ROOT, "data", "config")

CHARS = ["白厄", "万敌", "那刻夏", "昔涟", "遐蝶", "缇宝", "海瑟音", "刻律德菈",
         "阿格莱雅", "赛飞儿", "风堇", "开拓者", "三月七", "丹恒"]
# 无自有神谕的角色：开拓者（见证者）、三月七（幽灵期）；丹恒承接 O12（大地）
NO_ORACLE = {"开拓者", "三月七"}
EXTRA_OWN = {"丹恒": ["O12"]}
# 与 tools/oracle_similarity_curves.py 的 oracle_mapping 保持一致


def load_oracles():
    rows = []
    with io.open(os.path.join(ROOT, "data", "corpus", "oracles.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda o: o["oracle_id"])
    return rows


def own_oracle_map(oracles):
    m = {c: [] for c in CHARS}
    for o in oracles:
        h = o.get("holder")
        if h in m:
            m[h].append(o["oracle_id"])
    for c, ids in EXTRA_OWN.items():
        m[c] = ids
    return m


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    oracles = load_oracles()
    oids = [o["oracle_id"] for o in oracles]
    otexts = [o["text"] for o in oracles]
    holders = {o["oracle_id"]: o.get("holder") for o in oracles}
    own = own_oracle_map(oracles)

    cen = np.load(os.path.join(MODELS, "character_centroids.npz"))

    # ---- TF-IDF：神谕向量用同一个 vec_word 空间 ----
    vec_rec = joblib.load(os.path.join(MODELS, "vec_rec.joblib"))  # 角色质心在 vec_rec 空间（11,737 维）
    O_tfidf = normalize(vec_rec.transform(otexts))
    C_tfidf = normalize(np.vstack([cen["tfidf_" + c] for c in CHARS]))
    O_tfidf_dense = O_tfidf.toarray() if hasattr(O_tfidf, "toarray") else np.asarray(O_tfidf)
    M_tfidf = np.asarray(C_tfidf @ O_tfidf_dense.T)

    # ---- 语义向量：本地 bge 模型编码 13 条神谕 ----
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(os.path.join(MODELS, "sbert_model"), device="cpu")
    O_sbert = model.encode(otexts, normalize_embeddings=True)
    C_sbert = normalize(np.vstack([cen["sbert_" + c] for c in CHARS]))
    M_sbert = C_sbert.dot(O_sbert.T)

    labels = ["TF-IDF（词频加权）", "SBERT（语义向量）"]
    matrices = [M_tfidf, M_sbert]

    # ---- 排名与发现 ----
    ranking = {}
    for ci, c in enumerate(CHARS):
        entry = {"char": c, "own": own.get(c, []), "by": {}}
        for name, M in zip(["tfidf", "sbert"], matrices):
            order = list(np.argsort(-M[ci]))
            ranked = [{"oracle_id": oids[j], "holder": holders[oids[j]],
                       "cos": round(float(M[ci, j]), 4), "rank": k + 1}
                      for k, j in enumerate(order)]
            own_rank = None
            if entry["own"]:
                best = [r for r in ranked if r["oracle_id"] in entry["own"]]
                own_rank = min(r["rank"] for r in best) if best else None
            entry["by"][name] = {"top3": ranked[:3], "own_best_rank": own_rank,
                                 "own_cos": next((r["cos"] for r in ranked if r["oracle_id"] in entry["own"]), None)}
        ranking[c] = entry

    # 镜像对交叉检查：海瑟音 / 刻律德菈 对 O10/O11 的相似度
    def cos_of(char, oid, M):
        return round(float(M[CHARS.index(char), oids.index(oid)]), 4)

    findings = {
        "mirror_pair": {
            "海瑟音": {"O10(自有)": cos_of("海瑟音", "O10", M_tfidf), "O11": cos_of("海瑟音", "O11", M_tfidf),
                       "O10_sbert": cos_of("海瑟音", "O10", M_sbert), "O11_sbert": cos_of("海瑟音", "O11", M_sbert)},
            "刻律德菈": {"O11(自有)": cos_of("刻律德菈", "O11", M_tfidf), "O10": cos_of("刻律德菈", "O10", M_tfidf),
                        "O11_sbert": cos_of("刻律德菈", "O11", M_sbert), "O10_sbert": cos_of("刻律德菈", "O10", M_sbert)},
        },
        "own_rank": {c: {"tfidf": ranking[c]["by"]["tfidf"]["own_best_rank"],
                         "sbert": ranking[c]["by"]["sbert"]["own_best_rank"]} for c in CHARS if own.get(c)},
        "no_oracle_top": {c: {"tfidf": ranking[c]["by"]["tfidf"]["top3"][0]["oracle_id"],
                              "sbert": ranking[c]["by"]["sbert"]["top3"][0]["oracle_id"]}
                          for c in NO_ORACLE},
    }

    # ---- CSV（同一行=角色×神谕，两种表示并列） ----
    rows = []
    for ci, c in enumerate(CHARS):
        for j, oid in enumerate(oids):
            rows.append({
                "char": c, "oracle_id": oid, "holder": holders[oid],
                "is_own": int(oid in own.get(c, [])),
                "tfidf_cos": round(float(M_tfidf[ci, j]), 6),
                "sbert_cos": round(float(M_sbert[ci, j]), 6),
                "tfidf_rank": int(np.argsort(-M_tfidf[ci]).tolist().index(j) + 1),
                "sbert_rank": int(np.argsort(-M_sbert[ci]).tolist().index(j) + 1),
            })

    # ---- 图：两联热图 ----
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 6.4))  # 约 1:1 展示（页面容器约 1100px），保证格内数字可读
    for ax, M, title in zip(axes, matrices, labels):
        im = ax.imshow(M, cmap="YlGnBu", vmin=0, vmax=float(np.ceil(M.max() * 10) / 10))
        ax.set_xticks(range(len(oids)), [f"{o}\n{holders[o]}" if holders[o] else o for o in oids],
                      fontsize=7, rotation=90)
        ax.set_yticks(range(len(CHARS)), CHARS, fontsize=9)
        for ci in range(len(CHARS)):
            for j in range(len(oids)):
                v = M[ci, j]
                ax.text(j, ci, f"{v:.2f}", ha="center", va="center", fontsize=6.2,
                        color="#ffffff" if v > M.max() * 0.62 else "#2b3a45")
                if oids[j] in own.get(CHARS[ci], []):
                    ax.add_patch(Rectangle((j - 0.5, ci - 0.5), 1, 1, fill=False, ec="#c0392b", lw=1.8))
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("13 条神谕（列；红框=该角色自有神谕）", fontsize=9)
        cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
        cb.set_label("余弦相似度", fontsize=8)
    fig.suptitle("图16 角色向量 × 神谕向量：整体语言习惯离哪条命定最近（角色向量=该角色全部台词的质心）",
                 fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    png = os.path.join(FIG_DIR, "f16_char_oracle_similarity.png")
    fig.savefig(png, dpi=100, bbox_inches="tight")
    plt.close(fig)

    # ---- 写配置 ----
    cfg = {
        "note": "角色向量 = character_centroids.npz（该角色全部台词向量质心，L2 归一）；神谕向量 = 神谕原文在 vec_word / bge-small-zh-v1.5 下的向量。同一表示内可比，跨表示不可比。",
        "oracles": [{"oracle_id": o["oracle_id"], "text": o["text"], "holder": o.get("holder")} for o in oracles],
        "own_oracle": {c: own.get(c, []) for c in CHARS},
        "tfidf": {c: {oids[j]: round(float(M_tfidf[i, j]), 4) for j in range(len(oids))} for i, c in enumerate(CHARS)},
        "sbert": {c: {oids[j]: round(float(M_sbert[i, j]), 4) for j in range(len(oids))} for i, c in enumerate(CHARS)},
        "ranking": ranking,
        "findings": findings,
        "sources": ["data/models/character_centroids.npz", "data/models/vec_rec.joblib",
                    "data/models/sbert_model", "data/corpus/oracles.jsonl"],
    }
    cfg_path = os.path.join(CFG, "character-oracle-similarity.json")
    with io.open(cfg_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)

    # ---- 登记图-数据配对（export_for 会调用 data_f16 写 csv+meta） ----
    try:
        from export_plot_data import export_for
        export_for("tools/character_oracle_similarity.py")
    except Exception as e:  # noqa
        print("  [plot_data] 无法登记配对：%s" % e, file=sys.stderr)
    print("已写", png, "→", len(rows), "行矩阵")
    print("own_rank:", json.dumps(findings["own_rank"], ensure_ascii=False))
    print("no_oracle_top:", json.dumps(findings["no_oracle_top"], ensure_ascii=False))
    print("mirror:", json.dumps(findings["mirror_pair"], ensure_ascii=False))


if __name__ == "__main__":
    main()
