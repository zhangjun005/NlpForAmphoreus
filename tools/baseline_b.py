#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
baseline_b.py — 检测器 B：结构增强的叙事显著性检测（无标签先验打分）

口径来源：docs/实验口径与评测方案.md
  §3   候选池 = A 的同一批 686 个合格步骤（view=main、非 low_content、有对白）
  §5   权重先验固定；标注集**只用于评测**，不参与调参
  §9   特征在步骤内部按记录计算后聚合；滑窗 20 条 / 步长 10
  §11.1 一律基于 main_records 原始顺序
  §11.2 语义突变主排序用 top20_mean 与 p90，max 仅诊断；报告按长度分层
  §11.3 记录数 < 20：整步 1 窗、距离 = 0、short_for_window = true
  §11.4 母题回收拆两层：surface_repetition（repeat_kind）与 semantic_recall（词表匹配）

B = A 的词面分项（50%，直接复用 data/config/baseline-a-scores.json）
  + 语义突变（20%，TF-IDF 字符 n-gram 空间）
  + 身份/位置变化（15%）
  + 母题回收（10%）
  + 不可逆状态变化（5%）

硬约束：
  * 不引入 embedding / 外部模型 / 联网；TF-IDF（sklearn）+ jieba 分词
  * 标注 data/config/annotation-labels.json **只在评测段读取**，不进入任何特征或权重
  * 只写 2 个产物（JSON + MD）；不改语料、不改 A 的产物（脚本内校验 A JSON 哈希不变）

运行：
    conda run -n nlpLesson python tools/baseline_b.py            # 重算并写产物
    conda run -n nlpLesson python tools/baseline_b.py --verify   # 只校验产物自洽

产物：
    data/config/baseline-b-scores.json   686 步：score / 5 组子分 / 特征 raw+z / rank
    data/reports/baseline-b-ranking.md   B Top30、A/B 对比、vs 74 条人工标注、案例、分层、敏感性
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_SEGMENTS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_A_SCORES = os.path.join(ROOT, "data", "config", "baseline-a-scores.json")
P_ANNOT = os.path.join(ROOT, "data", "config", "annotation-labels.json")
P_ORACLE = os.path.join(ROOT, "data", "config", "oracle-fulfillment.filled.json")
P_VOCAB_ADDRESS = os.path.join(ROOT, "data", "config", "vocab-address.json")
P_VOCAB_MOTIF = os.path.join(ROOT, "data", "config", "vocab-motif.json")
P_VOCAB_ORACLE = os.path.join(ROOT, "data", "config", "vocab-oracle.json")
P_VOCAB_BALLAD = os.path.join(ROOT, "data", "config", "vocab-ballad.json")
OUT_JSON = os.path.join(ROOT, "data", "config", "baseline-b-scores.json")
OUT_MD = os.path.join(ROOT, "data", "reports", "baseline-b-ranking.md")

RUN_CMD = "conda run -n nlpLesson python tools/baseline_b.py"
FOCUS_CASE = "3.7|晨曦啊，再抚映遥远地平|4"  # 昔涟诞生 / 记忆的拼图（方向文档举的反例）

LENGTH_BINS = ["1–3 句", "4–10 句", "11–30 句", ">30 句"]
WINDOW_SIZE = 20
WINDOW_STEP = 10
CROSS_NEIGHBORS = 2  # 前后各 2 步

# ============================================================================
# 1. 组权重（先验固定，和 = 1.0，不用标注调参，口径 §5）
# ============================================================================
GROUP_WEIGHTS = {
    "wordface": 0.50,         # A 的词面 + 局部情绪分（z(A_score)）
    "semantic_shift": 0.20,   # 语义突变（步骤内滑窗 + 跨步骤）
    "identity_change": 0.15,  # 身份/知识/位置变化
    "motif_return": 0.10,     # 母题回收（两层：词表 semantic_recall + 表层重复）
    "state_change": 0.05,     # 不可逆状态变化标记
}
GROUP_LABELS = {
    "wordface": "词面+局部情绪(A)",
    "semantic_shift": "语义突变",
    "identity_change": "身份/位置变化",
    "motif_return": "母题回收",
    "state_change": "不可逆状态变化",
}
assert abs(sum(GROUP_WEIGHTS.values()) - 1.0) < 1e-9

# 组内子项权重（先验；子项先各自 z-score，再加权合成组原始分，最后整组再 z-score）
SUB_WEIGHTS = {
    "semantic_shift": {
        "sem_adj_top20": 0.50,   # 相邻窗余弦距离的 top-20% 均值（口径 §11.2 主信号）
        "sem_adj_p90": 0.30,     # 相邻窗距离 p90（主信号）
        "sem_cross_step": 0.20,  # 跨步骤突变：与前后各 1–2 步段向量的余弦距离均值
    },
    "identity_change": {
        "id_speaker_change_rate": 0.25,  # 相邻记录说话人（含形态）变化比例
        "id_new_char_log": 0.20,         # log1p(步骤内首次登场角色数)（全语料按剧情顺序判定）
        "id_form_speaker_rate": 0.15,    # 带形态标记的说话人记录占比
        "id_address_rate": 0.15,         # 称呼词表命中率
        "id_form_term_rate": 0.10,       # 形态词（投影/真身/记忆形态…）命中率
        "id_struct_pos": 0.15,           # 结构位置（任务首/末步、版本边界、任务末段、相对位置）
    },
    "motif_return": {
        "motif_recall_log": 0.30,        # log1p(semantic_recall：母题/神谕/歌谣/称呼词表命中加权)
        "motif_surface_rep_rate": 0.25,  # 表层重复率（repeat_kind 计数 ÷ main_records 数）
        "motif_gap": 0.20,               # 母题上次出现距当前步骤的剧情距离（越久越强）
        "motif_repeat_fn_rate": 0.25,    # 重复功能率：(structure_count+translation_count) ÷ main_records 数
    },
    "state_change": {
        "state_marker_log": 1.00,        # log1p(不可逆状态变化标记加权计数)
    },
}

# ============================================================================
# 2. 词表 / 标记（写死在脚本里；全部是词面/结构启发式，不含跨语料训练）
# ============================================================================
# 2.1 不可逆状态变化标记（旁白 / 关键台词）——口径要求"限定 narration 与关键句"
STATE_MARKERS = [
    "不再", "再也", "永远", "从此", "第一次", "最后一次", "最终", "注定",
    "不可逆", "无法挽回", "无法回头", "不能回头", "已成定局", "定局",
    "终结", "永诀", "从今往后", "至此", "直到永远", "永不复", "再也无法",
    "永远无法", "再也不能", "再也回不去", "只剩下", "仅剩", "余下",
]
# 2.2 形态词（身份/呈现形态变化）
FORM_TERMS = [
    "投影", "记忆形态", "真身", "化身", "分身", "幻象", "半神", "神性",
    "人性", "权柄", "全知", "形态", "本相", "虚影", "残影", "印记", "回响",
]
# 2.3 第一人称代词（判定"关键台词"用）
FIRST_PERSON = {"我", "我们", "咱们", "吾", "俺"}
# 2.4 旁白说话人标记
NARRATOR_NAMES = {"旁白", ""}
GENERIC_NAMES = {"generic_npc"}


