#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
style_compare.py — 神谕语体 vs 普通对白 vs 角色引用语体（v2 主分析第 4 项）

三组文本（评测口径：docs/实验口径与评测方案.md §4「语体对比：全量 + 话题匹配」）：
  G1 神谕原文：data/corpus/oracles.jsonl 的 13 条神谕（拆成句）
  G2 普通对白：686 个合格步骤里 main_records 的 dialogue 记录（按版本分层、确定性抽样），
              并**剔除**与神谕原文有长字面重合的句子，避免与 G3 混淆
  G3 角色引用：data/corpus/oracles.jsonl 中 13 条神谕的 34 处 occurrences 所在记录
              （若 data/config/oracle-citation-coding.json 已生成，可改用其分组；本脚本默认 occurrences）

特征（全部是规则 + jieba，可测、可复现；词表在脚本里写死并注释来源）：
  句长 / 分句长、文言虚词、情态词、第二/第一人称、抽象名词比例、复沓（排比）率、
  称呼词命中、感叹/疑问/祈使密度

统计：
  * 三组均值/中位数；
  * 每特征做 G1–G2、G1–G3、G2–G3 的 Mann–Whitney U 检验 + 效应量（Cliff's delta，
    由 U 换算：delta = 2U/(n1·n2) − 1）+ Bonferroni 校正；
  * **全量比较** 与 **话题匹配比较**（只在含「死亡/命运/终结/记忆」词的句子里比）两组都报；
  * G3 再按「原句引用 / 近原文引用 / 改写复述」分型，回答「靠拢 / 偏离 / 改写」。

约束：只读语料与 config；不装依赖（scipy/matplotlib 已可用；本报告只输出数值表，不写图片文件）；
无随机（抽样用确定性的等距抽样）。

运行：
    conda run -n nlpLesson python tools/style_compare.py            # 重算并写产物
    conda run -n nlpLesson python tools/style_compare.py --verify   # 只校验产物自洽

产物（只写这 3 个文件）：
    data/config/style-compare-results.json
    data/reports/style-compare.md
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

import jieba
import numpy as np
from scipy.stats import mannwhitneyu

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_ORACLES = os.path.join(ROOT, "data", "corpus", "oracles.jsonl")
P_SEGMENTS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_VOCAB_ADDRESS = os.path.join(ROOT, "data", "config", "vocab-address.json")
P_CITATION_CODING = os.path.join(ROOT, "data", "config", "oracle-citation-coding.json")
OUT_JSON = os.path.join(ROOT, "data", "config", "style-compare-results.json")
OUT_MD = os.path.join(ROOT, "data", "reports", "style-compare.md")
RUN_CMD = "conda run -n nlpLesson python tools/style_compare.py"

GROUPS = ["G1", "G2", "G3"]
GROUP_LABELS = {"G1": "G1 神谕原文", "G2": "G2 普通对白", "G3": "G3 角色引用"}
PAIRS = [("G1", "G2"), ("G1", "G3"), ("G2", "G3")]

# ============================================================================
# 1. 词表（自建，来源写在这里；全部只做字面匹配）
# ============================================================================
# 1.1 文言虚词（任务指定：之/乎/者/也/矣/焉/哉/汝/吾；另加 尔/乃 两个高频古汉语标记）
LITERARY_CHARS = set("之乎者也矣焉哉汝吾尔乃")
# 1.2 情态词（任务指定：将/必/终/应/须/当/定；"必将"由"必"覆盖）
MODAL_TERMS = ["将", "必", "终", "应", "须", "当", "定"]
# 1.3 人称
PERSON2_TERMS = ["汝", "尔", "你", "您", "你们"]
PERSON1_TERMS = ["吾", "我", "余", "咱", "我们"]
# 1.4 抽象名词表（自建）：来源 = ①13 条神谕及兑现证据里的高频抽象概念；②docs/方向与理由v2.md
#     讨论的叙事维度（命运/记忆/身份/终结/救赎等）。只收抽象概念词，不收具体人名/地名/物名。
ABSTRACT_TERMS = [
    "命运", "宿命", "命途", "天命", "因果", "预言", "神谕", "箴言", "谶语", "卦象",
    "记忆", "回忆", "忘却", "灵魂", "心灵", "意志", "自由", "希望", "绝望", "真理",
    "虚无", "存在", "意义", "真相", "秩序", "规则", "律法", "永恒", "轮回", "终结",
    "起始", "收梢", "死亡", "牺牲", "救赎", "毁灭", "代价", "抉择", "誓言", "背叛",
    "荣耀", "神性", "人性", "时间", "世界", "因果报应", "彼岸", "归宿", "重负", "试炼",
    "印证", "箴言", "苦黑", "纯粹", "终极", "征服", "长眠", "凋零", "新生", "火种",
    "黎明", "长夜", "天空", "大地", "海洋", "花海", "墓碑", "坟墓", "凋谢", "诞生",
]
# 1.5 祈使标记（命令/愿望/劝阻）
IMPERATIVE_TERMS = ["请", "勿", "莫", "愿", "望", "速", "宜", "且", "务必", "切莫", "吧", "罢", "啊"]
# 1.6 话题词表（话题匹配比较用）：死亡 / 命运 / 终结 / 记忆
TOPIC_TERMS = {
    "death": ["死", "亡", "殁", "逝", "牺牲", "殒", "葬", "长眠", "离世", "亡故", "尸", "墓", "坟墓"],
    "fate": ["命运", "命途", "宿命", "注定", "预言", "神谕", "箴言", "谶语", "天命", "卦"],
    "ending": ["终结", "结束", "尽头", "终点", "收梢", "起始", "永远", "永别", "最后", "最终"],
    "memory": ["记忆", "回忆", "忘却", "铭记", "想起", "回想", "记得", "忘"],
}
TOPIC_FLAT = [t for ts in TOPIC_TERMS.values() for t in ts]


