#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
oracle_similarity_curves.py — 14 角色 × 神谕文本相似度的全程曲线（双空间）

问题背景：之前只给「峰值点」，用户要求给出整条曲线/整个「山峰」，并记录每个点怎么来的。
本脚本复用已有向量资产（不重新训练）：
  data/models/vec_rec.joblib   记录级 词频加权（analyzer=tokenize, ngram=(1,2), min_df=2, sublinear_tf）
  data/models/ids.json         记录/神谕顺序（records 26332 / oracles 13）
  data/models/Z_sbert_rec.npy  记录级 bge-small-zh-v1.5 句向量（26332×512，已 L2 归一）
  （可选交叉核对）data/models/S_oracle_rec.npy 13×26332 记录级 词频加权 相似度

方法链路（每个点可追溯）：
  原始记录（text_clean） → vec_rec.transform → 记录级 词频加权 向量 / Z_sbert_rec 行 → 
  按 (version, task, step_idx) 聚合该角色台词的**均值向量**（另存 max 与条数）→ 
  与「自己神谕」向量（vec_rec 映射；语义向量 用同一模型 BAAI/bge-small-zh-v1.5 现场编码 13 条神谕）算余弦 → 
  时间轴用 order（3.0→3.7），滚动均值窗口 5 步。

产出：
  data/config/oracle-similarity-curves.json   完整时间序列 + 13 神谕矩阵 + 神谕向量（可复算）
  data/config/oracle-similarity-curves.csv    长表（含 13 列 词频加权 + 13 列 语义向量 相似度）
  docs/report/figures/oracle_sim/<角色>.png   14 张单人曲线
  docs/report/figures/f11_oracle_similarity_heatmap.png  总览热力图
  docs/report/oracle-similarity-curves.md     报告

运行：
  conda run -n nlpLesson python tools/oracle_similarity_curves.py
  conda run -n nlpLesson python tools/oracle_similarity_curves.py --verify

无随机；模型/HF 均走本地缓存（HF_HUB_OFFLINE=1），不联网。
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, OrderedDict, defaultdict

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import joblib
import jieba
from sklearn.preprocessing import normalize

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_FINAL = os.path.join(ROOT, "data", "corpus", "amphoreus.final.jsonl")
P_SEGS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_ORACLES = os.path.join(ROOT, "data", "corpus", "oracles.jsonl")
P_CITE = os.path.join(ROOT, "data", "config", "oracle-citation-coding.json")
P_FILLED_V2 = os.path.join(ROOT, "data", "config", "oracle-fulfillment.v2.json")
P_KEYS = os.path.join(ROOT, "data", "config", "key-events.json")
P_KNIFE = os.path.join(ROOT, "data", "config", "knife-scenes.json")
MODELS = os.path.join(ROOT, "data", "models")
P_IDS = os.path.join(MODELS, "ids.json")
P_VEC_REC = os.path.join(MODELS, "vec_rec.joblib")
P_Z_语义向量 = os.path.join(MODELS, "Z_sbert_rec.npy")
P_S_ORACLE_REC = os.path.join(MODELS, "S_oracle_rec.npy")
OUT_JSON = os.path.join(ROOT, "data", "config", "oracle-similarity-curves.json")
OUT_CSV = os.path.join(ROOT, "data", "config", "oracle-similarity-curves.csv")
FIG_DIR = os.path.join(ROOT, "docs", "report", "figures", "oracle_sim")
FIG_HEAT = os.path.join(ROOT, "docs", "report", "figures", "f11_oracle_similarity_heatmap.png")
OUT_MD = os.path.join(ROOT, "docs", "report", "oracle-similarity-curves.md")
RUN_CMD = "conda run -n nlpLesson python tools/oracle_similarity_curves.py"

GROUP_A = ["白厄", "万敌", "阿格莱雅", "缇宝", "遐蝶", "那刻夏", "风堇",
           "赛飞儿", "海瑟音", "刻律德菈", "昔涟"]                   # A 组：黄金裔 11 位（最终口径）
GROUP_B = ["开拓者", "三月七", "丹恒"]                              # B 组：单列（非黄金裔）
GROUP_NPC = []                                                      # 不单列 NPC：荒笛/玻吕茜亚只在相关角色条目内说明
CHARS = GROUP_A + GROUP_B + GROUP_NPC
GROUP_LABEL = {"A": "A 组：11 黄金裔", "B": "B 组：单列（非黄金裔）"}
# 口径（用户拍板）：A 组=12 黄金裔；B 组=开拓者/丹恒/三月七（主线塑造在篇外，单独成表、不与黄金裔比）；
# 玻吕茜亚（遐蝶之妹）不进主名单，只在遐蝶条目/O05 注记说明（O05 holder=玻吕茜亚，双子共有神谕）；
# 荒笛 70 条/4 步标样本量；「大地承接：荒笛 → 丹恒」，但丹恒归 B 组；
# 三月七 = 长夜月/永夜之帷/幻象/记忆形态（canonical=三月七，form 区分）。
# 修正说明（lead 2026-10-24）：O05「汝将凋零…」holder = 玻吕茜亚（双子共有，不归遐蝶）；
# O04 仍属遐蝶；O13 有两个事件段（3.4|点燃|7 意义转折 + 3.7|魔女|21 兑现）。
# 「大地」线 = 荒笛 ↔ 丹恒（荒笛是前任大地之化身，丹恒承接大地火种），故丹恒的 own oracle 取 O12。
VERSIONS = ["3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"]
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
ROLL_WIN = 5

CJK_CANDIDATES = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans SC",
                  "Source Han Sans SC", "WenQuanYi Zen Hei", "PingFang SC", "Arial Unicode MS"]


def setup_font():
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in CJK_CANDIDATES:
        if cand in names:
            plt.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return True, cand
    plt.rcParams["axes.unicode_minus"] = False
    return False, None


HAS_CJK, CJK_FONT = setup_font()


def L(cn, en):
    return cn if HAS_CJK else en


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


# ---------------------------------------------------------------------------
# 0) 分词语料必须与 export_artifacts.py 完全一致（否则 vec_rec.joblib 反序列化/transform 会错）
# ---------------------------------------------------------------------------
STOP = set("""
的 了 是 在 我 你 他 她 它 我们 你们 他们 这 那 这个 那个 一个 一种 什么 怎么 为什么 不 也 都 就 而 与 和 或
但 却 又 很 更 最 非常 已经 还是 因为 所以 如果 虽然 但是 然后 可以 没有 不是 自己 这样 那样 一些 这些 那些
啊 吧 呢 吗 呀 哦 唉 嗯 唔 诶 哈 呵 诶 之 其 者 也 矣 焉 哉
""".split())
KEEP_SINGLE = set("汝 吾 尔 她 他 我 你 花 海 火 光 梦 死 生 爱 痛 刀 剑 星 月 日 夜 风 雨 雪 冰 雷".split())


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


