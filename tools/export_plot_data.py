#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
export_plot_data.py — 图-数据配对归档（task-26）

规范：docs/交付物规格.md §2 —— 每张图与「它实际画的那份处理后数据」成对存储：
  data/plot_data/<图名>.csv       列名=图上轴/分组，一行一个绘图单元（不存全量原始语料）
  data/plot_data/<图名>.meta.json  figure/title/axes/plot_data_csv/sources/filters/generator/
                                   run_command/data_sha256_16/created_at

用法：
  conda run -n nlpLesson python tools/export_plot_data.py --all     # 生成新图 + 全部配对 + index
  conda run -n nlpLesson python tools/export_plot_data.py --verify  # 校验配对完整性/sha256/index 行数
  其他绘图脚本在重画图后调用 export_for("tools/xxx.py") 自动同步配对数据。
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(ROOT, "docs", "report", "figures")
PLOT_DIR = os.path.join(ROOT, "data", "plot_data")
INDEX_MD = os.path.join(ROOT, "docs", "report", "figures-index.md")
MODELS = os.path.join(ROOT, "data", "models")

P_ANNOT = os.path.join(ROOT, "data", "config", "annotation-labels.json")
P_A = os.path.join(ROOT, "data", "config", "baseline-a-scores.json")
P_B1 = os.path.join(ROOT, "data", "config", "baseline-b-scores.json")
P_STYLE = os.path.join(ROOT, "data", "config", "style-compare-results.json")
P_CITE = os.path.join(ROOT, "data", "config", "oracle-citation-coding.json")
P_KNIFE_RES = os.path.join(ROOT, "data", "config", "knife-scene-scores.json")
P_TRAJ = os.path.join(ROOT, "data", "config", "character-trajectory.json")
P_TRAJ_ALL = os.path.join(ROOT, "data", "config", "character-trajectory-all.json")
P_CURVES = os.path.join(ROOT, "data", "config", "oracle-similarity-curves.json")
P_TYPESIG = os.path.join(ROOT, "data", "config", "type-and-oracle-significance.json")
P_KNIFE = os.path.join(ROOT, "data", "config", "knife-scenes.json")
P_FILLED = os.path.join(ROOT, "data", "config", "oracle-fulfillment.filled.json")
P_CORPUS = os.path.join(ROOT, "data", "corpus", "amphoreus.final.jsonl")
P_SEGS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_IDS = os.path.join(MODELS, "ids.json")

RUN = {
    "tools/make_figures.py": "conda run -n nlpLesson python tools/make_figures.py",
    "tools/knife_scene_eval.py": "conda run -n nlpLesson python tools/knife_scene_eval.py",
    "tools/character_trajectory.py": "conda run -n nlpLesson python tools/character_trajectory.py --all",
    "tools/oracle_similarity_curves.py": "conda run -n nlpLesson python tools/oracle_similarity_curves.py",
    "tools/export_plot_data.py": "conda run -n nlpLesson python tools/export_plot_data.py --all",
}

# 与 tools/export_artifacts.py 完全一致的分词器（vec_word/vec_rec.joblib 反序列化依赖 __main__.tokenize）
import jieba  # noqa: E402

STOP = set("""
的 了 是 在 我 你 他 她 它 我们 你们 他们 这 那 这个 那个 一个 一种 什么 怎么 为什么 不 也 都 就 而 与 和 或
但 却 又 很 更 最 非常 已经 还是 因为 所以 如果 虽然 但是 然后 可以 没有 不是 自己 这样 那样 一些 这些 那些
啊 吧 呢 吗 呀 哦 唉 嗯 唔 诶 哈 呵 诶 之 其 者 也 矣 焉 哉
""".split())
KEEP_SINGLE = set("汝 吾 尔 她 他 我 你 花 海 火 光 梦 死 生 爱 痛 刀 剑 星 月 日 夜 风 雨 雪 冰 雷".split())


def tokenize(text):
    toks = []
    for w in jieba.cut(text or ""):
        w = w.strip()
        if not w or w in STOP:
            continue
        if len(w) == 1 and w not in KEEP_SINGLE and not w.isdigit() and not w.isascii():
            continue
        toks.append(w)
    return toks


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
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


def sha256_16_bytes(b):
    return hashlib.sha256(b).hexdigest()[:16]


def _rel(path):
    x = os.path.relpath(path, ROOT) if os.path.isabs(path) else path
    return x.replace(os.sep, "/")


def created_at(sources):
    mtimes = []
    for s in sources:
        p = os.path.join(ROOT, s) if not os.path.isabs(s) else s
        if os.path.exists(p):
            mtimes.append(os.path.getmtime(p))
    ts = max(mtimes) if mtimes else os.path.getmtime(__file__)
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def _stem(fig):
    return os.path.splitext(fig)[0].replace("/", "__").replace(os.sep, "__")


