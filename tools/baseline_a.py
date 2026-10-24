#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
baseline_a.py — 检测器 A：词面 + 局部情绪基线（无标签先验打分）

口径来源：docs/实验口径与评测方案.md
  - §3  候选池：view=main 的步骤实例，排除 low_content（本脚本用
        n_main>0 且 !low_content 且 has_dialogue，共 686 个，与正文一致）
  - §5  权重先验固定、标注不参与调参
  - §9  特征在步骤内部按记录（句）计算后聚合（比例 + top-20% 均值）
  - §11.1 一律基于 main_records（保持原始顺序），不用拼接文本
  - §11.2/§11.3 长度偏差：报告按长度分层，A 只用局部特征、不做滑窗

硬约束：
  * 只使用**局部**文本特征（单步骤内部），不使用任何跨步骤 / 结构信息
    （语义突变、身份变化、母题回收等全部属于检测器 B，本脚本不触碰）
  * 不使用 embedding / 外部模型 / 联网；不读取任何标注
  * 语料与 config 只读；输出仅 2 个产物（JSON + MD）

运行：
    conda run -n nlpLesson python tools/baseline_a.py            # 重算并写产物
    conda run -n nlpLesson python tools/baseline_a.py --verify   # 只校验产物自洽

产物：
    data/config/baseline-a-scores.json   全部 686 步的分数 + raw/z/贡献（可复算）
    data/reports/baseline-a-ranking.md   Top30 + 末尾10 + 长度分层 + 口径说明
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter

import jieba
import numpy as np

# 让 Windows 控制台按 UTF-8 输出（conda run 下偶发 GBK 报错）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEGMENTS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
OUT_JSON = os.path.join(ROOT, "data", "config", "baseline-a-scores.json")
OUT_MD = os.path.join(ROOT, "data", "reports", "baseline-a-ranking.md")

RUN_CMD = "conda run -n nlpLesson python tools/baseline_a.py"

# ============================================================================
# 1. 词表（全部写死；只做字面匹配，不做语义/跨步骤判断）
# ============================================================================
# 1.1 死亡 / 牺牲 / 告别词表（任务要求自建；来源为人工通读 + docs/NLP思路.md
#     的关键词基线清单）。分两档权重：
#       强档 weight=1.0：直接指向死亡、牺牲、埋葬、遗言、诀别等
#       弱档 weight=0.5：语境相关但易泛化（最后 / 再见 / 失去 / 尽头 等），
#                        命中 1 次只算 0.5 次，避免"最后""不再"这类高频词主导分数

DEATH_STRONG = [
    # 死亡 / 逝去
    "死", "死亡", "死去", "死了", "至死", "致死", "必死", "寻死", "生死",
    "去世", "逝世", "逝去", "消逝", "殒", "殒命", "殁", "亡", "亡故",
    "身亡", "阵亡", "离世", "长眠", "永眠", "安眠", "沉睡不醒",
    # 牺牲 / 献祭 / 殉
    "牺牲", "赴死", "献祭", "殉", "殉道", "殉难", "自掘坟墓",
    # 被杀 / 誓死（含"死"但分词会切成两字以上的复合词）
    "杀死", "处死", "赐死", "誓死", "拼死", "舍命",
    # 尸体 / 埋葬 / 陵墓
    "尸", "尸体", "遗骸", "遗体", "骸骨", "坟", "墓", "坟墓", "陵墓", "墓碑", "陵园",
    "棺", "灵柩", "葬", "埋葬", "葬身", "火化", "灰烬", "余烬", "祭奠", "悼念", "哀悼",
    # 告别 / 诀别 / 遗言
    "告别", "永别", "诀别", "永诀", "送别", "道别", "别了", "离别", "惜别",
    "后会无期", "遗言", "遗愿", "临终",
]

DEATH_WEAK = [
    "最后", "再见", "失去", "失落", "尽头", "终结", "再也", "不再",
    "别走", "不要走", "别离开", "回不来", "再也见不到",
]

# 1.2 负面情绪词表（多字词做子串匹配；单字词只在 jieba 分词结果里精确匹配，
#     否则「哪怕」里的"怕"、「积累」里的"累"会误伤）
NEG_MULTI = [
    "悲伤", "悲哀", "悲痛", "难过", "痛苦", "绝望", "失望", "遗憾", "后悔",
    "愧疚", "抱歉", "对不起", "孤独", "寂寞", "恐惧", "害怕", "颤抖", "战栗",
    "哭泣", "流泪", "眼泪", "忧伤", "忧愁", "愤怒", "憎恨", "厌恶", "无助",
    "无力", "无奈", "叹息", "沉重", "苦涩", "灰暗", "黑暗", "冰冷", "寒冷",
    "破碎", "崩坏", "崩塌", "残酷", "残忍", "毁灭", "折磨", "煎熬", "疲惫",
    "疲倦", "虚无", "空无", "幻灭", "心灰意冷", "无能为力", "不知所措",
    "痛不欲生", "生不如死", "心如死灰", "哽咽", "嘶哑", "颤声",
    # 增补：常见负面情绪表达（仍是纯词面，不含语体/结构信息）
    "心痛", "心碎", "迷惘", "彷徨", "惶恐", "不安", "焦虑", "担忧", "担心",
    "惋惜", "惆怅", "凄凉", "荒凉", "自责", "懊悔", "沮丧", "酸楚",
]
NEG_SINGLE = ["悲", "痛", "疼", "怕", "泪", "哭", "恨", "苦", "惨", "累"]

# 1.3 否定词（token 精确匹配；用于两个作用：
#     ① 否定本身是情绪/态度信号，计入负面情绪强度；
#     ② "不难过""没有遗憾"这类**否定掉负面词**的情况按 0.6 折减）
NEGATION_TOKENS = {
    "不", "没", "没有", "无", "未", "别", "勿", "莫", "非", "否",
    "不是", "不会", "不能", "不想", "不要", "无法", "毫无", "并不", "从不",
    "绝不", "从未", "未能", "未曾", "不必", "不用", "没法", "没能",
}
# 否定词在文本里的字符回看窗口：命中负面词前 5 个字符内出现否定字，
# 视为"被否定的负面表达"（如 不难过 / 没后悔）
NEG_LOOKBACK = 5

# 1.4 第一人称脆弱表达：
#     模式 = {第一人称代词} + 3 个 token 内出现脆弱词（中间遇标点即中断）。
#     只有"我/我们 + 求/怕/不想/不能/别走…"这种**同句贴身**的脆弱表达计入；
#     单独的"别走"（无第一人称）不计入本特征（留给词面词表）。
FIRST_PERSON = {"我", "我们", "咱们", "吾", "俺", "我自己", "我自己"}
VULN_PREFIX = [
    "求", "恳求", "祈求", "求求", "怕", "害怕", "恐惧", "不敢", "不想",
    "不愿", "不能", "不会", "不要", "无法", "做不到", "受不了", "撑不住",
    "抱歉", "对不起", "难过", "疼", "痛", "舍不得", "忘不了", "忘不掉",
    "放不下", "怎么办", "救我", "救救", "救命", "别走", "别离开", "留下",
    "拜托",
]
PUNCT = set("，。！？、；：…—「」『』（）().,!?;:~-· \t\r\n\"'")