# ---------------------------------------------------------------------------
# 1) 数据与向量资产
# ---------------------------------------------------------------------------
def load_all():
    ids = read_json(P_IDS)
    recs = read_jsonl(P_FINAL)
    rec_by_id = {r["id"]: r for r in recs}
    recs_ordered = [rec_by_id[rid] for rid in ids["records"]]
    assert [r["id"] for r in recs_ordered] == ids["records"], "记录顺序与 ids.json 不对齐"
    segs = read_jsonl(P_SEGS)
    seg_by_key = {(s["version"], s["task"], s["step_idx"]): s for s in segs}
    oracles = read_jsonl(P_ORACLES)
    assert [o["oracle_id"] for o in oracles] == ids["oracles"], "神谕顺序与 ids.json 不对齐"
    vec = joblib.load(P_VEC_REC)
    docs = [r.get("text_clean") or "" for r in recs_ordered]
    X = vec.transform(docs)                      # 26332 × V（记录级 词频加权，复用已训练模型）
    Z = np.load(P_Z_语义向量, mmap_mode="r")        # 26332 × 512（已归一）
    return ids, recs_ordered, seg_by_key, segs, oracles, vec, X, Z


def oracle_mapping(oracles):
    """角色 → 自己神谕（按 oracles.jsonl 的 holder；开拓者没有自己的神谕）。
    修正：O05 holder=玻吕茜亚（不是遐蝶）→ 遐蝶 own = O04；丹恒承接「大地」火种 → own = O12。"""
    m = defaultdict(list)
    for o in oracles:
        m[o.get("holder")].append(o["oracle_id"])
    m["丹恒"] = ["O12"]   # 大地线 = 荒笛 ↔ 丹恒（荒笛为前任大地之化身）
    return {c: m.get(c, []) for c in CHARS}


def rolling_mean(vals, win=ROLL_WIN):
    a = np.asarray(vals, dtype=float)
    n = len(a)
    if n == 0:
        return []
    half = win // 2
    out = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        out.append(round(float(a[lo:hi].mean()), 6))
    return out


def version_boundaries(segs):
    """每个版本的起始 order（用于图上的版本分隔线）"""
    out = {}
    for v in VERSIONS:
        orders = [s["order"] for s in segs if s["version"] == v]
        if orders:
            out[v] = int(min(orders))
    return out


def annotations(own_oracles, char, seg_by_key, cite, filled_v2, keys, knife):
    """每条曲线上的标注（按 order）：神谕首现 / 吟诵步 / 事件段（兑现/意义转折） / 关键事件 / 刀子"""
    def seg_order(seg_id):
        parts = (seg_id or "").split("|")
        if len(parts) < 3:
            return None
        try:
            s = seg_by_key.get((parts[0], parts[1], int(parts[2])))
        except ValueError:
            return None
        return int(s["order"]) if s else None

    own = set(own_oracles)
    recits, events = [], []
    for f in filled_v2["oracles"]:
        if f["oracle_id"] not in own:
            continue
        for seg in f.get("recitation_segments") or []:
            oo = seg_order(seg)
            if oo is not None:
                recits.append({"order": oo, "oracle": f["oracle_id"], "segment_id": seg})
        for ev in f.get("event_segments") or []:
            oo = seg_order(ev.get("segment_id"))
            if oo is None:
                continue
            events.append({"order": oo, "oracle": f["oracle_id"], "role": ev.get("role"),
                           "note": ev.get("note"), "segment_id": ev.get("segment_id")})
    first = sorted({r["order"] for r in recits})[:1]
    key_orders = []
    for e in keys["events"]:
        seg = e.get("segment_id")
        if seg:
            oo = seg_order(seg)
            if oo is not None:
                key_orders.append({"order": oo, "event": e.get("event_name"),
                                   "id": e.get("id"), "phase": e.get("phase"),
                                   "segment_id": seg})
    knife_orders = []
    for k in knife["scenes"]:
        role = k.get("role") or ""
        if char not in role:
            continue
        ids = list(k.get("segment_ids") or [])
        for r in k.get("ranges") or []:
            ids.append(r.split("#")[0])
        for seg in ids:
            oo = seg_order(seg)
            if oo is not None:
                knife_orders.append({"order": oo, "scene": k["id"], "title": k.get("title"),
                                     "segment_id": seg})
    # 兑现用 current_filled_fulfillment（人工确认的兑现段）；event_segments 里的「兑现」
    # 是候选/事件段，O01、O09 等与 confirmed 不一致，不能拿来当「兑现」打点。
    filled = []
    for f in filled_v2["oracles"]:
        if f["oracle_id"] not in own:
            continue
        cff = f.get("current_filled_fulfillment")
        if cff:
            oo = seg_order(cff)
            if oo is not None:
                filled.append({"order": oo, "oracle": f["oracle_id"], "segment_id": cff})
    return {"oracle_first_orders": first, "recitations": recits, "events": events,
            "filled": filled,
            "key_events": key_orders, "knife_scenes": knife_orders}