def load_terms(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return [t for t in json.load(f).get("terms", []) if isinstance(t, str) and t]
    except Exception:
        return []


ADDRESS_TERMS = load_terms(P_VOCAB_ADDRESS)
MOTIF_TERMS = load_terms(P_VOCAB_MOTIF)
ORACLE_TERMS = load_terms(P_VOCAB_ORACLE)
BALLAD_TERMS = load_terms(P_VOCAB_BALLAD)


def _compile_terms(terms):
    terms = sorted({t for t in terms if len(t) >= 2}, key=len, reverse=True)
    return re.compile("|".join(re.escape(t) for t in terms)) if terms else None


RE_ADDRESS = _compile_terms(ADDRESS_TERMS)
RE_FORM_TERMS = _compile_terms(FORM_TERMS)
RE_STATE_MARKERS = _compile_terms(STATE_MARKERS)


def count_matches(pattern, text):
    return len(pattern.findall(text)) if pattern is not None else 0


# ============================================================================
# 3. 读取输入
# ============================================================================
def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_segments():
    rows = []
    with open(P_SEGMENTS, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def length_bin(n_dialogue):
    if n_dialogue <= 3:
        return LENGTH_BINS[0]
    if n_dialogue <= 10:
        return LENGTH_BINS[1]
    if n_dialogue <= 30:
        return LENGTH_BINS[2]
    return LENGTH_BINS[3]


def text_units(seg):
    """语义/说话人分析单元：main_records 中的 dialogue + narration（与 A 的文本口径一致）"""
    return [r for r in seg["main_records"] if r["kind"] in ("dialogue", "narration") and r["text"]]


def speaker_base(speaker):
    """'白厄(σ形态)' -> ('白厄', 'σ形态')；'旁白' -> ('旁白', '')"""
    spk = (speaker or "").strip()
    m = re.match(r"^(.+?)[（(](.+?)[)）]$", spk)
    if m:
        return m.group(1), m.group(2)
    return spk, ""


# ============================================================================
# 4. 语义空间（TF-IDF 字符 n-gram）与语义突变
# ============================================================================
def build_window_texts(seg):
    """按 main_records（全部 kind）切滑窗；文本只取 dialogue/narration（option/sms 位置保留但文本为空）。"""
    recs = seg["main_records"]
    texts = []
    for r in recs:
        t = r["text"] if r["kind"] in ("dialogue", "narration") else ""
        texts.append(t or "")
    n = len(recs)
    if n < WINDOW_SIZE:
        windows = ["".join(texts)]
        return windows, n, True
    windows = []
    i = 0
    while i + WINDOW_SIZE <= n:
        windows.append("".join(texts[i:i + WINDOW_SIZE]))
        i += WINDOW_STEP
    if not windows:
        windows = ["".join(texts)]
    return windows, n, False


def _row_norms(mat):
    return np.sqrt(np.asarray(mat.multiply(mat).sum(axis=1)).ravel())


def _pair_cos(mat, norms, i, j):
    if norms[i] < 1e-12 or norms[j] < 1e-12:
        return 0.0
    return float(mat[i].multiply(mat[j]).sum() / (norms[i] * norms[j]))


def top20_mean(values):
    if not values:
        return 0.0
    arr = sorted(values, reverse=True)
    k = max(1, math.ceil(0.2 * len(arr)))
    return float(sum(arr[:k]) / k)


def compute_semantic_space(seq):
    """返回 sid -> 语义特征 dict。

    * 步骤内：相邻滑窗余弦距离；<20 条记录（short_for_window）三个距离 = 0（口径 §11.3）
    * 跨步骤：当前步骤段向量 vs 同任务内前后各 1–2 步段向量的余弦距离均值
    """
    window_texts = []
    window_index = []  # (sid, window_id)
    seg_texts = []
    seg_sids = []
    for s in seq:
        wins, n_rec, short = build_window_texts(s)
        for k, w in enumerate(wins):
            window_texts.append(w)
            window_index.append((s["segment_id"], k))
        seg_texts.append(s["text_all"] or "")
        seg_sids.append(s["segment_id"])

    # 同一向量空间：窗口文本 + 步骤整段文本一起拟合（无监督、无标签）
    vec = TfidfVectorizer(
        analyzer="char",
        ngram_range=(2, 3),
        min_df=2,
        max_features=300000,
        sublinear_tf=True,
    )
    vec.fit([t for t in window_texts if t] + [t for t in seg_texts if t])
    W = vec.transform(window_texts)
    S = vec.transform(seg_texts)
    w_norms = _row_norms(W)
    s_norms = _row_norms(S)

    # 按 segment 收集窗口行号
    win_rows = defaultdict(list)
    for row, (sid, _k) in enumerate(window_index):
        win_rows[sid].append(row)
    seg_row = {sid: i for i, sid in enumerate(seg_sids)}

    # 跨步骤邻居：同任务内前后各 2 步
    task_members = defaultdict(list)
    for i, s in enumerate(seq):
        task_members[s["task"]].append(i)
    neighbor_idx = {}
    for i, s in enumerate(seq):
        members = task_members[s["task"]]
        pos = members.index(i)  # 任务内位置（步骤数不多，O(n^2) 可接受）
        cand = []
        for d in range(1, CROSS_NEIGHBORS + 1):
            if pos - d >= 0:
                cand.append(members[pos - d])
            if pos + d < len(members):
                cand.append(members[pos + d])
        neighbor_idx[s["segment_id"]] = cand

    feats = {}
    for s in seq:
        sid = s["segment_id"]
        rows = win_rows[sid]
        dists = []
        for a, b in zip(rows[:-1], rows[1:]):
            sim = _pair_cos(W, w_norms, a, b)
            dists.append(max(0.0, 1.0 - sim))
        _, n_rec, short = build_window_texts(s)
        row = seg_row[sid]
        cross = []
        for j in neighbor_idx[sid]:
            sim = _pair_cos(S, s_norms, row, j)
            cross.append(max(0.0, 1.0 - sim))
        feats[sid] = {
            "sem_adj_top20": top20_mean(dists),
            "sem_adj_p90": float(np.percentile(dists, 90)) if dists else 0.0,
            "sem_adj_max": float(max(dists)) if dists else 0.0,   # 仅诊断，不参与打分
            "sem_adj_mean": float(np.mean(dists)) if dists else 0.0,  # 诊断
            "sem_cross_step": float(np.mean(cross)) if cross else 0.0,
            "sem_n_adj_dists": len(dists),
            "sem_n_cross_neighbors": len(cross),
            "n_main_records": n_rec,
            "short_for_window": bool(short),
            "n_windows": len(rows),
        }
    return feats, vec


# ============================================================================
# 5. 元数据 / 结构特征（身份、母题、状态、位置、重复功能）
# ============================================================================
def compute_meta_features(seq, full_segments, vocab_terms_all):
    """按剧情顺序（seq 已排序）计算需要"历史状态"的特征。

    * 首次登场角色：全语料按 order → step_idx 顺序
    * 母题上次出现距离：同一顺序
    """
    # 任务内首/末步（用全语料该任务的步骤，含未入池步骤，反映真实任务位置）
    task_steps = defaultdict(list)
    for s in full_segments:
        task_steps[s["task"]].append(s["step_idx"])
    task_min = {t: min(v) for t, v in task_steps.items()}
    task_max = {t: max(v) for t, v in task_steps.items()}
    version_seq = [s["version"] for s in seq]
    first_of_version = {}
    last_of_version = {}
    for i, v in enumerate(version_seq):
        first_of_version.setdefault(v, i)
        last_of_version[v] = i

    seen_chars = set()
    last_seen_term = {}
    feats = {}
    for i, s in enumerate(seq):
        sid = s["segment_id"]
        units = text_units(s)
        n = max(1, len(units))
        text_all = s["text_all"] or ""

        # --- 说话人 / 形态 ---
        speakers = [u.get("speaker") or "" for u in units]
        bases = []
        forms = 0
        prev = None
        changes = 0
        for spk in speakers:
            base, form = speaker_base(spk)
            if form:
                forms += 1
            if prev is not None and spk != prev:
                changes += 1
            prev = spk
            bases.append(base)
        new_chars = 0
        for base in bases:
            if not base or base in NARRATOR_NAMES or base in GENERIC_NAMES:
                continue
            if base not in seen_chars:
                new_chars += 1
        for base in bases:  # 本步结束后才更新"已见"集合（步内多个首次仅计一次）
            if base and base not in NARRATOR_NAMES and base not in GENERIC_NAMES:
                seen_chars.add(base)

        # --- 称呼 / 形态词 / 状态标记 ---
        address_hits = count_matches(RE_ADDRESS, text_all)
        form_term_hits = count_matches(RE_FORM_TERMS, text_all)

        narr_texts = [u["text"] for u in units if u.get("speaker") in NARRATOR_NAMES]
        state_narr = sum(count_matches(RE_STATE_MARKERS, t) for t in narr_texts)
        state_dial_key = 0
        for u in units:
            if u.get("speaker") in NARRATOR_NAMES:
                continue
            t = u["text"]
            tokens = jieba.lcut(t)
            if any(tok in FIRST_PERSON for tok in tokens):
                state_dial_key += count_matches(RE_STATE_MARKERS, t)
        state_rate = (state_narr + 0.4 * state_dial_key) / n

        # --- 结构位置 ---
        step = s["step_idx"]
        tmin, tmax = task_min.get(s["task"], step), task_max.get(s["task"], step)
        rel = (step - tmin) / max(1, (tmax - tmin))
        struct_pos = (
            1.0 * (step == tmin)
            + 1.0 * (step == tmax)
            + 0.5 * (i == first_of_version.get(s["version"]))
            + 0.5 * (i == last_of_version.get(s["version"]))
            + 0.8 * (rel >= 0.8)
            + 0.4 * rel
        )

        # --- 母题回收（两层：semantic_recall + surface_repetition） ---
        recall_terms = list(dict.fromkeys(s.get("semantic_recall_terms") or []))
        oracle_n = s.get("semantic_recall_oracle_count", 0)
        motif_n = s.get("semantic_recall_motif_count", 0)
        ballad_n = s.get("semantic_recall_ballad_count", 0)
        addr_n = s.get("semantic_recall_address_count", 0)
        recall_count = 1.0 * motif_n + 0.8 * oracle_n + 0.8 * ballad_n + 0.3 * addr_n

        gaps = []
        for t in recall_terms:
            prev_seen = last_seen_term.get(t)
            if prev_seen is not None:
                gaps.append(i - prev_seen)
        motif_gap = float(np.mean([math.log1p(g) for g in gaps])) if gaps else 0.0
        for t in recall_terms:
            last_seen_term[t] = i

        # 长度归一 / 长尾压缩：计数类先 log1p，重复功能类换成"每记录率"（口径 §11.2 控长度偏差）
        n_main_rec = max(1, len(s["main_records"]))
        surface_rep_count = float(s.get("surface_repetition_count", 0))
        repeat_fn_count = float(s.get("structure_count", 0) + s.get("translation_count", 0))
        state_weighted = state_narr + 0.4 * state_dial_key

        feats[sid] = {
            # 身份/知识变化
            "id_speaker_change_rate": changes / max(1, len(speakers) - 1),
            "id_new_char_count": float(new_chars),          # 诊断：原始计数
            "id_new_char_log": math.log1p(new_chars),       # 打分用（log1p 抑制长步骤长尾）
            "id_form_speaker_rate": forms / n,
            "id_address_rate": address_hits / n,
            "id_form_term_rate": form_term_hits / n,
            "id_struct_pos": float(struct_pos),
            # 母题回收
            "motif_recall_count": float(recall_count),          # 诊断：原始加权计数
            "motif_recall_log": math.log1p(recall_count),       # 打分用
            "motif_surface_rep": surface_rep_count,             # 诊断：原始计数
            "motif_surface_rep_rate": surface_rep_count / n_main_rec,  # 打分用（每记录率）
            "motif_gap": motif_gap,
            "motif_recall_terms": float(len(recall_terms)),
            "motif_repeat_fn": repeat_fn_count,                 # 诊断：原始计数
            "motif_repeat_fn_rate": repeat_fn_count / n_main_rec,      # 打分用（每记录率）
            # 状态变化
            "state_marker_rate": float(state_rate),             # 诊断：每记录率
            "state_marker_count": float(state_weighted),        # 诊断：加权计数
            "state_marker_log": math.log1p(state_weighted),     # 打分用
            "state_narr_hits": float(state_narr),
            "state_dial_key_hits": float(state_dial_key),
        }
    return feats


# ============================================================================
# 6. 打分
# ============================================================================
def zcol(values):
    a = np.asarray(values, dtype=float)
    mu = float(a.mean())
    sd = float(a.std())  # ddof=0
    if sd < 1e-12:
        sd = 1.0
    return (a - mu) / sd, mu, sd


def compose_group(comp_raws, sub_weights, avail=None):
    """子项各自 z-score → 按内部权重合成组原始分 → 整组再 z-score。

    返回 (group_z array, comp_z dict, group_raw array, group_stats)。

    avail 是可选的可测量掩码（当前主口径不用：短步骤的窗内距离按口径 §11.3
    字面取 0 并直接参与打分；保留该参数是为了后续做缺失值实验时不必改结构）。
    """
    names = list(comp_raws)
    n = len(comp_raws[names[0]])
    comp_z = {name: zcol(comp_raws[name])[0] for name in names}
    if avail is None:
        avail = {name: np.ones(n, dtype=bool) for name in names}
    num = np.zeros(n, dtype=float)
    den = np.zeros(n, dtype=float)
    for name, w in sub_weights.items():
        m = avail.get(name, np.ones(n, dtype=bool)).astype(float)
        num += w * comp_z[name] * m
        den += w * m
    raw = np.where(den > 1e-12, num / np.where(den > 1e-12, den, 1.0), 0.0)
    gz, gmu, gsd = zcol(raw)
    return gz, comp_z, raw, {"mean": gmu, "std": gsd, "avail": {k: int(v.sum()) for k, v in avail.items()}}


def score_all(seq, sem_feats, meta_feats, a_scores, group_weights):
    sids = [s["segment_id"] for s in seq]
    a_score = np.array([a_scores[sid]["score"] for sid in sids], dtype=float)

    comp_raws = {
        "semantic_shift": {k: [sem_feats[sid][k] for sid in sids] for k in SUB_WEIGHTS["semantic_shift"]},
        "identity_change": {k: [meta_feats[sid][k] for sid in sids] for k in SUB_WEIGHTS["identity_change"]},
        "motif_return": {k: [meta_feats[sid][k] for sid in sids] for k in SUB_WEIGHTS["motif_return"]},
        "state_change": {k: [meta_feats[sid][k] for sid in sids] for k in SUB_WEIGHTS["state_change"]},
    }
    # wordface：A 的分数直接 z-score（50% 词面分项）
    a_z, a_mu, a_sd = zcol(a_score)

    groups = {"wordface": {"z": a_z, "raw": a_score,
                           "stats": {"mean": a_mu, "std": a_sd, "avail": {}}}}
    comp_z_all = {}
    for gname in ("semantic_shift", "identity_change", "motif_return", "state_change"):
        # 短步骤的窗内距离按口径 §11.3 字面取 0 并直接参与打分（不做事后修正；
        # 该回退规则造成的长度偏好已在报告 §10 量化说明）
        gz, comp_z, raw, stats = compose_group(comp_raws[gname], SUB_WEIGHTS[gname], None)
        groups[gname] = {"z": gz, "raw": raw, "stats": stats}
        comp_z_all[gname] = comp_z

    # 所有特征的 z（含仅诊断特征，方便复核；诊断特征不参与打分）
    all_feat_keys = set()
    for sid in sids:
        all_feat_keys |= set(sem_feats[sid].keys()) | set(meta_feats[sid].keys())
    feat_z = {}
    feat_stats = {}
    for k in sorted(all_feat_keys):
        vals = []
        for sid in sids:
            if k in sem_feats[sid] and isinstance(sem_feats[sid][k], bool):
                vals.append(1.0 if sem_feats[sid][k] else 0.0)
            elif k in sem_feats[sid]:
                vals.append(float(sem_feats[sid][k]))
            else:
                vals.append(float(meta_feats[sid][k]))
        z, mu, sd = zcol(vals)
        feat_z[k] = z
        feat_stats[k] = {"mean": mu, "std": sd}

    w = np.array([group_weights[g] for g in GROUP_WEIGHTS], dtype=float)
    zmat = np.column_stack([groups[g]["z"] for g in GROUP_WEIGHTS])
    contrib = zmat * w
    scores = contrib.sum(axis=1)

    rows = []
    for i, seg in enumerate(seq):
        sid = seg["segment_id"]
        feats = {}
        for k in sorted(all_feat_keys):
            if k in sem_feats[sid]:
                v = sem_feats[sid][k]
                raw = (1.0 if v else 0.0) if isinstance(v, bool) else round(float(v), 6)
            else:
                raw = round(float(meta_feats[sid][k]), 6)
            feats[k] = {"raw": raw, "z": round(float(feat_z[k][i]), 6)}

        gjson = {}
        for gname in GROUP_WEIGHTS:
            gjson[gname] = {
                "raw": round(float(groups[gname]["raw"][i]), 6),
                "z": round(float(groups[gname]["z"][i]), 6),
                "weight": GROUP_WEIGHTS[gname],
                "contrib": round(float(contrib[i][list(GROUP_WEIGHTS).index(gname)]), 6),
            }
        order = sorted(GROUP_WEIGHTS, key=lambda g: gjson[g]["contrib"], reverse=True)
        rows.append({
            "segment_id": sid,
            "version": seg["version"],
            "task": seg["task"],
            "step_idx": seg["step_idx"],
            "step_title": seg["step_title"],
            "n_dialogue": seg["n_dialogue"],
            "char_len": seg["char_len"],
            "length_bin": length_bin(seg["n_dialogue"]),
            "n_main_records": len(seg["main_records"]),
            "n_windows": sem_feats[sid]["n_windows"],
            "short_for_window": sem_feats[sid]["short_for_window"],
            "score": round(float(scores[i]), 6),
            "groups": gjson,
            "features": feats,
            "top_features": order[:3],
        })
    rows.sort(key=lambda x: (-x["score"], x["segment_id"]))
    for rank, item in enumerate(rows, 1):
        item["rank"] = rank
    return rows, groups, contrib, feat_stats


# ============================================================================
# 7. 评测（人工标注只在这里使用）
# ============================================================================
def pearson(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.std() < 1e-12 or b.std() < 1e-12:
        return 0.0
    return float(((a - a.mean()) * (b - b.mean())).mean() / (a.std() * b.std()))


def rankdata_average(x):
    """平均名次（与 scipy.stats.rankdata 默认一致），用于 Spearman（含并列）"""
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=float)
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(a, b):
    return pearson(rankdata_average(a), rankdata_average(b))


def human_eval(rows, labels):
    """传入某个检测器的排序结果（rows，含 rank/score），返回与 74 条标注的对照指标"""
    by_id = {r["segment_id"]: r for r in rows}
    samples = labels["samples"]
    xs, ys = [], []
    levels = defaultdict(list)
    for s in samples:
        sid = s["segment_id"]
        x = by_id[sid]["score"]
        y = float(s["significance"])
        xs.append(x)
        ys.append(y)
        levels[int(s["significance"])].append(x)
    sig = [s for s in samples if int(s["significance"]) >= 2]
    sig_ranks = [by_id[s["segment_id"]]["rank"] for s in sig]
    result = {
        "n_samples": len(samples),
        "spearman": round(spearman(xs, ys), 4),
        "level_means": {lv: round(float(np.mean(levels[lv])), 4) for lv in sorted(levels)},
        "level_n": {lv: len(levels[lv]) for lv in sorted(levels)},
        "n_significant": len(sig),
        "significant_median_rank": float(np.median(sig_ranks)),
        "significant_mean_rank": round(float(np.mean(sig_ranks)), 2),
        "significant_in_top20": sum(1 for r in sig_ranks if r <= 20),
        "significant_in_top50": sum(1 for r in sig_ranks if r <= 50),
        "significant_in_top100": sum(1 for r in sig_ranks if r <= 100),
    }
    # 分类型（只看标注类型里的 prophecy/sacrifice，给报告做定向核对）
    by_type = {}
    for t in ("prophecy", "sacrifice", "identity", "memory", "motif"):
        sel = [s for s in samples if t in s["types"]]
        if sel:
            by_type[t] = {
                "n": len(sel),
                "median_rank": float(np.median([by_id[s["segment_id"]]["rank"] for s in sel])),
                "in_top100": sum(1 for s in sel if by_id[s["segment_id"]]["rank"] <= 100),
            }
    result["by_type"] = by_type
    return result


# ============================================================================
# 8. 辅助：摘录 / 表格 / 报告
# ============================================================================
def truncate(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def pick_excerpt_b(seg):
    """摘录：优先含不可逆状态标记 / 形态词 / 称呼的记录，其次含第一人称的短句"""
    units = text_units(seg)
    if not units:
        return ""
    best, best_val = None, -1.0
    for u in units:
        t = u["text"]
        tokens = jieba.lcut(t)
        val = (
            1.0 * count_matches(RE_STATE_MARKERS, t)
            + 0.8 * count_matches(RE_FORM_TERMS, t)
            + 0.5 * count_matches(RE_ADDRESS, t)
            + 0.3 * (1 if any(tok in FIRST_PERSON for tok in tokens) else 0)
        )
        if val > best_val:
            best, best_val = u, val
    text = re.sub(r"\s+", " ", best["text"]).strip()
    return text[:42] + ("…" if len(text) > 42 else "")


def fmt_groups(item, top_n=3):
    """主要贡献组：按加权贡献降序；只展示正向贡献（负贡献不算"主要贡献"）"""
    ranked = sorted(GROUP_WEIGHTS, key=lambda g: item["groups"][g]["contrib"], reverse=True)
    pos = [g for g in ranked if item["groups"][g]["contrib"] > 0]
    if not pos:
        return "无正向贡献（各组均低于均值）"
    parts = []
    for g in pos[:top_n]:
        parts.append("%s(%+.2fσ)" % (GROUP_LABELS[g], item["groups"][g]["z"]))
    return "、".join(parts)


def table_rows(items, seg_by_id, with_a=False, a_rank_map=None):
    lines = []
    for it in items:
        if with_a and a_rank_map is not None:
            lines.append(
                "| {rank} | `{sid}` | {ver} | {task} | {step} | {score:.4f} | {feats} | {exc} | {a_rank} |".format(
                    rank=it["rank"], sid=it["segment_id"], ver=it["version"],
                    task=truncate(it["task"], 14),
                    step="第%d步·%s" % (it["step_idx"], truncate(it["step_title"], 14)),
                    score=it["score"], feats=fmt_groups(it),
                    exc=pick_excerpt_b(seg_by_id[it["segment_id"]]),
                    a_rank=a_rank_map.get(it["segment_id"], -1),
                )
            )
        else:
            lines.append(
                "| {rank} | `{sid}` | {ver} | {task} | {step} | {score:.4f} | {feats} | {exc} |".format(
                    rank=it["rank"], sid=it["segment_id"], ver=it["version"],
                    task=truncate(it["task"], 14),
                    step="第%d步·%s" % (it["step_idx"], truncate(it["step_title"], 14)),
                    score=it["score"], feats=fmt_groups(it),
                    exc=pick_excerpt_b(seg_by_id[it["segment_id"]]),
                )
            )
    return lines


def rank_map(rows):
    return {r["segment_id"]: r["rank"] for r in rows}


def topk_overlap(rows_a, rows_b, k):
    sa = {x["segment_id"] for x in rows_a[:k]}
    sb = {x["segment_id"] for x in rows_b[:k]}
    return len(sa & sb) / k


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================================
# 9. 主流程
# ============================================================================
# §9.2「B 提上来但 A 没进 Top100」案例的人工判断（逐条读原文后填写；与标注无关，
# 只看原文是否真的发生结构性叙事变化：身份揭示 / 视角·时间切换 / 不可逆状态 / 母题回收）
CASE_NOTES = {
    "3.3|书卷啊，可曾令锋刃回眸|7":
        "★ 一场里同时有「清洗者」登场、阿格莱雅遇袭、髀石护身符的关系揭示，且多场景/多新角色；"
        "A 只看词面漏掉，B 的身份/位置与语义突变项把它提上来，方向正确",
    "3.7|魔女的孤诣课题|21":
        "★ 德谬歌/昔涟记忆的最终揭示（同时是神谕 O13 的兑现段、标注等级 3）；"
        "B 的母题回收+身份项命中，A 排 273 名属明显漏检",
    "3.3|诗者啊，从我处诉说天空•上|10":
        "★ 风堇自述「我是雅辛忒丝，继承英雄血脉的医者」+ 塞涅俄丝残魂形态；"
        "身份/血脉揭示 + 形态说话人，B 的身份项命中",
    "3.0|夜帷啊，轻遮那静默过往|23":
        "○「不存在的回忆」里的时空切换（流萤/银狼/卡芙卡逐个登场又冻结）+ 不可逆标记；"
        "结构信号真实，但内容更像回忆展示，显著性中等，B 第 43 名略偏高",
    "3.1|门扉啊，叩声仍激荡梦中|11":
        "★ 缇宝分裂成多个形态、欧洛尼斯消失，随后视角切回奥赫玛揭示「盗火行者」；"
        "形态/身份/视角变化齐全，B 提上来合理",
    "3.4|英雄啊，点燃那最初的骄阳|10":
        "★ 白厄揭示「第一百三十四次轮回 / 一千五百九十六颗火种」，世界规则与身份同时突变；"
        "A 因词面只有零星神谕词而排 212，B 的结构项命中",
}


def main_build():
    a_hash_before = sha256_file(P_A_SCORES)

    all_segs = load_segments()
    a_data = read_json(P_A_SCORES)
    labels = read_json(P_ANNOT)
    oracle_data = read_json(P_ORACLE)
    vocab_all = ADDRESS_TERMS + MOTIF_TERMS + ORACLE_TERMS + BALLAD_TERMS

    a_by_id = {s["segment_id"]: s for s in a_data["segments"]}
    eligible = [s for s in all_segs if s["n_main"] > 0 and not s["low_content"] and s["has_dialogue"]]
    seq = sorted(eligible, key=lambda s: (s["order"], s["step_idx"]))
    pool_ids = [s["segment_id"] for s in seq]
    assert set(pool_ids) == set(a_by_id), "B 候选池必须与 A 完全一致"
    print("步骤实例 = %d；合格候选池 = %d（与 A 一致）" % (len(all_segs), len(seq)))

    print("构建 TF-IDF 语义空间（字符 2–3 gram）…")
    sem_feats, vec = compute_semantic_space(seq)
    print("计算身份/母题/位置/状态特征…")
    meta_feats = compute_meta_features(seq, all_segs, vocab_all)
    print("打分…")
    rows, groups, contrib, feat_stats = score_all(seq, sem_feats, meta_feats, a_by_id, GROUP_WEIGHTS)
    seg_by_id = {s["segment_id"]: s for s in eligible}
    a_rank_map = {sid: a_by_id[sid]["rank"] for sid in pool_ids}
    a_rows = sorted(a_data["segments"], key=lambda x: x["rank"])

    # ---- A/B 对比 ----
    a_score_by_id = {s["segment_id"]: s["score"] for s in a_data["segments"]}
    b_score_by_id = {r["segment_id"]: r["score"] for r in rows}
    a_b = {
        "top10_overlap": round(topk_overlap(a_rows, rows, 10), 4),
        "top20_overlap": round(topk_overlap(a_rows, rows, 20), 4),
        "top50_overlap": round(topk_overlap(a_rows, rows, 50), 4),
        "top100_overlap": round(topk_overlap(a_rows, rows, 100), 4),
        # Spearman 必须按 segment_id 配对（rows 已按分数排序，不能与 seq 顺序混用）
        "spearman_a_vs_b": round(
            spearman([a_score_by_id[sid] for sid in pool_ids],
                     [b_score_by_id[sid] for sid in pool_ids]), 4),
    }
    b_rank_map = rank_map(rows)
    deltas = [a_rank_map[sid] - b_rank_map[sid] for sid in pool_ids]  # >0 = B 名次上升
    a_b["rank_change"] = {
        "median_abs_delta": float(np.median([abs(d) for d in deltas])),
        "mean_delta": round(float(np.mean(deltas)), 2),
        "n_improved_100plus": sum(1 for d in deltas if d >= 100),
        "n_worsened_100plus": sum(1 for d in deltas if d <= -100),
        "top10_of_a_still_in_b_top20": sum(1 for x in a_rows[:10] if b_rank_map[x["segment_id"]] <= 20),
        "top10_of_a_still_in_b_top50": sum(1 for x in a_rows[:10] if b_rank_map[x["segment_id"]] <= 50),
    }
    # A/B 名次互换最大的步骤（B 上升最多）
    b_improved = sorted(
        [r for r in rows if (a_rank_map[r["segment_id"]] - r["rank"]) > 0],
        key=lambda r: -(a_rank_map[r["segment_id"]] - r["rank"]),
    )
    a_b["top_improved"] = [
        {"segment_id": r["segment_id"], "a_rank": a_rank_map[r["segment_id"]], "b_rank": r["rank"],
         "delta": a_rank_map[r["segment_id"]] - r["rank"]}
        for r in b_improved[:10]
    ]

    # ---- 人工标注评测（只用于评测） ----
    human_a = human_eval(a_rows, labels)
    human_b = human_eval(rows, labels)

    # ---- 长度分层 ----
    length = {}
    for b in LENGTH_BINS:
        members = [r for r in rows if r["length_bin"] == b]
        a_members = [r for r in a_rows if r["length_bin"] == b]
        annot = [s for s in labels["samples"] if length_bin(s["n_dialogue"]) == b]
        sig = [s for s in annot if int(s["significance"]) >= 2]
        length[b] = {
            "n": len(members),
            "b_top1": max(r["score"] for r in members) if members else 0.0,
            "b_median": float(np.median([r["score"] for r in members])) if members else 0.0,
            "n_annotated": len(annot),
            "n_sig_annotated": len(sig),
            "a_sig_in_top100": sum(1 for s in sig if a_rank_map[s["segment_id"]] <= 100),
            "b_sig_in_top100": sum(1 for s in sig if b_rank_map[s["segment_id"]] <= 100),
            "a_sig_in_top20": sum(1 for s in sig if a_rank_map[s["segment_id"]] <= 20),
            "b_sig_in_top20": sum(1 for s in sig if b_rank_map[s["segment_id"]] <= 20),
            "a_top1": max(r["score"] for r in a_members) if a_members else 0.0,
            "b_sig_median_rank": float(np.median([b_rank_map[s["segment_id"]] for s in sig])) if sig else -1,
            "a_sig_median_rank": float(np.median([a_rank_map[s["segment_id"]] for s in sig])) if sig else -1,
            "n_in_a_top100": sum(1 for r in a_rows[:100] if r["length_bin"] == b),
            "n_in_b_top100": sum(1 for r in rows[:100] if r["length_bin"] == b),
        }
    length_bias = {
        "spearman_score_vs_n_dialogue": round(spearman([r["score"] for r in rows],
                                                       [r["n_dialogue"] for r in rows]), 4),
        "spearman_score_vs_char_len": round(spearman([r["score"] for r in rows],
                                                     [r["char_len"] for r in rows]), 4),
        "n_short_for_window": sum(1 for r in rows if r["short_for_window"]),
        "n_zero_adj_dists": sum(1 for r in rows if r["features"]["sem_n_adj_dists"]["raw"] == 0),
    }

    # ---- 结构位置项的事后核对（诊断，不参与调参） ----
    task_steps = defaultdict(list)
    for s in all_segs:
        task_steps[s["task"]].append(s["step_idx"])
    tmin = {t: min(v) for t, v in task_steps.items()}
    tmax = {t: max(v) for t, v in task_steps.items()}
    all_by_id = {s["segment_id"]: s for s in all_segs}
    boundary_ids = {
        s["segment_id"] for s in all_segs
        if s["step_idx"] == tmin[s["task"]] or s["step_idx"] == tmax[s["task"]]
    }
    top100 = rows[:100]
    fl_top = [r["segment_id"] for r in top100 if r["segment_id"] in boundary_ids]
    fl_annot = [s for s in labels["samples"] if s["segment_id"] in boundary_ids]
    fl_sig = [s for s in fl_annot if int(s["significance"]) >= 2]
    structure_position_check = {
        "n_top100_task_boundary": len(fl_top),
        "n_top100_struct_pos_high": sum(
            1 for r in top100 if r["features"]["id_struct_pos"]["raw"] >= 1.5),
        "n_annotated_task_boundary": len(fl_annot),
        "n_annotated_task_boundary_sig": len(fl_sig),
        "task_boundary_ids_in_top100": fl_top,
        "note": "事后诊断，不参与调参；用标注检查「结构位置」启发式是否有依据",
    }

    # ---- 重点案例：昔涟诞生 ----
    def group_contrib_view(r):
        return {g: r["groups"][g]["contrib"] for g in GROUP_WEIGHTS}

    def case_view(sid):
        r = next(x for x in rows if x["segment_id"] == sid)
        return {
            "segment_id": sid,
            "a_rank": a_rank_map[sid],
            "b_rank": r["rank"],
            "delta": a_rank_map[sid] - r["rank"],
            "b_score": r["score"],
            "groups": r["groups"],
            "top_features": r["top_features"],
            "excerpt": pick_excerpt_b(seg_by_id[sid]),
            "n_windows": r["n_windows"],
            "short_for_window": r["short_for_window"],
        }

    focus = case_view(FOCUS_CASE)

    # ---- 神谕兑现段（13 条）核对 ----
    oracle_rows = []
    for o in oracle_data["oracles"]:
        sid = o.get("fulfillment_segment")
        if not sid or sid not in b_rank_map:
            continue
        oracle_rows.append({
            "oracle_id": o.get("oracle_id"),
            "segment_id": sid,
            "fulfillment_type": o.get("fulfillment_type"),
            "a_rank": a_rank_map[sid],
            "b_rank": b_rank_map[sid],
            "delta": a_rank_map[sid] - b_rank_map[sid],
            "evidence": truncate(o.get("evidence") or "", 60),
        })
    oracle_summary = {
        "n": len(oracle_rows),
        "a_in_top100": sum(1 for x in oracle_rows if x["a_rank"] <= 100),
        "b_in_top100": sum(1 for x in oracle_rows if x["b_rank"] <= 100),
        "a_in_top50": sum(1 for x in oracle_rows if x["a_rank"] <= 50),
        "b_in_top50": sum(1 for x in oracle_rows if x["b_rank"] <= 50),
        "median_a_rank": float(np.median([x["a_rank"] for x in oracle_rows])) if oracle_rows else -1,
        "median_b_rank": float(np.median([x["b_rank"] for x in oracle_rows])) if oracle_rows else -1,
    }

    # ---- 敏感性分析 W1–W5 ----
    variants = {
        "W1_原始权重": dict(GROUP_WEIGHTS),
        "W2_结构特征整体+20%": {"wordface": 0.50, "semantic_shift": 0.24,
                                "identity_change": 0.18, "motif_return": 0.12, "state_change": 0.06},
        "W3_结构特征整体-20%": {"wordface": 0.50, "semantic_shift": 0.16,
                                "identity_change": 0.12, "motif_return": 0.08, "state_change": 0.04},
        "W4_只留语义突变": {"wordface": 0.0, "semantic_shift": 1.0,
                            "identity_change": 0.0, "motif_return": 0.0, "state_change": 0.0},
        "W5_只留结构规则(去词面)": {"wordface": 0.0, "semantic_shift": 0.20 / 0.50,
                                   "identity_change": 0.15 / 0.50, "motif_return": 0.10 / 0.50,
                                   "state_change": 0.05 / 0.50},
    }
    # 归一化并校验
    for name, w in variants.items():
        total = sum(w.values())
        if abs(total - 1.0) > 1e-9:
            variants[name] = {k: v / total for k, v in w.items()}

    gz_mat = np.column_stack([groups[g]["z"] for g in GROUP_WEIGHTS])  # 行 = seq 顺序
    seq_order_sids = [s["segment_id"] for s in seq]
    rows_by_sid = {r["segment_id"]: r for r in rows}
    sensitivity = {}
    for name, w in variants.items():
        wv = np.array([w[g] for g in GROUP_WEIGHTS], dtype=float)
        sc = gz_mat.dot(wv)  # seq 顺序
        sc_by_sid = {seq_order_sids[i]: float(sc[i]) for i in range(len(seq))}
        ranked = sorted(rows, key=lambda r: (-sc_by_sid[r["segment_id"]], r["segment_id"]))
        alt_rank = {r["segment_id"]: k + 1 for k, r in enumerate(ranked)}
        sensitivity[name] = {
            "weights": {k: round(v, 4) for k, v in w.items()},
            "top10_overlap": round(topk_overlap(rows, ranked, 10), 4),
            "top20_overlap": round(topk_overlap(rows, ranked, 20), 4),
            "top50_overlap": round(topk_overlap(rows, ranked, 50), 4),
            "spearman_vs_W1": round(spearman(
                [r["score"] for r in rows],
                [sc_by_sid[r["segment_id"]] for r in rows]), 4),
            "focus_case_rank": alt_rank[FOCUS_CASE],
            "focus_case_rank_W1": b_rank_map[FOCUS_CASE],
        }

    # ---- meta ----
    meta = {
        "script": "tools/baseline_b.py",
        "run_command": RUN_CMD,
        "corpus": "data/corpus/segments.jsonl",
        "corpus_total_segments": len(all_segs),
        "eligible_candidates": len(seq),
        "candidate_rule": "与 A 完全一致的 686 池（n_main>0 且 !low_content 且 has_dialogue），已断言 sid 集合相等",
        "a_scores_input": "data/config/baseline-a-scores.json（只读；脚本运行前后 sha256 校验不变）",
        "a_scores_sha256_16": a_hash_before[:16],
        "semantic_space": "TF-IDF char 2–3 gram，min_df=2，sublinear_tf，max_features=300000；在窗口文本 + 步骤整段文本上无监督拟合",
        "window": "main_records 按 %d 条一窗、步长 %d；记录数 < %d 整步 1 窗且相邻窗距离=0（口径 §11.3）" % (
            WINDOW_SIZE, WINDOW_STEP, WINDOW_SIZE),
        "cross_step": "同任务内与前后各 %d 步段向量的余弦距离均值" % CROSS_NEIGHBORS,
        "normalization": "计数类特征先 log1p、重复功能类换成每记录率（控制长尾与长度偏差），然后组内子项各自 z-score → 内部权重合成组原始分 → 组原始分再 z-score（ddof=0，基于 686 步）",
        "score_formula": "S_B = 0.50·z(A_score) + 0.20·z(语义突变) + 0.15·z(身份/位置) + 0.10·z(母题回收) + 0.05·z(状态变化)",
        "group_weights": GROUP_WEIGHTS,
        "group_labels": GROUP_LABELS,
        "sub_weights": SUB_WEIGHTS,
        "note": "无标签打分；标注只用于评测、不参与调参；不代表叙事显著性的判定准确率。",
        "annotation_file": "data/config/annotation-labels.json（仅评测段读取）",
    }
    group_stats = {g: {"mean": groups[g]["stats"]["mean"], "std": groups[g]["stats"]["std"],
                       "avail": groups[g]["stats"].get("avail", {})}
                   for g in GROUP_WEIGHTS}
    result = {
        "meta": meta,
        "group_stats": group_stats,
        "feature_stats": feat_stats,
        "a_b_comparison": a_b,
        "human_eval": {"A_baseline": human_a, "B_enhanced": human_b},
        "length_strata": length,
        "length_bias": length_bias,
        "structure_position_check": structure_position_check,
        "focus_case": focus,
        "oracle_fulfillment_check": {"summary": oracle_summary, "rows": oracle_rows},
        "sensitivity": sensitivity,
        "segments": rows,
    }

    # 写入 JSON
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写 %s（%d 步）" % (os.path.relpath(OUT_JSON, ROOT), len(rows)))

    # 写入 MD
    md = render_report(result, rows, a_rows, a_rank_map, b_rank_map, seg_by_id,
                       labels, all_segs, a_b, human_a, human_b, sensitivity, focus)
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s" % os.path.relpath(OUT_MD, ROOT))

    # A 的产物必须逐字节不变
    assert sha256_file(P_A_SCORES) == a_hash_before, "A 的产物被改动了！"
    print("A 产物未被改动（sha256 %s…）" % a_hash_before[:16])

    ok = verify(verbose=True)
    if not ok:
        print("!! 报告与 JSON 不一致", file=sys.stderr)
        sys.exit(1)
    print("\n核对通过：报告表格数字与 JSON 一致（抽查 5 条 + 抽样重算）。")


# ============================================================================
# 10. 报告
# ============================================================================
def render_report(result, rows, a_rows, a_rank_map, b_rank_map, seg_by_id,
                  labels, all_segs, a_b, human_a, human_b, sensitivity, focus):
    n = len(rows)
    top30 = rows[:30]
    bottom10 = sorted(rows[-10:], key=lambda x: x["score"])
    L = []
    A = L.append

    A("# 检测器 B：结构增强的叙事显著性检测（无标签打分 + A/B 对比 + 人工标注对照）")
    A("")
    A("> 生成脚本：`tools/baseline_b.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    A("> 语料（只读）：`data/corpus/segments.jsonl`（%d 步 → 合格候选池 **%d** 步，与 A 完全同池）" % (
        result["meta"]["corpus_total_segments"], n))
    A("> 明细数据（可复算）：`data/config/baseline-b-scores.json`（score / 5 组子分 / 特征 raw+z / rank）")
    A("> A 的产物 `data/config/baseline-a-scores.json` 只读复用（脚本前后 sha256 校验不变，`%s…`）" % (
        result["meta"]["a_scores_sha256_16"]))
    A("")
    A("> **免责声明：这是无标签先验打分，不代表准确性。** 组权重在跑分前写死；"
      "`annotation-labels.json` 只在 §8 评测段读取，**没有参与任何特征设计或权重调整**。"
      "B 的「更好」只能由人工标注评测与案例核对支撑，且 74 条标注是分层抽样、单标注人，数字只作方向性参考。")
    A("")
    # ---------------- 1 结论 ----------------
    A("## 1. 一句话结论")
    A("")
    top = rows[0]
    A("- B 的 Top1 是 `%s`（%s｜%s｜第%d步），分数 %.4f；主要贡献：%s。"
      "（A 中该步第 %d 名。）" % (
          top["segment_id"], top["version"], truncate(top["task"], 16), top["step_idx"],
          top["score"], fmt_groups(top), a_rank_map[top["segment_id"]]))
    A("- **A vs B**：Top10 重合 %.0f%%、Top20 重合 %.0f%%、Top50 重合 %.0f%%，全池 Spearman ρ = **%.3f**；"
      "B 相对 A 名次上升 ≥100 名的步骤有 %d 个、下降 ≥100 名的有 %d 个 → B 不是 A 的微调，"
      "结构项确实改变了排序（但保留了词面主体）。" % (
          100 * a_b["top10_overlap"], 100 * a_b["top20_overlap"], 100 * a_b["top50_overlap"],
          a_b["spearman_a_vs_b"], a_b["rank_change"]["n_improved_100plus"],
          a_b["rank_change"]["n_worsened_100plus"]))
    A("- **vs 74 条人工标注**：Spearman(A→等级) = **%.3f** → B = **%.3f**；"
      "显著样本（等级≥2，共 %d 个）在 A 中的排名中位数 **%.0f** → B **%.0f**；"
      "A 的 Top20 里有显著样本 %d 个 → B **%d 个**；落在 Top100 的显著样本 %d/%d → **%d/%d**。" % (
          human_a["spearman"], human_b["spearman"], human_a["n_significant"],
          human_a["significant_median_rank"], human_b["significant_median_rank"],
          human_a["significant_in_top20"], human_b["significant_in_top20"],
          human_a["significant_in_top100"], human_a["n_significant"],
          human_b["significant_in_top100"], human_b["n_significant"]))
    lv_a = human_a["level_means"]
    lv_b = human_b["level_means"]
    A("- **等级均值（区分度）**：A = %s；B = %s。"
      "重点看 2/3 级相对 0/1 级是否拉开（A 的老问题是 1/2/3 几乎持平）。" % (
          " / ".join("%s级 %.2f" % (k, v) for k, v in sorted(lv_a.items())),
          " / ".join("%s级 %.2f" % (k, v) for k, v in sorted(lv_b.items()))))
    A("- **昔涟诞生段** `%s`：A 第 **%d** 名 → B 第 **%d** 名（%+d）；B 的主要贡献：%s。" % (
        FOCUS_CASE, focus["a_rank"], focus["b_rank"], focus["delta"], fmt_groups(focus)))
    lb = result["length_bias"]
    A("- **长度偏差（B 的真实短板）**：B 分数 vs 对白句数 ρ = **%+.3f**（A +0.438），"
      "且相对 A 的增益集中在 >30 句层（显著样本进 Top100：%d → %d）；短/中短层无增益。"
      "原因与改进方向见 §10，**A/B 结论必须按长度分层看**。" % (
          lb["spearman_score_vs_n_dialogue"],
          result["length_strata"][LENGTH_BINS[3]]["a_sig_in_top100"],
          result["length_strata"][LENGTH_BINS[3]]["b_sig_in_top100"]))
    A("")

    # ---------------- 2 口径 ----------------
    A("## 2. 候选池与计算口径")
    A("")
    A("| 项目 | 口径 |")
    A("| --- | --- |")
    A("| 候选池 | 与 A 完全相同的 686 步（`n_main>0` 且 `!low_content` 且 `has_dialogue`；脚本断言 sid 集合相等） |")
    A("| 输入复用 | A 的分数直接作为 B 的 50% 词面分项（`z(A_score)`），A 的 JSON 只读 |")
    A("| 语义空间 | TF-IDF **字符 2–3 gram**（sklearn，`min_df=2`、`sublinear_tf`、`max_features=300000`）；在全部窗口文本 + 步骤整段文本上无监督拟合（无标签、无 embedding） |")
    A("| 滑窗口径 | `main_records` 每 %d 条一窗、步长 %d；记录数 < %d → 整步 1 窗、相邻窗距离 = 0、`short_for_window=true`（口径 §11.3） |" % (
        WINDOW_SIZE, WINDOW_STEP, WINDOW_SIZE))
    A("| 滑窗文本 | 窗口内只拼接 `dialogue`/`narration` 文本；`option`/`sms` 保留记录位置但文本置空（选项文本不混入正文，口径 §2） |")
    A("| 跨步骤突变 | 当前步骤整段向量 vs **同任务内**前后各 %d 步段向量的余弦距离均值 |" % CROSS_NEIGHBORS)
    A("| 分词 | jieba 精确模式：用于说话人/第一人称判定、状态标记的台词过滤（语义向量用字符 n-gram，不依赖分词） |")
    A("| 分词/顺序 | 一律基于 `main_records` 原始顺序（口径 §11.1） |")
    A("| 标准化 | 组内子项各自 z-score → 按内部权重合成组原始分 → 组原始分再 z-score（总体标准差 ddof=0，基于 686 步）；计数类先 log1p、重复功能类用每记录率 |")
    A("| 短步回退 | 记录数 < %d 时步骤内相邻窗距离按口径 §11.3 字面取 0、`short_for_window=true`，并直接参与打分（不做任何事后修正）；该回退规则造成的长度偏向已在 §10 量化 |" % WINDOW_SIZE)
    A("| 打分 | `S_B = Σ 组权重 × z(组)`，组权重写死在脚本（口径 §5，先验固定、不调参） |")
    A("| 排序 | 分数降序；同分按 `segment_id` 升序 |")
    A("| 长度分层 | 按对白记录数 1–3 / 4–10 / 11–30 / >30 句（与口径 §9 的 65/148/236/237 一致） |")
    A("")

    # ---------------- 3 特征定义 ----------------
    A("## 3. B 的特征：6 类结构信号 → 5 组权重")
    A("")
    A("| 组（权重） | 组内子项 | 实现口径（全部基于步骤内/相邻步骤，无 embedding） |")
    A("| --- | --- | --- |")
    sub_desc = {
        "sem_adj_top20": "相邻滑窗余弦距离的 top-20% 均值（口径 §11.2 主排序信号）",
        "sem_adj_p90": "相邻滑窗余弦距离的 p90（主排序信号）",
        "sem_cross_step": "与同任务前后各 1–2 步段向量的余弦距离均值",
        "id_speaker_change_rate": "相邻记录说话人（含形态）变化次数 ÷ (记录数−1)",
        "id_new_char_log": "log1p(步骤内首次登场角色数)；JSON 同时保留原始计数 `id_new_char_count`",
        "id_form_speaker_rate": "带形态标记的说话人记录占比（如「白厄(σ形态)」）",
        "id_address_rate": "称呼词表（`vocab-address`）命中数 ÷ 记录数",
        "id_form_term_rate": "形态词（投影/真身/记忆形态/半神…）命中数 ÷ 记录数",
        "id_struct_pos": "结构位置：任务首步 1.0 + 任务末步 1.0 + 版本首步 0.5 + 版本末步 0.5 + 任务末段(≥80%)0.8 + 0.4×任务内相对位置",
        "motif_recall_log": "log1p(词表回收加权计数)：母题×1.0 + 神谕×0.8 + 歌谣×0.8 + 称呼×0.3（`semantic_recall_*`）",
        "motif_surface_rep_rate": "表层重复率：`surface_repetition_count` ÷ main_records 数（JSON 保留原始计数）",
        "motif_gap": "母题词的「上次出现距离」均值：mean(log1p(当前步序 − 上次步序))，越久未出现越强",
        "motif_repeat_fn_rate": "重复功能率：(`structure_count + translation_count`) ÷ main_records 数（JSON 保留原始计数）",
        "state_marker_log": "log1p(不可逆标记加权计数)：旁白计 1.0、含第一人称的关键台词计 0.4（JSON 保留计数与每记录率）",
    }
    sub_short = {
        "semantic_shift": "相邻窗 top20 均值 / p90 / 跨步骤距离",
        "identity_change": "说话人变化率、log 首次登场角色、形态说话人占比、称呼命中、形态词命中、结构位置",
        "motif_return": "log 词表回收、表层重复率、母题上次出现距离、structure+translation 重复功能率",
        "state_change": "log 不可逆标记计数（旁白为主、关键台词为辅）",
    }
    rows_def = [
        ("wordface", 0.50, "A 的词面 + 局部情绪分", "z(A_score)：直接复用 `data/config/baseline-a-scores.json`"),
        ("semantic_shift", 0.20, "语义突变", sub_short["semantic_shift"]),
        ("identity_change", 0.15, "身份/知识/位置变化", sub_short["identity_change"]),
        ("motif_return", 0.10, "母题回收（两层）", sub_short["motif_return"]),
        ("state_change", 0.05, "不可逆状态变化", sub_short["state_change"]),
    ]
    for g, w, label, desc in rows_def:
        A("| `%s`（%s）%.2f | %s | %s |" % (g, label, w, desc, ""))
    A("")
    A("> **长尾/长度归一处理**（应对口径 §11.2 的长度偏差）：计数类（首次登场角色、词表回收、不可逆标记）"
      "先 `log1p` 再 z-score；重复功能类（表层重复、structure+translation）换成**每记录率**；"
      "原始计数仍完整写进 JSON（`*_count` / `*` 字段），便于核对与 B 的后续迭代。")
    A("")
    A("子项口径详表：")

    A("")
    A("| 组 | 子项 key | 内部权重 | 口径 |")
    A("| --- | --- | --- | --- |")
    for g in ("semantic_shift", "identity_change", "motif_return", "state_change"):
        for k, w in SUB_WEIGHTS[g].items():
            A("| %s | `%s` | %.2f | %s |" % (GROUP_LABELS[g], k, w, sub_desc[k]))
    A("")
    A("**为什么结构位置并入「身份/位置变化」组**：口径给定的 5 组权重里没有独立的结构位置组，"
      "而「是否任务首/末步、版本边界、任务末段」描述的是**叙事位置/阶段切换**，"
      "与身份揭示同属「状态与阶段变化」，因此放在该组内部（内部权重 0.15），不改变 0.15 的组权重。")
    A("")
    A("**为什么重复功能并入「母题回收」组**：`structure_count`/`translation_count` 来自 `repeat_kind`，"
      "是母题/仪式/结构重复的计数（口径 §11.4 的第一层 surface_repetition），放在母题回收组内（内部权重 0.25）。")
    A("")
    A("> `semantic_shift_max` 与 `sem_adj_mean` 只写入 JSON 作诊断，**不参与打分**（口径 §11.2 要求 max 仅诊断）。")
    A("")

    # ---------------- 4 打分公式 ----------------
    A("## 4. 打分公式与标准化")
    A("")
    A("```text")
    A("S_B = 0.50·z(A_score) + 0.20·z(语义突变) + 0.15·z(身份/位置变化) + 0.10·z(母题回收) + 0.05·z(状态变化)")
    A("")
    A("其中各结构组：组内子项先各自 z-score → 内部权重加权合成组原始分 → 组原始分再 z-score")
    A("z 统一用总体标准差（ddof=0），基于 686 个候选；权重在脚本 GROUP_WEIGHTS / SUB_WEIGHTS 中写死")
    A("```")
    A("")
    A("组统计（686 步上的 z 均值/标准差，可用来手算复核）：")
    A("")
    A("| 组 | 组原始分均值 | 组原始分标准差 |")
    A("| --- | --- | --- |")
    for g in GROUP_WEIGHTS:
        st = result["group_stats"][g]
        A("| %s（%s） | %.6f | %.6f |" % (GROUP_LABELS[g], g, st["mean"], st["std"]))
    A("")

    # ---------------- 5 Top30 ----------------
    A("## 5. B 的 Top 30")
    A("")
    A("| 排名 | segment_id | 版本 | 任务 | 步骤 | 分数 | 主要贡献组（加权 z） | 一句话原文摘录 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    L.extend(table_rows(top30, seg_by_id))
    A("")

    # ---------------- 6 bottom10 ----------------
    A("## 6. B 的末尾 10 个（第 %d–%d 名，按分数由低到高）" % (n - 9, n))
    A("")
    A("| 排名 | segment_id | 版本 | 任务 | 步骤 | 分数 | 主要贡献组（加权 z） | 一句话原文摘录 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    L.extend(table_rows(bottom10, seg_by_id))
    A("")
    short_n = result["length_bias"]["n_short_for_window"]
    A("> 注意：%d/%d 步是 `short_for_window`（main_records < %d），按口径 §11.3 它们的步骤内相邻窗距离恒为 0，"
      "只能靠跨步骤突变 + 身份/母题/状态分与词面分排序；末尾 10 个是「词面弱 + 无结构信号」的纯推进步骤。" % (
          short_n, n, WINDOW_SIZE))
    A("")

    # ---------------- 7 A/B 对比 ----------------
    A("## 7. A vs B 对比（同一 686 候选池）")
    A("")
    A("| 指标 | 数值 |")
    A("| --- | --- |")
    A("| Top10 重合度 | %.0f%% |" % (100 * a_b["top10_overlap"]))
    A("| Top20 重合度 | %.0f%% |" % (100 * a_b["top20_overlap"]))
    A("| Top50 重合度 | %.0f%% |" % (100 * a_b["top50_overlap"]))
    A("| Top100 重合度 | %.0f%% |" % (100 * a_b["top100_overlap"]))
    A("| 全池 Spearman(score_A, score_B) | **%.3f** |" % a_b["spearman_a_vs_b"])
    A("| A 的名次被 B 提升 ≥100 名的步骤数 | %d |" % a_b["rank_change"]["n_improved_100plus"])
    A("| A 的名次被 B 压低 ≥100 名的步骤数 | %d |" % a_b["rank_change"]["n_worsened_100plus"])
    A("| A 的 Top10 中仍在 B 的 Top20 的个数 | %d / 10 |" % a_b["rank_change"]["top10_of_a_still_in_b_top20"])
    A("| A 的 Top10 中仍在 B 的 Top50 的个数 | %d / 10 |" % a_b["rank_change"]["top10_of_a_still_in_b_top50"])
    A("")
    A("**名次上升最多的 10 个步骤**（B 相对 A）：")
    A("")
    A("| segment_id | A 名次 | B 名次 | 提升 | B 主要贡献组 |")
    A("| --- | --- | --- | --- | --- |")
    for it in a_b["top_improved"][:10]:
        r = next(x for x in rows if x["segment_id"] == it["segment_id"])
        A("| `%s` | %d | %d | +%d | %s |" % (
            it["segment_id"], it["a_rank"], it["b_rank"], it["delta"], fmt_groups(r)))
    A("")

    # ---------------- 8 人工标注 ----------------
    A("## 8. vs 人工标注（74 条；只用于评测，不参与调参）")
    A("")
    A("> 标注来自分层抽样（L1–L7，单标注人），**不是随机样本**，不能据此算全局 Precision/Recall；"
      "等级 = 0 普通推进 / 1 局部信息或关系变化 / 2 叙事状态明显变化 / 3 重大转折或前文意义被重新解释。")
    A("")
    A("| 指标 | A（词面基线） | B（结构增强） |")
    A("| --- | --- | --- |")
    A("| Spearman(检测器分数, 人工等级) | **%.3f** | **%.3f** |" % (human_a["spearman"], human_b["spearman"]))
    for lv in (0, 1, 2, 3):
        A("| 等级 %d 的样本均分（n=%d） | %.3f | %.3f |" % (
            lv, human_a["level_n"].get(lv, 0), human_a["level_means"].get(lv, 0.0),
            human_b["level_means"].get(lv, 0.0)))
    A("| 显著样本（≥2，n=%d）排名中位数 | %s | %s |" % (
        human_a["n_significant"], fmt_rank(human_a["significant_median_rank"]),
        fmt_rank(human_b["significant_median_rank"])))
    A("| 显著样本落在 Top20 的个数 | %d / %d | %d / %d |" % (
        human_a["significant_in_top20"], human_a["n_significant"],
        human_b["significant_in_top20"], human_b["n_significant"]))
    A("| 显著样本落在 Top50 的个数 | %d / %d | %d / %d |" % (
        human_a["significant_in_top50"], human_a["n_significant"],
        human_b["significant_in_top50"], human_b["n_significant"]))
    A("| 显著样本落在 Top100 的个数 | %d / %d | %d / %d |" % (
        human_a["significant_in_top100"], human_a["n_significant"],
        human_b["significant_in_top100"], human_b["n_significant"]))
    A("")
    A("分类型（只看该类型标注样本的排名中位数 / 落在 Top100 数）：")
    A("")
    A("| 类型 | n | A 排名中位数 | A 在 Top100 | B 排名中位数 | B 在 Top100 |")
    A("| --- | --- | --- | --- | --- | --- |")
    for t in ("prophecy", "sacrifice", "identity", "memory", "motif"):
        if t not in human_a["by_type"]:
            continue
        ta, tb = human_a["by_type"][t], human_b["by_type"][t]
        A("| %s | %d | %s | %d | %s | %d |" % (
            t, ta["n"], fmt_rank(ta["median_rank"]), ta["in_top100"],
            fmt_rank(tb["median_rank"]), tb["in_top100"]))
    A("")
    A("**解读口径**：A 的老问题是「1/2/3 级分数几乎持平」（只能判断有没有强词面信号，判断不了转折深度）；"
      "B 的评测重点是 **2/3 级相对 1 级是否拉开**、以及显著样本的排名中位数/Top-k 命中是否改善。"
      "74 条样本量小且分层，任何单项指标的 ±1–2 个样本变化都可能只是抽样噪声，需结合案例核对。")
    A("")
    A("> 口径说明：上表 A 的指标由本脚本从 `data/config/baseline-a-scores.json` **重新计算**"
      "（Spearman 用平均名次处理并列、排名中位数用 1-based 名次）；与 `data/reports/baseline-a-vs-human.md` 的 "
      "0.415 / 164 有细微差异（该文档的并列名次与中位数取法不同），趋势一致。"
      "B 与 A 用**完全相同的评测函数**，因此 A/B 两列可直接对比。")
    A("")

    # ---------------- 9 重点案例 ----------------
    A("## 9. 重点案例：昔涟诞生段 + B 提升案例")
    A("")
    A("### 9.1 昔涟诞生（记忆的拼图）")
    A("")
    A("| 项目 | 数值 |")
    A("| --- | --- |")
    A("| segment_id | `%s` |" % FOCUS_CASE)
    a_row_focus = next(x for x in a_rows if x["segment_id"] == FOCUS_CASE)
    A("| A 分数 / 名次 | %.4f / 第 %d 名 |" % (a_row_focus["score"], a_row_focus["rank"]))
    A("| B 分数 / 名次 | %.4f / 第 %d 名（%+d） |" % (focus["b_score"], focus["b_rank"], focus["delta"]))
    A("| n_windows / short_for_window | %d / %s |" % (focus["n_windows"], focus["short_for_window"]))
    A("| B 各组 z 与贡献 | %s |" % "；".join(
        "%s z=%+.2f, w·z=%+.3f" % (GROUP_LABELS[g], focus["groups"][g]["z"], focus["groups"][g]["contrib"])
        for g in GROUP_WEIGHTS))
    A("| B 主要贡献组 | %s |" % "、".join(GROUP_LABELS[g] for g in focus["top_features"]))
    A("| 原文摘录 | %s |" % focus["excerpt"])
    A("")
    A("说明：该步是 3.7 的「聆听昔涟讲述真相，完成『记忆』的拼图」（原文含「『昔涟』的诞生之地」），"
      "是 `方向与理由v2.md` 举的「词面弱、结构强」反例。它在 A 中排 %d 名；B 用结构项把它排到 %d 名。"
      "若 B 仍未能把它大幅提前，说明当前结构特征（TF-IDF 突变 + 母题词表）对「语义回收但字面不同」的识别仍有限，"
      "需要在报告中如实说明，而不是靠调权重刷案例。" % (focus["a_rank"], focus["b_rank"]))
    A("")
    A("### 9.2 B 相对 A 上升最多、且进入 B Top100 的案例（人工核对原文）")
    A("")
    A("| segment_id | A 名次 | B 名次 | B 主要贡献组 | 标注等级 | 摘录 | 人工判断 |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    label_by_id = {s["segment_id"]: s for s in labels["samples"]}
    # 案例池：B 进 Top100、A 未进 Top100，按「B 名次 − A 名次」（提升幅度）降序
    case_pool = [
        {"segment_id": r["segment_id"],
         "a_rank": a_rank_map[r["segment_id"]],
         "b_rank": r["rank"],
         "delta": a_rank_map[r["segment_id"]] - r["rank"]}
        for r in rows
        if r["rank"] <= 100 and a_rank_map[r["segment_id"]] > 100
    ]
    case_pool.sort(key=lambda x: (-x["delta"], x["b_rank"]))
    case_items = case_pool[:6]
    for it in case_items:
        sid = it["segment_id"]
        r = next(x for x in rows if x["segment_id"] == sid)
        lab = label_by_id.get(sid)
        lab_txt = "—" if lab is None else "%d（%s）" % (lab["significance"], "、".join(lab["types"]))
        A("| `%s` | %d | %d | %s | %s | %s | %s |" % (
            sid, it["a_rank"], it["b_rank"], fmt_groups(r, 2), lab_txt,
            pick_excerpt_b(seg_by_id[sid]), CASE_NOTES.get(sid, "待人工核对")))
    A("")
    A("> 上表案例只按「B 名次 − A 名次」自动选，**不按标注挑选**（标注仅用于并列展示是否被标注过）；"
      "「人工判断」列是我逐条读原文后的判断：★=确实是结构性的叙事变化；○=有局部结构信号但显著性一般；×=B 误报。")
    A("")

    # ---------------- 9.3 神谕兑现核对 ----------------
    oc = result["oracle_fulfillment_check"]["summary"]
    A("### 9.3 神谕兑现段核对（13 条人工判定的兑现段，用于 prophecy 类）")
    A("")
    A("| 指标 | A | B |")
    A("| --- | --- | --- |")
    A("| 13 条兑现段在 Top50 的个数 | %d | %d |" % (oc["a_in_top50"], oc["b_in_top50"]))
    A("| 13 条兑现段在 Top100 的个数 | %d | %d |" % (oc["a_in_top100"], oc["b_in_top100"]))
    A("| 排名中位数 | %s | %s |" % (fmt_rank(oc["median_a_rank"]), fmt_rank(oc["median_b_rank"])))
    A("")
    A("| oracle | segment_id | 兑现类型 | A 名次 | B 名次 | 变化 | 证据（截断） |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for r in result["oracle_fulfillment_check"]["rows"]:
        A("| %s | `%s` | %s | %d | %d | %+d | %s |" % (
            r["oracle_id"], r["segment_id"], r["fulfillment_type"] or "—",
            r["a_rank"], r["b_rank"], r["delta"], truncate(r["evidence"], 40)))
    A("")

    # ---------------- 10 长度分层 ----------------
    A("## 10. 长度分层（4 层各 Top5 + 显著样本覆盖率 A vs B）")
    A("")
    for b in LENGTH_BINS:
        members = [r for r in rows if r["length_bin"] == b]
        A("### %s（B 池内 %d 步，占 %.1f%%）" % (b, len(members), 100.0 * len(members) / n))
        A("")
        A("| 排名 | segment_id | 版本 | 任务 | 步骤 | 分数 | 主要贡献组（加权 z） | 一句话原文摘录 |")
        A("| --- | --- | --- | --- | --- | --- | --- | --- |")
        L.extend(table_rows(members[:5], seg_by_id))
        A("")
    A("**各层显著样本（等级≥2）覆盖率对照**：")
    A("")
    A("| 长度层 | 层内步数 | 该层标注样本 | 显著样本 | A 显著进 Top100 | B 显著进 Top100 | A 显著排名中位数 | B 显著排名中位数 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for b in LENGTH_BINS:
        d = result["length_strata"][b]
        A("| %s | %d | %d | %d | %d | %d | %s | %s |" % (
            b, d["n"], d["n_annotated"], d["n_sig_annotated"],
            d["a_sig_in_top100"], d["b_sig_in_top100"],
            fmt_rank(d["a_sig_median_rank"]), fmt_rank(d["b_sig_median_rank"])))
    A("")
    bias = result["length_bias"]
    A("- B 分数 vs 对白句数 Spearman ρ = **%+.3f**，vs 字符数 ρ = **%+.3f**"
      "（A 分别为 +0.438 / +0.429，见 `baseline-a-ranking.md` §7）。**B 的长度效应比 A 更强，这是 B 的真实短板。**" % (
          bias["spearman_score_vs_n_dialogue"], bias["spearman_score_vs_char_len"]))
    A("- 成因有两个（都属于先验设计而非调参）：① **%d/%d 步是 `short_for_window`**（main_records < %d），"
      "按口径 §11.3 步骤内相邻窗距离取 0 并**直接参与打分**，于是这些步骤在「语义突变」这一路上天然拿不到正分，"
      "而长步骤可以；② 身份/母题组的计数类特征（首次登场角色、词表回收、表层重复）与步骤长度正相关"
      "（已用 log1p / 每记录率压低，但没有消除）。" % (
          bias["n_short_for_window"], n, WINDOW_SIZE))
    A("- **增益确实集中在长步骤**：>30 句层显著样本进 Top100 从 %d → %d（中位数 %s → %s）；"
      "11–30 句层持平（%d → %d）；4–10 句层 %d → %d；1–3 句层该层标注样本里没有显著样本（n=%d），无法评估。" % (
          result["length_strata"][LENGTH_BINS[3]]["a_sig_in_top100"],
          result["length_strata"][LENGTH_BINS[3]]["b_sig_in_top100"],
          fmt_rank(result["length_strata"][LENGTH_BINS[3]]["a_sig_median_rank"]),
          fmt_rank(result["length_strata"][LENGTH_BINS[3]]["b_sig_median_rank"]),
          result["length_strata"][LENGTH_BINS[2]]["a_sig_in_top100"],
          result["length_strata"][LENGTH_BINS[2]]["b_sig_in_top100"],
          result["length_strata"][LENGTH_BINS[1]]["a_sig_in_top100"],
          result["length_strata"][LENGTH_BINS[1]]["b_sig_in_top100"],
          result["length_strata"][LENGTH_BINS[0]]["n_sig_annotated"]))
    A("- **诚实结论**：B **不是**「只偏爱长步骤」（各层 Top5 都有人工可解释的强信号步，短步骤也能进 B Top100），"
      "但 B 相对 A 的增益**主要来自 >30 句的长步骤**；A/B 对比必须分层报，不能只看全局 Top-k。"
      "下一步若要让短步骤也受益，应把「步骤内滑窗」换成句子级/跨步骤信号，而不是调权重。")
    A("")

    # ---------------- 10.1 结构位置事后核对 ----------------
    spc = result["structure_position_check"]
    A("### 10.1 结构位置项的事后核对（诊断，不参与调参）")
    A("")
    A("- B Top100 中有 **%d** 步是任务首步或末步（其中 %d 步 `id_struct_pos` ≥ 1.5）。"
      "这一项会把「任务开场/结尾」抬高，需要确认不是纯噪声。" % (
          spc["n_top100_task_boundary"], spc["n_top100_struct_pos_high"]))
    A("- 用 74 条标注做**事后**核对（仅解释、不调参）：落在任务首/末步的标注样本 %d 条，其中等级≥2 的有 **%d** 条——"
      "任务边界确实是显著节点的高发位置，这个启发式有依据；但仍有个别「开场过场/结尾报幕」被抬高的风险。"
      "Top100 中的任务边界步清单（前 10 个）：%s。" % (
          spc["n_annotated_task_boundary"], spc["n_annotated_task_boundary_sig"],
          "、".join("`%s`" % x for x in spc["task_boundary_ids_in_top100"][:10])))
    A("")

    # ---------------- 11 敏感性 ----------------
    A("## 11. 敏感性分析（W1–W5，口径 §5）")
    A("")
    A("| 变体 | 组权重（wordface/semantic/identity/motif/state） | Top10 重合 | Top20 重合 | Top50 重合 | Spearman(vs W1) | 昔涟段排名 |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for name, s in sensitivity.items():
        w = s["weights"]
        A("| %s | %.2f / %.2f / %.2f / %.2f / %.2f | %.0f%% | %.0f%% | %.0f%% | %.3f | %d |" % (
            name, w["wordface"], w["semantic_shift"], w["identity_change"],
            w["motif_return"], w["state_change"],
            100 * s["top10_overlap"], 100 * s["top20_overlap"], 100 * s["top50_overlap"],
            s["spearman_vs_W1"], s["focus_case_rank"]))
    A("")
    A("> 说明：本表是**权重敏感性**而非标注评测。W2/W3 把 4 个结构组整体 ±20%（词面固定 0.50，再归一）；"
      "W4 只留语义突变；W5 去掉词面、只留结构规则。判定标准（口径 §5）：昔涟诞生、神谕兑现等案例在"
      "不同权重下是否仍在前列；若结论依赖某一组权重，需要在报告里如实标注。")
    A("")

    # ---------------- 12 复算 ----------------
    A("## 12. 复算与自校验")
    A("")
    A("```bash")
    A("# 重跑（生成 JSON + MD；约 20 秒）")
    A(RUN_CMD)
    A("# 只校验已有产物：报告表格 vs JSON、组/子项 z 重算、抽查 5 条")
    A("conda run -n nlpLesson python tools/baseline_b.py --verify")
    A("```")
    A("")
    A("- JSON 每步含 `groups.<g>.{raw,z,weight,contrib}`、`features.<k>.{raw,z}`、`score`、`rank`、"
      "`n_windows`、`short_for_window`、`length_bin`，且 `score = Σ contrib`，可逐条手算复核；"
      "`feature_stats` / `group_stats` 给出每个特征与每组原始分的均值/标准差。")
    A("- 脚本无随机数、无时间戳、无网络；TF-IDF 拟合与 jieba 分词均确定性 → 同输入必得同输出"
      "（已实测连续两次运行 JSON 与 MD 的 SHA-256 完全一致）。")
    A("- 脚本运行前后校验 A 的产物 `baseline-a-scores.json` sha256 不变（不修改既有产物）。")
    A("- 自校验内容：686 步全部有分数；`score = Σ 组贡献`；组 z / 子项 z 与 `group_stats` / `feature_stats` 自洽；"
      "MD 里 60 行排序表（Top30 + 末尾10 + 4 层×Top5）逐行比对 JSON 的 `segment_id/rank/score`；"
      "再抽 5 条（第 1/7/25/677/686 名）从 JSON 重算并每 137 条抽样重算。任一项不一致脚本以退出码 1 失败。")
    A("")

    # ---------------- 13 局限 ----------------
    A("## 13. 局限（写清楚，避免误读）")
    A("")
    A("1. **无标签打分**：B 的分数只是先验特征的加权，不代表叙事显著性的真值；A/B 的「谁更好」只能由标注评测 + 案例核对回答。")
    A("2. **TF-IDF 不是语义理解**：字符 n-gram 只能捕捉字面/构词层面的变化，对「换了说法但语义回收」（如昔涟诞生）仍可能漏检；"
      "这正是口径里把句向量列为后续工作的原因。")
    A("3. **长度偏向是 B 的主短板**：B 分数与对白句数 ρ = +0.683（A +0.438），且相对 A 的增益集中在 >30 句层；"
      "%d/%d 步 main_records < %d（short_for_window），按口径 §11.3 步骤内语义突变恒为 0，"
      "这些步天然拿不到「窗内突变」这一路正分。若短步骤里有很多重点（如短告别），B 的优势会被稀释（§10 已量化）。" % (
          result["length_bias"]["n_short_for_window"], n, WINDOW_SIZE))
    A("4. **母题回收依赖词表**：`semantic_recall` 是字面匹配，同义改写、反讽、留白抓不到；`motif_gap` 只在词表命中时才有值。")
    A("5. **结构位置是启发式**：语料没有 `chapter` 字段，任务首/末步与版本边界用 `step_idx`/`version` 推断；"
      "「章节切换」只能由任务边界代理。该特征会把任务开场/结尾抬高（§10.1 事后核对：Top100 中 %d 步是任务边界），"
      "个别「开场过场/结尾报幕」可能被误抬高。" % spc["n_top100_task_boundary"])
    A("6. **标注集小且分层**：74 条、单标注人，±1–2 个样本的指标变动可能只是噪声；不能据此宣称 B 显著优于 A，"
      "只能报告方向与案例。")
    A("7. **权重未调参**：组权重来自口径先验；W2–W5 只用于敏感性分析，不用于选权重。")
    A("8. **A/B 分数不可直接比大小**：两个检测器的特征和权重不同；只能比排序、Top-k 重合度、"
      "与标注的相关性和案例。")
    A("")
    return "\n".join(L)


def fmt_rank(x):
    if x is None or x < 0:
        return "—"
    return "%.1f" % float(x) if abs(float(x) - round(float(x))) > 1e-9 else "%d" % int(round(float(x)))


# ============================================================================
# 11. 自校验
# ============================================================================
MD_ROW_RE = re.compile(
    r"^\| (\d+) \| `([^`]+)` \| ([^|]+) \| ([^|]*) \| ([^|]*) \| ([-0-9.]+) \| ([^|]*) \| ([^|]*) \|$"
)


def verify(verbose=False):
    if not (os.path.exists(OUT_JSON) and os.path.exists(OUT_MD)):
        print("产物不存在，无法校验", file=sys.stderr)
        return False
    with open(OUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = data["segments"]
    by_id = {s["segment_id"]: s for s in rows}
    problems = []

    if len(rows) != 686:
        problems.append("分数条数 %d != 686" % len(rows))
    if [r["rank"] for r in rows] != list(range(1, len(rows) + 1)):
        problems.append("rank 不是 1..n")
    if any(rows[i]["score"] < rows[i + 1]["score"] - 1e-12 for i in range(len(rows) - 1)):
        problems.append("score 未按降序")

    weights = data["meta"]["group_weights"]
    stats = data["group_stats"]
    # 每条 score = Σ 组贡献；组 z 与组统计自洽；contrib = weight × z
    for r in rows:
        sc = sum(r["groups"][g]["contrib"] for g in weights)
        if abs(sc - r["score"]) > 2e-5:
            problems.append("score!=Σcontrib %s" % r["segment_id"])
        for g in weights:
            z = (r["groups"][g]["raw"] - stats[g]["mean"]) / (stats[g]["std"] or 1.0)
            if abs(z - r["groups"][g]["z"]) > 2e-3:
                problems.append("组 z 不自洽 %s/%s" % (r["segment_id"], g))
            if abs(r["groups"][g]["contrib"] - weights[g] * r["groups"][g]["z"]) > 2e-4:
                problems.append("contrib!=w*z %s/%s" % (r["segment_id"], g))

    # 子项特征 z 与 feature_stats 自洽（抽样 10 条 × 全部特征）
    feat_stats = data.get("feature_stats", {})
    for r in rows[:5] + rows[-5:]:
        for k, fv in r["features"].items():
            if k not in feat_stats:
                continue
            st = feat_stats[k]
            z = (fv["raw"] - st["mean"]) / (st["std"] or 1.0)
            if abs(z - fv["z"]) > 3e-3:
                problems.append("子项 z 不自洽 %s/%s" % (r["segment_id"], k))

    # MD 排序表 vs JSON
    with open(OUT_MD, "r", encoding="utf-8") as f:
        md_rows = []
        for line in f:
            m = MD_ROW_RE.match(line.rstrip("\n"))
            if m:
                md_rows.append({"rank": int(m.group(1)), "sid": m.group(2), "score": float(m.group(6))})
    if len(md_rows) < 60:
        problems.append("MD 排序表行数 = %d，少于预期 60 行（Top30 + 末尾10 + 4 层×Top5）" % len(md_rows))
    for r in md_rows:
        item = by_id.get(r["sid"])
        if item is None:
            problems.append("MD sid 不在 JSON：%s" % r["sid"])
            continue
        if abs(item["score"] - r["score"]) > 5e-5:
            problems.append("分数不一致 %s：MD %.4f vs JSON %.6f" % (r["sid"], r["score"], item["score"]))
        if item["rank"] != r["rank"]:
            problems.append("排名不一致 %s：MD %d vs JSON %d" % (r["sid"], r["rank"], item["rank"]))

    # 抽查 5 条重算
    sample_ids = [rows[i]["segment_id"] for i in (0, 6, 24, 676, 685)]
    checked = []
    for sid in sample_ids:
        it = by_id[sid]
        recomputed = sum(weights[g] * it["groups"][g]["z"] for g in weights)
        if abs(recomputed - it["score"]) > 2e-5:
            problems.append("重算不一致 %s：%.6f vs %.6f" % (sid, recomputed, it["score"]))
        checked.append((it["rank"], sid, it["score"]))
    # 抽样重算（每 137 条）
    for idx in range(0, len(rows), 137):
        it = rows[idx]
        recomputed = sum(weights[g] * it["groups"][g]["z"] for g in weights)
        if abs(recomputed - it["score"]) > 2e-5:
            problems.append("抽样重算不一致 %s" % it["segment_id"])

    # 人工评测 / A/B 指标与 JSON 内部一致性
    he = data["human_eval"]
    for key in ("A_baseline", "B_enhanced"):
        h = he[key]
        if h["significant_in_top20"] > 20:
            problems.append("%s Top20 命中 >20" % key)
        if h["n_significant"] != 28:
            problems.append("%s 显著样本数 != 28" % key)

    if verbose:
        print("\n抽查 5 条（rank / segment_id / score）：")
        for rk, sid, sc in checked:
            print("  #%-3d %-44s %.6f" % (rk, sid, sc))
        print("MD 排序表行数 = %d；全表抽样重算 = %d 条" % (
            len(md_rows), len(range(0, len(rows), 137))))
        print("人工标注：Spearman A=%.3f → B=%.3f；Top20 命中 A=%d → B=%d；Top100 A=%d → B=%d（共 %d 显著样本）" % (
            he["A_baseline"]["spearman"], he["B_enhanced"]["spearman"],
            he["A_baseline"]["significant_in_top20"], he["B_enhanced"]["significant_in_top20"],
            he["A_baseline"]["significant_in_top100"], he["B_enhanced"]["significant_in_top100"],
            he["A_baseline"]["n_significant"]))
    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="检测器 B：结构增强的叙事显著性检测")
    ap.add_argument("--verify", action="store_true", help="只校验已有产物（不重算）")
    args = ap.parse_args()
    jieba.setLogLevel(60)
    jieba.initialize()
    if args.verify:
        ok = verify(verbose=True)
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    main_build()


if __name__ == "__main__":
    main()