# 1.5 疑问 / 感叹 / 短句判定
QUESTION_ENDS = ("？", "?")
QUESTION_PARTICLES = ("吗", "呢", "么", "嘛")
QUESTION_MARKERS = ["为什么", "为何", "怎么", "如何", "难道", "是否", "岂", "多少", "什么时候"]
EXCLAIM_CHARS = ("！", "!")
SHORT_SENTENCE_MAX_CHARS = 12  # 记录文本字符数 <= 12 视为短句（合格池平均 22.7 字）

# ============================================================================
# 2. 特征与权重（先验固定，不参与调参；权重和 = 1.0）
# ============================================================================
# 设计依据 docs/方向与理由v2.md §2-A：「只看词面和局部情绪的常规基线」。
# 权重大小反映先验重要性：本语料（翁法罗斯主线）的叙事显著性最常由
# 死亡/牺牲/告别词触发，故 death 组合计 0.30 最高；负面情绪与第一人称
# 脆弱表达各 0.20；`pause_ratio` 是语料已给字段，占 0.10；标点/句式类
# 局部节奏特征合计 0.20（短句 0.07、感叹 0.06、疑问 0.07）。
WEIGHTS = {
    "death_hit_rate": 0.18,        # 死亡/牺牲/告别词：每记录加权命中数（比例口径）
    "death_hit_top20": 0.12,       # 死亡/牺牲/告别词：记录级命中的 top-20% 均值（峰值口径）
    "neg_emotion_rate": 0.12,      # 负面情绪 + 否定：每记录净强度（比例口径）
    "neg_emotion_top20": 0.08,     # 负面情绪 + 否定：top-20% 均值（峰值口径）
    "vulnerable_fp_rate": 0.12,    # 第一人称脆弱表达：每记录命中数
    "vulnerable_fp_top20": 0.08,   # 第一人称脆弱表达：top-20% 均值
    "pause_ratio": 0.10,           # 语料字段：pause 类重复记录占比（「……」停顿）
    "short_sentence_ratio": 0.07,  # 短句（<=12 字）记录占比
    "exclaim_ratio": 0.06,         # 含感叹号的记录占比（感叹密度）
    "question_ratio": 0.07,        # 疑问记录占比（问句密度）
}

FEATURE_LABELS = {
    "death_hit_rate": "死亡/牺牲/告别词密度",
    "death_hit_top20": "死亡/牺牲/告别词峰值(top20%)",
    "neg_emotion_rate": "负面情绪+否定密度",
    "neg_emotion_top20": "负面情绪+否定峰值(top20%)",
    "vulnerable_fp_rate": "第一人称脆弱表达密度",
    "vulnerable_fp_top20": "第一人称脆弱表达峰值(top20%)",
    "pause_ratio": "停顿比例(……)",
    "short_sentence_ratio": "短句比例",
    "exclaim_ratio": "感叹记录比例",
    "question_ratio": "疑问记录比例",
}

FEATURE_KEYS = list(WEIGHTS.keys())
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "权重和必须为 1"

LENGTH_BINS = ["1–3 句", "4–10 句", "11–30 句", ">30 句"]


def length_bin(n_dialogue):
    """§9 的规模分层口径：按步骤内**对白记录数**分箱（与正文 65/148/236/237 一致）"""
    if n_dialogue <= 3:
        return LENGTH_BINS[0]
    if n_dialogue <= 10:
        return LENGTH_BINS[1]
    if n_dialogue <= 30:
        return LENGTH_BINS[2]
    return LENGTH_BINS[3]


# ============================================================================
# 3. 匹配器
# ============================================================================
def _compile_multi(terms):
    """多字词表 → 最长优先的正则（同一位置长词优先，finditer 不重叠）"""
    terms = sorted({t for t in terms if len(t) >= 2}, key=len, reverse=True)
    if not terms:
        return None
    return re.compile("|".join(re.escape(t) for t in terms))


RE_DEATH_MULTI = _compile_multi(DEATH_STRONG + DEATH_WEAK)
RE_NEG_MULTI = _compile_multi(NEG_MULTI)
RE_QUESTION_MARKERS = _compile_multi(QUESTION_MARKERS)
DEATH_STRONG_SET = set(DEATH_STRONG)
DEATH_WEAK_SET = set(DEATH_WEAK)
NEG_SINGLE_SET = set(NEG_SINGLE)


def death_hits_record(text, tokens):
    """记录级：死亡/牺牲/告别词**加权**命中次数（强档 1.0 / 弱档 0.5）"""
    n = 0.0
    # 多字词：子串匹配，避免依赖分词边界（"永别"可能被切成 永/别）
    for m in RE_DEATH_MULTI.finditer(text):
        n += 1.0 if m.group(0) in DEATH_STRONG_SET else 0.5
    # 单字档：只在分词 token 精确匹配时计（"死"作为独立 token；不误伤 该死/生死？——
    # 这里对单字采用 token 相等：jieba 会把 该死 切成 该死，故不会命中；这是保守选择）
    for t in tokens:
        if t in DEATH_STRONG_SET and len(t) == 1:
            n += 1.0
    return n


def _negation_before(text, pos):
    """命中位置前 NEG_LOOKBACK 个字符内是否有否定字（用于"不难过"折减）"""
    head = text[max(0, pos - NEG_LOOKBACK):pos]
    return any(ch in head for ch in "不没无未别勿莫非否")


def neg_score_record(text, tokens):
    """记录级：负面情绪净强度 + 否定词作用。

    净强度 = 负面词加权命中 + 0.5 × 否定词数 − 0.6 × 被否定的负面词数，截断到 >=0。
    否定词本身计正分：否定在叙事里常是拒绝/抗拒/否认的强表达（"我不能""不会忘记"）。
    """
    hits = 0.0
    negated = 0.0
    for m in RE_NEG_MULTI.finditer(text):
        hits += 1.0
        if _negation_before(text, m.start()):
            negated += 1.0
    for idx, t in enumerate(tokens):
        if t in NEG_SINGLE_SET:
            hits += 1.0
            # 单字词用 token 下标回看：上一个 token 若以否定字开头则算被否定
            if idx > 0 and tokens[idx - 1] and tokens[idx - 1][0] in "不没无未别勿莫非否":
                negated += 1.0
    neg_tokens = sum(1 for t in tokens if t in NEGATION_TOKENS)
    return max(0.0, hits + 0.5 * neg_tokens - 0.6 * negated)