# ---------------------------------------------------------------------------
# 2) 逐角色曲线
# ---------------------------------------------------------------------------
def compute_curves(ids, recs_ordered, seg_by_key, oracles, X, Z, own_map, cite, filled_v2, keys, knife):
    oids = [o["oracle_id"] for o in oracles]
    oracle_texts = [o["text"] for o in oracles]
    vec = joblib.load(P_VEC_REC)
    OT = vec.transform(oracle_texts)                 # 13 × V
    OTn = normalize(OT)
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(1)   # 固定单线程，保证两次运行的神谕句向量逐位一致（--verify 要求可复现）
    model = SentenceTransformer(MODEL_NAME, device="cpu")
    OS = model.encode(oracle_texts, normalize_embeddings=True).astype(np.float32)
    OSn = normalize(OS)
    # 记录级：与 13 神谕的余弦（用于 max 与交叉核对）
    C_tfidf = np.asarray(normalize(X).dot(OTn.T).toarray())   # 26332 × 13
    C_sbert = np.asarray(Z.dot(OSn.T))               # 26332 × 13（Z 已归一）
    # 交叉核对：与 S_oracle_rec.npy 的差异
    cross = {}
    if os.path.exists(P_S_ORACLE_REC):
        So = np.load(P_S_ORACLE_REC, mmap_mode="r")
        cross = {"max_abs_diff_vs_S_oracle_rec": round(float(np.max(np.abs(C_tfidf.T - So))), 6),
                 "checked": True}
    Xn = normalize(X)
    idx_by_id = {rid: i for i, rid in enumerate(ids["records"])}
    steps_out = {}
    for char in CHARS:
        own = own_map[char]
        own_idx = [oids.index(o) for o in own]
        rows = [r for r in recs_ordered if r.get("canonical_speaker") == char]
        groups = OrderedDict()
        for r in rows:
            key = (r["version"], r["task"], r["step_idx"])
            groups.setdefault(key, []).append(r)
        steps = []
        for key, rs in groups.items():
            idx = [idx_by_id[r["id"]] for r in rs]
            order = int(min(r["order"] for r in rs))
            seg = seg_by_key.get(key) or {}
            # 均值向量（词频加权：稀疏行取均值后再归一；语义向量：行均值后再归一）
            xmean = np.asarray(X[idx].mean(axis=0)).ravel().astype(np.float32)
            xmean = xmean / (np.linalg.norm(xmean) + 1e-12)
            zmean = np.asarray(Z[idx].mean(axis=0)).astype(np.float32)
            zmean = zmean / (np.linalg.norm(zmean) + 1e-12)
            sim_tfidf = [round(float(v), 6) for v in np.asarray(OTn.dot(xmean)).ravel()]
            sim_sbert = [round(float(v), 6) for v in OSn.dot(zmean)]
            if own_idx:
                own_tfidf = max(sim_tfidf[i] for i in own_idx)
                own_sbert = max(sim_sbert[i] for i in own_idx)
                max_tfidf = round(float(np.max(C_tfidf[idx][:, own_idx])), 6)
                max_sbert = round(float(np.max(C_sbert[idx][:, own_idx])), 6)
                own_def = "max_over_own_oracles"
                other_idx = [i for i in range(len(oids)) if i not in own_idx]
                b_other = max(other_idx, key=lambda i: sim_tfidf[i])
                b_other_s = max(other_idx, key=lambda i: sim_sbert[i])
            else:
                # 开拓者：没有自己的神谕 → 取 13 条中的最高值，曲线名为「与 13 条神谕的最高相似度」
                own_tfidf = max(sim_tfidf)
                own_sbert = max(sim_sbert)
                max_tfidf = round(float(C_tfidf[idx].max()), 6)
                max_sbert = round(float(C_sbert[idx].max()), 6)
                own_def = "max_over_all_oracles"
                b_other = max(range(len(oids)), key=lambda i: sim_tfidf[i])
                b_other_s = max(range(len(oids)), key=lambda i: sim_sbert[i])
            steps.append({
                "order": order, "version": key[0], "task": key[1], "step_idx": int(key[2]),
                # 精确 segment_id：事件打标必须按 segment 而不是按任务序号（order 在同一任务的
                # 所有出场步上是相同的，按 order 打标会把整段任务都标成事件）
                "segment_id": "%s|%s|%d" % (key[0], key[1], int(key[2])),
                "step_title": seg.get("step_title"),
                "n_lines": len(rs), "record_ids": [int(r["id"]) for r in rs],
            "dominant_form": (Counter([r.get("form") for r in rs if r.get("form")]).most_common(1)[0][0]
                              if any(r.get("form") for r in rs) else None),
                "record_id_span": [int(min(r["id"] for r in rs)), int(max(r["id"] for r in rs))],
                "tfidf_own": own_tfidf, "sbert_own": own_sbert,
                "tfidf_own_max": max_tfidf, "sbert_own_max": max_sbert,
                "argmax_tfidf": oids[max(range(len(oids)), key=lambda i: sim_tfidf[i])],
                "argmax_sbert": oids[max(range(len(oids)), key=lambda i: sim_sbert[i])],
                "best_other_tfidf": oids[b_other], "best_other_tfidf_sim": sim_tfidf[b_other],
                "best_other_sbert": oids[b_other_s], "best_other_sbert_sim": sim_sbert[b_other_s],
                "sim_tfidf_all": sim_tfidf, "sim_sbert_all": sim_sbert,
            })
        steps.sort(key=lambda s: (s["order"], s["step_idx"]))
        t_roll = rolling_mean([s["tfidf_own"] for s in steps])
        s_roll = rolling_mean([s["sbert_own"] for s in steps])
        for s, a, b in zip(steps, t_roll, s_roll):
            s["tfidf_roll5"] = a
            s["sbert_roll5"] = b
        ann = annotations(own, char, seg_by_key, cite, filled_v2, keys, knife)
        # 峰值（原始 & 滚动）
        def top(key):
            if not steps:
                return None
            s = max(steps, key=lambda x: x[key])
            return {"order": s["order"], "version": s["version"], "task": s["task"],
                    "step_idx": s["step_idx"], "step_title": s["step_title"], "value": s[key],
                    "n_lines": s["n_lines"]}
        steps_out[char] = {
            "group": "A" if char in GROUP_A else ("B" if char in GROUP_B else "NPC"),
            "own_oracles": own, "own_definition": own_def,
            "n_records": len(rows), "n_steps": len(steps),
            "steps": steps,
            "annotations": ann,
            "summary": {
                "peak_tfidf_raw": top("tfidf_own"), "peak_sbert_raw": top("sbert_own"),
                "peak_tfidf_roll5": top("tfidf_roll5"), "peak_sbert_roll5": top("sbert_roll5"),
                "mean_tfidf_own": round(float(np.mean([s["tfidf_own"] for s in steps])), 6) if steps else None,
                "mean_sbert_own": round(float(np.mean([s["sbert_own"] for s in steps])), 6) if steps else None,
            },
        }
    return steps_out, OT, OS, oids, cross