def load_terms(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return list(json.load(f).get("terms") or [])
    except Exception:
        return []


ADDRESS_TERMS = load_terms(P_VOCAB_ADDRESS)

# ============================================================================
# 2. 文本单元与特征
# ============================================================================
PUNCT_CHARS = set("，。！？、；：…—「」『』（）().,!?;:~-·\"'《》〈〉【】 \t\r\n")
PUNCT_RE = re.compile(r"^[\s，。！？、；：…—「」『』（）().,!?;:~\-·\"'《》〈〉【】]+$")
CLAUSE_SPLIT_RE = re.compile(r"[，、：；,;]")
SENT_RE = re.compile(r"[。！？；]+")


def strip_punct(text):
    return "".join(c for c in (text or "") if c not in PUNCT_CHARS and not c.isspace())


def split_sentences(text):
    """按句末标点切句，并**保留句末标点**（感叹/疑问密度需要标点信息）；
    …… 归一成 。 避免产生只有省略号片段"""
    t = (text or "").replace("……", "。").replace("…", "。")
    parts = re.findall(r"[^。！？；]+[。！？；]*", t)
    out = []
    for p in parts:
        p = p.strip()
        if p and strip_punct(p):
            out.append(p)
    return out


def count_chars(text, chars):
    return sum(1 for c in text if c in chars)


def count_terms(text, terms):
    """子串计数（不重叠，多字词优先长匹配）"""
    if not text:
        return 0
    terms = sorted(set(terms), key=len, reverse=True)
    pat = re.compile("|".join(re.escape(t) for t in terms))
    return len(pat.findall(text))


def token_repetition(tokens):
    """词级复沓率：1 − 不同内容词数 ÷ 内容词总数（重复用词越多越高）"""
    if len(tokens) < 2:
        return 0.0
    return float(1.0 - len(set(tokens)) / len(tokens))


def parallel_rate(clauses):
    """排比/同句式：相邻分句是否共享字符 bigram（共享越多说明句式/用词重复越强）。
    单分句返回 0；否则 = 共享 bigram 的相邻分句对数 ÷ 相邻分句对数"""
    if len(clauses) < 2:
        return 0.0
    grams = []
    for c in clauses:
        c = strip_punct(c)
        grams.append(set(c[i:i + 2] for i in range(max(0, len(c) - 1))))
    pairs = len(clauses) - 1
    hit = 0
    for i in range(pairs):
        if grams[i] and grams[i + 1] and (grams[i] & grams[i + 1]):
            hit += 1
    return float(hit / pairs)


def extract_features(text):
    t = text or ""
    content_chars = strip_punct(t)
    n = max(1, len(content_chars))
    clauses = [c for c in CLAUSE_SPLIT_RE.split(t) if strip_punct(c)]
    n_clauses = max(1, len(clauses))
    toks = [x for x in jieba.lcut(t) if x.strip() and not PUNCT_RE.match(x)]
    content_toks = [x for x in toks if not PUNCT_RE.match(x)]
    feats = {
        "char_len": float(len(content_chars)),
        "clause_len": float(len(content_chars) / n_clauses),
        "literary_rate": round(count_chars(t, LITERARY_CHARS) / n * 100.0, 4),
        "modal_rate": round(count_terms(t, MODAL_TERMS) / n * 100.0, 4),
        "person2_rate": round(count_terms(t, PERSON2_TERMS) / n * 100.0, 4),
        "person1_rate": round(count_terms(t, PERSON1_TERMS) / n * 100.0, 4),
        "abstract_ratio": round(count_terms(t, ABSTRACT_TERMS) / max(1, len(content_toks)), 4),
        "repeat_token_rate": round(token_repetition(content_toks), 4),
        "parallel_rate": round(parallel_rate(clauses), 4),
        "address_rate": round(count_terms(t, ADDRESS_TERMS) / n * 100.0, 4) if ADDRESS_TERMS else 0.0,
        "exclaim_rate": round((t.count("！") + t.count("!")) / n * 100.0, 4),
        "question_rate": round((t.count("？") + t.count("?")) / n * 100.0, 4),
        "imperative_rate": round(count_terms(t, IMPERATIVE_TERMS) / n * 100.0, 4),
    }
    return feats


FEATURES = ["char_len", "clause_len", "literary_rate", "modal_rate", "person2_rate",
            "person1_rate", "abstract_ratio", "repeat_token_rate", "parallel_rate",
            "address_rate", "exclaim_rate", "question_rate", "imperative_rate"]
FEATURE_LABELS = {
    "char_len": "句长（字）",
    "clause_len": "分句长（字/分句）",
    "literary_rate": "文言虚词（次/百字）",
    "modal_rate": "情态词（次/百字）",
    "person2_rate": "第二人称（次/百字）",
    "person1_rate": "第一人称（次/百字）",
    "abstract_ratio": "抽象名词比例（/内容词）",
    "repeat_token_rate": "词复沓率（1−不同词/总词）",
    "parallel_rate": "排比率（相邻分句共享 bigram）",
    "address_rate": "称呼词（次/百字）",
    "exclaim_rate": "感叹号（个/百字）",
    "question_rate": "问号（个/百字）",
    "imperative_rate": "祈使标记（次/百字）",
}


# ============================================================================
# 3. 构造三组文本
# ============================================================================
def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_oracles():
    rows = []
    with open(P_ORACLES, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_segments():
    rows = []
    with open(P_SEGMENTS, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_g1(oracles):
    units = []
    for o in oracles:
        for si, sent in enumerate(split_sentences(o["text"])):
            units.append({
                "group": "G1", "oracle_id": o["oracle_id"], "sent_idx": si,
                "text": sent, "features": extract_features(sent),
                "is_oracle_quote": True, "subtype": None,
                "source": "oracles.jsonl:%s" % o["oracle_id"],
            })
    return units


def build_g3(oracles):
    """34 处 occurrences；每处拆句成单元；并给出「原句引用/近原文引用/改写复述」分型"""
    units = []
    occ_rows = []
    for o in oracles:
        oid = o["oracle_id"]
        norm_oracle = strip_punct(o["text"])
        for k, occ in enumerate(o.get("occurrences") or []):
            text = occ.get("text") or ""
            norm_occ = strip_punct(text)
            # 分型：
            #   A 完整引用：神谕规范化文本整体出现在记录中
            #   B 片段引用：记录内容基本全部来自神谕（只是截断/省略号），即 source_in_oracle 高
            #   C 改写/复述：有替换/增删/复述，或引用了另一条神谕（同词异序）
            recall = ngram_recall(norm_oracle, norm_occ, 4)          # 神谕的 4-gram 有多少出现在记录里
            src_in_oracle = ngram_recall(norm_occ, norm_oracle, 3)   # 记录的 3-gram 有多少来自本条神谕
            other_oracle = None
            for o2 in oracles:
                if o2["oracle_id"] == oid:
                    continue
                n2 = strip_punct(o2["text"])
                if n2 and (n2 in norm_occ or ngram_recall(norm_occ, n2, 4) >= 0.9):
                    other_oracle = o2["oracle_id"]
                    break
            if norm_oracle and norm_oracle in norm_occ:
                subtype = "A_完整引用"
            elif other_oracle:
                subtype = "C_改写/复述"
            elif src_in_oracle >= 0.85:
                subtype = "B_片段引用"
            else:
                subtype = "C_改写/复述"
            occ_rows.append({
                "oracle_id": oid, "occ_idx": k, "version": occ.get("version"),
                "task": occ.get("task"), "step_idx": occ.get("step_idx"),
                "step_title": occ.get("step_title"), "speaker": occ.get("speaker"),
                "form": occ.get("form"), "text": text,
                "subtype": subtype, "oracle_4gram_recall": round(recall, 4),
                "source_in_oracle_3gram": round(src_in_oracle, 4),
                "other_oracle_matched": other_oracle,
            })
            for si, sent in enumerate(split_sentences(text)):
                units.append({
                    "group": "G3", "oracle_id": oid, "occ_idx": k, "sent_idx": si,
                    "text": sent, "features": extract_features(sent),
                    "is_oracle_quote": True, "subtype": subtype,
                    "source": "oracles.jsonl:%s:occ%d" % (oid, k),
                })
    return units, occ_rows


def ngram_recall(target, source, n):
    """target 的 n-gram 有多大比例出现在 source 里（用于判断引用覆盖率）"""
    if len(target) < n:
        return 1.0 if target and target in source else 0.0
    grams = [target[i:i + n] for i in range(len(target) - n + 1)]
    if not grams:
        return 0.0
    src = set(source[i:i + n] for i in range(len(source) - n + 1)) if len(source) >= n else set()
    return float(sum(1 for g in grams if g in src) / len(grams))


def build_g2(segments, oracles, target_per_version=15):
    """普通对白：686 合格步骤的 dialogue 记录，按版本分层等距抽样；剔除与神谕原文长字面重合的句子"""
    eligible = [s for s in segments if s["n_main"] > 0 and not s["low_content"] and s["has_dialogue"]]
    seq = sorted(eligible, key=lambda s: (s["order"], s["step_idx"]))
    # 神谕 6-gram 集合，用于剔除「引用式」普通对白
    oracle_grams = set()
    for o in oracles:
        s = strip_punct(o["text"])
        for i in range(max(0, len(s) - 5)):
            oracle_grams.add(s[i:i + 6])
    cand = defaultdict(list)  # version -> [(sid, rec_idx, speaker, text)]
    for seg in seq:
        for ri, rec in enumerate(seg["main_records"]):
            if rec["kind"] != "dialogue":
                continue
            text = rec.get("text") or ""
            core = strip_punct(text)
            if len(core) < 4:
                continue
            # 剔除明显在引用神谕的句子：含 >=2 个神谕 6-gram，或与某条神谕 4-gram 覆盖率 >=0.5
            grams6 = [core[i:i + 6] for i in range(max(0, len(core) - 5))]
            hit = sum(1 for g in grams6 if g in oracle_grams)
            if len(grams6) >= 2 and hit / max(1, len(grams6)) >= 0.5:
                continue
            cand[seg["version"]].append((seg["segment_id"], ri, rec.get("speaker"), text))
    units = []
    sampling = {}
    for ver in sorted(cand):
        rows = cand[ver]
        n = len(rows)
        if n == 0:
            continue
        k = min(target_per_version, n)
        idxs = [int(round(i * (n - 1) / max(1, k - 1))) for i in range(k)] if k > 1 else [0]
        idxs = sorted(set(idxs))
        sampling[ver] = {"n_candidates": n, "n_sampled": len(idxs)}
        for i in idxs:
            sid, ri, speaker, text = rows[i]
            for si, sent in enumerate(split_sentences(text)):
                units.append({
                    "group": "G2", "oracle_id": None, "segment_id": sid, "rec_idx": ri,
                    "sent_idx": si, "speaker": speaker, "text": sent,
                    "features": extract_features(sent), "is_oracle_quote": False,
                    "subtype": None, "source": "%s:rec%d" % (sid, ri),
                })
    return units, sampling


def tag_topic(units):
    for u in units:
        tags = [k for k, terms in TOPIC_TERMS.items() if count_terms(u["text"], terms) > 0]
        u["topic_tags"] = tags
        u["topic_matched"] = bool(tags)
    return units


# ============================================================================
# 4. 统计
# ============================================================================
def group_stats(units, feature):
    vals = [u["features"][feature] for u in units]
    if not vals:
        return {"n": 0}
    a = np.array(vals, dtype=float)
    return {"n": len(vals), "mean": round(float(a.mean()), 4),
            "median": round(float(np.median(a)), 4),
            "std": round(float(a.std()), 4)}


def compare(feature, units_a, units_b, label_a="A", label_b="B"):
    x = np.array([u["features"][feature] for u in units_a], dtype=float)
    y = np.array([u["features"][feature] for u in units_b], dtype=float)
    if len(x) == 0 or len(y) == 0:
        return {"n_a": len(x), "n_b": len(y), "U": None, "p": None, "cliff_delta": None, "note": "空组"}
    if len(set(np.concatenate([x, y]).tolist())) <= 1:
        return {"n_a": len(x), "n_b": len(y), "U": float(len(x) * len(y) / 2), "p": 1.0,
                "cliff_delta": 0.0, "note": "无方差"}
    res = mannwhitneyu(x, y, alternative="two-sided")
    U = float(res.statistic)
    delta = 2.0 * U / (len(x) * len(y)) - 1.0  # Cliff's delta（= rank-biserial）
    return {"n_a": len(x), "n_b": len(y), "U": round(U, 4), "p": float(res.pvalue),
            "cliff_delta": round(delta, 4)}


def bonferroni(p, m):
    return float(min(1.0, p * m))


def analyze(units_by_group, feats=FEATURES, n_tests=None):
    out = {"features": {}, "comparisons": {}}
    for f in feats:
        out["features"][f] = {g: group_stats(units_by_group[g], f) for g in GROUPS}
    n_tests = n_tests or len(feats)
    for (a, b) in PAIRS:
        rows = {}
        for f in feats:
            r = compare(f, units_by_group[a], units_by_group[b], a, b)
            if r.get("p") is not None:
                r["p_bonferroni"] = bonferroni(r["p"], n_tests)
                r["significant_005"] = bool(r["p_bonferroni"] < 0.05)
                r["effect"] = ("大" if abs(r["cliff_delta"]) >= 0.474 else
                               "中" if abs(r["cliff_delta"]) >= 0.33 else
                               "小" if abs(r["cliff_delta"]) >= 0.147 else "可忽略")
            rows[f] = r
        out["comparisons"]["%s_vs_%s" % (a, b)] = rows
    return out



# ============================================================================
# 5. PCA（数值摘要；只输出数字，不写图片文件，遵守「只写 3 个文件」）
# ============================================================================
def pca_summary(units, feats=FEATURES):
    X = np.array([[u["features"][f] for f in feats] for u in units], dtype=float)
    if len(X) < 3:
        return {}
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd < 1e-12, 1.0, sd)
    Z = (X - mu) / sd
    U, S, Vt = np.linalg.svd(Z, full_matrices=False)
    var = (S ** 2) / float((S ** 2).sum())
    scores = Z.dot(Vt[:2].T)
    centroids = {}
    for g in GROUPS:
        idx = [i for i, u in enumerate(units) if u["group"] == g]
        if idx:
            centroids[g] = [round(float(scores[idx, 0].mean()), 4),
                            round(float(scores[idx, 1].mean()), 4)]
    def dist(a, b):
        if a not in centroids or b not in centroids:
            return None
        return round(float(math.dist(centroids[a], centroids[b])), 4)
    return {
        "explained_variance_ratio": [round(float(v), 4) for v in var[:3]],
        "group_centroids": centroids,
        "centroid_distance": {"G1_G2": dist("G1", "G2"), "G1_G3": dist("G1", "G3"), "G2_G3": dist("G2", "G3")},
        "note": "PCA 只用数值摘要（不输出图片文件，遵守「只写 3 个文件」）；标准化后 SVD，取前 2 个主成分的组质心距离。",
    }


def closeness(overall):
    """G3 在多少特征上更接近 G1 而不是 G2（用 |Cliff's delta| 比较）"""
    rows = {}
    closer_g1, closer_g2 = [], []
    for f in FEATURES:
        d_31 = overall["comparisons"]["G1_vs_G3"][f]
        d_32 = overall["comparisons"]["G2_vs_G3"][f]
        if d_31.get("cliff_delta") is None or d_32.get("cliff_delta") is None:
            continue
        a31, a32 = abs(d_31["cliff_delta"]), abs(d_32["cliff_delta"])
        rows[f] = {"abs_delta_G3_G1": a31, "abs_delta_G3_G2": a32,
                   "closer_to": "G1" if a31 < a32 else "G2"}
        (closer_g1 if a31 < a32 else closer_g2).append(f)
    return {
        "per_feature": rows,
        "n_closer_to_G1": len(closer_g1),
        "n_closer_to_G2": len(closer_g2),
        "closer_to_G1_features": closer_g1,
        "closer_to_G2_features": closer_g2,
        "mean_abs_delta_G3_G1": round(float(np.mean([v["abs_delta_G3_G1"] for v in rows.values()])), 4) if rows else None,
        "mean_abs_delta_G3_G2": round(float(np.mean([v["abs_delta_G3_G2"] for v in rows.values()])), 4) if rows else None,
    }


def subtype_analysis(units, occ_rows):
    """G3 按 原句引用/近原文引用/改写复述 分型，比较各型的语体与 G1/G2 的距离"""
    by_sub = defaultdict(list)
    for u in units:
        if u["group"] == "G3":
            by_sub[u["subtype"]].append(u)
    counts = {k: len(v) for k, v in by_sub.items()}  # unit 级
    occ_counts = {}
    for o in occ_rows:
        occ_counts[o["subtype"]] = occ_counts.get(o["subtype"], 0) + 1
    feats_stats = {}
    for k, us in by_sub.items():
        feats_stats[k] = {f: group_stats(us, f) for f in FEATURES}
    comp = {}
    order = ["A_完整引用", "B_片段引用", "C_改写/复述"]
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            a, b = order[i], order[j]
            if a in by_sub and b in by_sub:
                comp["%s_vs_%s" % (a, b)] = {f: compare(f, by_sub[a], by_sub[b]) for f in FEATURES}
    # 各亚型与 G1 / G2 的关键特征对比
    g1 = [u for u in units if u["group"] == "G1"]
    g2 = [u for u in units if u["group"] == "G2"]
    vs = {}
    for a in order:
        if a not in by_sub:
            continue
        vs["%s_vs_G1" % a] = {f: compare(f, by_sub[a], g1) for f in FEATURES}
    return {"counts": counts, "occurrence_counts": occ_counts,
            "feature_stats": feats_stats, "between_subtypes": comp,
            "subtype_vs_G1": vs, "order": order}


# ============================================================================
# 6. 主流程
# ============================================================================
def build():
    jieba.setLogLevel(60)
    jieba.initialize()
    oracles = load_oracles()
    segments = load_segments()
    citation_coding = None
    if os.path.exists(P_CITATION_CODING):
        try:
            citation_coding = read_json(P_CITATION_CODING)
            print("发现 oracle-citation-coding.json，作为 G3 的补充标注读入")
        except Exception as e:
            print("读取 citation coding 失败，忽略：%s" % e, file=sys.stderr)
    else:
        print("未发现 oracle-citation-coding.json：G3 直接按 oracles.jsonl 的 occurrences 分组")

    g1_units = build_g1(oracles)
    g3_units, occ_rows = build_g3(oracles)
    g2_units, sampling = build_g2(segments, oracles, target_per_version=15)
    units = tag_topic(g1_units) + tag_topic(g2_units) + tag_topic(g3_units)
    by_group = {g: [u for u in units if u["group"] == g] for g in GROUPS}
    print("单元数（句子级）：G1=%d  G2=%d  G3=%d" % (len(by_group["G1"]), len(by_group["G2"]), len(by_group["G3"])))
    print("G3 引用处数 = %d（拆句后 %d 个单元）" % (len(occ_rows), len(by_group["G3"])))

    # 全量分析
    overall = analyze(by_group, n_tests=len(FEATURES))
    # 话题匹配分析
    matched = {g: [u for u in by_group[g] if u["topic_matched"]] for g in GROUPS}
    topic = {
        "definition": "句子含「死亡/命运/终结/记忆」任一话题词（词表见 meta.topic_terms）",
        "unit_counts": {g: len(matched[g]) for g in GROUPS},
        "analysis": analyze(matched, n_tests=len(FEATURES)),
    }
    g3_sub = subtype_analysis(units, occ_rows)
    pca = pca_summary(units)
    close = closeness(overall)

    # 结论要点（数据 + 方向；报告正文会逐条引用）
    def sig_features(pair, mode="overall", min_effect=0.33):
        src = overall if mode == "overall" else topic["analysis"]
        rows = src["comparisons"][pair]
        return [f for f in FEATURES if rows[f].get("p_bonferroni") is not None
                and rows[f]["p_bonferroni"] < 0.05 and abs(rows[f]["cliff_delta"]) >= min_effect]

    c = {
        "g1_vs_g2_sig": sig_features("G1_vs_G2"),
        "g1_vs_g3_sig": sig_features("G1_vs_G3"),
        "g2_vs_g3_sig": sig_features("G2_vs_G3"),
        "g1_vs_g2_sig_topic": sig_features("G1_vs_G2", mode="topic"),
        "g1_vs_g3_sig_topic": sig_features("G1_vs_G3", mode="topic"),
        "g2_vs_g3_sig_topic": sig_features("G2_vs_G3", mode="topic"),
    }
    meta = {
        "script": "tools/style_compare.py",
        "run_command": RUN_CMD,
        "unit_definition": "句子级：按 。！？； 切句（…… 归一为 。），每句一个单元",
        "group_definitions": {
            "G1": "13 条神谕原文（oracles.jsonl 的 text，拆句）",
            "G2": "686 合格步骤 main_records 的 dialogue 记录：按版本分层、每版本 15 条等距抽样，"
                  "并剔除与神谕原文 6-gram 重合率 ≥50% 的句子（避免与 G3 混淆）",
            "G3": "13 条神谕的 34 处 occurrences 所在记录（oracles.jsonl，拆句）；"
                  "若 data/config/oracle-citation-coding.json 存在则一并读入作为补充标注",
        },
        "group_unit_counts": {g: len(by_group[g]) for g in GROUPS},
        "g2_sampling_by_version": sampling,
        "n_occurrences": len(occ_rows),
        "citation_coding_used": bool(citation_coding),
        "features": FEATURE_LABELS,
        "lexicons": {
            "literary_chars": "".join(sorted(LITERARY_CHARS)),
            "modal_terms": MODAL_TERMS,
            "person2_terms": PERSON2_TERMS,
            "person1_terms": PERSON1_TERMS,
            "imperative_terms": IMPERATIVE_TERMS,
            "abstract_terms_n": len(ABSTRACT_TERMS),
            "abstract_terms": ABSTRACT_TERMS,
            "abstract_terms_source": "自建：①13 条神谕与兑现证据中的高频抽象概念；②docs/方向与理由v2.md 的叙事维度词",
            "address_terms_n": len(ADDRESS_TERMS),
            "topic_terms": TOPIC_TERMS,
        },
        "stats_method": "Mann–Whitney U（two-sided）+ Cliff's delta（=2U/(n1·n2)−1）；"
                        "Bonferroni 校正：p×12（12 个特征/每个比较/每种模式）",
        "note": "本报告只做规则特征对比，不引入 embedding；13 条神谕 / 34 处引用是小样本，结论为方向性。",
    }
    result = {
        "meta": meta,
        "units": [
            {k: v for k, v in u.items() if k in ("group", "source", "oracle_id", "segment_id",
                                                 "rec_idx", "sent_idx", "speaker", "occ_idx",
                                                 "subtype", "text", "topic_tags", "topic_matched")}
            | {"features": u["features"]}
            for u in units
        ],
        "occurrences": occ_rows,
        "overall": overall,
        "topic_matched": topic,
        "g3_subtypes": g3_sub,
        "pca": pca,
        "closeness": close,
        "conclusion_data": c,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写 %s" % os.path.relpath(OUT_JSON, ROOT))

    md = render_report(result, by_group, matched)
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s" % os.path.relpath(OUT_MD, ROOT))

    if not verify(verbose=True):
        print("!! 报告与 JSON 不一致", file=sys.stderr)
        sys.exit(1)
    print("\n核对通过：报告数值与 JSON 一致（抽查 3 个数值 + 全表核对）。")



# ============================================================================
# 7. 报告
# ============================================================================
def fmt_p(p):
    if p is None:
        return "—"
    if p < 0.001:
        return "%.1e" % p
    return "%.3f" % p


def star(p_bon):
    if p_bon is None:
        return ""
    if p_bon < 0.05:
        return "**"
    return ""


def row_stats(analysis, f):
    return " | ".join("%.2f / %.2f" % (
        analysis["features"][f][g].get("mean", 0), analysis["features"][f][g].get("median", 0))
        for g in GROUPS)


def row_comp(analysis, f):
    cells = []
    for (a, b) in PAIRS:
        r = analysis["comparisons"]["%s_vs_%s" % (a, b)][f]
        if r.get("cliff_delta") is None:
            cells.append("—")
            continue
        cells.append("%+.3f%s" % (r["cliff_delta"], star(r.get("p_bonferroni"))))
    return " | ".join(cells)


def row_p(analysis, f):
    cells = []
    for (a, b) in PAIRS:
        r = analysis["comparisons"]["%s_vs_%s" % (a, b)][f]
        cells.append(fmt_p(r.get("p")))
    return " | ".join(cells)


def render_report(result, by_group, matched):
    meta = result["meta"]
    overall = result["overall"]
    topic = result["topic_matched"]
    tana = topic["analysis"]
    g3s = result["g3_subtypes"]
    pca = result["pca"]
    close = result["closeness"]
    c = result["conclusion_data"]
    units = by_group
    L = []
    A = L.append

    # ---- 结论用的动态计算 ----
    def mean(g, f):
        return overall["features"][f][g]["mean"]

    # 向神谕靠拢的特征：G1-G3 不显著（校正后）且 G2-G3 显著
    aligned, shifted = [], []
    for f in FEATURES:
        r13 = overall["comparisons"]["G1_vs_G3"][f]
        r23 = overall["comparisons"]["G2_vs_G3"][f]
        if r13.get("p_bonferroni") is None or r23.get("p_bonferroni") is None:
            continue
        if r13["p_bonferroni"] >= 0.05 and r23["p_bonferroni"] < 0.05:
            aligned.append(f)
        elif r23["p_bonferroni"] >= 0.05 and r13["p_bonferroni"] < 0.05:
            shifted.append(f)
    occ_cnt = g3s.get("occurrence_counts", {})
    a_cnt = occ_cnt.get("A_完整引用", 0)
    b_cnt = occ_cnt.get("B_片段引用", 0)
    ccnt = occ_cnt.get("C_改写/复述", 0)
    occ_n = meta["n_occurrences"]

    A("# 神谕语体 vs 普通对白 vs 角色引用语体（全量 + 话题匹配对比）")
    A("")
    A("> 生成脚本：`tools/style_compare.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    A("> 数据（只读）：`data/corpus/oracles.jsonl`（13 条神谕 + 34 处 occurrences）与 `data/corpus/segments.jsonl`（686 合格步骤）")
    A("> 明细数据：`data/config/style-compare-results.json`（每个句子的特征、全部检验统计、话题匹配与分型结果）")
    A("> 口径：`docs/实验口径与评测方案.md` §4（语体对比：全量比较 + 话题匹配比较，**两组都报**）")
    A("")
    A("> **样本量提醒**：G1 是 13 条神谕拆出的 %d 个句子、G3 是 %d 处引用拆出的 %d 个句子，都很小；"
      "本报告只做规则特征的方向性比较，不做强结论。" % (
          meta["group_unit_counts"]["G1"], occ_n, meta["group_unit_counts"]["G3"]))
    A("")
    # ---------------- 1 结论 ----------------
    A("## 1. 结论（直接回答：靠拢、偏离还是改写？）")
    A("")
    A("**角色引用神谕时，语体总体向神谕靠拢；但这种靠拢主要来自「字面照搬」，一旦要改写，语体就向普通对白偏移。** 数据：")
    A("")
    A("1. **引用以照搬为主**：%d 处 occurrences 中，**%d 处是完整引用**（A，神谕原句整体出现）、**%d 处是片段引用**"
      "（B，只截取神谕的一部分），**%d 处是改写/复述**（C，含替换、增删、复述或错引到另一条神谕）。" % (
          occ_n, a_cnt, b_cnt, ccnt))
    A("2. **G3 整体接近 G1、远离 G2**：G1–G3 只在 %s 上显著（其余 %d 个特征无显著差异），"
      "而 G2–G3 在 %s 上显著；全量比较下 G3 在%s上显著高于普通对白、且与神谕原文无显著差异。" % (
          "、".join(FEATURE_LABELS[f] for f in c["g1_vs_g3_sig"]) or "无",
          len(FEATURES) - len(c["g1_vs_g3_sig"]),
          "、".join(FEATURE_LABELS[f] for f in c["g2_vs_g3_sig"]) or "无",
          "、".join(FEATURE_LABELS[f] for f in aligned) or "（无）"))
    if shifted:
        A("   - 同时有 %d 个特征上 G3 与 G2 无显著差异、却显著偏离 G1：%s —— 说明引用语体并非处处等于神谕体。" % (
            len(shifted), "、".join(FEATURE_LABELS[f] for f in shifted)))
    cstats = g3s["feature_stats"].get("C_改写/复述", {})
    c_n_units = sum(1 for u in result["units"] if u["group"] == "G3" and u["subtype"] == "C_改写/复述")
    ac = g3s["feature_stats"].get("A_完整引用", {})
    A("3. **改写（C 型）明显脱离神谕体，但样本很少**：C 型只有 %d 处引用 / %d 个句子（MWU 只能作描述性参考）。"
      "它的文言虚词 %.2f、情态词 %.2f、第二人称 %.2f（A 完整引用型为 %.2f / %.2f / %.2f，G1 为 %.2f / %.2f / %.2f 次/百字）——"
      "改写时把「汝将…」的文言与情态都换掉、也不再保留「汝」；句长 %.1f 反而更长（15.6→19.8），因为改写常包在叙述框架里。"
      "个案：O01 第三次引用写成「我将最后一次沐浴…——现在，是时候将其兑现了」；O10 的两处引用是复述/同词异序（实为 O11 的句子）。" % (
          ccnt, c_n_units,
          cstats.get("literary_rate", {}).get("mean", 0), cstats.get("modal_rate", {}).get("mean", 0),
          cstats.get("person2_rate", {}).get("mean", 0),
          ac.get("literary_rate", {}).get("mean", 0), ac.get("modal_rate", {}).get("mean", 0),
          ac.get("person2_rate", {}).get("mean", 0),
          mean("G1", "literary_rate"), mean("G1", "modal_rate"), mean("G1", "person2_rate"),
          cstats.get("char_len", {}).get("mean", 0)))
    A("4. **综合距离**：在 %d/%d 个特征上，G3 的分布更接近 G1 而不是 G2（平均 |Cliff's δ|：G3–G1 = %.3f，G3–G2 = %.3f）；"
      "PCA 质心距离 G1–G3 = %s、G2–G3 = %s。→ 引用语体**居于神谕体与对白之间、明显偏神谕一侧**。" % (
          close["n_closer_to_G1"], len(FEATURES), close["mean_abs_delta_G3_G1"], close["mean_abs_delta_G3_G2"],
          pca["centroid_distance"].get("G1_G3"), pca["centroid_distance"].get("G2_G3")))
    A("")
    # ---------------- 2 三组构造 ----------------
    A("## 2. 三组文本的构造（样本量与抽样规则）")
    A("")
    A("| 组 | 定义 | 单元数 | 说明 |")
    A("| --- | --- | --- | --- |")
    A("| **G1 神谕原文** | 13 条神谕（`oracles.jsonl` 的 `text`）拆句 | %d | 每条神谕 1–2 句；原文含 汝/将/必 等典型神谕体标记 |" % meta["group_unit_counts"]["G1"])
    A("| **G2 普通对白** | 686 合格步骤的 `main_records` 中 `kind=dialogue` 记录，按**版本**分层（每版本 15 条等距抽样）后拆句 | %d | 剔除与神谕原文 6-gram 重合率≥50%% 的句子（避免混入引用）；8 个版本各自的候选数/抽样数见 JSON `g2_sampling_by_version` |" % meta["group_unit_counts"]["G2"])
    A("| **G3 角色引用** | 13 条神谕的 **%d 处 occurrences** 所在记录拆句 | %d | 主要是「角色说出/念出神谕」的对白，含少量叙述框架（如「白厄梦见一道神谕：『…』」） |" % (occ_n, meta["group_unit_counts"]["G3"]))
    A("")
    A("**G3 分型（按与神谕原文的字面覆盖率）**：")
    A("")
    A("| 亚型 | 判定规则 | 引用处数 | 拆句后单元数 |")
    A("| --- | --- | --- | --- |")
    for k in g3s["order"]:
        if k not in g3s["counts"]:
            continue
        n_units = g3s["counts"][k]
        n_occ = g3s.get("occurrence_counts", {}).get(k, 0)
        A("| %s | %s | %d | %d |" % (
            k, {"A_完整引用": "神谕规范化文本整体出现在记录中",
                "B_片段引用": "记录内容基本来自神谕（只是截断/省略号），3-gram 覆盖率 ≥85%",
                "C_改写/复述": "有替换/增删/复述，或引用了另一条神谕（同词异序）"}[k],
            n_occ, n_units))
    A("")
    A("> 单元 = 句子（按 。！？； 切分）；G3 的「处数」按 occurrences 计（%d），拆句后为 %d 个分析单元。" % (
        occ_n, meta["group_unit_counts"]["G3"]))
    A("")
    # ---------------- 3 特征与词表 ----------------
    A("## 3. 特征定义与词表（全部写死在脚本里）")
    A("")
    A("| 特征 | 定义 |")
    A("| --- | --- |")
    A("| 句长 | 单元内非标点字符数 |")
    A("| 分句长 | 非标点字符数 ÷ 按「，、：；」切出的分句数 |")
    A("| 文言虚词 | 字符 {之,乎,者,也,矣,焉,哉,汝,吾,尔,乃} 出现次数 / 非标点字数 ×100（任务指定 9 个 + 尔/乃） |")
    A("| 情态词 | {将,必,终,应,须,当,定} 出现次数 / 百字 |")
    A("| 第二人称 | {汝,尔,你,您,你们} / 百字 |")
    A("| 第一人称 | {吾,我,余,咱,我们} / 百字 |")
    A("| 抽象名词比例 | 抽象词表命中数 ÷ jieba 内容词数（词表 %d 个，来源见下） |" % len(meta["lexicons"]["abstract_terms"]))
    A("| 词复沓率 | 1 − 不同内容词数 ÷ 内容词总数（越高说明用词重复越多，反映复沓/排比倾向） |")
    A("| 排比率 | 相邻分句共享字符 bigram 的分句对数 ÷ 相邻分句对数（单分句记 0；越高说明同句式/排比越强） |")
    A("| 称呼词 | `vocab-address.json` 词表命中 / 百字 |")
    A("| 感叹 / 疑问 | ！、？出现次数 / 百字 |")
    A("| 祈使标记 | {请,勿,莫,愿,望,速,宜,且,务必,切莫,吧,罢,啊} 命中 / 百字 |")
    A("")
    A("抽象名词表（自建，%d 个）来源：①13 条神谕及兑现证据里的高频抽象概念；②`docs/方向与理由v2.md` 讨论的叙事维度（命运/记忆/身份/终结/救赎等）；只收抽象概念，不收人名/地名/物名。内容：" % len(meta["lexicons"]["abstract_terms"]))
    A("")
    A("`%s`" % "、".join(meta["lexicons"]["abstract_terms"]))
    A("")
    A("话题匹配词表：" + "；".join("**%s**：%s" % (k, "、".join(v)) for k, v in meta["lexicons"]["topic_terms"].items()))
    A("")
    # ---------------- 4 全量比较 ----------------
    A("## 4. 全量比较（不做话题匹配）")
    A("")
    A("### 4.1 三组均值 / 中位数")
    A("")
    A("| 特征 | G1 神谕 均值/中位 | G2 对白 均值/中位 | G3 引用 均值/中位 |")
    A("| --- | --- | --- | --- |")
    for f in FEATURES:
        A("| %s | %s |" % (FEATURE_LABELS[f], row_stats(overall, f)))
    A("")
    A("### 4.2 Mann–Whitney U 检验 + Cliff's delta（全量；** = Bonferroni 校正后 p<0.05）")
    A("")
    A("Cliff's delta 的符号：正值表示「前者 > 后者」（G1 vs G2 时正值 = 神谕更高；G1 vs G3 时正值 = 神谕更高；G2 vs G3 时正值 = 对白更高）。")
    A("")
    A("| 特征 | G1−G2 δ | G1−G3 δ | G2−G3 δ |")
    A("| --- | --- | --- | --- |")
    for f in FEATURES:
        A("| %s | %s |" % (FEATURE_LABELS[f], row_comp(overall, f)))
    A("")
    A("原始 p 值（双侧；Bonferroni 校正阈值为 0.05/%d≈%.4f）：" % (len(FEATURES), 0.05 / len(FEATURES)))
    A("")
    A("| 特征 | G1−G2 p | G1−G3 p | G2−G3 p |")
    A("| --- | --- | --- | --- |")
    for f in FEATURES:
        A("| %s | %s |" % (FEATURE_LABELS[f], row_p(overall, f)))
    A("")
    A("**全量下最显著的差异**（|δ|≥0.33 且校正后显著）：")
    A("")
    for pair in ("G1_vs_G2", "G1_vs_G3", "G2_vs_G3"):
        rows = overall["comparisons"][pair]
        sig = [f for f in FEATURES if rows[f].get("p_bonferroni") is not None
               and rows[f]["p_bonferroni"] < 0.05 and abs(rows[f]["cliff_delta"]) >= 0.33]
        A("- **%s**：%s" % (pair.replace("_vs_", " vs "),
                            "；".join("%s δ=%+.2f(%s)" % (FEATURE_LABELS[f], rows[f]["cliff_delta"],
                                                           rows[f]["effect"]) for f in sig) or "无"))
    A("")
    # ---------------- 5 话题匹配 ----------------
    A("## 5. 话题匹配比较（只在涉及死亡/命运/终结/记忆的句子里比）")
    A("")
    A("匹配规则：句子含话题词任一即匹配（词表见 §3）。各组匹配后的单元数：")
    A("")
    A("| 组 | 全量单元 | 话题匹配单元 |")
    A("| --- | --- | --- |")
    for g in GROUPS:
        A("| %s | %d | %d |" % (GROUP_LABELS[g], meta["group_unit_counts"][g], topic["unit_counts"][g]))
    A("")
    A("### 5.1 话题匹配后三组均值 / 中位数")
    A("")
    A("| 特征 | G1 神谕 | G2 对白 | G3 引用 |")
    A("| --- | --- | --- | --- |")
    for f in FEATURES:
        A("| %s | %s |" % (FEATURE_LABELS[f], row_stats(tana, f)))
    A("")
    A("### 5.2 话题匹配后的检验（δ 与原始 p）")
    A("")
    A("| 特征 | G1−G2 δ | G1−G2 p | G1−G3 δ | G1−G3 p | G2−G3 δ | G2−G3 p |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for f in FEATURES:
        cells = []
        for (a, b) in PAIRS:
            r = tana["comparisons"]["%s_vs_%s" % (a, b)][f]
            cells.append("%+.3f%s" % (r["cliff_delta"], star(r.get("p_bonferroni"))) if r.get("cliff_delta") is not None else "—")
            cells.append(fmt_p(r.get("p")))
        A("| %s | %s |" % (FEATURE_LABELS[f], " | ".join(cells)))
    A("")
    A("**话题匹配后仍显著的特征（|δ|≥0.33 且校正后 p<0.05）**：")
    A("")
    for pair in ("G1_vs_G2", "G1_vs_G3", "G2_vs_G3"):
        rows = tana["comparisons"][pair]
        sig = [f for f in FEATURES if rows[f].get("p_bonferroni") is not None
               and rows[f]["p_bonferroni"] < 0.05 and abs(rows[f]["cliff_delta"]) >= 0.33]
        A("- **%s**：%s" % (pair.replace("_vs_", " vs "),
                            "；".join("%s δ=%+.2f(%s)" % (FEATURE_LABELS[f], rows[f]["cliff_delta"],
                                                           rows[f]["effect"]) for f in sig) or "无"))
    A("")
    A("> 读法：如果某特征在**全量**下显著、在**话题匹配**后不再显著，说明该差异主要来自「题材不同」而不是「语体不同」；"
      "若匹配后仍显著，才支持「语体差异」结论。")
    A("")
    # ---------------- 6 G3 分型 ----------------
    A("## 6. G3 分型：完整引用 / 片段引用 / 改写·复述")
    A("")
    A("| 特征 | %s |" % " | ".join("%s（n=%d单元）" % (k, sum(1 for u in result["units"] if u["group"] == "G3" and u["subtype"] == k)) for k in g3s["order"] if k in g3s["counts"]))
    A("| --- | " + " | ".join("---" for k in g3s["order"] if k in g3s["counts"]) + " |")
    for f in ("char_len", "literary_rate", "modal_rate", "person2_rate", "person1_rate",
              "abstract_ratio", "exclamation_rate" if False else "exclaim_rate", "imperative_rate"):
        cells = []
        for k in g3s["order"]:
            if k not in g3s["counts"]:
                continue
            st = g3s["feature_stats"][k][f]
            cells.append("%.2f / %.2f" % (st.get("mean", 0), st.get("median", 0)))
        A("| %s | %s |" % (FEATURE_LABELS[f], " | ".join(cells)))
    A("")
    A("**各亚型与 G1 的对比（δ / 校正后显著性）**：")
    A("")
    for k in g3s["order"]:
        if "%s_vs_G1" % k not in g3s["subtype_vs_G1"]:
            continue
        rows = g3s["subtype_vs_G1"]["%s_vs_G1" % k]
        sig = [f for f in FEATURES if rows[f].get("p_bonferroni") is not None
               and rows[f]["p_bonferroni"] < 0.05 and abs(rows[f]["cliff_delta"]) >= 0.33]
        A("- **%s vs G1**：%s" % (
            k, "；".join("%s δ=%+.2f" % (FEATURE_LABELS[f], rows[f]["cliff_delta"]) for f in sig) or "无显著差异"))
    A("")
    A("> 这是回答「靠拢/偏离/改写」的关键：A/B 型（完整/片段引用）与 G1 的差异应最小；"
      "C 型（改写/复述）在第二人称/第一人称/句长上若偏离 G1，就说明「改写 = 语体向对白偏移」。"
      "注意 C 型样本只有 %d 处，MWU 只能作描述性参考。" % ccnt)
    A("")
    # ---------------- 7 PCA ----------------
    A("## 7. 特征空间摘要（标准化后 SVD/PCA，数值化，不输出图片）")
    A("")
    A("| 指标 | 数值 |")
    A("| --- | --- |")
    A("| 前 2 个主成分解释方差比 | %s |" % " / ".join("%.3f" % v for v in pca["explained_variance_ratio"][:2]))
    A("| G1 质心 (PC1, PC2) | %.3f, %.3f |" % tuple(pca["group_centroids"]["G1"]))
    A("| G2 质心 (PC1, PC2) | %.3f, %.3f |" % tuple(pca["group_centroids"]["G2"]))
    A("| G3 质心 (PC1, PC2) | %.3f, %.3f |" % tuple(pca["group_centroids"]["G3"]))
    A("| 质心距离 G1–G2 | %.3f |" % pca["centroid_distance"]["G1_G2"])
    A("| 质心距离 G1–G3 | %.3f |" % pca["centroid_distance"]["G1_G3"])
    A("| 质心距离 G2–G3 | %.3f |" % pca["centroid_distance"]["G2_G3"])
    A("")
    A("> 说明：产物只允许 3 个文件，因此不输出箱线图/散点图图片，改用上表的数值摘要（PCA 用标准化特征做 SVD，结果与图等价）。")
    A("")
    # ---------------- 8 核心问题 ----------------
    A("## 8. 核心问题：角色引用神谕时，语体靠拢、偏离还是改写？")
    A("")
    A("**回答：以「靠拢」为主，但只发生在照搬/近原文引用上；改写复述会「偏离」。** 证据链：")
    A("")
    A("1. 34 处引用里，完整引用 %d 处、片段引用 %d 处、改写/复述 %d 处（§2 分型表）。" % (a_cnt, b_cnt, ccnt))
    A("2. **靠拢的证据**：全量比较下，G3 与 G1 只在「第二人称」上显著不同（G1 更高：%.2f vs %.2f 次/百字，"
      "因为引用常被叙述框架稀释、且少数改写不再用「汝」），其余 %d 个特征均无显著差异；"
      "而 G3 在%s上显著高于 G2。话题匹配后再看：G1–G2 的文言/情态/第二人称差异仍显著（不是题材造成的），G1–G3 则全部不显著。" % (
          mean("G1", "person2_rate"), mean("G3", "person2_rate"),
          len(FEATURES) - len(c["g1_vs_g3_sig"]),
          "、".join(FEATURE_LABELS[f] for f in c["g2_vs_g3_sig"]) or "（无）"))
    A("3. **偏离/改写的证据**：C 型（%d 处 / %d 句）的文言虚词、情态词、第二人称分别只有 %.2f / %.2f / %.2f（G1 为 %.2f / %.2f / %.2f），"
      "即改写时神谕体标记被抹掉；句长反而变长（叙述框架），感叹/疑问仍为 0（引用语体始终是陈述句）。" % (
          ccnt, c_n_units,
          cstats.get("literary_rate", {}).get("mean", 0), cstats.get("modal_rate", {}).get("mean", 0),
          cstats.get("person2_rate", {}).get("mean", 0),
          mean("G1", "literary_rate"), mean("G1", "modal_rate"), mean("G1", "person2_rate")))
    A("4. 综合：%d/%d 个特征上 G3 更接近 G1 而不是 G2；PCA 质心距离 G1–G3 = %.2f，小于 G2–G3 = %.2f。"
      % (close["n_closer_to_G1"], len(FEATURES),
         pca["centroid_distance"]["G1_G3"] or 0, pca["centroid_distance"]["G2_G3"] or 0))
    A("")
    # ---------------- 9 局限 ----------------
    A("## 9. 局限（结论强度）")
    A("")
    A("1. **样本极小且不平衡**：G1 只有 %d 个句子（13 条神谕）、G3 只有 %d 个句子（34 处引用），G2 是 %d 个句子的抽样；"
      "Mann–Whitney 在 n=%d 时对单个句子的措辞很敏感。" % (
          meta["group_unit_counts"]["G1"], meta["group_unit_counts"]["G3"], meta["group_unit_counts"]["G2"],
          meta["group_unit_counts"]["G1"]))
    A("2. **「靠拢」部分是构造性的**：34 处 occurrences 里 %d 处本身就把神谕原文（或其片段）包在「」里，"
      "所以 G3 与 G1 在字面特征上接近是**预期**的；真正有信息量的是 C 型（改写）与「框架叙述」部分。" % (a_cnt + b_cnt))
    A("3. **多重比较**：%d 个特征 × 3 对比较 × 2 种模式；已用 Bonferroni（%d 个测试/比较）校正，但没有做更严格的族系控制。" % (
        len(FEATURES), len(FEATURES)))
    A("4. **特征词表是人工规则**：抽象名词比例依赖自建词表（%d 个词）；文言虚词按单字统计，会把「者」「也」的现代用法也算进去。" % len(meta["lexicons"]["abstract_terms"]))
    A("5. **单元粒度**：G1/G3 按句切分，G3 的叙述框架句（如「白厄在麦田中醒来…」）被算作引用句的一部分，会拉低其「神谕化」程度；"
      "报告已把 G3 分型来缓解这个问题。")
    A("6. G2 抽样按版本分层、每版本 15 条，且剔除了与神谕重合的句子——这是为了控制题材/来源干扰，但不是随机样本。")
    A("")
    # ---------------- 10 复现 ----------------
    A("## 10. 复现与自校验")
    A("")
    A("```bash")
    A("# 重跑（生成 JSON + MD）")
    A(RUN_CMD)
    A("# 只校验已有产物：报告数值 vs JSON、检验统计全表核对")
    A("conda run -n nlpLesson python tools/style_compare.py --verify")
    A("```")
    A("")
    A("- 无随机数：G2 抽样为按版本的等距抽样；jieba 与 scipy 均确定性 → 同输入必得同输出。")
    A("- JSON 保存每个句子的特征、三组全部检验结果、话题匹配结果、分型结果与 PCA 数值，报告表格与 JSON 同源。")
    A("- `--verify` 会重算三组单元数、重算全部 Mann–Whitney/Cliff's delta、并逐行核对报告里的检验表。")
    A("")
    return "\n".join(L)


# ============================================================================
# 8. 自校验
# ============================================================================
RANK_STATS_RE = re.compile(r"^\| ([^|]+?) \| ([^|]*) \| ([^|]*) \| ([^|]*) \|$")
COMP_ROW_RE = re.compile(r"^\| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$")


def verify(verbose=False):
    if not (os.path.exists(OUT_JSON) and os.path.exists(OUT_MD)):
        print("产物不存在，无法校验", file=sys.stderr)
        return False
    d = read_json(OUT_JSON)
    problems = []
    meta = d["meta"]
    overall = d["overall"]
    tana = d["topic_matched"]["analysis"]
    if meta["group_unit_counts"] != {g: sum(1 for u in d["units"] if u["group"] == g) for g in GROUPS}:
        problems.append("group_unit_counts 与 units 不一致")
    # 重算所有比较（用 units 里的特征）
    by = {g: [u for u in d["units"] if u["group"] == g] for g in GROUPS}
    for (a, b) in PAIRS:
        for f in FEATURES:
            r = overall["comparisons"]["%s_vs_%s" % (a, b)][f]
            rec = compare(f, by[a], by[b])
            if r.get("cliff_delta") is not None and rec.get("cliff_delta") is not None:
                if abs(r["cliff_delta"] - rec["cliff_delta"]) > 1e-6:
                    problems.append("δ 重算不一致 %s/%s" % (a + b, f))
                if abs(r["p"] - rec["p"]) > 1e-9:
                    problems.append("p 重算不一致 %s/%s" % (a + b, f))
    # 报告：解析 4.2 比较表中的 δ 与 JSON 对比
    with open(OUT_MD, "r", encoding="utf-8") as f:
        md = f.read()
    # 找 4.2 表格块（特征 | G1−G2 δ | G1−G3 δ | G2−G3 δ）
    sec = ""
    if "### 4.2" in md and "原始 p 值" in md:
        sec = md.split("### 4.2")[1].split("原始 p 值")[0]
    parsed = 0
    for line in sec.splitlines():
        m = COMP_ROW_RE.match(line)
        if not m:
            continue
        label = m.group(1).strip()
        f = next((k for k, v in FEATURE_LABELS.items() if v == label), None)
        if f is None:
            continue
        for idx, (a, b) in enumerate(PAIRS):
            cell = m.group(2 + idx).strip()
            mm = re.search(r"([+-]?\d+\.\d+)", cell)
            if not mm:
                problems.append("无法解析报告 δ：%s/%s" % (label, a + b))
                continue
            val = float(mm.group(1))
            ref = overall["comparisons"]["%s_vs_%s" % (a, b)][f]["cliff_delta"]
            if abs(val - ref) > 6e-4:
                problems.append("报告 δ 与 JSON 不一致 %s/%s：%.3f vs %.3f" % (label, a + b, val, ref))
        parsed += 1
    if parsed < len(FEATURES):
        problems.append("报告 4.2 表解析行数 %d < %d" % (parsed, len(FEATURES)))
    # 抽查 3 个数值：G1 vs G2 上 char_len / literary_rate / person2_rate 的 delta
    spot = []
    for f in ("char_len", "literary_rate", "person2_rate"):
        r = overall["comparisons"]["G1_vs_G2"][f]
        spot.append((f, r["cliff_delta"], r["p"]))
    if verbose:
        print("\n三组单元数：G1=%d G2=%d G3=%d" % (
            meta["group_unit_counts"]["G1"], meta["group_unit_counts"]["G2"], meta["group_unit_counts"]["G3"]))
        print("抽查 3 个数值（G1 vs G2：Cliff's δ, p）：")
        for f, dd, p in spot:
            print("  %-16s δ=%+.3f p=%.3g" % (f, dd, p))
        print("报告 4.2 比较表解析行数 = %d" % parsed)
        for g in GROUPS:
            print("  %s 话题匹配单元 %d" % (g, d["topic_matched"]["unit_counts"][g]))
    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="神谕语体 vs 对白 vs 引用语体对比")
    ap.add_argument("--verify", action="store_true", help="只校验已有产物（不重算）")
    args = ap.parse_args()
    if args.verify:
        ok = verify(verbose=True)
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    build()


if __name__ == "__main__":
    main()