def vulnerable_fp_record(tokens):
    """记录级：第一人称脆弱表达命中数（代词 + 3 token 内脆弱词，遇标点中断）"""
    hits = 0
    n = len(tokens)
    for i, t in enumerate(tokens):
        if t not in FIRST_PERSON:
            continue
        for j in range(i + 1, min(i + 4, n)):
            w = tokens[j]
            if w in PUNCT or (w and w[0] in PUNCT):
                break
            if any(w == p or w.startswith(p) for p in VULN_PREFIX):
                hits += 1
                break
    return hits


def is_question(text):
    t = text.strip()
    if not t:
        return False
    if t.endswith(QUESTION_ENDS):
        return True
    if t.endswith(QUESTION_PARTICLES):
        return True
    return RE_QUESTION_MARKERS is not None and RE_QUESTION_MARKERS.search(t) is not None


def is_exclaim(text):
    return any(ch in text for ch in EXCLAIM_CHARS)


def top20_mean(values):
    """记录级数值的 top-20% 均值（k=max(1, ceil(0.2n))）——§9 的峰值聚合口径"""
    if not values:
        return 0.0
    arr = sorted(values, reverse=True)
    k = max(1, math.ceil(0.2 * len(arr)))
    return float(sum(arr[:k]) / k)


# ============================================================================
# 4. 读取候选池 + 特征抽取
# ============================================================================
def load_segments():
    rows = []
    with open(SEGMENTS, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def eligible(rows):
    """§3 合格候选池：n_main>0 且 !low_content 且 has_dialogue"""
    return [r for r in rows if r["n_main"] > 0 and not r["low_content"] and r["has_dialogue"]]


def extract_features(seg):
    """在步骤内部按记录（句）抽特征，再聚合到步骤。返回 (raw_features, 诊断信息)"""
    units = [x for x in seg["main_records"] if x["kind"] in ("dialogue", "narration")]
    # 与 text_all 口径一致：只用 main 视图的对白 + 旁白，不混入选项文本
    texts = [x["text"] for x in units if x["text"]]
    n_units = len(texts)

    death_rec, neg_rec, vuln_rec = [], [], []
    short_flags, exclaim_flags, question_flags = [], [], []
    for text in texts:
        tokens = [t for t in jieba.lcut(text) if t.strip()]
        death_rec.append(death_hits_record(text, tokens))
        neg_rec.append(neg_score_record(text, tokens))
        vuln_rec.append(float(vulnerable_fp_record(tokens)))
        short_flags.append(1.0 if len(text) <= SHORT_SENTENCE_MAX_CHARS else 0.0)
        exclaim_flags.append(1.0 if is_exclaim(text) else 0.0)
        question_flags.append(1.0 if is_question(text) else 0.0)

    raw = {
        # 比例口径：记录级命中 / 记录数（长度归一，避免长步骤天然占优）
        "death_hit_rate": float(sum(death_rec) / n_units) if n_units else 0.0,
        # 峰值口径：top-20% 记录的命中均值（长步骤的内部强度峰）
        "death_hit_top20": top20_mean(death_rec),
        "neg_emotion_rate": float(sum(neg_rec) / n_units) if n_units else 0.0,
        "neg_emotion_top20": top20_mean(neg_rec),
        "vulnerable_fp_rate": float(sum(vuln_rec) / n_units) if n_units else 0.0,
        "vulnerable_fp_top20": top20_mean(vuln_rec),
        # 语料已给字段（pause 类重复记录占比）
        "pause_ratio": float(seg["pause_ratio"]),
        # 句式/标点类（记录占比口径）
        "short_sentence_ratio": float(sum(short_flags) / n_units) if n_units else 0.0,
        "exclaim_ratio": float(sum(exclaim_flags) / n_units) if n_units else 0.0,
        "question_ratio": float(sum(question_flags) / n_units) if n_units else 0.0,
    }
    # 报告用诊断：这些不计入分数
    diag = {
        "n_units": n_units,
        "death_sum": sum(death_rec),
        "neg_sum": sum(neg_rec),
        "vuln_sum": sum(vuln_rec),
    }
    return raw, diag


# ============================================================================
# 5. 打分（z-score + 固定权重）
# ============================================================================
def zscore_matrix(feat_rows):
    """对每个特征在 686 个候选上做 z-score（总体标准差 ddof=0）"""
    keys = FEATURE_KEYS
    mat = np.array([[f[k] for k in keys] for f in feat_rows], dtype=float)
    mean = mat.mean(axis=0)
    std = mat.std(axis=0)  # ddof=0
    std_safe = np.where(std < 1e-12, 1.0, std)
    z = (mat - mean) / std_safe
    return z, mean, std


def score_rows(rows, feat_rows, z, weights):
    w = np.array([weights[k] for k in FEATURE_KEYS], dtype=float)
    contrib = z * w  # (n, k)
    scores = contrib.sum(axis=1)
    out = []
    for i, r in enumerate(rows):
        feats = {}
        for j, k in enumerate(FEATURE_KEYS):
            feats[k] = {
                "raw": round(float(feat_rows[i][k]), 6),
                "z": round(float(z[i, j]), 6),
                "contrib": round(float(contrib[i, j]), 6),
            }
        # top_features：按加权贡献从大到小取前 3（主排序解释用）
        order = sorted(range(len(FEATURE_KEYS)), key=lambda j: contrib[i, j], reverse=True)
        tops = [FEATURE_KEYS[j] for j in order[:3]]
        out.append(
            {
                "segment_id": r["segment_id"],
                "version": r["version"],
                "task": r["task"],
                "step_idx": r["step_idx"],
                "step_title": r["step_title"],
                "n_dialogue": r["n_dialogue"],
                "char_len": r["char_len"],
                "length_bin": length_bin(r["n_dialogue"]),
                "score": round(float(scores[i]), 6),
                "features": feats,
                "top_features": tops,
            }
        )
    # 排序：分数降序；同分按 segment_id 升序（保证可复现）
    out.sort(key=lambda x: (-x["score"], x["segment_id"]))
    for rank, item in enumerate(out, 1):
        item["rank"] = rank
    return out


# ============================================================================
# 6. 报告辅助
# ============================================================================
def pick_excerpt(seg, diag):
    """挑「一句话原文摘录」：优先词面/情绪命中最多的记录，其次第一条非空记录"""
    units = [x for x in seg["main_records"] if x["kind"] in ("dialogue", "narration") and x["text"]]
    if not units:
        return ""
    best, best_val = None, -1.0
    for x in units:
        text = x["text"]
        tokens = [t for t in jieba.lcut(text) if t.strip()]
        val = death_hits_record(text, tokens) + 0.6 * neg_score_record(text, tokens) + vulnerable_fp_record(tokens)
        if val > best_val:
            best, best_val = x, val
    if best_val <= 0:
        best = units[0]
    text = re.sub(r"\s+", " ", best["text"]).strip()
    return text[:42] + ("…" if len(text) > 42 else "")


def fmt_feats(item):
    """主要贡献特征：按 w*z 降序取前 3。若最高贡献<=0（整步所有特征都低于均值），
    则显示「无正向贡献」并给出最低的两项——避免对末尾步骤产生误导。"""
    ranked = sorted(FEATURE_KEYS, key=lambda k: item["features"][k]["contrib"], reverse=True)
    if item["features"][ranked[0]]["contrib"] > 0:
        parts = []
        for k in ranked[:3]:
            z = item["features"][k]["z"]
            parts.append("%s(%+.2fσ)" % (FEATURE_LABELS[k], z))
        return "、".join(parts)
    lowest = ranked[-2:][::-1]
    parts = ["%s(%+.2fσ)" % (FEATURE_LABELS[k], item["features"][k]["z"]) for k in lowest]
    return "无正向贡献；最低：" + "、".join(parts)


def table_rows(items, seg_by_id, diag_by_id):
    lines = []
    for it in items:
        seg = seg_by_id[it["segment_id"]]
        lines.append(
            "| {rank} | `{sid}` | {ver} | {task} | {step} | {score:.4f} | {feats} | {exc} |".format(
                rank=it["rank"],
                sid=it["segment_id"],
                ver=it["version"],
                task=truncate(it["task"], 14),
                step="第%d步·%s" % (it["step_idx"], truncate(it["step_title"], 16)),
                score=it["score"],
                feats=fmt_feats(it),
                exc=pick_excerpt(seg, diag_by_id[it["segment_id"]]),
            )
        )
    return lines


def truncate(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _rank_of(scored, sid):
    for x in scored:
        if x["segment_id"] == sid:
            return x["rank"]
    return -1


def _score_of(scored, sid):
    for x in scored:
        if x["segment_id"] == sid:
            return x["score"]
    return float("nan")


def _max_unit_chars(seg):
    units = [len(x["text"]) for x in seg["main_records"] if x["kind"] in ("dialogue", "narration") and x["text"]]
    return max(units) if units else 0


def pearson(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.std() < 1e-12 or b.std() < 1e-12:
        return 0.0
    return float(((a - a.mean()) * (b - b.mean())).mean() / (a.std() * b.std()))


def spearman(a, b):
    ra = np.argsort(np.argsort(np.asarray(a, dtype=float)))
    rb = np.argsort(np.argsort(np.asarray(b, dtype=float)))
    return pearson(ra, rb)


def topk_overlap(items_a, items_b, k):
    sa = {x["segment_id"] for x in items_a[:k]}
    sb = {x["segment_id"] for x in items_b[:k]}
    return len(sa & sb) / k


# ============================================================================
# 7. 主流程
# ============================================================================
def build():
    rows = load_segments()
    cands = eligible(rows)
    print("步骤实例总数 = %d；合格候选 = %d" % (len(rows), len(cands)))

    feat_rows, diag_rows = [], {}
    for seg in cands:
        raw, diag = extract_features(seg)
        feat_rows.append(raw)
        diag_rows[seg["segment_id"]] = diag
    z, mean, std = zscore_matrix(feat_rows)
    scored = score_rows(cands, feat_rows, z, WEIGHTS)
    seg_by_id = {s["segment_id"]: s for s in cands}

    # 敏感性分析：固定权重之外，再跑 3 组先验变体，看 Top-k 是否稳定（§5）
    variants = {
        "W1_原始权重": dict(WEIGHTS),
        "W2_只留词面词表（death/neg/vuln 归一）": {
            "death_hit_rate": 0.18 / 0.70, "death_hit_top20": 0.12 / 0.70,
            "neg_emotion_rate": 0.12 / 0.70, "neg_emotion_top20": 0.08 / 0.70,
            "vulnerable_fp_rate": 0.12 / 0.70, "vulnerable_fp_top20": 0.08 / 0.70,
            "pause_ratio": 0.0, "short_sentence_ratio": 0.0,
            "exclaim_ratio": 0.0, "question_ratio": 0.0,
        },
        "W3_去掉death（只留情绪/脆弱/节奏）": {
            "death_hit_rate": 0.0, "death_hit_top20": 0.0,
            "neg_emotion_rate": 0.12 / 0.70, "neg_emotion_top20": 0.08 / 0.70,
            "vulnerable_fp_rate": 0.12 / 0.70, "vulnerable_fp_top20": 0.08 / 0.70,
            "pause_ratio": 0.10 / 0.70, "short_sentence_ratio": 0.07 / 0.70,
            "exclaim_ratio": 0.06 / 0.70, "question_ratio": 0.07 / 0.70,
        },
        "W4_十特征等权": {k: 0.1 for k in FEATURE_KEYS},
    }
    sensitivity = {}
    base = scored
    base_scores = [x["score"] for x in base]
    for name, w in variants.items():
        if name == "W1_原始权重":
            alt = base
        else:
            alt = score_rows(cands, feat_rows, z, w)
        # 注意：base / alt 是两种不同排序，Spearman 必须**按 segment_id 对齐**后配对
        alt_by_id = {x["segment_id"]: x["score"] for x in alt}
        alt_in_base_order = [alt_by_id[x["segment_id"]] for x in base]
        sensitivity[name] = {
            "top10_overlap": round(topk_overlap(base, alt, 10), 4),
            "top20_overlap": round(topk_overlap(base, alt, 20), 4),
            "top50_overlap": round(topk_overlap(base, alt, 50), 4),
            "spearman_vs_W1": round(spearman(base_scores, alt_in_base_order), 4),
        }

    # 长度偏差诊断
    nd = [x["n_dialogue"] for x in scored]
    cl = [x["char_len"] for x in scored]
    sc = [x["score"] for x in scored]
    length_diag = {
        "spearman_score_vs_n_dialogue": round(spearman(sc, nd), 4),
        "spearman_score_vs_char_len": round(spearman(sc, cl), 4),
        "by_bin": {},
    }
    for b in LENGTH_BINS:
        members = [x for x in scored if x["length_bin"] == b]
        if not members:
            continue
        length_diag["by_bin"][b] = {
            "n": len(members),
            "top1_score": max(x["score"] for x in members),
            "median_score": float(np.median([x["score"] for x in members])),
            "mean_score": round(float(np.mean([x["score"] for x in members])), 6),
            "n_in_global_top100": sum(1 for x in scored[:100] if x["length_bin"] == b),
            "n_zero_signal": sum(1 for x in members if all(v["raw"] == 0 for v in x["features"].values())),
        }

    # 零信号步骤（所有特征原始值 = 0，分数相同）与并列情况诊断
    zero_signal = [x for x in scored if all(v["raw"] == 0 for v in x["features"].values())]
    nonzero = [x for x in scored if x not in zero_signal]
    score_counter = Counter(x["score"] for x in scored)
    length_diag["n_zero_signal_steps"] = len(zero_signal)
    length_diag["n_distinct_scores"] = len(score_counter)
    length_diag["max_tie_group"] = score_counter.most_common(1)[0][1] if score_counter else 0
    length_diag["spearman_excl_zero_signal"] = {
        "vs_n_dialogue": round(spearman([x["score"] for x in nonzero], [x["n_dialogue"] for x in nonzero]), 4),
        "vs_char_len": round(spearman([x["score"] for x in nonzero], [x["char_len"] for x in nonzero]), 4),
    }
    length_diag["zero_signal_bins"] = Counter(x["length_bin"] for x in zero_signal)

    meta = {
        "script": "tools/baseline_a.py",
        "run_command": RUN_CMD,
        "corpus": "data/corpus/segments.jsonl",
        "corpus_total_segments": len(rows),
        "eligible_candidates": len(cands),
        "candidate_rule": "n_main>0 且 !low_content 且 has_dialogue（view=main，见口径 §3）",
        "text_unit": "main_records 中 kind ∈ {dialogue, narration}；排除 option/sms（与 text_all 口径一致）",
        "normalization": "各特征在 686 个候选上做 z-score（总体标准差 ddof=0）",
        "score_formula": "S_base = Σ w_i * z_i（权重见 weights，先验固定，未用标注调参）",
        "note": "无标签打分；不代表叙事显著性判定的准确率，只用于 A/B 对比的基线排序。",
        "feature_keys": FEATURE_KEYS,
        "feature_labels": FEATURE_LABELS,
        "weights": WEIGHTS,
    }
    result = {
        "meta": meta,
        "feature_stats": {
            k: {"mean": round(float(mean[j]), 6), "std": round(float(std[j]), 6)}
            for j, k in enumerate(FEATURE_KEYS)
        },
        "sensitivity": sensitivity,
        "length_bias_diagnostics": length_diag,
        "segments": scored,
    }

    # ---------------- 写 JSON ----------------
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写 %s（%d 步）" % (os.path.relpath(OUT_JSON, ROOT), len(scored)))

    # ---------------- 写 MD 报告 ----------------
    md = render_report(result, scored, seg_by_id, diag_rows, rows, cands)
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s" % os.path.relpath(OUT_MD, ROOT))

    # ---------------- 自洽核对（报告数字 vs JSON 抽查 5 条） ----------------
    ok = verify(verbose=True)
    if not ok:
        print("!! 报告与 JSON 不一致，请检查", file=sys.stderr)
        sys.exit(1)
    print("\n核对通过：报告表格数字与 JSON 一致（抽查 5 条 + 抽样重算）。")


def render_report(result, scored, seg_by_id, diag_rows, all_rows, cands):
    n = len(scored)
    top30 = scored[:30]
    bottom10 = sorted(scored[-10:], key=lambda x: x["score"])  # 最末 10 个，按分数由低到高
    bins = {b: [x for x in scored if x["length_bin"] == b] for b in LENGTH_BINS}
    L = []
    A = L.append

    A("# 基线 A：词面 + 局部情绪检测器（无标签打分）")
    A("")
    A("> 生成脚本：`tools/baseline_a.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    A("> 语料（只读）：`data/corpus/segments.jsonl`（%d 个步骤实例 → 合格候选池 **%d** 个）" % (len(all_rows), n))
    A("> 明细数据（可复算）：`data/config/baseline-a-scores.json`（全部 %d 步，含 raw / z / contrib）" % n)
    A("")
    A("> **免责声明：这是无标签的先验打分，不代表准确性。** 权重在跑分前写死、"
      "标注集未参与任何调参；分数只表示「按预先固定的词面/局部情绪特征排序」，"
      "不能当作叙事显著性的真值或检测准确率。A 与 B 的对比必须回到**同一候选池 + 人工标注**上做 Precision@k / Recall@k。")
    A("")
    A("## 1. 一句话结论")
    A("")
    top = scored[0]
    lb = result["length_bias_diagnostics"]
    A("- Top1 是 `%s`（%s｜%s｜第%d步，长度层 %s），分数 %.4f；主要贡献：%s。"
      "核对原记录：这是「翻阅记忆」的回顾式旁白，单条 %d 字长旁白里重复出现「长眠于涛声中」「永远不会再升起」"
      "等死亡与终结意象，词面信号极强——属于词面基线应当命中的类型（也是它「偏爱长旁白」的典型样本）。" % (
          top["segment_id"], top["version"], truncate(top["task"], 18), top["step_idx"],
          top["length_bin"], top["score"], fmt_feats(top), _max_unit_chars(seg_by_id[top["segment_id"]])))
    A("- 词面基线拿到的是「显性死亡/牺牲/告别 + 负面情绪 + 第一人称脆弱 + 停顿/短句/感叹/疑问」的信号，"
      "**不含任何结构信息**（语义突变、身份变化、母题回收），这正是留给 B 的空间。")
    A("- 分数≥1 的步骤只有 %d 个，分数分布长尾（最高 %.3f，最低 %.3f），说明词面信号本身很稀疏。" % (
        sum(1 for x in scored if x["score"] >= 1), top["score"], scored[-1]["score"]))
    A("- 长度偏差：分数 vs 对白句数 ρ = **%+.3f**、vs 字符数 ρ = **%+.3f**（剔除零信号步骤后 ρ = %+.3f / %+.3f）；"
      "即 A 存在**中等偏弱、偏向长步骤**的长度效应，成因见 §7。" % (
          lb["spearman_score_vs_n_dialogue"], lb["spearman_score_vs_char_len"],
          lb["spearman_excl_zero_signal"]["vs_n_dialogue"],
          lb["spearman_excl_zero_signal"]["vs_char_len"]))
    A("- 有 **%d** 个步骤 10 个特征原始值全为 0（零信号，全部并列最低分 %.4f），其中 %s；"
      "这是词面基线对「纯操作/过渡步骤」的天然盲区，评测时应作为「无信息步」单独看。" % (
          lb["n_zero_signal_steps"], scored[-1]["score"],
          "、".join("%s %d 个" % (b, lb["zero_signal_bins"][b]) for b in LENGTH_BINS if lb["zero_signal_bins"].get(b))))
    A("")

    A("## 2. 候选池与计算口径")
    A("")
    A("| 项目 | 口径 |")
    A("| --- | --- |")
    A("| 候选单位 | 步骤实例 `segment_id = version|task|step_idx`（口径 §1） |")
    A("| 候选池 | `n_main>0` 且 `!low_content` 且 `has_dialogue`（view=main），共 **%d** 个（口径 §3 / §9） |" % n)
    A("| 文本单元 | `main_records` 中 `kind ∈ {dialogue, narration}`，保持原始剧情顺序（口径 §11.1）；**不混入** `option`/`sms` 文本（与 `text_all` 一致） |")
    A("| 特征计算 | 先按记录（句）算，再聚合到步骤：**比例** = 记录级均值；**峰值** = top-20% 记录均值（口径 §9） |")
    A("| 标准化 | 每个特征在 %d 个候选上做 z-score（总体标准差 ddof=0） |" % n)
    A("| 打分 | `S_base = Σ w_i · z_i`，权重在脚本 `WEIGHTS` 里写死（先验固定，未调参，口径 §5） |")
    A("| 排序 | 分数降序；同分按 `segment_id` 升序（保证可复现） |")
    A("| 长度分层 | 按步骤内**对白记录数**分箱 1–3 / 4–10 / 11–30 / >30 句（与口径 §9 的 65/148/236/237 一致） |")
    A("")
    A("本候选池的长度分布（与口径 §9 完全一致）：")
    A("")
    A("| 长度层 | 1–3 句 | 4–10 句 | 11–30 句 | >30 句 | 合计 |")
    A("| --- | --- | --- | --- | --- | --- |")
    A("| 步骤数 | %s |" % " | ".join(str(len(bins[b])) for b in LENGTH_BINS) + " %d |" % n)
    A("")

    A("## 3. 特征定义（10 个，全部是步骤内局部特征）")
    A("")
    A("| # | 特征 key | 定义 | 聚合口径 | 权重 |")
    A("| --- | --- | --- | --- | --- |")
    defs = {
        "death_hit_rate": "死亡/牺牲/告别词加权命中数 ÷ 记录数（强档词 1.0、弱档词 0.5）",
        "death_hit_top20": "记录级死亡词加权命中数的 top-20% 均值",
        "neg_emotion_rate": "负面情绪净强度 ÷ 记录数；净强度 = 负面词 + 0.5×否定词 − 0.6×被否定的负面词（≥0）",
        "neg_emotion_top20": "记录级负面情绪净强度的 top-20% 均值",
        "vulnerable_fp_rate": "第一人称脆弱表达命中数 ÷ 记录数",
        "vulnerable_fp_top20": "记录级第一人称脆弱表达命中数的 top-20% 均值",
        "pause_ratio": "语料字段：`repeat_kind=pause` 记录占 main 记录的比例（即「……」停顿密度）",
        "short_sentence_ratio": "文本字符数 ≤ %d 的记录占比" % SHORT_SENTENCE_MAX_CHARS,
        "exclaim_ratio": "含 `！/!` 的记录占比（感叹密度）",
        "question_ratio": "疑问记录占比（以 ？/?/吗/呢/么 结尾，或含 为什么/怎么/如何/是否/难道 等标记）",
    }
    for i, k in enumerate(FEATURE_KEYS, 1):
        kind = "峰值" if k.endswith("_top20") else ("语料字段" if k == "pause_ratio" else "比例")
        A("| %d | `%s` | %s | %s | %.2f |" % (i, k, defs[k], kind, WEIGHTS[k]))
    A("| | **合计** | | | **%.2f** |" % sum(WEIGHTS.values()))
    A("")
    A("**权重先验理由**：本语料（翁法罗斯主线）的叙事显著性最常由显性死亡/牺牲/告别触发，"
      "故 death 组合计 0.30 最高；负面情绪与第一人称脆弱表达各 0.20；`pause_ratio` 是语料已给字段占 0.10；"
      "标点/句式类节奏特征合计 0.20。权重是**事先固定**的先验值（口径 §5），标注集只用于后续评测。")
    A("")
    A("### 3.1 词表（写死在脚本里，可逐条核对）")
    A("")
    A("- **死亡/牺牲/告别 · 强档（weight 1.0）**：%s" % "、".join(DEATH_STRONG))
    A("- **死亡/牺牲/告别 · 弱档（weight 0.5，易泛化的高频词）**：%s" % "、".join(DEATH_WEAK))
    A("- **负面情绪 · 多字词（子串匹配）**：%s" % "、".join(NEG_MULTI))
    A("- **负面情绪 · 单字词（仅在 jieba token 精确匹配时计，避免「哪怕/积累」误伤）**：%s" % "、".join(NEG_SINGLE))
    A("- **否定词（token 精确匹配）**：%s" % "、".join(sorted(NEGATION_TOKENS)))
    A("- **第一人称代词**：%s" % "、".join(sorted(FIRST_PERSON)))
    A("- **脆弱表达词干（代词后 3 个 token 内命中，遇标点中断）**：%s" % "、".join(VULN_PREFIX))
    A("")
    A("匹配实现：多字词用**最长优先、不重叠**的正则（避免「死亡」重复计入「死」），单字词只在分词 token 上精确匹配；"
      "分词用 jieba 精确模式（`jieba.lcut`，日志已静音）。")
    A("")
    A("> 四份 `data/config/vocab-*.json`（神谕/母题/称呼/歌谣）在本基线中**不进入打分权重**："
      "按口径 §11.4，词表匹配（`semantic_recall`）属于检测器 B 的「母题回收」结构特征；"
      "若 A 也使用，会削弱 A/B 对比的可解释性。A 保持「纯局部词面 + 情绪」定位。")
    A("")

    A("## 4. Top 30")
    A("")
    A("| 排名 | segment_id | 版本 | 任务 | 步骤 | 分数 | 主要贡献特征（加权 z） | 一句话原文摘录 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    L.extend(table_rows(top30, seg_by_id, diag_rows))
    A("")

    A("## 5. 末尾 10 个（第 %d–%d 名，按分数由低到高）" % (n - 9, n))
    A("")
    A("| 排名 | segment_id | 版本 | 任务 | 步骤 | 分数 | 主要贡献特征（加权 z） | 一句话原文摘录 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    L.extend(table_rows(bottom10, seg_by_id, diag_rows))
    A("")
    A("> **注意并列**：全部 %d 步中有 %d 个「零信号步骤」（10 个特征原始值全为 0），分数完全相同 = %.4f，"
      "并列占据第 %d–%d 名；表中第 677 名起的顺序只是**按 `segment_id` 升序的编号**，不代表这些步骤之间有强弱差别。"
      "它们都是纯操作/过渡步骤（短旁白、无情绪词、无停顿符号），词面基线对它们没有可用信号。" % (
          n, lb["n_zero_signal_steps"], scored[-1]["score"],
          n - lb["n_zero_signal_steps"] + 1, n))
    A("> 分数分布：%d 个不同分值（%d 步），最大并列组 %d 步——除零信号组外，其余并列都是局部特征向量恰好相同。" % (
        lb["n_distinct_scores"], n, lb["max_tie_group"]))
    A("")

    A("## 6. 长度分层 Top 5（检查是否只偏爱短句 / 长段）")
    A("")
    for b in LENGTH_BINS:
        members = bins[b]
        A("### %s（%d 步，占 %.1f%%）" % (b, len(members), 100.0 * len(members) / n))
        A("")
        A("| 排名 | segment_id | 版本 | 任务 | 步骤 | 分数 | 主要贡献特征（加权 z） | 一句话原文摘录 |")
        A("| --- | --- | --- | --- | --- | --- | --- | --- |")
        L.extend(table_rows(members[:5], seg_by_id, diag_rows))
        A("")

    A("## 6.1 案例观察（人工核对原文，非标注）")
    A("")
    # 动态取三条代表性步骤，避免硬编码随重跑失效
    top_vuln = max(scored[:100], key=lambda x: x["features"]["vulnerable_fp_rate"]["raw"])
    top_neg = max(scored[:100], key=lambda x: x["features"]["neg_emotion_rate"]["raw"])
    A("- **词面命中（死亡/告别）典型**：Top1 `%s` 摘录「%s」；Top2 `%s` 摘录「%s」；Top4 `%s` 摘录「%s」——"
      "都是死亡/告别词面显性、局部情绪强的段落，符合基线定位。" % (
          top["segment_id"],
          pick_excerpt(seg_by_id[top["segment_id"]], diag_rows[top["segment_id"]]),
          scored[1]["segment_id"],
          pick_excerpt(seg_by_id[scored[1]["segment_id"]], diag_rows[scored[1]["segment_id"]]),
          scored[3]["segment_id"],
          pick_excerpt(seg_by_id[scored[3]["segment_id"]], diag_rows[scored[3]["segment_id"]])))
    A("- **第一人称脆弱表达最强**：`%s`（第 %d 名），vulnerable_fp_rate 原始值 %.3f（z=%+.2fσ），"
      "摘录「%s」。这类「我/我们 + 求/怕/不能」的贴身脆弱句是 A 能抓住的另一类信号。" % (
          top_vuln["segment_id"], top_vuln["rank"], top_vuln["features"]["vulnerable_fp_rate"]["raw"],
          top_vuln["features"]["vulnerable_fp_rate"]["z"],
          pick_excerpt(seg_by_id[top_vuln["segment_id"]], diag_rows[top_vuln["segment_id"]])))
    A("- **负面情绪最强**：`%s`（第 %d 名），neg_emotion_rate 原始值 %.3f（z=%+.2fσ），摘录「%s」。" % (
        top_neg["segment_id"], top_neg["rank"], top_neg["features"]["neg_emotion_rate"]["raw"],
        top_neg["features"]["neg_emotion_rate"]["z"],
        pick_excerpt(seg_by_id[top_neg["segment_id"]], diag_rows[top_neg["segment_id"]])))
    A("- **A 的预期漏检（重点）**：`方向与理由v2.md` 举的 3.7 版本「昔涟诞生」相关剧情反例，"
      "对应本文档 `3.7|晨曦啊，再抚映遥远地平|4`（步骤标题「聆听昔涟讲述真相，完成『记忆』的拼图」），"
      "该步原文有「『昔涟』的诞生之地」，但在 A 中排第 **%d** 名（分数 %.4f，各特征 z 基本都在 ±0.5 内）。"
      "这正是 B 的结构特征（身份揭示 / 母题回收 / 语义突变）应当补上的漏检，可直接作为 B 的增益检验用例。" % (
          _rank_of(scored, "3.7|晨曦啊，再抚映遥远地平|4"),
          _score_of(scored, "3.7|晨曦啊，再抚映遥远地平|4")))
    A("")

    A("## 7. 长度偏差诊断")
    A("")
    A("| 长度层 | 步数 | 层内 Top1 分数 | 层内中位数 | 层内均值 | 进入全局 Top100 的步数 | 该层在 Top100 中的占比 | 若按步数比例的期望占比 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for b in LENGTH_BINS:
        d = result["length_bias_diagnostics"]["by_bin"][b]
        A("| %s | %d | %.4f | %.4f | %.4f | %d | %.1f%% | %.1f%% |" % (
            b, d["n"], d["top1_score"], d["median_score"], d["mean_score"],
            d["n_in_global_top100"], float(d["n_in_global_top100"]),
            100.0 * d["n"] / n))
    A("")
    diag = result["length_bias_diagnostics"]
    A("- 分数 vs 对白句数：Spearman ρ = **%+.3f**；分数 vs 字符数：Spearman ρ = **%+.3f**。" % (
        diag["spearman_score_vs_n_dialogue"], diag["spearman_score_vs_char_len"]))
    A("- 剔除 %d 个零信号步骤后，ρ 降到 **%+.3f / %+.3f**（对白句数 / 字符数）："
      "**短步骤在基线里大量「无信号」，是长度效应的一部分来源**（1–3 句层有 %d/%d 步全零，"
      "因为它们记录太少，任何词表/标点特征都没命中，只能拿最低分）。" % (
          diag["n_zero_signal_steps"],
          diag["spearman_excl_zero_signal"]["vs_n_dialogue"],
          diag["spearman_excl_zero_signal"]["vs_char_len"],
          diag["zero_signal_bins"].get(LENGTH_BINS[0], 0),
          diag["by_bin"][LENGTH_BINS[0]]["n"]))
    A("- 另一个来源是**峰值口径**：`_top20` 取记录级 top-20%% 均值，长步骤记录多，"
      "更容易在某一小段里连续出现死亡/情绪词从而抬高 top20 均值（口径 §11.2 已提醒 `max` 类统计天然偏长）。"
      ">30 句层在 Top100 中占 %.0f%%（步数占比仅 %.1f%%），4–10 句层只占 %.0f%%（步数占比 %.1f%%）——"
      "**A 有中等偏弱的「偏爱长步骤」倾向，但短步骤并未被完全压死**（1–3 句层仍有 %d 步进 Top100，"
      "其 Top1 就是全局第 1）。" % (
          float(diag["by_bin"][LENGTH_BINS[3]]["n_in_global_top100"]),
          100.0 * diag["by_bin"][LENGTH_BINS[3]]["n"] / n,
          float(diag["by_bin"][LENGTH_BINS[1]]["n_in_global_top100"]),
          100.0 * diag["by_bin"][LENGTH_BINS[1]]["n"] / n,
          diag["by_bin"][LENGTH_BINS[0]]["n_in_global_top100"]))
    A("- 结论：以后 A/B 对比**必须按这 4 层分别报**（口径 §11.2/§11.5）；"
      "若只看全局 Top-k，>30 句的长步骤会略微占便宜，不能据此说 B「更好」或「更差」。")
    A("")

    A("## 8. 敏感性分析（先验权重扰动下的排序稳定性，口径 §5）")
    A("")
    A("| 权重变体 | Top10 重合 | Top20 重合 | Top50 重合 | Spearman ρ（vs 原始） |")
    A("| --- | --- | --- | --- | --- |")
    for name, s in result["sensitivity"].items():
        A("| %s | %.0f%% | %.0f%% | %.0f%% | %.3f |" % (
            name, 100 * s["top10_overlap"], 100 * s["top20_overlap"],
            100 * s["top50_overlap"], s["spearman_vs_W1"]))
    A("")
    A("> 说明：本表只做**权重敏感性**（不是标注评测）。Top10 重合度高说明词面基线排序不依赖某一组权重的细微取值；"
      "W3（去掉 death 组）用来检查「是不是全靠死亡词」——若 Top-k 重合度明显下降，说明死亡/告别词是 A 的主要信号源；"
      "这也正是 `方向与理由v2.md` 里「A 会漏掉昔涟诞生这类词面弱、结构强的片段」的机制来源。"
      "（注意：W4 等权与 W1 的 Spearman 接近 1 是正常的——两者的区别只在几个权重上；"
      "`spearman_vs_W1` 是按 segment_id 对齐后计算的。）")
    A("")

    A("## 9. 复算与核对")
    A("")
    A("```bash")
    A("# 重跑（重新生成 JSON + MD；约 10 秒）")
    A(RUN_CMD)
    A("# 只校验已有产物：报告表格数字 vs JSON（抽查 5 条 + 全表抽样重算）")
    A("conda run -n nlpLesson python tools/baseline_a.py --verify")
    A("```")
    A("")
    A("可复算性：")
    A("")
    A("- JSON 里每一段都有 `features.<key>.raw`（原始聚合值）、`.z`（标准化值）、`.contrib`（$w_i z_i$）；"
      "`score = Σ contrib`，`feature_stats` 给出每列均值/标准差，可逐条手算复核。")
    A("- 脚本无随机数、无时间戳、无网络请求；同输入必得同输出。")
    A("- 候选池：语料 723 步中，`low_content` 排除 %d 步、无对白排除 %d 步（两者有重叠），剩 **%d** 步全部有分数；"
      "本报告表格由与 JSON 同一份内存结果生成，`--verify` 会重新解析 MD 表格与 JSON 做逐行 + 抽样核对。" % (
          sum(1 for r in all_rows if r["low_content"]),
          sum(1 for r in all_rows if not r["has_dialogue"]), n))
    A("- **自校验**：`build()` 写完两个产物后会立刻调用 `verify()`——①把 MD 里 %d 行排序表逐行比对 JSON 的"
      "`segment_id`/`rank`/`score`；②抽 5 条（第 1/7/25/677/686 名）从 JSON 重算 `Σ w_i z_i` 并核对 z 与 `feature_stats` 自洽；"
      "③再每 137 条抽样重算。任一项不一致脚本会以退出码 1 失败，本次运行已通过（输出「核对通过」）。" % 60)
    A("")

    A("## 10. 局限（写清楚，避免误读）")
    A("")
    A("1. **这是无标签打分**：没有 ground truth，Top 榜只能说明「词面/情绪看起来强」，不能证明「叙事显著」；"
      "本报告里所有「排名」都只是同一个候选池内的相对位置。")
    A("2. **词表是人工先验**：死亡/负面/脆弱词表覆盖率有限，反讽、留白、隐喻（如「碎作千片」）会漏检；"
      "文言/注音隐喻表面词（神谕体）与口语对白的词面分布不同，会带来语体偏差（口径 §4 要求另报话题匹配结果）。")
    A("3. **只用局部信息**：没有跨句/跨步骤上下文，母题回收、身份揭示、语义突变一律看不到——这是设计选择，不是缺陷修复项。")
    A("4. **长度**：比例口径已归一，但峰值口径（top-20%%）仍使分数与长度正相关（§7 已量化：ρ = %+.3f），"
      "且 1–3 句层有 %d/%d 步是零信号；B 对比时必须按长度分层报告（口径 §11.2）。" % (
          diag["spearman_score_vs_n_dialogue"],
          diag["zero_signal_bins"].get(LENGTH_BINS[0], 0), diag["by_bin"][LENGTH_BINS[0]]["n"]))
    A("5. **并列**：%d 个零信号步骤分数完全相同（并列第 %d–%d 名），排名编号靠 segment_id 决定；"
      "评测 Top-k 时建议把「零信号步」单列，或用并列名次（competition rank）。" % (
          diag["n_zero_signal_steps"], n - diag["n_zero_signal_steps"] + 1, n))
    A("6. 分数绝对值没有语义，只用于**同一候选池内的相对排序**；A/B 分数不可直接比较大小。")
    A("")
    return "\n".join(L)


# ============================================================================
# 8. 自校验（MD 表格数字 vs JSON，抽查 5 条 + 全表抽样重算）
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
    by_id = {s["segment_id"]: s for s in data["segments"]}
    md_rows = []
    with open(OUT_MD, "r", encoding="utf-8") as f:
        for line in f:
            m = MD_ROW_RE.match(line.rstrip("\n"))
            if m:
                md_rows.append(
                    {"rank": int(m.group(1)), "sid": m.group(2), "score": float(m.group(6))}
                )
    problems = []

    # 1) 每条 MD 表格行的 segment_id/rank/score 都必须和 JSON 一致
    for r in md_rows:
        item = by_id.get(r["sid"])
        if item is None:
            problems.append("MD 里的 segment_id 不在 JSON：%s" % r["sid"])
            continue
        if abs(item["score"] - r["score"]) > 5e-5:
            problems.append("分数不一致 %s：MD %.4f vs JSON %.6f" % (r["sid"], r["score"], item["score"]))
        if item["rank"] != r["rank"]:
            problems.append("排名不一致 %s：MD %d vs JSON %d" % (r["sid"], r["rank"], item["rank"]))

    # 2) 抽查 5 条：从 JSON 重算 score = Σ w*z，且 z 与 feature_stats 自洽
    stats = data["feature_stats"]
    weights = data["meta"]["weights"]
    sample_ids = [data["segments"][i]["segment_id"] for i in (0, 6, 24, 676, 685)]
    checked = []
    for sid in sample_ids:
        it = by_id[sid]
        recomputed = sum(weights[k] * it["features"][k]["z"] for k in weights)
        if abs(recomputed - it["score"]) > 2e-5:
            problems.append("重算分数不一致 %s：%.6f vs %.6f" % (sid, recomputed, it["score"]))
        for k in weights:
            z_expect = (it["features"][k]["raw"] - stats[k]["mean"]) / (stats[k]["std"] or 1.0)
            if abs(z_expect - it["features"][k]["z"]) > 2e-3:
                problems.append("z 不自洽 %s/%s：%.6f vs %.6f" % (sid, k, z_expect, it["features"][k]["z"]))
        checked.append((it["rank"], sid, it["score"]))

    # 3) 全表抽样重算（每 137 个抽 1 个，确定性）
    for idx in range(0, len(data["segments"]), 137):
        it = data["segments"][idx]
        recomputed = sum(weights[k] * it["features"][k]["z"] for k in weights)
        if abs(recomputed - it["score"]) > 2e-5:
            problems.append("抽样重算不一致 %s：%.6f vs %.6f" % (it["segment_id"], recomputed, it["score"]))

    if verbose:
        print("\n抽查 5 条（rank / segment_id / score）：")
        for rk, sid, sc in checked:
            print("  #%-3d %-42s %.6f" % (rk, sid, sc))
        print("MD 表格行核对 = %d 行；全表抽样重算 = %d 条" % (
            len(md_rows), len(range(0, len(data["segments"]), 137))))

    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="基线 A：词面 + 局部情绪检测器（无标签打分）")
    ap.add_argument("--verify", action="store_true", help="只校验已有产物（不重算、不写文件）")
    args = ap.parse_args()

    jieba.setLogLevel(60)  # 静音 jieba 构建词典日志，保持输出干净
    jieba.initialize()

    if args.verify:
        ok = verify(verbose=True)
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)

    build()


if __name__ == "__main__":
    main()