# ---------------------------------------------------------------------------
# 3) 输出 JSON / CSV
# ---------------------------------------------------------------------------
def write_outputs(steps_out, OT, OS, oids, own_map, vec, meta):
    terms = list(vec.get_feature_names_out())
    oracle_tfidf = {}
    for i, oid in enumerate(oids):
        row = OT.getrow(i).tocoo()
        oracle_tfidf[oid] = {terms[j]: round(float(v), 6) for j, v in zip(row.col, row.data)}
    data = {
        "meta": meta,
        "oracle_mapping": own_map,
        "oracle_vectors": {
            "tfidf_sparse": oracle_tfidf,
            "sbert": {oid: [round(float(x), 6) for x in OS[i]] for i, oid in enumerate(oids)},
            "note": "tfidf_sparse 为 vec_rec 映射后的非零项（term→weight）；sbert 为 bge-small-zh-v1.5 归一化向量",
        },
        "characters": steps_out,
    }
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    # CSV：长表，13 列 词频加权 + 13 列 语义向量
    cols = ["char", "own_oracles", "order", "version", "task", "step_idx", "step_title",
            "n_lines", "record_id_span", "tfidf_own", "sbert_own", "tfidf_own_max", "sbert_own_max",
            "tfidf_roll5", "sbert_roll5", "argmax_tfidf", "argmax_sbert",
            "best_other_tfidf", "best_other_tfidf_sim", "best_other_sbert", "best_other_sbert_sim"] + \
           ["sim_tfidf_%s" % o for o in oids] + ["sim_sbert_%s" % o for o in oids]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for char, ch in steps_out.items():
            for s in ch["steps"]:
                w.writerow([char, "|".join(ch["own_oracles"]), s["order"], s["version"], s["task"],
                            s["step_idx"], s["step_title"], s["n_lines"],
                            "%d-%d" % tuple(s["record_id_span"]),
                            s["tfidf_own"], s["sbert_own"], s["tfidf_own_max"], s["sbert_own_max"],
                            s["tfidf_roll5"], s["sbert_roll5"],
                            s["argmax_tfidf"], s["argmax_sbert"],
                            s["best_other_tfidf"], s["best_other_tfidf_sim"],
                            s["best_other_sbert"], s["best_other_sbert_sim"]] +
                           list(s["sim_tfidf_all"]) + list(s["sim_sbert_all"]))
    print("已写 %s（%.1f KB）" % (os.path.relpath(OUT_JSON, ROOT), os.path.getsize(OUT_JSON) / 1024.0))
    print("已写 %s（%.1f KB）" % (os.path.relpath(OUT_CSV, ROOT), os.path.getsize(OUT_CSV) / 1024.0))
    return data