def write_csv(path, columns, rows):
    import csv as _csv
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(columns)
        for r in rows:
            out = []
            for c in columns:
                v = r.get(c)
                if isinstance(v, float):
                    if v != v:
                        out.append("")
                    else:
                        out.append(("%.6f" % v).rstrip("0").rstrip("."))
                elif v is None:
                    out.append("")
                else:
                    out.append(v)
            w.writerow(out)


def write_pair(fig, columns, rows, title, axes, sources, filters, generator):
    os.makedirs(PLOT_DIR, exist_ok=True)
    stem = _stem(fig)
    csv_rel = "data/plot_data/%s.csv" % stem
    csv_path = os.path.join(ROOT, csv_rel)
    write_csv(csv_path, columns, rows)
    with open(csv_path, "rb") as f:
        sha = sha256_16_bytes(f.read())
    meta = {
        "figure": fig, "title": title, "axes": axes, "plot_data_csv": csv_rel,
        "sources": [s.replace(os.sep, "/") for s in sources],
        "filters": filters, "generator": generator,
        "run_command": RUN.get(generator, ""),
        "data_sha256_16": sha, "created_at": created_at(sources),
    }
    meta_rel = "data/plot_data/%s.meta.json" % stem
    with open(os.path.join(ROOT, meta_rel), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return fig, stem, len(rows)


# ===========================================================================
# 各图「实际绘制数据」重算
# ===========================================================================
def data_f1():
    annot = read_json(P_ANNOT)["samples"]
    A = {s["segment_id"]: s for s in read_json(P_A)["segments"]}
    B = {s["segment_id"]: s for s in read_json(P_B1)["segments"]}
    rows = []
    for s in annot:
        rows.append({"group": "A", "level": s["significance"], "score": A[s["segment_id"]]["score"]})
        rows.append({"group": "B1", "level": s["significance"], "score": B[s["segment_id"]]["score"]})
    return dict(columns=["group", "level", "score"], rows=rows,
                title="图1 A 与 B1 在人工等级 0/1/2/3 上的分数分布（箱线图）",
                axes={"x": "人工显著等级 0/1/2/3", "y": "检测器分数（z 化）"},
                sources=[P_ANNOT, P_A, P_B1],
                filters="74 个人工标注样本；A/B1 记录级分数；箱线图按等级分组")


def data_f2():
    A = {s["segment_id"]: s for s in read_json(P_A)["segments"]}
    B = {s["segment_id"]: s for s in read_json(P_B1)["segments"]}
    sids = sorted(A)
    deltas = [(sid, A[sid]["rank"] - B[sid]["rank"]) for sid in sids]
    top_up = {sid for sid, d in sorted(deltas, key=lambda x: -x[1])[:5]}
    top_down = {sid for sid, d in sorted(deltas, key=lambda x: x[1])[:5]}
    rows = [{"segment_id": sid, "a_rank": A[sid]["rank"], "b1_rank": B[sid]["rank"],
             "delta_a_minus_b1": A[sid]["rank"] - B[sid]["rank"],
             "is_top5_improved": int(sid in top_up), "is_top5_declined": int(sid in top_down)}
            for sid in sids]
    return dict(columns=["segment_id", "a_rank", "b1_rank", "delta_a_minus_b1",
                         "is_top5_improved", "is_top5_declined"], rows=rows,
                title="图2 686 步 A→B1 排名散点（标注 5 个最大提升/下降）",
                axes={"x": "A 检测器排名", "y": "B1 检测器排名（已反转：1 在顶部）"},
                sources=[P_A, P_B1],
                filters="686 候选步骤；排名 1-based；标注位=按 delta=A_rank−B1_rank 取最大/最小各 5")


def data_f3():
    style = read_json(P_STYLE)
    ov = style["overall"]["features"]
    feats = [("literary_rate", 1.0), ("modal_rate", 1.0), ("person2_rate", 1.0),
             ("person1_rate", 1.0), ("imperative_rate", 1.0), ("exclaim_rate", 1.0),
             ("char_len", 1.0), ("abstract_ratio", 100.0), ("repeat_token_rate", 100.0),
             ("parallel_rate", 100.0)]
    rows = []
    for g in ("G1", "G2", "G3"):
        for f, sc in feats:
            mean = ov[f][g]["mean"]
            rows.append({"group": g, "feature": f, "mean": mean, "scale": sc,
                         "value_plotted": mean * sc})
    return dict(columns=["group", "feature", "mean", "scale", "value_plotted"], rows=rows,
                title="图3 神谕 / 普通对白 / 角色引用的语体特征均值",
                axes={"x": "语体特征（比率类；长度/抽象/复沓类 ×100）", "y": "均值"},
                sources=[P_STYLE],
                filters="G1=神谕原文句、G2=普通对白句、G3=角色引用句；value_plotted=mean×scale，与图上柱高一致")


def data_f4():
    summ = read_json(P_CITE)["summary"]
    rows = []
    for v in sorted(summ["per_version"]):
        for st, n in summ["per_version"][v]["stages"].items():
            rows.append({"version": v, "stage": st, "count": n})
    return dict(columns=["version", "stage", "count"], rows=rows,
                title="图4 34 处神谕引用的 版本×阶段 堆叠分布",
                axes={"x": "版本", "y": "引用次数（堆叠=阶段）"},
                sources=[P_CITE],
                filters="34 处 occurrence；阶段取 oracle-citation-coding 的 stage 字段")


def data_f5():
    A = {s["segment_id"]: s for s in read_json(P_A)["segments"]}
    B = {s["segment_id"]: s for s in read_json(P_B1)["segments"]}
    gold = read_json(P_TYPESIG)["gold_ids"]
    rest = [sid for sid in A if sid not in set(gold)]
    rows = []
    for ds, ids, mp in (("A_gold", gold, A), ("A_rest", rest, A),
                        ("B1_gold", gold, B), ("B1_rest", rest, B)):
        for sid in ids:
            rows.append({"dataset": ds, "segment_id": sid, "score": mp[sid]["score"]})
    return dict(columns=["dataset", "segment_id", "score"], rows=rows,
                title="图5 神谕兑现段 vs 其余步骤的 A/B1 分数分布",
                axes={"x": "数据集（A/B1 × 兑现/其余）", "y": "检测器分数"},
                sources=[P_A, P_B1, P_TYPESIG, P_FILLED],
                filters="13 个神谕兑现段（type-and-oracle-significance.gold_ids）vs 其余 673 步；箱线图含 fliers")


def data_f6():
    d = read_json(P_KNIFE_RES)
    rows = []
    for s in d["scenes"]:
        rows.append({"scene_id": s["id"], "role": s["role"], "intensity": s["intensity"],
                     "n_pool_segments": s["n_pool_segments"],
                     "best_a": s["best_a"], "best_b1": s["best_b1"],
                     "best_a_minus_b1": s["best_a"] - s["best_b1"],
                     "is_double_miss": int(s["best_a"] > 100 and s["best_b1"] > 100)})
    return dict(columns=["scene_id", "role", "intensity", "n_pool_segments",
                         "best_a", "best_b1", "best_a_minus_b1", "is_double_miss"], rows=rows,
                title="图6 刀子/高光场景在 A / B1 下的排名分布",
                axes={"x": "A 场景级最好名次（log，图 b）", "y": "B1 场景级最好名次（log，图 b）"},
                sources=[P_KNIFE_RES],
                filters="35 个刀子场景（knife-scene-scores.json）；场景级最好名次=场景映射步骤的最小 rank")


ADDR_TERMS = ["老师", "开拓者", "伙伴", "救世主", "英雄", "黄金裔", "半神", "阁下"]
MOTIF_TERMS = ["火种", "逐火", "骄阳", "灰白的黎明", "明天见", "无名", "黎明", "记忆"]
FORM_TERMS = ["卡厄斯兰那", "心中的英雄", "盗火行者", "空白的愿望", "毁灭的容器",
              "幼年形态", "记忆形态", "往昔的涟漪", "迷迷"]
TRAJ_COLS = ["char", "version", "n_records", "n_steps", "n_tasks", "mean_text_len",
             "mean_score_a", "mean_score_b1", "top100_b1"] + \
            ["form_" + t for t in FORM_TERMS] + ["addr_" + t for t in ADDR_TERMS] + \
            ["motif_" + t for t in MOTIF_TERMS]


def _traj_data(path, key=None):
    chars = read_json(path)["characters"]
    keys = [key] if key else list(chars)
    rows = []
    for c in keys:
        ch = chars[c]
        for v, pv in ch["per_version"].items():
            row = {"char": c, "version": v, "n_records": pv["n_records"],
                   "n_steps": pv["n_steps"], "n_tasks": pv["n_tasks"],
                   "mean_text_len": pv["mean_text_len"],
                   "mean_score_a": pv["mean_score_a"], "mean_score_b1": pv["mean_score_b1"],
                   "top100_b1": pv["top100_b1"]}
            for t in FORM_TERMS:
                row["form_" + t] = pv["forms"].get(t, 0)
            for t in ADDR_TERMS:
                row["addr_" + t] = pv["address_own"].get(t, 0)
            for t in MOTIF_TERMS:
                row["motif_" + t] = pv["motif_own"].get(t, 0)
            rows.append(row)
    return rows


def data_f7():
    rows = _traj_data(P_TRAJ, "白厄")
    return dict(columns=TRAJ_COLS, rows=rows,
                title="图7 白厄全程轨迹（台词量/形态/称呼/母题/A-B 分数）",
                axes={"x": "版本 3.0–3.7", "y": "台词条数 / 命中次数 / 分数（各子图不同）"},
                sources=[P_TRAJ],
                filters="白厄 canonical 记录；版本聚合；称呼/母题只统计其自己台词")


def data_f8():
    rows = _traj_data(P_TRAJ, "昔涟")
    return dict(columns=TRAJ_COLS, rows=rows,
                title="图8 昔涟全程轨迹（台词量/形态/称呼/母题/A-B 分数）",
                axes={"x": "版本 3.0–3.7", "y": "台词条数 / 命中次数 / 分数（各子图不同）"},
                sources=[P_TRAJ],
                filters="昔涟 canonical 记录；版本聚合；形态含 迷迷/往昔的涟漪/记忆形态/另一位作者")


def data_f9():
    d = read_json(P_TRAJ_ALL)
    rows = []
    for c, ch in d["characters"].items():
        if ch.get("group") not in ("A", "B"):
            continue
        for v, pv in ch["per_version"].items():
            rows.append({"char": c, "group": ch["group"], "version": v,
                         "n_records": pv["n_records"], "n_steps": pv["n_steps"]})
    return dict(columns=["char", "group", "version", "n_records", "n_steps"], rows=rows,
                title="图9 14 个角色分版本台词量（A 组 11 + B 组 3）",
                axes={"x": "版本", "y": "角色（格内=台词条数，颜色=log 值）"},
                sources=[P_TRAJ_ALL],
                filters="A 组 11 黄金裔 + B 组 3 单列；荒笛/玻吕茜亚为注记，不入图")


def data_f10():
    d = read_json(P_TRAJ_ALL)
    rows = []
    for c, ch in d["characters"].items():
        if ch.get("group") not in ("A", "B"):
            continue
        rows.append({"char": c, "group": ch["group"],
                     "n_steps": ch["summary"]["n_steps"],
                     "deep_n": ch["coverage"]["union_knife_key_events"]["n"],
                     "annotation_n": ch["coverage"]["annotation"]["n"],
                     "deep_rate": ch["coverage"]["union_knife_key_events"]["rate"]})
    return dict(columns=["char", "group", "n_steps", "deep_n", "annotation_n", "deep_rate"], rows=rows,
                title="图10 14 个角色：出场步骤 vs 精读覆盖",
                axes={"x": "步骤数", "y": "角色"},
                sources=[P_TRAJ_ALL],
                filters="A11+B3；深读=K36 刀子 ∪ 30 关键事件；annotation=74 条标注")


def data_f11():
    d = read_json(P_CURVES)
    rows = []
    for c, ch in d["characters"].items():
        for v in ["3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"]:
            ss = [x for x in ch["steps"] if x["version"] == v]
            if not ss:
                continue
            rows.append({"char": c, "group": ch.get("group"), "version": v,
                         "n_steps": len(ss),
                         "tfidf_own_mean": sum(x["tfidf_own"] for x in ss) / len(ss),
                         "sbert_own_mean": sum(x["sbert_own"] for x in ss) / len(ss)})
    return dict(columns=["char", "group", "version", "n_steps", "tfidf_own_mean", "sbert_own_mean"],
                rows=rows,
                title="图11 14 角色 × 8 版本的「与神谕文本相似度」总览",
                axes={"x": "版本", "y": "角色（格内=版本均值；左 TF-IDF / 右 SBERT）"},
                sources=[P_CURVES],
                filters="每格=该角色该版本各出场步骤 own-oracle 余弦的均值")


SIM_COLS = ["order", "version", "task", "step_idx", "step_title", "n_lines",
            "tfidf_own", "sbert_own", "tfidf_roll5", "sbert_roll5", "dominant_form",
            "in_oracle_first", "in_recitation", "in_fulfillment", "in_meaning_turn",
            "in_key_event", "in_knife"]


def _sim_char(char):
    ch = read_json(P_CURVES)["characters"][char]
    ann = ch["annotations"]
    first = set(ann["oracle_first_orders"])
    recits = {a["order"] for a in ann["recitations"]}
    ful = {a["order"] for a in ann["events"] if a.get("role") == "兑现"}
    turns = {a["order"] for a in ann["events"] if a.get("role") != "兑现"}
    keys = {a["order"] for a in ann["key_events"]}
    knife = {a["order"] for a in ann["knife_scenes"]}
    rows = []
    for s in ch["steps"]:
        o = s["order"]
        rows.append({"order": o, "version": s["version"], "task": s["task"],
                     "step_idx": s["step_idx"], "step_title": s.get("step_title"),
                     "n_lines": s["n_lines"], "tfidf_own": s["tfidf_own"],
                     "sbert_own": s["sbert_own"], "tfidf_roll5": s["tfidf_roll5"],
                     "sbert_roll5": s["sbert_roll5"], "dominant_form": s.get("dominant_form"),
                     "in_oracle_first": int(o in first), "in_recitation": int(o in recits),
                     "in_fulfillment": int(o in ful), "in_meaning_turn": int(o in turns),
                     "in_key_event": int(o in keys), "in_knife": int(o in knife)})
    own = "、".join(ch["own_oracles"]) if ch["own_oracles"] else "无自有（取 13 条最高）"
    return dict(columns=SIM_COLS, rows=rows,
                title="神谕相似度全程曲线：%s（own oracle=%s）" % (char, own),
                axes={"x": "order（3.0→3.7）；左轴 TF-IDF、右轴 SBERT",
                      "y": "与神谕文本的相似度（余弦，不是含义强度）"},
                sources=[P_CURVES, P_CITE, P_FILLED, P_KNIFE],
                filters="步骤均值向量 vs own oracle；滚动均值窗口 5；标注=首现/吟诵/兑现/意义转折/关键事件/刀子")


# ---- 新增 3 张报告图 ----
def data_f12():
    rows_all = []
    for r in read_jsonl(P_CORPUS):
        if "明天见" in (r.get("text") or ""):
            spk = r.get("canonical_speaker") or ("旁白" if r.get("kind") == "narration" else (r.get("speaker") or "其他"))
            rows_all.append({"record_id": r["id"], "order": r["order"], "version": r["version"],
                             "task": r["task"], "step_idx": r["step_idx"], "speaker": spk})
    from collections import Counter
    top = [s for s, _ in Counter(x["speaker"] for x in rows_all).most_common(8)]
    rows = []
    for v in ["3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"]:
        sub = [x for x in rows_all if x["version"] == v]
        for spk in top + ["其他"]:
            n = sum(1 for x in sub if (x["speaker"] if x["speaker"] in top else "其他") == spk)
            if n:
                rows.append({"version": v, "speaker": spk, "count": n})
    return dict(columns=["version", "speaker", "count"], rows=rows,
                title="图12「明天见」时间线：按版本×说话人的出现次数",
                axes={"x": "版本", "y": "出现次数（堆叠=说话人 top8 + 其他）"},
                sources=[P_CORPUS],
                filters="全语料 26332 条记录中 text 含「明天见」；说话人取 canonical_speaker（旁白=旁白）")


def data_f13():
    knife = read_json(P_KNIFE)
    k36 = next((s for s in knife["scenes"] if s["id"] == "K36"), None)
    ref = (k36["title"] + " " + (k36.get("why") or "")) if k36 else "水晶花寓言"
    ids = read_json(P_IDS)
    segs = read_jsonl(P_SEGS)
    seg_by_id = {s["segment_id"]: s for s in segs}
    import joblib
    import scipy.sparse as sp
    from sklearn.preprocessing import normalize
    vec_word = joblib.load(os.path.join(MODELS, "vec_word.joblib"))
    X_word = sp.load_npz(os.path.join(MODELS, "X_word.npz"))
    q_tf = normalize(vec_word.transform([ref]))
    tf = np.asarray(q_tf.dot(normalize(X_word).T).todense()).ravel()
    Z_seg = np.load(os.path.join(MODELS, "Z_sbert_seg.npy"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(1)
    model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")
    q_s = model.encode([ref], normalize_embeddings=True)[0]
    sb = np.asarray(Z_seg.dot(q_s)).ravel()
    order = {sid: i for i, sid in enumerate(ids["segments"])}
    rows = []
    for sid in ids["segments"]:
        seg = seg_by_id.get(sid) or {}
        i = order[sid]
        rows.append({"segment_id": sid, "order": seg.get("order"), "version": seg.get("version"),
                     "tfidf_sim": round(float(tf[i]), 6), "sbert_sim": round(float(sb[i]), 6)})
    def roll(vals, w=25):
        a = np.asarray(vals, dtype=float)
        half = w // 2
        return [float(a[max(0, i - half):min(len(a), i + half + 1)].mean()) for i in range(len(a))]
    rt, rs = roll([r["tfidf_sim"] for r in rows]), roll([r["sbert_sim"] for r in rows])
    for r, a, b in zip(rows, rt, rs):
        r["tfidf_roll25"] = round(a, 6)
        r["sbert_roll25"] = round(b, 6)
    return dict(columns=["segment_id", "order", "version", "tfidf_sim", "sbert_sim",
                         "tfidf_roll25", "sbert_roll25"], rows=rows,
                title="图13「水晶花寓言」语义曲线：686 个步骤 vs K36 参考文本（TF-IDF + SBERT）",
                axes={"x": "order（3.0→3.7）", "y": "与参考文本的余弦相似度（细线=原始，粗线=滚动均值 25）"},
                sources=[P_KNIFE, P_SEGS, "data/models/vec_word.joblib", "data/models/X_word.npz",
                         "data/models/Z_sbert_seg.npy", "data/models/ids.json"],
                filters="参考文本=K36「水晶花寓言」title+why；步骤文本=segments.jsonl 的 686 个候选步骤")


def data_f14():
    ids = read_json(P_IDS)
    segs = read_jsonl(P_SEGS)
    seg_by_id = {s["segment_id"]: s for s in segs}
    S_tf = np.load(os.path.join(MODELS, "S_oracle_seg.npy"))
    S_sb = np.load(os.path.join(MODELS, "S_sbert_oracle_seg.npy"))
    oi = {o: i for i, o in enumerate(ids["oracles"])}
    i10, i11 = oi["O10"], oi["O11"]
    rows = []
    for j, sid in enumerate(ids["segments"]):
        seg = seg_by_id.get(sid) or {}
        rows.append({"segment_id": sid, "order": seg.get("order"), "version": seg.get("version"),
                     "tfidf_O10": round(float(S_tf[i10, j]), 6),
                     "tfidf_O11": round(float(S_tf[i11, j]), 6),
                     "sbert_O10": round(float(S_sb[i10, j]), 6),
                     "sbert_O11": round(float(S_sb[i11, j]), 6)})
    return dict(columns=["segment_id", "order", "version", "tfidf_O10", "tfidf_O11",
                         "sbert_O10", "sbert_O11"], rows=rows,
                title="图14 O10/O11 镜像对对照：686 步分别与两条神谕的相似度（TF-IDF + SBERT）",
                axes={"x": "order（3.0→3.7）", "y": "余弦相似度（O10 实线 / O11 虚线）"},
                sources=["data/models/S_oracle_seg.npy", "data/models/S_sbert_oracle_seg.npy",
                         "data/models/ids.json", P_SEGS],
                filters="13×686 相似度矩阵中取 O10/O11 两行；686 个候选步骤")


# ===========================================================================
# 规格表 / 导出
# ===========================================================================
def specs():
    sp = {
        "f1_level_scores.png": ("tools/make_figures.py", data_f1),
        "f2_rank_shift.png": ("tools/make_figures.py", data_f2),
        "f3_style_features.png": ("tools/make_figures.py", data_f3),
        "f4_citation_stage.png": ("tools/make_figures.py", data_f4),
        "f5_oracle_vs_rest.png": ("tools/make_figures.py", data_f5),
        "f6_knife_ranks.png": ("tools/knife_scene_eval.py", data_f6),
        "f7_bai_trajectory.png": ("tools/character_trajectory.py", data_f7),
        "f8_xi_trajectory.png": ("tools/character_trajectory.py", data_f8),
        "f9_all_trajectories.png": ("tools/character_trajectory.py", data_f9),
        "f10_coverage.png": ("tools/character_trajectory.py", data_f10),
        "f11_oracle_similarity_heatmap.png": ("tools/oracle_similarity_curves.py", data_f11),
        "f12_mingtian_timeline.png": ("tools/export_plot_data.py", data_f12),
        "f13_crystal_flower_semantic.png": ("tools/export_plot_data.py", data_f13),
        "f14_mirror_pair_O10_O11.png": ("tools/export_plot_data.py", data_f14),
    }
    for char in read_json(P_CURVES)["characters"]:
        sp["oracle_sim/%s.png" % char] = ("tools/oracle_similarity_curves.py",
                                          (lambda c: (lambda: _sim_char(c)))(char))
    return sp


def export_one(fig, generator, fn):
    if not os.path.exists(os.path.join(FIG_DIR, fig)):
        return None
    spec = fn()
    return write_pair(fig, spec["columns"], spec["rows"], spec["title"], spec["axes"],
                      [_rel(p) for p in spec["sources"]], spec["filters"], generator)


def export_for(generator):
    n = 0
    for fig, (gen, fn) in sorted(specs().items()):
        if gen != generator:
            continue
        try:
            if export_one(fig, gen, fn):
                n += 1
        except Exception as e:
            print("  [plot_data] 跳过 %s：%s" % (fig, e), file=sys.stderr)
    if n:
        write_index()
        print("[plot_data] 已为 %d 张图写入配对数据（generator=%s）" % (n, generator))
    return n


# ===========================================================================
# 新图（f12/f13/f14）
# ===========================================================================
def make_new_figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans SC"]:
        if cand in names:
            plt.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False
    os.makedirs(FIG_DIR, exist_ok=True)

    # f12
    d = data_f12()
    from collections import defaultdict
    by_v = defaultdict(dict)
    spk = []
    for r in d["rows"]:
        by_v[r["version"]][r["speaker"]] = r["count"]
        if r["speaker"] not in spk:
            spk.append(r["speaker"])
    versions = sorted(by_v)
    fig, ax = plt.subplots(figsize=(9.4, 4.6))
    bottom = np.zeros(len(versions))
    cmap = plt.get_cmap("tab20")
    for i, s in enumerate(spk):
        vals = np.array([by_v[v].get(s, 0) for v in versions], dtype=float)
        ax.bar(versions, vals, bottom=bottom, label=s, color=cmap(i % 20))
        bottom += vals
    ax.set_xlabel("版本")
    ax.set_ylabel("出现次数")
    ax.set_title("图12「明天见」时间线（按版本×说话人；全语料文本含「明天见」）", fontsize=10)
    ax.legend(fontsize=7, ncol=2, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "f12_mingtian_timeline.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)

    # f13
    d = data_f13()
    rows = [r for r in d["rows"] if r["order"] is not None]
    fig, ax = plt.subplots(figsize=(10.6, 4.8))
    ax.plot([r["order"] for r in rows], [r["tfidf_sim"] for r in rows],
            color="#a9c0d8", lw=0.6, alpha=0.6)
    ax.plot([r["order"] for r in rows], [r["tfidf_roll25"] for r in rows],
            color="#1f4e79", lw=2.0, label="TF-IDF 相似度（滚动25）")
    ax2 = ax.twinx()
    ax2.plot([r["order"] for r in rows], [r["sbert_sim"] for r in rows],
             color="#f0b27a", lw=0.6, alpha=0.6)
    ax2.plot([r["order"] for r in rows], [r["sbert_roll25"] for r in rows],
             color="#b9530f", lw=2.0, label="SBERT 相似度（滚动25）")
    ax.set_xlabel("order（3.0→3.7）")
    ax.set_ylabel("与参考文本的相似度（TF-IDF）", color="#1f4e79")
    ax2.set_ylabel("与参考文本的相似度（SBERT）", color="#b9530f")
    ax.set_title("图13「水晶花寓言」语义曲线：686 步 vs K36 参考文本（纵轴=相似度，不是含义强度）", fontsize=10)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, frameon=False, loc="upper left")
    ax.grid(alpha=0.22)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "f13_crystal_flower_semantic.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)

    # f14
    d = data_f14()
    rows = [r for r in d["rows"] if r["order"] is not None]
    rows.sort(key=lambda r: r["order"])
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 4.6), sharex=True)
    for ax, space in ((axes[0], "tfidf"), (axes[1], "sbert")):
        ax.plot([r["order"] for r in rows], [r[space + "_O10"] for r in rows],
                color="#c0392b", lw=1.5, label="O10（海瑟音词序）")
        ax.plot([r["order"] for r in rows], [r[space + "_O11"] for r in rows],
                color="#2e5c8a", lw=1.5, ls="--", label="O11（刻律德菈词序）")
        ax.set_title("(%s) O10 vs O11" % space.upper(), fontsize=9)
        ax.set_xlabel("order（3.0→3.7）")
        ax.grid(alpha=0.22)
        ax.legend(fontsize=8, frameon=False)
    axes[0].set_ylabel("余弦相似度")
    fig.suptitle("图14 O10/O11 镜像对对照：686 步分别与两条神谕的相似度", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(FIG_DIR, "f14_mirror_pair_O10_O11.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


# ===========================================================================
# index / verify / main
# ===========================================================================
def write_index():
    sp = specs()
    files = [fig for fig in sorted(sp) if os.path.exists(os.path.join(FIG_DIR, fig))]
    L = ["# 图表索引（图 ↔ 配对数据 ↔ 生成脚本）", "",
         "> 规范：`docs/交付物规格.md` §2。每张图在 `data/plot_data/<图名>.csv` 有「它实际画的数据」，"
         "并在 `<图名>.meta.json` 记录 axes/sources/filters/generator/sha256。",
         "> 本文件由 `tools/export_plot_data.py` 自动生成；行数 = 图数。", "",
         "| # | 图文件 | 配对 CSV | 配对 meta | 生成脚本 | 数据来源 | 说明 |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for i, fig in enumerate(files, 1):
        stem = _stem(fig)
        csv_rel = "data/plot_data/%s.csv" % stem
        meta_rel = "data/plot_data/%s.meta.json" % stem
        gen = sp[fig][0]
        meta = read_json(os.path.join(ROOT, meta_rel)) if os.path.exists(os.path.join(ROOT, meta_rel)) else {}
        src = "、".join(os.path.basename(x) for x in meta.get("sources", []))
        L.append("| %d | `docs/report/figures/%s` | `%s` | `%s` | `%s` | %s | %s |" % (
            i, fig, csv_rel, meta_rel, gen, src, meta.get("title", "")))
    L += ["", "## 换样式流程（改样式不改数据）", "",
          "1. 只改绘图脚本的样式（颜色/字号/布局），**不要改 `data/plot_data/<图名>.csv` 的数值**；",
          "2. 重新运行该图的生成脚本（脚本会自动调用 `export_for` 同步配对数据）；",
          "3. 比对 `data/plot_data/<图名>.meta.json` 的 `data_sha256_16`：与改样式前一致 = 数据未变；",
          "4. 若 sha256 变了，说明数据重算结果变化，需在提交说明里解释原因。", "",
          "校验：`conda run -n nlpLesson python tools/export_plot_data.py --verify`", ""]
    os.makedirs(os.path.dirname(INDEX_MD), exist_ok=True)
    with open(INDEX_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def verify():
    problems = []
    pngs = []
    for root, _, fs in os.walk(FIG_DIR):
        for fn in fs:
            if fn.lower().endswith(".png"):
                pngs.append(os.path.relpath(os.path.join(root, fn), FIG_DIR).replace(os.sep, "/"))
    pngs.sort()
    sp = specs()
    n_csv = n_meta = 0
    for fig in pngs:
        stem = _stem(fig)
        csv_rel = "data/plot_data/%s.csv" % stem
        meta_rel = "data/plot_data/%s.meta.json" % stem
        if not os.path.exists(os.path.join(ROOT, csv_rel)):
            problems.append("缺 CSV：%s" % fig)
        else:
            n_csv += 1
        if not os.path.exists(os.path.join(ROOT, meta_rel)):
            problems.append("缺 meta：%s" % fig)
            continue
        n_meta += 1
        meta = read_json(os.path.join(ROOT, meta_rel))
        with open(os.path.join(ROOT, csv_rel), "rb") as f:
            sha = sha256_16_bytes(f.read())
        if meta.get("data_sha256_16") != sha:
            problems.append("sha256 不一致：%s" % fig)
        for k in ("figure", "title", "axes", "plot_data_csv", "sources", "filters",
                  "generator", "run_command", "data_sha256_16", "created_at"):
            if k not in meta:
                problems.append("meta 缺字段 %s：%s" % (k, fig))
        if fig not in sp:
            problems.append("图未登记到 specs：%s" % fig)
    idx_rows = 0
    if not os.path.exists(INDEX_MD):
        problems.append("缺 figures-index.md")
    else:
        txt = open(INDEX_MD, "r", encoding="utf-8").read()
        idx_rows = sum(1 for line in txt.splitlines()
                       if line.startswith("| ") and "`docs/report/figures/" in line)
        if idx_rows != len(pngs):
            problems.append("index 行数 %d != 图数 %d" % (idx_rows, len(pngs)))
    print("图数=%d，CSV=%d，meta=%d，index 行数=%d" % (len(pngs), n_csv, n_meta, idx_rows))
    if problems:
        for p in problems[:30]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="图-数据配对归档")
    ap.add_argument("--all", action="store_true", help="生成新图 + 全部配对 + index")
    ap.add_argument("--verify", action="store_true", help="校验配对完整性与 sha256")
    args = ap.parse_args()
    if args.verify:
        ok = verify()
        print("校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    make_new_figures()
    total = 0
    for fig, (gen, fn) in sorted(specs().items()):
        if not os.path.exists(os.path.join(FIG_DIR, fig)):
            continue
        try:
            if export_one(fig, gen, fn):
                total += 1
        except Exception as e:
            print("  [plot_data] 跳过 %s：%s" % (fig, e), file=sys.stderr)
    write_index()
    print("已写 %d 组 csv+meta → data/plot_data/，并生成 docs/report/figures-index.md" % total)
    ok = verify()
    print("校验%s" % ("通过" if ok else "失败"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