# ---------------------------------------------------------------------------
# 4) 图
# ---------------------------------------------------------------------------
def make_character_figure(char, ch, vbound, out):
    steps = ch["steps"]
    if not steps:
        return
    x = np.array([s["order"] for s in steps], dtype=float)
    fig, ax = plt.subplots(figsize=(12.8, 5.0))
    ax2 = ax.twinx()
    # 左轴：词频加权（绝对尺度较小）
    ax.plot(x, [s["tfidf_own"] for s in steps], color="#a9c0d8", lw=0.8, alpha=0.8)
    ax.plot(x, [s["tfidf_roll5"] for s in steps], color="#1f4e79", lw=2.0,
            label=L("词频加权 滚动均值(5)（左轴）", "词频加权 roll5 (left)"))
    # 右轴：语义向量
    ax2.plot(x, [s["sbert_own"] for s in steps], color="#f0b27a", lw=0.8, alpha=0.8)
    ax2.plot(x, [s["sbert_roll5"] for s in steps], color="#b9530f", lw=2.0,
             label=L("语义向量 滚动均值(5)（右轴）", "语义向量 roll5 (right)"))
    form_handles = []
    form_present = []
    if char == "三月七":
        # 三月七按 form 分层：长夜月 / 永夜之帷 / 幻象 / 记忆形态（canonical 已统一为三月七）
        FCOL = {"长夜月": "#8e44ad", "永夜之帷": "#2c3e50", "幻象": "#16a085",
                "记忆形态": "#c0392b", "无形态": "#95a5a6"}
        for f in ["长夜月", "永夜之帷", "幻象", "记忆形态", "无形态"]:
            pts = [s for s in steps if (s.get("dominant_form") or "无形态") == f]
            if not pts:
                continue
            form_present.append((f, len(pts)))
            ax2.scatter([p["order"] for p in pts], [p["sbert_own"] for p in pts],
                        s=22, color=FCOL[f], edgecolors="white", linewidths=0.4, zorder=6)
            form_handles.append(plt.Line2D([], [], marker="o", lw=0, color=FCOL[f], ms=6,
                                           label=L("形态：" + f, f)))
    tmin, tmax = min(s["tfidf_own"] for s in steps), max(s["tfidf_own"] for s in steps)
    smin, smax = min(s["sbert_own"] for s in steps), max(s["sbert_own"] for s in steps)
    tpad = (tmax - tmin) * 0.15 + 0.01
    spad = (smax - smin) * 0.15 + 0.01
    ax.set_ylim(tmin - tpad, tmax + tpad)
    ax2.set_ylim(smin - spad, smax + spad)
    ax.set_ylabel(L("词频加权 与神谕文本的相似度（余弦）", "词频加权 cosine"), color="#1f4e79")
    ax2.set_ylabel(L("语义向量 与神谕文本的相似度（余弦）", "语义向量 cosine"), color="#b9530f")
    ax.tick_params(axis="y", labelcolor="#1f4e79")
    ax2.tick_params(axis="y", labelcolor="#b9530f")
    for v in VERSIONS[1:]:
        o = vbound.get(v)
        if o is not None and x.min() <= o <= x.max():
            ax.axvline(o, color="0.62", lw=0.8, ls="--")
    ann = ch["annotations"]
    # 吟诵步（自己的神谕被念出）
    for o in sorted({a["order"] for a in ann["recitations"]}):
        ax.axvline(o, color="#8e44ad", lw=0.9, ls=":", alpha=0.8)
    for o in ann["oracle_first_orders"]:
        ax.axvline(o, color="#2c3e50", lw=1.4, ls="-", alpha=0.9)
    # 事件轨（axes 分数坐标，避免与 y 轴刻度打架）
    tx = ax.get_xaxis_transform()
    for ev in ann["events"]:
        if ev.get("role") == "兑现":
            ax.plot([ev["order"]], [0.97], marker="*", ms=13, color="#c0392b",
                    transform=tx, clip_on=False, zorder=6)
        else:
            ax.plot([ev["order"]], [0.93], marker="D", ms=5, color="#8e44ad",
                    transform=tx, clip_on=False, zorder=6, alpha=0.9)
    for e in ann["key_events"]:
        ax.plot([e["order"]], [0.90], marker="s", ms=4, color="#7f8c8d", transform=tx, clip_on=False, alpha=0.9)
    for k in ann["knife_scenes"]:
        ax.plot([k["order"]], [0.83], marker="v", ms=5, color="#d35400", transform=tx, clip_on=False, alpha=0.95)
    ax.set_xlabel(L("order（3.0→3.7 全局顺序；顶部竖线=版本边界）", "order (3.0 → 3.7)"))
    if vbound:
        ax.set_xticks([vbound[v] for v in VERSIONS if v in vbound])
        ax.set_xticklabels([v for v in VERSIONS if v in vbound], fontsize=7)
    gt = {"A": "A 组", "B": "B 组单列", "NPC": "NPC 类"}.get(ch.get("group", "A"), "A 组")
    if ch["own_oracles"]:
        title_cn = "%s（%s）：与神谕 %s 文本相似度全程曲线（纵轴=与神谕文本的相似度，不是含义强度）" % (
            char, gt, "、".join(ch["own_oracles"]))
        title_en = "%s: similarity to oracle %s" % (char, "、".join(ch["own_oracles"]))
    else:
        title_cn = "%s（%s）：与 13 条神谕的最高相似度全程曲线（无自有神谕；纵轴=相似度，不是含义强度）" % (
            char, gt)
        title_en = "%s: max similarity over 13 oracles" % char
    ax.set_title(L(title_cn, title_en), fontsize=10)
    handles = [plt.Line2D([], [], color="#1f4e79", lw=2, label=L("词频加权 滚动(5)", "词频加权 roll5")),
               plt.Line2D([], [], color="#b9530f", lw=2, label=L("语义向量 滚动(5)", "语义向量 roll5")),
               plt.Line2D([], [], color="#8e44ad", lw=1, ls=":", label=L("吟诵步", "recitation")),
               plt.Line2D([], [], color="#2c3e50", lw=1.4, label=L("首现", "first appearance")),
               plt.Line2D([], [], marker="*", color="#c0392b", lw=0, ms=10, label=L("兑现", "fulfillment")),
               plt.Line2D([], [], marker="D", color="#8e44ad", lw=0, ms=5, label=L("意义转折", "meaning turn")),
               plt.Line2D([], [], marker="s", color="#7f8c8d", lw=0, ms=4, label=L("关键事件", "key event")),
               plt.Line2D([], [], marker="v", color="#d35400", lw=0, ms=5, label=L("刀子", "knife scene"))]
    ax.legend(handles=handles + form_handles, fontsize=7, frameon=False,
              ncol=min(9, len(handles) + len(form_handles)), loc="upper center",
              bbox_to_anchor=(0.5, -0.20))
    ax.grid(alpha=0.18)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_heatmap(steps_out, out):
    names = CHARS
    mat_t = np.full((len(names), len(VERSIONS)), np.nan)
    mat_s = np.full((len(names), len(VERSIONS)), np.nan)
    for i, c in enumerate(names):
        for j, v in enumerate(VERSIONS):
            ss = [x for x in steps_out[c]["steps"] if x["version"] == v]
            if ss:
                mat_t[i, j] = np.mean([x["tfidf_own"] for x in ss])
                mat_s[i, j] = np.mean([x["sbert_own"] for x in ss])
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 7.4))
    for ax, mat, title in ((axes[0], mat_t, "词频加权"), (axes[1], mat_s, "语义向量")):
        vmin = float(np.nanmin(mat))
        vmax = float(np.nanmax(mat))
        im = ax.imshow(mat, aspect="auto", cmap="YlOrRd", vmin=vmin, vmax=vmax)
        for i in range(len(names)):
            for j in range(len(VERSIONS)):
                if not np.isnan(mat[i, j]):
                    ax.text(j, i, "%.2f" % mat[i, j], ha="center", va="center", fontsize=6.2,
                            color="white" if mat[i, j] > vmin + 0.65 * (vmax - vmin) else "black")
        ax.axhline(len(GROUP_A) - 0.5, color="black", lw=1.4, ls="--")

        ax.set_xticks(range(len(VERSIONS)))
        ax.set_xticklabels(VERSIONS)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names)
        for lab in ax.get_yticklabels()[:len(GROUP_A)]:
            lab.set_color("#1f4e79")
        for lab in ax.get_yticklabels()[len(GROUP_A):len(GROUP_A) + len(GROUP_B)]:
            lab.set_color("#b9530f")
        for lab in ax.get_yticklabels()[len(GROUP_A) + len(GROUP_B):]:
            lab.set_color("#7f8c8d")
        ax.set_title("(%s) 与神谕文本相似度（版本均值；本格独立色标 %.2f–%.2f）" % (title, vmin, vmax)
                     if HAS_CJK else "(%s) mean similarity per version" % title, fontsize=9)
        ax.set_xlabel(L("版本", "version"))
        ax.text(-0.06, len(GROUP_A) / 2.0 / len(names), L("A 组 11 黄金裔", "A: 11"),
                transform=ax.transAxes, rotation=90, va="center", ha="right",
                fontsize=9, color="#1f4e79")
        ax.text(-0.06, (len(GROUP_A) + len(GROUP_B) / 2.0) / len(names),
                L("B 组 3 单列", "B: 3"), transform=ax.transAxes, rotation=90,
                va="center", ha="right", fontsize=9, color="#b9530f")
        cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
        cb.set_label(L("与神谕文本的相似度（余弦）", "cosine"), fontsize=8)
    fig.suptitle(L("图11  14 条曲线 × 8 版本的「与神谕文本相似度」总览（A 组 11 黄金裔 / B 组 3 单列；荒笛/玻吕茜亚按 NPC 处理，不单列；纵轴=相似度，不是含义强度）",
                   "Fig11  Oracle similarity overview (A: 12; B: 3)"), fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return mat_t, mat_s


# ---------------------------------------------------------------------------
# 5) 报告
# ---------------------------------------------------------------------------
def render_report(data, mat_t, mat_s, vbound):
    meta = data["meta"]
    chars = data["characters"]
    Lr = []
    A = Lr.append
    A("# 14 角色 × 神谕文本相似度：全程曲线（词频加权 + 语义向量 双空间；荒笛/玻吕茜亚按 NPC 处理）")
    A("")
    A("> 生成脚本：`tools/oracle_similarity_curves.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    A("> 明细数据：`data/config/oracle-similarity-curves.json`（含神谕向量，可逐点复算）、"
      "`oracle-similarity-curves.csv`（长表）")
    A("> 图：`docs/report/figures/oracle_sim/<角色>.png`（14 张）、"
      "`docs/report/figures/f11_oracle_similarity_heatmap.png`")
    A("")
    A("> **纵轴口径**：纵轴 = **与神谕文本的相似度（余弦）**，不是「含义强度」，也不是「角色是否在谈论神谕」。")
    A("")
    A("## 0. 角色分层口径（报告口径，按用户最终拍板）")
    A("")
    A("- **A 组 = 黄金裔 11 位**：%s。" % "、".join(GROUP_A))
    A("  > 脚注：游戏虽称「十二黄金裔」，但「岁月」这一席位历史上多次更换（欧洛尼斯一线 / 德谬歌与昔涟的演化），"
      "所以实际固定的黄金裔是 **11 位**；本报告一律按 11 位口径。")
    A("- **B 组 = 单列分析（非黄金裔）**：%s。它们的主线塑造在翁法罗斯之外，"
      "本报告单独成节、不与黄金裔横向比较。" % "、".join(GROUP_B))
    A("- **荒笛、玻吕茜亚按 NPC 处理**：只在相关角色条目内说明，**不单列分析、不出表/图/曲线/章节**——"
      "荒笛（70 条 / 4 步）写在丹恒条目（大地承接：荒笛 → 丹恒）；玻吕茜亚写在遐蝶条目（遐蝶之妹；"
      "O05「汝将凋零…」双子共有神谕 holder=玻吕茜亚）。")
    A("- **三月七 ↔ 长夜月**：canonical_speaker 已统一为「三月七」，form 区分 长夜月/永夜之帷/幻象/记忆形态；"
      "单人图按 form 分层着色。")
    A("- **O13 两个事件段**：`3.4|英雄啊，点燃那最初的骄阳|7`（意义转折，菱形）与 "
      "`3.7|魔女的孤诣课题|21`（兑现，星形）。")
    A("")
    A("## 1. 方法链路（每个点怎么来的）")
    A("")
    A("1. **记录**：`amphoreus.final.jsonl` 中 `canonical_speaker == 角色` 的记录（记录 id 与 `ids.json` 对齐，共 %d 条）。" % meta["n_records_total"])
    A("2. **向量**（复用 `data/models/`，未重新训练）：")
    A("   - 词频加权：`vec_rec.joblib`（analyzer=tokenize, ngram=(1,2), min_df=2, sublinear_tf）对 `text_clean` 做映射（%d 维）；" % meta["tfidf_dim"])
    A("   - 语义向量：`Z_sbert_rec.npy`（bge-small-zh-v1.5，512 维，已 L2 归一）按记录 id 取行。")
    A("3. **步骤聚合**：按 `(version, task, step_idx)` 分组，取该角色台词的**均值向量**（词频加权 行均值后再归一；语义向量 行均值后再归一），"
      "同时保存「记录级最大值」`*_own_max`、台词条数 `n_lines`、记录 id 列表 `record_ids`（可回查）。")
    A("4. **神谕向量**：`vec_rec.transform(13 条神谕原文)`（词频加权）；语义向量 用同一模型现场编码 13 条神谕（`normalize_embeddings=True`），"
      "两条向量都保存在 JSON 的 `oracle_vectors` 里。")
    A("5. **余弦**：`cos(步骤均值向量, 自己神谕向量)`；同时保存与**全部 13 条神谕**的相似度向量。")
    A("6. **平滑**：原始值 + 居中滚动均值（窗口 %d 步，基于该角色自己的出场步骤序列）。" % ROLL_WIN)
    A("7. **时间轴**：`order`（3.0→3.7）；版本边界：%s。" % "、".join("%s@%d" % (k, v) for k, v in vbound.items()))
    A("")
    A("**own oracle 映射**：%s；开拓者与三月七没有自己的神谕 → 曲线取「与 13 条神谕的最高相似度」；"
      "丹恒承接大地火种 → own = O12（大地线）。" % "；".join(
          "%s→%s" % (c, "、".join(chars[c]["own_oracles"]) or "无") for c in CHARS))
    A("")
    A("**数据一致性**：记录级 词频加权 相似度与已有 `S_oracle_rec.npy`（13×26332）最大绝对差 = **%s**；"
      "总记录 %d / 总步骤 %d。" % (
          meta["crosscheck_max_abs_diff"], meta["n_records_total"], meta["n_steps_total"]))
    A("")

    # ---- 逐角色观察（分组） ----
    obs = []
    for c in CHARS:
        ch = chars[c]
        s = ch["summary"]
        steps = ch["steps"]
        if not steps:
            continue
        ps = s["peak_sbert_roll5"]
        pt = s["peak_tfidf_roll5"]
        near_rec = [a for a in ch["annotations"]["recitations"] if abs(a["order"] - ps["order"]) <= 40]
        near_ful = [a for a in ch["annotations"]["events"] if abs(a["order"] - ps["order"]) <= 40]
        align = ("峰值附近 40 个 order 内有吟诵步 %d 处" % len(near_rec) if near_rec else "峰值附近没有吟诵步") + \
                ("；事件段 %d 处" % len(near_ful) if near_ful else "；也没有事件段")
        best_other = max(steps, key=lambda x: x["best_other_sbert_sim"])
        obs.append({"char": c, "group": ch.get("group", "A"), "n_records": ch["n_records"],
                    "n_steps": ch["n_steps"],
                    "own": "、".join(ch["own_oracles"]) or "无（取最高）",
                    "mean_tfidf": s["mean_tfidf_own"], "mean_sbert": s["mean_sbert_own"],
                    "peak_sbert": ps, "peak_tfidf": pt, "align": align,
                    "best_other": best_other["best_other_sbert"],
                    "best_other_sim": best_other["best_other_sbert_sim"],
                    "range_tfidf": (min(x["tfidf_own"] for x in steps), max(x["tfidf_own"] for x in steps)),
                    "range_sbert": (min(x["sbert_own"] for x in steps), max(x["sbert_own"] for x in steps)),
                    "forms": dict(Counter(x.get("dominant_form") for x in steps if x.get("dominant_form")))})

    def render_obs(o):
        ps, pt = o["peak_sbert"], o["peak_tfidf"]
        A("### %s（%s，%d 条台词 / %d 步）" % (o["char"], o["own"], o["n_records"], o["n_steps"]))
        A("")
        A("- 语义向量 峰值（滚动 5 步）：**%.3f** @ order %d（%s「%s」）；词频加权 峰值：%.3f @ order %d（%s）。" % (
            ps["value"], ps["order"], ps["version"], (ps["step_title"] or "")[:20],
            pt["value"], pt["order"], pt["version"]))
        A("- 曲线范围：词频加权 %.2f–%.2f，语义向量 %.2f–%.2f；均值 %.3f / %.3f（词频加权 / 语义向量）。" % (
            o["range_tfidf"][0], o["range_tfidf"][1], o["range_sbert"][0], o["range_sbert"][1],
            o["mean_tfidf"], o["mean_sbert"]))
        A("- 峰值对齐：%s。" % o["align"])
        A("- 与「最相似的其他神谕」：%s（相似度 %.3f）；own oracle 在该点的领先幅度见 JSON 的 `best_other_*`。" % (
            o["best_other"], o["best_other_sim"]))
        if o["char"] == "丹恒":
            A("- **相关注记**：荒笛（NPC，70 条 / 4 步，样本量小）是大地前任；**大地承接：荒笛 → 丹恒**。")
        if o["char"] == "遐蝶":
            A("- **相关注记**：玻吕茜亚（NPC，遐蝶之妹）与遐蝶共有 O05 神谕（「汝将凋零…」，holder=玻吕茜亚，不归遐蝶的 O04）。")
        if o["forms"]:
            A("- 形态分布（按步的主形态）：%s。" % "、".join(
                "%s %d 步" % (k, v) for k, v in sorted(o["forms"].items(), key=lambda kv: -kv[1])))
        if o["n_records"] < 100:
            A("- **样本量提示**：仅 %d 条台词 / %d 步，曲线噪声大，不宜单独下结论。" % (
                o["n_records"], o["n_steps"]))
        A("")

    A("## 2. A 组：黄金裔 11 位（逐角色观察）")
    A("")
    A("> **尺度提醒**：词频加权 的绝对相似度普遍很低（own 峰值约 0.02–0.19），因为神谕文本只有 10–20 字、"
      "词表稀疏；请比较曲线形状与相对高低，不要把 词频加权 绝对值与 语义向量（约 0.5–0.7）直接横比。")
    A("")
    for o in obs:
        if o["group"] == "A":
            render_obs(o)
    A("## 3. B 组：单列 3 人（开拓者 / 三月七 / 丹恒；不与黄金裔比较）")
    A("")
    A("> B 组三人的主线塑造在翁法罗斯之外；本节只做单独观察，**不放进黄金裔的横向排序/均值比较**。")
    A("")
    for o in obs:
        if o["group"] == "B":
            render_obs(o)
    A("## 4. 两个空间不一致的案例")
    A("")
    diffs = []
    for c in CHARS:
        for s in chars[c]["steps"]:
            diffs.append((abs(s["tfidf_own"] - s["sbert_own"]), c, s))
    diffs.sort(key=lambda x: -x[0])
    A("词频加权 与 语义向量 的 own-oracle 相似度差异最大的 3 个点（|Δ| 降序）：")
    A("")
    A("| # | 角色 | 组 | order/版本 | 步骤 | 词频加权 | 语义向量 | Δ | 说明 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for i, (d, c, s) in enumerate(diffs[:3], 1):
        A("| %d | %s | %s | %d / %s | %s | %.3f | %.3f | %+.3f | %s |" % (
            i, c, chars[c].get("group", "A"), s["order"], s["version"], (s["step_title"] or "")[:14],
            s["tfidf_own"], s["sbert_own"], s["sbert_own"] - s["tfidf_own"],
            "词面有神谕关键词但句义不同" if s["tfidf_own"] > s["sbert_own"] else "词面不像、句义更接近"))
    A("")
    n_argmax_diff = sum(1 for c in CHARS for s in chars[c]["steps"]
                        if s["argmax_tfidf"] != s["argmax_sbert"])
    n_steps_total = sum(len(chars[c]["steps"]) for c in CHARS)
    A("此外，**argmax 神谕不一致**（词频加权 与 语义向量 各自最相似的神谕不同）的步骤有 **%d/%d = %.1f%%**——"
      "两个空间给出的「最像哪条神谕」并不总一致。" % (
          n_argmax_diff, n_steps_total, 100.0 * n_argmax_diff / n_steps_total))
    A("")
    A("## 5. 局限")
    A("")
    A("1. **词频加权 是词面相似**：会因共享「汝将/涛声/火种」等词而高，不代表语义读懂；语义向量 是句子级语义，"
      "但仍非「含义强度」，两者都不能直接当作「角色理解了神谕」的证据。")
    A("2. **3.5 嵌套闪回**：3.5 版本内有大量回放/嵌套叙事（如 O10/O11 的镜像段），order 是全局顺序，"
      "闪回内容会与当前时间线错位；曲线在 3.5 附近的峰可能只是「在复述过去」，不是「当下剧情」的峰。")
    A("3. **稀疏角色样本量小**：刻律德菈 %d 步、海瑟音 %d 步（A 组）与三月七 %d 步（B 组），"
      "滚动均值与峰值的稳定性有限；荒笛（NPC，70 条 / 4 步）只在丹恒条目内说明、不单列曲线。" % (
          chars["刻律德菈"]["n_steps"], chars["海瑟音"]["n_steps"], chars["三月七"]["n_steps"]))
    A("4. **B 组 own oracle 口径不同**：开拓者/三月七没有自己的神谕，曲线取「与 13 条神谕的最高相似度」，"
      "与黄金裔的 own-oracle 曲线不可直接比大小；丹恒 own=O12 为大地承接设定。")
    A("5. 步骤均值向量丢失了步内分布；`*_own_max`（记录级最大）保留了上界信息，可对照看。")
    A("")
    A("## 6. 复现与自校验")
    A("")
    A("```bash")
    A(RUN_CMD)
    A("conda run -n nlpLesson python tools/oracle_similarity_curves.py --verify")
    A("```")
    A("")
    A("- 无随机：向量资产复用、模型推理 deterministic；`--verify` 从 JSON 抽查 5 个点重算 step 均值向量余弦。")
    A("- JSON 保存每步的 `record_ids`、`record_id_span`、13 神谕相似度向量、神谕向量（词频加权 稀疏项 + 语义向量 512 维），"
      "任何点可按「记录 id → 向量 → 均值 → 余弦」复算。")
    A("")
    return "\n".join(Lr)


# ---------------------------------------------------------------------------
# 6) 主流程 / 校验
# ---------------------------------------------------------------------------
def build():
    ids, recs_ordered, seg_by_key, segs, oracles, vec, X, Z = load_all()
    own_map = oracle_mapping(oracles)
    cite = read_json(P_CITE)["occurrences"]
    filled_v2 = read_json(P_FILLED_V2)
    keys = read_json(P_KEYS)
    knife = read_json(P_KNIFE)
    vbound = version_boundaries(segs)
    print("计算 14 角色曲线（词频加权 + 语义向量）…")
    steps_out, OT, OS, oids, cross = compute_curves(
        ids, recs_ordered, seg_by_key, oracles, X, Z, own_map, cite, filled_v2, keys, knife)
    meta = {
        "script": "tools/oracle_similarity_curves.py",
        "run_command": RUN_CMD,
        "assets": {
            "vec_rec": "data/models/vec_rec.joblib（记录级 词频加权，未重训）",
            "ids": "data/models/ids.json（records 26332 / oracles 13）",
            "Z_sbert_rec": "data/models/Z_sbert_rec.npy（bge-small-zh-v1.5，26332×512，已归一）",
        },
        "model": MODEL_NAME,
        "tfidf_dim": int(OT.shape[1]),
        "n_records_total": len(recs_ordered),
        "n_steps_total": sum(len(ch["steps"]) for ch in steps_out.values()),
        "own_oracle_definition": "max_over_own_oracles（遐蝶 = O04，O05 归玻吕茜亚不进主名单；开拓者/三月七无自有神谕 → 取 13 条最高；丹恒承接大地 → O12）",
        "groups": {"A_11黄金裔": GROUP_A, "B_单列3": GROUP_B,
                   "note": "荒笛、玻吕茜亚按 NPC 处理，只在相关角色条目内说明，不单列分析/曲线。",
                   "note": "按用户最终口径：黄金裔=11 位（岁月席位历史更替）；玻吕茜亚仅注记、不画曲线。"},
        "rolling_window": ROLL_WIN,
        "method_chain": "text_clean → vec_rec.transform（词频加权）/ Z_sbert_rec 行（语义向量）→ 按 (version,task,step_idx) 取均值向量 → 归一 → 与神谕向量余弦 → 居中滚动均值(5)",
        "crosscheck_max_abs_diff": cross.get("max_abs_diff_vs_S_oracle_rec"),
        "version_boundaries": vbound,
        "note": "纵轴=与神谕文本的相似度（余弦），不是含义强度。归属修正：O05 holder=玻吕茜亚（不归遐蝶）；"
                "丹恒承接大地火种 → own=O12（大地线=荒笛↔丹恒）；O13 有 3.4|点燃|7（意义转折）+ 3.7|魔女|21（兑现）两个事件段。",
    }
    data = write_outputs(steps_out, OT, OS, oids, own_map, vec, meta)
    os.makedirs(FIG_DIR, exist_ok=True)
    for char in CHARS:
        out = os.path.join(FIG_DIR, "%s.png" % char)
        make_character_figure(char, steps_out[char], vbound, out)
    print("已生成 14 张单人曲线图 → %s" % os.path.relpath(FIG_DIR, ROOT))
    mat_t, mat_s = make_heatmap(steps_out, FIG_HEAT)
    print("已生成 %s（%.1f KB）" % (os.path.relpath(FIG_HEAT, ROOT), os.path.getsize(FIG_HEAT) / 1024.0))
    md = render_report(data, mat_t, mat_s, vbound)
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s（%.1f KB）" % (os.path.relpath(OUT_MD, ROOT), os.path.getsize(OUT_MD) / 1024.0))
    if HAS_CJK:
        print("中文字体：%s" % CJK_FONT)
    try:
        from export_plot_data import export_for
        export_for("tools/oracle_similarity_curves.py")
    except Exception as _e:
        print("  [plot_data] 跳过：%s" % _e, file=sys.stderr)
    if not verify(data, verbose=True):
        print("!! 校验失败", file=sys.stderr)
        sys.exit(1)
    print("\n校验通过：14 角色曲线齐全（荒笛/玻吕茜亚按 NPC 处理），抽查 5 点可从 JSON + 资产复算。")


def verify(data=None, verbose=False):
    problems = []
    if data is None:
        if not os.path.exists(OUT_JSON):
            print("缺少 %s" % OUT_JSON, file=sys.stderr)
            return False
        data = read_json(OUT_JSON)
    chars = data["characters"]
    if len(chars) != 14:
        problems.append("角色数 %d != 14" % len(chars))
    ids, recs_ordered, seg_by_key, segs, oracles, vec, X, Z = load_all()
    oids = [o["oracle_id"] for o in oracles]
    idx_by_id = {rid: i for i, rid in enumerate(ids["records"])}
    OTn = normalize(vec.transform([o["text"] for o in oracles]))
    OS = np.array([[float(x) for x in data["oracle_vectors"]["sbert"][o]] for o in oids], dtype=np.float32)
    OSn = normalize(OS)
    # 抽查 5 个点（固定规则，跨角色/版本）
    picks = [("白厄", 0.10), ("万敌", 0.30), ("遐蝶", 0.50), ("昔涟", 0.70), ("开拓者", 0.90)]
    checks = []
    for char, frac in picks:
        steps = chars[char]["steps"]
        st = steps[min(len(steps) - 1, int(len(steps) * frac))]
        idx = [idx_by_id[rid] for rid in st["record_ids"]]
        xmean = np.asarray(X[idx].mean(axis=0)).ravel().astype(np.float32)
        xmean /= (np.linalg.norm(xmean) + 1e-12)
        sims_t = np.asarray(OTn.dot(xmean)).ravel()
        own = [oids.index(o) for o in chars[char]["own_oracles"]]
        rec_t = float(max(sims_t[i] for i in own)) if own else float(sims_t.max())
        zmean = np.asarray(Z[idx].mean(axis=0)).astype(np.float32)
        zmean /= (np.linalg.norm(zmean) + 1e-12)
        sims_s = OSn.dot(zmean)
        rec_s = float(max(sims_s[i] for i in own)) if own else float(sims_s.max())
        d_t = abs(rec_t - st["tfidf_own"])
        d_s = abs(rec_s - st["sbert_own"])
        checks.append((char, st["order"], st["version"], d_t, d_s))
        if d_t > 2e-4 or d_s > 2e-4:
            problems.append("抽查点复算不一致：%s order=%d（Δtfidf=%.2e, Δsbert=%.2e）" % (
                char, st["order"], d_t, d_s))
    # 图与文件
    for char in CHARS:
        p = os.path.join(FIG_DIR, "%s.png" % char)
        if not os.path.exists(p) or os.path.getsize(p) < 5000:
            problems.append("%s 单人图不存在或过小" % char)
    if not os.path.exists(FIG_HEAT) or os.path.getsize(FIG_HEAT) < 5000:
        problems.append("热力图不存在或过小")
    if os.path.exists(OUT_CSV):
        import csv as _csv
        with open(OUT_CSV, "r", encoding="utf-8-sig") as f:
            n_rows = sum(1 for _ in f) - 1
        n_steps = sum(len(chars[c]["steps"]) for c in CHARS)
        if n_rows != n_steps:
            problems.append("CSV 行数 %d != JSON 步骤数 %d" % (n_rows, n_steps))
    else:
        problems.append("缺少 CSV")
    md = open(OUT_MD, "r", encoding="utf-8").read() if os.path.exists(OUT_MD) else ""
    for c in CHARS:
        if c not in md:
            problems.append("报告缺少角色 %s" % c)
    for kw in ("每个点怎么来的", "与神谕文本的相似度", "3.5 嵌套闪回", "荒笛", "丹恒",
               "玻吕茜亚", "三月七", "A 组", "B 组", "NPC 处理"):
        if kw not in md:
            problems.append("报告缺少章节/口径：%s" % kw)
    if verbose:
        print("\n抽查 5 点（角色, order, 版本, Δ词频加权, Δ语义向量）：")
        for c in checks:
            print("  %-5s order=%4d %s | Δtfidf=%.2e Δsbert=%.2e" % c)
        print("14 角色 / %d 步；CSV 行数 %d" % (
            sum(len(chars[c]["steps"]) for c in CHARS),
            (sum(1 for _ in open(OUT_CSV, encoding="utf-8-sig")) - 1) if os.path.exists(OUT_CSV) else -1))
    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="14 角色 × 神谕相似度全程曲线")
    ap.add_argument("--verify", action="store_true", help="只校验已有产物（抽查 5 点复算）")
    args = ap.parse_args()
    if args.verify:
        ok = verify(verbose=True)
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    build()


if __name__ == "__main__":
    main()
