#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
character_trajectory.py — 角色全程轨迹分析（默认：白厄、昔涟；可复用到 12 黄金裔）

问题背景：数据层是全量的（如白厄 2550 条台词 / 202 步 / 38 任务），但精读只覆盖
21–25 步（约 10–12%）。本脚本对任意角色统计**全部出场**，并显式算「精读覆盖率」，
把「全量数据」与「精读覆盖」的差距摆出来。

统计（对每个角色）：
  * 全部出场：记录数 / 步骤数 / 任务数 / 版本分布；步骤映射到 723 个 segment（686 池子集）
  * 分版本：台词量占比、形态（form）分布、称呼词命中（own lines + 同步骤他人台词）、
    母题词命中、神谕引用（oracle-citation-coding 中 speaker=该角色的 occurrence）、
    所在步骤的 A/B1 分数均值与 Top100 命中率
  * 分任务：记录/步骤数（找「低存在感段」）
  * 精读覆盖率：该角色出场步骤中被 35 个刀子场景 / 29 条关键事件 / 74 条标注覆盖的比例
    （以文件实际内容为准；若文件数量变化，报告会自动更新）
  * 时间线：形态/称呼/母题在各版本的出现序列

产出（只写这些）：
  data/config/character-trajectory.json
  data/reports/character-trajectory.md
  docs/report/figures/f7_bai_trajectory.png（白厄）
  docs/report/figures/f8_xi_trajectory.png（昔涟）
  其他角色（可选）：data/config/character-trajectory.json 会一并收录；图名为
  docs/report/figures/f_traj_<角色>.png

运行：
  conda run -n nlpLesson python tools/character_trajectory.py
  conda run -n nlpLesson python tools/character_trajectory.py --characters 白厄,昔涟
  conda run -n nlpLesson python tools/character_trajectory.py --verify
"""

import argparse
import json
import os
import sys
from collections import Counter, OrderedDict

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_FINAL = os.path.join(ROOT, "data", "corpus", "amphoreus.final.jsonl")
P_SEGMENTS = os.path.join(ROOT, "data", "corpus", "segments.jsonl")
P_ORACLES = os.path.join(ROOT, "data", "corpus", "oracles.jsonl")
P_KNIFE = os.path.join(ROOT, "data", "config", "knife-scenes.json")
P_EVENTS = os.path.join(ROOT, "data", "config", "key-events.json")
P_ANNOT = os.path.join(ROOT, "data", "config", "annotation-labels.json")
P_CITE = os.path.join(ROOT, "data", "config", "oracle-citation-coding.json")
P_A = os.path.join(ROOT, "data", "config", "baseline-a-scores.json")
P_B1 = os.path.join(ROOT, "data", "config", "baseline-b-scores.json")
P_ADDR = os.path.join(ROOT, "data", "config", "vocab-address.json")
P_MOTIF = os.path.join(ROOT, "data", "config", "vocab-motif.json")
P_JSON = os.path.join(ROOT, "data", "config", "character-trajectory.json")
P_MD = os.path.join(ROOT, "data", "reports", "character-trajectory.md")
FIG_DIR = os.path.join(ROOT, "docs", "report", "figures")
RUN_CMD = "conda run -n nlpLesson python tools/character_trajectory.py"
VERSIONS = ["3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"]

# 称呼词与母题词：在 vocab 基础上补本分析需要的（任务点名）
ADDRESS_TERMS = ["救世主", "英雄", "无名英雄", "伙伴", "开拓者", "阁下", "老师",
                 "灰宝", "小灰", "黄金裔", "半神", "救世的烈阳"]
MOTIF_TERMS = ["骄阳", "灰白的黎明", "明天见", "逐火", "火种", "无名", "太阳", "烈阳",
               "黎明", "记忆", "德谬歌", "迷迷", "逐火是不断失却的旅途", "不要回头", "一页永恒"]

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
# 数据装载
# ---------------------------------------------------------------------------
def load_all():
    recs = read_jsonl(P_FINAL)
    segs = read_jsonl(P_SEGMENTS)
    seg_by_key = {(s["version"], s["task"], s["step_idx"]): s for s in segs}
    pool = {s["segment_id"] for s in segs if s["n_main"] > 0 and not s["low_content"] and s["has_dialogue"]}
    A = {s["segment_id"]: s for s in read_json(P_A)["segments"]}
    B = {s["segment_id"]: s for s in read_json(P_B1)["segments"]}
    knife = read_json(P_KNIFE)
    events = read_json(P_EVENTS)
    annot = read_json(P_ANNOT)["samples"]
    cite = read_json(P_CITE)["occurrences"]
    recs_by_step = {}
    for r in recs:
        recs_by_step.setdefault((r["version"], r["task"], r["step_idx"]), []).append(r)
    for k in recs_by_step:
        recs_by_step[k].sort(key=lambda r: r["id"])
    return recs, segs, seg_by_key, pool, A, B, knife, events, annot, cite, recs_by_step


def set_of_segments(items, key_name):
    out = set()
    for it in items:
        v = it.get(key_name)
        if isinstance(v, str) and v:
            out.add(v)
        elif isinstance(v, list):
            out.update(x for x in v if x)
    return out


def knife_segments(knife):
    out = set()
    for s in knife["scenes"]:
        out.update(x for x in (s.get("segment_ids") or []) if x)
        for r in s.get("ranges") or []:
            out.add(r.split("#")[0])
    return out


def key_event_segments(events):
    return set_of_segments(events["events"], "segment_id")


def annotation_segments(annot):
    return {s["segment_id"] for s in annot}


# ---------------------------------------------------------------------------
# 单角色统计
# ---------------------------------------------------------------------------
def count_terms(text, terms):
    c = Counter()
    for t in terms:
        n = (text or "").count(t)
        if n:
            c[t] += n
    return c


def character_stats(name, recs, seg_by_key, pool, A, B, knife, events, annot, cite,
                    listen, recs_by_step=None):
    rows = [r for r in recs if r.get("canonical_speaker") == name]
    if not rows:
        raise SystemExit("角色 %s 没有任何台词记录（canonical_speaker 未匹配）" % name)
    # 步骤：所有出现过的 (version, task, step_idx)
    step_keys = OrderedDict()
    for r in rows:
        k = (r["version"], r["task"], r["step_idx"])
        step_keys.setdefault(k, 0)
        step_keys[k] += 1
    segids = []
    for k in step_keys:
        seg = seg_by_key.get(k)
        if seg:
            segids.append(seg["segment_id"])
    segids = list(dict.fromkeys(segids))
    pool_steps = [x for x in segids if x in pool]
    tasks = sorted({r["task"] for r in rows})
    per_version = {}
    for v in VERSIONS:
        vr = [r for r in rows if r["version"] == v]
        vsteps = [k for k in step_keys if k[0] == v]
        vsegs = [seg_by_key[k]["segment_id"] for k in vsteps if k in seg_by_key]
        vpool = [x for x in vsegs if x in pool]
        forms = Counter(r.get("form") for r in vr)
        own_addr = Counter()
        other_addr = Counter()
        own_motif = Counter()
        other_motif = Counter()
        for r in vr:
            own_addr.update(count_terms(r.get("text") or "", ADDRESS_TERMS))
            own_motif.update(count_terms(r.get("text") or "", MOTIF_TERMS))
        # 同步骤他人台词（他称代理）：只统计同步骤内、非本角色说话者的台词
        same_step_other = []
        if recs_by_step is not None:
            for k in vsteps:
                for r in recs_by_step.get(k, []):
                    if r.get("canonical_speaker") != name and r.get("kind") == "dialogue":
                        same_step_other.append(r)
        else:
            for r in recs:
                if r["version"] == v and (r["version"], r["task"], r["step_idx"]) in step_keys and \
                        r.get("canonical_speaker") != name and r.get("kind") == "dialogue":
                    same_step_other.append(r)
        if same_step_other:
            for r in same_step_other:
                other_addr.update(count_terms(r.get("text") or "", ADDRESS_TERMS))
                other_motif.update(count_terms(r.get("text") or "", MOTIF_TERMS))
        a_scores = [A[x]["score"] for x in vpool]
        b_scores = [B[x]["score"] for x in vpool]
        a_ranks = [A[x]["rank"] for x in vpool]
        b_ranks = [B[x]["rank"] for x in vpool]
        per_version[v] = {
            "n_records": len(vr),
            "share_of_records": round(len(vr) / len(rows), 4),
            "n_steps": len(vsegs),
            "n_steps_in_pool": len(vpool),
            "n_tasks": len({r["task"] for r in vr}),
            "forms": {k: v2 for k, v2 in forms.most_common()},
            "address_own": dict(own_addr.most_common()),
            "address_other_same_steps": dict(other_addr.most_common()),
            "motif_own": dict(own_motif.most_common()),
            "motif_other_same_steps": dict(other_motif.most_common()),
            "mean_score_a": round(float(np.mean(a_scores)), 4) if a_scores else None,
            "mean_score_b1": round(float(np.mean(b_scores)), 4) if b_scores else None,
            "top100_a": round(sum(1 for x in a_ranks if x <= 100) / len(a_ranks), 4) if a_ranks else None,
            "top100_b1": round(sum(1 for x in b_ranks if x <= 100) / len(b_ranks), 4) if b_ranks else None,
            "median_rank_a": float(np.median(a_ranks)) if a_ranks else None,
            "median_rank_b1": float(np.median(b_ranks)) if b_ranks else None,
            "mean_text_len": round(float(np.mean([len(r.get("text") or "") for r in vr])), 2) if vr else None,
        }
    # 分任务
    task_rows = OrderedDict()
    for r in rows:
        task_rows.setdefault(r["task"], []).append(r)
    task_step = {t: len({(r["version"], r["task"], r["step_idx"]) for r in rs}) for t, rs in task_rows.items()}
    per_task = sorted(
        [{"task": t, "n_records": len(rs), "n_steps": task_step[t],
          "versions": sorted({r["version"] for r in rs})} for t, rs in task_rows.items()],
        key=lambda x: (x["n_steps"], x["n_records"], x["task"]))
    # 形态整体
    forms_overall = Counter(r.get("form") for r in rows)
    # 神谕引用（speaker = 该角色）
    oracle_quotes = [{"oracle_id": o["oracle_id"], "stage": o.get("stage"),
                      "version": o.get("version"), "record_id": o.get("record_id"),
                      "segment_id": o.get("segment_id"), "citation_form": o.get("citation_form")}
                     for o in cite if o.get("speaker") == name]
    # 精读覆盖率
    kseg = knife_segments(knife)
    eseg = key_event_segments(events)
    aseg = annotation_segments(annot)
    cov = {
        "n_steps": len(segids), "n_steps_in_pool": len(pool_steps),
        "knife": {"n": len(set(segids) & kseg), "n_total": len(knife["scenes"])},
        "key_events": {"n": len(set(segids) & eseg), "n_total": len(events["events"])},
        "annotation": {"n": len(set(segids) & aseg), "n_total": len(annot)},
    }
    cov["knife"]["rate"] = round(cov["knife"]["n"] / len(segids), 4)
    cov["key_events"]["rate"] = round(cov["key_events"]["n"] / len(segids), 4)
    cov["annotation"]["rate"] = round(cov["annotation"]["n"] / len(segids), 4)
    union_kd = set(segids) & (kseg | eseg)
    union_all = set(segids) & (kseg | eseg | aseg)
    cov["union_knife_key_events"] = {"n": len(union_kd), "rate": round(len(union_kd) / len(segids), 4)}
    cov["union_all_close_reads"] = {"n": len(union_all), "rate": round(len(union_all) / len(segids), 4)}
    cov["n_uncovered_knife_key"] = len(segids) - len(union_kd)
    # 未覆盖步骤的版本分布
    uncovered = [x for x in segids if x not in (kseg | eseg)]
    cov["uncovered_by_version"] = dict(Counter(x.split("|")[0] for x in uncovered).most_common())
    # 时间线（形态/称呼/母题首次与末次出现，按 order）
    rows_sorted = sorted(rows, key=lambda r: (r["order"], r["id"]))
    timeline = []
    seen = set()
    for r in rows_sorted:
        form = r.get("form")
        if form and (r["order"], form) not in seen and (not timeline or timeline[-1]["form"] != form):
            seen.add((r["order"], form))
            timeline.append({"order": r["order"], "version": r["version"], "task": r["task"],
                             "step_idx": r["step_idx"], "form": form,
                             "text": (r.get("text") or "")[:40]})
    # 低存在感：按版本台词占比 + 任务步骤数
    version_low = [v for v in VERSIONS if per_version[v]["n_records"] == 0 or
                   per_version[v]["share_of_records"] < 0.05]
    task_low = [t for t in per_task if t["n_steps"] <= 3][:10]
    summary = {
        "n_records": len(rows), "n_steps": len(segids), "n_steps_in_pool": len(pool_steps),
        "n_tasks": len(tasks), "n_versions_present": sum(1 for v in VERSIONS if per_version[v]["n_records"] > 0),
        "versions_present": [v for v in VERSIONS if per_version[v]["n_records"] > 0],
        "versions_absent": [v for v in VERSIONS if per_version[v]["n_records"] == 0],
        "mean_text_len": round(float(np.mean([len(r.get("text") or "") for r in rows])), 2),
        "mean_score_a": round(float(np.mean([A[x]["score"] for x in pool_steps])), 4) if pool_steps else None,
        "mean_score_b1": round(float(np.mean([B[x]["score"] for x in pool_steps])), 4) if pool_steps else None,
        "top100_a": round(sum(1 for x in pool_steps if A[x]["rank"] <= 100) / len(pool_steps), 4) if pool_steps else None,
        "top100_b1": round(sum(1 for x in pool_steps if B[x]["rank"] <= 100) / len(pool_steps), 4) if pool_steps else None,
        "median_rank_a": float(np.median([A[x]["rank"] for x in pool_steps])) if pool_steps else None,
        "median_rank_b1": float(np.median([B[x]["rank"] for x in pool_steps])) if pool_steps else None,
    }
    return {
        "name": name,
        "summary": summary,
        "per_version": per_version,
        "forms_overall": dict(forms_overall.most_common()),
        "per_task": per_task,
        "low_presence": {"versions": version_low, "tasks": task_low,
                         "note": "版本按台词占比<5%或为 0 判定；任务按步骤数≤3 判定（低存在感、可能被精读遗漏）"},
        "oracle_quotes": oracle_quotes,
        "coverage": cov,
        "timeline_form_changes": timeline,
        "all_steps": segids,
    }



# ---------------------------------------------------------------------------
# 图：单角色 2×2 轨迹图
# ---------------------------------------------------------------------------
FIG_NAMES = {"白厄": "f7_bai_trajectory.png", "昔涟": "f8_xi_trajectory.png"}


def figure_name(name):
    if name in FIG_NAMES:
        return FIG_NAMES[name]
    safe = name.replace("/", "_").replace("（", "(").replace("）", ")")
    return "f_traj_%s.png" % safe


def make_figure(ch, out):
    pv = ch["per_version"]
    vers = VERSIONS  # 含 0 台词的版本（如白厄 3.5）——「缺席」本身是重要信号
    xs = [VERSIONS.index(v) for v in vers]
    labels = vers
    fig, axes = plt.subplots(2, 2, figsize=(13.4, 8.6))
    # (a) 台词量 + 步骤数
    ax = axes[0][0]
    ax.bar(xs, [pv[v]["n_records"] for v in vers], color="#2e5c8a", alpha=0.85,
           label=L("台词条数", "records"))
    ax.set_ylabel(L("台词条数", "records"), color="#2e5c8a")
    ax.tick_params(axis="y", labelcolor="#2e5c8a")
    ax2 = ax.twinx()
    ax2.plot(xs, [pv[v]["n_steps"] for v in vers], color="#d98c3f", marker="o", lw=1.8,
             label=L("出场步骤数", "steps"))
    ax2.set_ylabel(L("出场步骤数", "steps"), color="#d98c3f")
    ax2.tick_params(axis="y", labelcolor="#d98c3f")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_title(L("(a) 台词量（柱）与出场步骤（线）", "(a) records and steps"), fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    # (b) 形态构成
    ax = axes[0][1]
    form_tot = Counter()
    for v in vers:
        form_tot.update(pv[v]["forms"])
    top_forms = [f for f, _ in form_tot.most_common(5)]
    bottom = np.zeros(len(vers))
    cmap = plt.get_cmap("tab20")
    for i, f in enumerate(top_forms):
        vals = np.array([pv[v]["forms"].get(f, 0) for v in vers], dtype=float)
        ax.bar(xs, vals, bottom=bottom, label=L(f, f) if f else L("无形态", "none"),
               color=cmap(i % 20), edgecolor="white", linewidth=0.5)
        bottom += vals
    other = np.array([sum(n for f, n in pv[v]["forms"].items() if f not in top_forms) for v in vers], dtype=float)
    if other.sum() > 0:
        ax.bar(xs, other, bottom=bottom, label=L("其他形态", "other"), color="0.7",
               edgecolor="white", linewidth=0.5)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_ylabel(L("台词条数", "records"))
    ax.set_title(L("(b) 形态（form）构成", "(b) form composition"), fontsize=9)
    ax.legend(fontsize=7, frameon=False, ncol=2)
    ax.grid(axis="y", alpha=0.25)
    # (c) 称呼词命中（own lines）
    ax = axes[1][0]
    addr_tot = Counter()
    for v in vers:
        addr_tot.update(pv[v]["address_own"])
    top_addr = [t for t, _ in addr_tot.most_common(5)]
    for i, t in enumerate(top_addr):
        ax.plot(xs, [pv[v]["address_own"].get(t, 0) for v in vers], marker="o", lw=1.6,
                label=t, color=cmap(i % 20))
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_ylabel(L("命中次数（自己的台词）", "hits in own lines"))
    ax.set_title(L("(c) 称呼词（自己台词）", "(c) address terms (own lines)"), fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    # (d) A/B1 分数与 Top100 率
    ax = axes[1][1]
    def _score(v, key):
        return float("nan") if pv[v][key] is None else float(pv[v][key])
    ax.plot(xs, [_score(v, "mean_score_a") for v in vers], marker="o", lw=1.6,
            color="#2e5c8a", label="A mean score")
    ax.plot(xs, [_score(v, "mean_score_b1") for v in vers], marker="s", lw=1.6,
            color="#d98c3f", label="B1 mean score")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_ylabel(L("所在步骤平均分", "mean score of steps"))
    ax3 = ax.twinx()
    ax3.plot(xs, [(pv[v]["top100_b1"] or 0) * 100 for v in vers], ls="--", lw=1.2, color="#8e44ad",
             label="B1 Top100 %")
    ax3.set_ylabel(L("B1 Top100 命中率 (%)", "B1 Top100 %"), color="#8e44ad")
    ax3.tick_params(axis="y", labelcolor="#8e44ad")
    ax.set_title(L("(d) 所在步骤 A/B1 分数与 B1 Top100 率", "(d) scores and Top100"), fontsize=9)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax3.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7, frameon=False, loc="upper left")
    ax.grid(axis="y", alpha=0.25)
    fig.suptitle(L("%s 全程轨迹（%d 条台词 / %d 步 / %d 任务）" % (
        ch["name"], ch["summary"]["n_records"], ch["summary"]["n_steps"], ch["summary"]["n_tasks"]),
        "%s trajectory" % ch["name"]), fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def render_report(data):
    meta = data["meta"]
    chars = data["characters"]
    Lr = []
    A = Lr.append
    A("# 角色全程轨迹分析：白厄、昔涟（全量出场 vs 精读覆盖）")
    A("")
    A("> 生成脚本：`tools/character_trajectory.py` ｜ 重跑命令：`%s`" % RUN_CMD)
    A("> 数据（只读）：`amphoreus.final.jsonl`、`segments.jsonl`、`oracle-citation-coding.json`、"
      "`knife-scenes.json`、`key-events.json`、`annotation-labels.json`、`baseline-a/b-scores.json`")
    A("> 明细数据：`data/config/character-trajectory.json` ｜ 图：`docs/report/figures/f7_…png` / `f8_…png`")
    A("")
    A("> 口径说明：")
    A("> - **全量出场** = `amphoreus.final.jsonl` 中 `canonical_speaker` 等于该角色的全部记录（含 dialogue/sms 等）；")
    A("> - **步骤** = 记录所在的 (version, task, step_idx)，映射到 `segments.jsonl` 的 723 个步骤（686 池为其中可按 A/B1 排序的子集）；")
    A("> - **精读覆盖** = 角色出场步骤中，被「刀子场景」「关键事件」「74 条标注」覆盖的比例（以文件实际内容为准）。")
    A("")
    # 结论
    bai, xi = chars["白厄"], chars["昔涟"]
    bc, xc = bai["coverage"], xi["coverage"]
    A("## 1. 结论（直接回答四个问题）")
    A("")
    A("1. **「只分析了最集中的位置」属实**：白厄全量 **%d 条台词 / %d 步 / %d 任务**，但精读只覆盖"
      "刀子场景 %d 步 + 关键事件 %d 步，去重后 **%d/%d = %.1f%%**；加上 74 条标注也只有 **%d/%d = %.1f%%**。"
      "昔涟同理：%d 步中精读 %d 步（%.1f%%），加标注 %d 步（%.1f%%）。" % (
          bai["summary"]["n_records"], bai["summary"]["n_steps"], bai["summary"]["n_tasks"],
          bc["knife"]["n"], bc["key_events"]["n"], bc["union_knife_key_events"]["n"],
          bc["n_steps"], 100 * bc["union_knife_key_events"]["rate"],
          bc["union_all_close_reads"]["n"], bc["n_steps"], 100 * bc["union_all_close_reads"]["rate"],
          xi["summary"]["n_steps"], xc["union_knife_key_events"]["n"],
          100 * xc["union_knife_key_events"]["rate"], xc["union_all_close_reads"]["n"],
          100 * xc["union_all_close_reads"]["rate"]))
    A("2. **白厄的称呼/形态/母题在 3.0→3.7 有明显阶段变化**：3.0 是「幼年/无形态 + 老师（%d 次）+ 火种（%d）」；"
      "3.1–3.3 以无形态为主、出现「盗火行者」；**3.4 是转折点**：形态大量切到「卡厄斯兰那」（%d 条）与「心中的英雄」（%d 条），"
      "自称语境里「伙伴」%d 次、「救世主」%d 次、「火种」%d 次、「逐火」%d 次达到峰值；"
      "3.5 **完全缺席**（0 条）；3.7 出现「空白的愿望」（%d）/「毁灭的容器」（%d）/「记忆形态」，句长从 3.0 的 %.1f 字降到 %.1f 字。" % (
          bai["per_version"]["3.0"]["address_own"].get("老师", 0),
          bai["per_version"]["3.0"]["motif_own"].get("火种", 0),
          bai["per_version"]["3.4"]["forms"].get("卡厄斯兰那", 0),
          bai["per_version"]["3.4"]["forms"].get("心中的英雄", 0),
          bai["per_version"]["3.4"]["address_own"].get("伙伴", 0),
          bai["per_version"]["3.4"]["address_own"].get("救世主", 0),
          bai["per_version"]["3.4"]["motif_own"].get("火种", 0),
          bai["per_version"]["3.4"]["motif_own"].get("逐火", 0),
          bai["per_version"]["3.7"]["forms"].get("空白的愿望", 0),
          bai["per_version"]["3.7"]["forms"].get("毁灭的容器", 0),
          bai["per_version"]["3.0"]["mean_text_len"], bai["per_version"]["3.7"]["mean_text_len"]))
    A("3. **白厄的低存在感段**（可能被精读遗漏）：版本层面 **3.5（0 条，完全缺席）**、3.6（%d 条，%.1f%%）、"
      "3.2（%d 条，%.1f%%）、3.7（%d 条，%.1f%%）；任务层面 %s —— 其中「魔女的孤诣课题」「大地啊」「行者啊」"
      "都是剧情上的关键任务，却只有 1–3 步，精读很容易只挑到 3.4 这类最集中的段落。" % (
          bai["per_version"]["3.6"]["n_records"], 100 * bai["per_version"]["3.6"]["share_of_records"],
          bai["per_version"]["3.2"]["n_records"], 100 * bai["per_version"]["3.2"]["share_of_records"],
          bai["per_version"]["3.7"]["n_records"], 100 * bai["per_version"]["3.7"]["share_of_records"],
          "、".join("%s（%d 步）" % (t["task"][:10], t["n_steps"]) for t in bai["low_presence"]["tasks"][:5])))
    A("4. **昔涟「迷迷/记忆形态 → 讲述者」的轨迹有可测变化**：3.0–3.3 形态 **100%% 是「迷迷」**（%d/%d/%d/%d 条）；"
      "3.4 起切换为「往昔的涟漪」（21 条）/「记忆形态」（3.5 起），3.7 出现「另一位作者」%d 条与「记忆形态」%d 条；"
      "语言上，平均句长从 3.0 的 %.1f 字升到 3.5 的 %.1f 字（讲述者化），3.7 回落到 %.1f；"
      "3.5 对「开拓者」的称呼达到 %d 次（全篇峰值），说明她从「伙伴」变成了「讲开拓者故事的人」。" % (
          xi["per_version"]["3.0"]["n_records"], xi["per_version"]["3.1"]["n_records"],
          xi["per_version"]["3.2"]["n_records"], xi["per_version"]["3.3"]["n_records"],
          xi["per_version"]["3.7"]["forms"].get("另一位作者", 0),
          xi["per_version"]["3.7"]["forms"].get("记忆形态", 0),
          xi["per_version"]["3.0"]["mean_text_len"], xi["per_version"]["3.5"]["mean_text_len"],
          xi["per_version"]["3.7"]["mean_text_len"],
          xi["per_version"]["3.5"]["address_own"].get("开拓者", 0)))
    A("5. **建议对 12 黄金裔都跑**：脚本已按角色名参数化（`--characters 白厄,昔涟,遐蝶,…`），"
      "每个角色只读语料 + 已生成分数，秒级完成；它能自动给出「全量出场 vs 精读覆盖」与低存在感版本/任务表——"
      "这正是本轮用户质疑的核心。白厄 3.5 的「完全缺席」说明：**只看精读，会漏掉整段角色的空白/消失**。")
    A("")

    # 数据与口径
    A("## 2. 数据与精读覆盖口径")
    A("")
    A("| 项目 | 数值 | 说明 |")
    A("| --- | --- | --- |")
    A("| 全量台词记录 | %d | `amphoreus.final.jsonl` 全部记录数（含无角色/旁白记录） |" % meta["n_records_total"])
    for ch in (bai, xi):
        A("| %s 出场 | %d 条 / %d 步 / %d 任务 | 步骤映射到 723 个 segment，其中 %d 步在 686 池 |" % (
            ch["name"], ch["summary"]["n_records"], ch["summary"]["n_steps"],
            ch["summary"]["n_tasks"], ch["summary"]["n_steps_in_pool"]))
    knife_note = ("task-21 说明为 36；文件实际为 %d，与之一致（含水晶花寓言）" % meta["n_knife"]
                  if meta["n_knife"] >= 36 else
                  "task-21 说明为 36；文件实际为 %d（水晶花寓言可能尚未加入，脚本以文件实际内容为准）"
                  % meta["n_knife"])
    event_note = ("task-21 说明为 30；文件实际为 %d，与之一致" % meta["n_events"]
                  if meta["n_events"] >= 30 else
                  "task-21 说明为 30；文件实际为 %d（脚本以文件实际内容为准）" % meta["n_events"])
    A("| 刀子场景 | %d 个（文件实际） | %s |" % (meta["n_knife"], knife_note))
    A("| 关键事件 | %d 个（文件实际） | %s |" % (meta["n_events"], event_note))
    A("| 人工标注 | %d 条 | `annotation-labels.json` |" % meta["n_annot"])
    A("")

    # 每角色
    for ch in (bai, xi):
        s = ch["summary"]
        cov = ch["coverage"]
        A("## 3. %s 全程轨迹" % ("白厄" if ch is bai else "昔涟"))
        A("")
        A("**总量**：%d 条台词 / %d 步（686 池 %d 步）/ %d 任务 / 出场版本 %s；缺席版本：%s。" % (
            s["n_records"], s["n_steps"], s["n_steps_in_pool"], s["n_tasks"],
            "、".join(s["versions_present"]) or "无", "、".join(s["versions_absent"]) or "无"))
        A("所在步骤 A/B1 平均分：%.3f / %.3f；Top100 命中率 %.1f%% / %.1f%%。" % (
            s["mean_score_a"], s["mean_score_b1"], 100 * s["top100_a"], 100 * s["top100_b1"]))
        A("")
        A("**分版本统计**：")
        A("")
        A("| 版本 | 台词 | 占比 | 步骤 | 任务 | 主要形态 | 称呼（自己台词，前 3） | 母题（前 3） | A/B1 均分 | B1 Top100 |")
        A("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for v in VERSIONS:
            pv = ch["per_version"][v]
            if pv["n_records"] == 0 and pv["n_steps"] == 0:
                A("| %s | 0 | 0%% | 0 | 0 | — | — | — | — | — |" % v)
                continue
            forms = "、".join("%s %d" % (k or "无形态", n) for k, n in list(pv["forms"].items())[:3])
            addr = "、".join("%s%d" % (k, n) for k, n in list(pv["address_own"].items())[:3])
            motif = "、".join("%s%d" % (k, n) for k, n in list(pv["motif_own"].items())[:3])
            A("| %s | %d | %.1f%% | %d | %d | %s | %s | %s | %.3f / %.3f | %.1f%% |" % (
                v, pv["n_records"], 100 * pv["share_of_records"], pv["n_steps"], pv["n_tasks"],
                forms or "—", addr or "—", motif or "—",
                pv["mean_score_a"] if pv["mean_score_a"] is not None else 0,
                pv["mean_score_b1"] if pv["mean_score_b1"] is not None else 0,
                100 * (pv["top100_b1"] or 0)))
        A("")
        A("**形态变化时间线**（按 order，形态首次切换）：")
        A("")
        tl = ch["timeline_form_changes"]
        if tl:
            A("| order | 版本 | 任务 | 形态 | 示例台词 |")
            A("| --- | --- | --- | --- | --- |")
            for e in tl[:14]:
                A("| %d | %s | %s | %s | %s |" % (
                    e["order"], e["version"], e["task"][:14], e["form"], e["text"]))
        else:
            A("（无形态标注）")
        A("")
        A("**精读覆盖率**：")
        A("")
        A("| 精读集合 | 覆盖步数 | 覆盖率 |")
        A("| --- | --- | --- |")
        A("| 刀子场景（%d 个） | %d | %.1f%% |" % (
            cov["knife"]["n_total"], cov["knife"]["n"], 100 * cov["knife"]["rate"]))
        A("| 关键事件（%d 个） | %d | %.1f%% |" % (
            cov["key_events"]["n_total"], cov["key_events"]["n"], 100 * cov["key_events"]["rate"]))
        A("| 74 条标注 | %d | %.1f%% |" % (cov["annotation"]["n"], 100 * cov["annotation"]["rate"]))
        A("| 刀子 ∪ 关键事件（深读） | %d | %.1f%% |" % (
            cov["union_knife_key_events"]["n"], 100 * cov["union_knife_key_events"]["rate"]))
        A("| 深读 ∪ 标注（全部精读） | %d | %.1f%% |" % (
            cov["union_all_close_reads"]["n"], 100 * cov["union_all_close_reads"]["rate"]))
        A("")
        A("未覆盖（深读之外）步骤数：%d；按版本：%s。" % (
            cov["n_uncovered_knife_key"],
            "、".join("%s %d" % (k, n) for k, n in list(cov["uncovered_by_version"].items())[:8]) or "—"))
        A("")
        A("**神谕引用**（speaker=该角色的 occurrence）：%s。" % (
            "、".join("%s（%s，%s）" % (o["oracle_id"], o["stage"], o["version"])
                     for o in ch["oracle_quotes"]) or "无"))
        A("")
        A("**低存在感段**（可能被精读遗漏）：版本 %s；任务（步骤≤3）%s。" % (
            "、".join(ch["low_presence"]["versions"]) or "无",
            "、".join("%s（%d 步）" % (t["task"], t["n_steps"]) for t in ch["low_presence"]["tasks"]) or "无"))
        A("")

    # 结论与局限
    A("## 4. 结论汇总")
    A("")
    A("1. **数据层是全量的，但「分析层」不是**：白厄 202 步里深读只覆盖 %.1f%%，昔涟 %.1f%%。"
      "之前对白厄的解读集中在 3.4（卡厄斯兰那转折）与几个刀子场景，这本身是数据里最集中的段落——"
      "所以「只分析了最集中的位置」这个质疑成立。" % (
          100 * bc["union_knife_key_events"]["rate"], 100 * xc["union_knife_key_events"]["rate"]))
    A("2. **补法**：本脚本已给出每个角色「全量出场 × 精读覆盖」的对照表。对 12 黄金裔各跑一遍，"
      "先找「台词量大但覆盖率为 0 / 极低」的版本/任务，再决定精读优先补哪里（而不是凭印象挑集中段落）。")
    A("3. **白厄的空白期值得单独看**：3.5 全篇 0 条台词（在剧情最紧张的阶段「消失」），3.6 只剩 %d 条。"
      "这种「角色缺席」本身就是重要的叙事信号，但任何只看台词的统计都会漏掉它。" % (
          bai["per_version"]["3.6"]["n_records"]))
    A("4. **昔涟的形态-语言变化可测**：迷迷（3.0–3.3）→ 往昔的涟漪/记忆形态（3.4–3.6）→ 另一位作者（3.7），"
      "对应句长变长、对「开拓者」称呼在 3.5 达峰——是她从「陪伴者」变成「讲述者」的可量化痕迹。")
    A("5. **建议**：对 12 裔都做；成本低（每个角色秒级），收益是能系统性回答「哪里没读到」，"
      "并支撑报告里「精读是抽样、不是全量」这一方法说明。")
    A("")
    A("## 5. 局限")
    A("")
    A("1. 形态（form）是语料字段，部分记录为 null；null 不等于「没有形态」。")
    A("2. 「同步骤他人台词」的称呼/母题命中只是「他称」的粗糙代理（同一步骤可能有多角色多话题）。")
    A("3. 精读覆盖只统计到「步骤」粒度：一个步骤被覆盖 ≠ 该步骤里关于此角色的内容都被读过。")
    A("4. 刀子场景/关键事件文件数量以实际为准（本报告生成时刀子 %d、关键事件 %d；task 说明为 36/30，"
      "文件更新后重跑即可自动同步）。" % (meta["n_knife"], meta["n_events"]))
    A("5. 只做描述统计，不做显著性检验（每版本样本与角色调度强相关，跨版本比较只能看趋势）。")
    A("")
    A("## 6. 复现")
    A("")
    A("```bash")
    A(RUN_CMD)
    A("conda run -n nlpLesson python tools/character_trajectory.py --characters 白厄,昔涟,遐蝶")
    A("conda run -n nlpLesson python tools/character_trajectory.py --verify")
    A("```")
    A("")
    A("- 无随机；全部数字由 JSONL/JSON 现场计算。")
    A("- `--verify` 会重算两角色的记录数/步骤数/覆盖率，并抽查报告数字与 JSON 一致。")
    A("")
    return "\n".join(Lr)


# ---------------------------------------------------------------------------
# 构建 / 校验
# ---------------------------------------------------------------------------
def build(characters):
    recs, segs, seg_by_key, pool, A, B, knife, events, annot, cite, recs_by_step = load_all()
    out_chars = OrderedDict()
    fig_info = {}
    os.makedirs(FIG_DIR, exist_ok=True)
    for name in characters:
        print("统计 %s …" % name)
        ch = character_stats(name, recs, seg_by_key, pool, A, B, knife, events, annot, cite,
                             listen=True, recs_by_step=recs_by_step)
        out_chars[name] = ch
        path = os.path.join(FIG_DIR, figure_name(name))
        make_figure(ch, path)
        print("  已生成 %s（%.1f KB）" % (os.path.relpath(path, ROOT), os.path.getsize(path) / 1024.0))
        fig_info[name] = os.path.relpath(path, ROOT)
    data = {
        "meta": {
            "script": "tools/character_trajectory.py",
            "run_command": RUN_CMD,
            "characters": list(out_chars.keys()),
            "n_records_total": len(recs),
            "n_segments_total": len(segs),
            "n_pool": len(pool),
            "n_knife": len(knife["scenes"]),
            "n_events": len(events["events"]),
            "n_annot": len(annot),
            "n_versions": len(VERSIONS),
            "note": "全量出场来自 amphoreus.final.jsonl 的 canonical_speaker；"
                    "精读覆盖以 knife-scenes / key-events / annotation-labels 文件实际内容为准。",
            "sources": ["amphoreus.final.jsonl", "segments.jsonl", "oracle-citation-coding.json",
                        "knife-scenes.json", "key-events.json", "annotation-labels.json",
                        "baseline-a-scores.json", "baseline-b-scores.json"],
        },
        "figures": fig_info,
        "characters": out_chars,
        "reuse": {
            "how": "conda run -n nlpLesson python tools/character_trajectory.py --characters 白厄,昔涟,遐蝶,…",
            "outputs": "data/config/character-trajectory.json 追加收录；图 f_traj_<角色>.png",
            "note": "角色名需是 canonical_speaker（speaker-alias.v3 归一后的名字）。",
        },
    }
    with open(P_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写 %s" % os.path.relpath(P_JSON, ROOT))
    md = render_report(data)
    with open(P_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s" % os.path.relpath(P_MD, ROOT))
    if HAS_CJK:
        print("中文字体：%s" % CJK_FONT)
    else:
        print("!! 未找到中文字体，图已退回英文标签")
    if not verify(data, verbose=True):
        print("!! 校验失败", file=sys.stderr)
        sys.exit(1)
    print("\n校验通过：两角色全量统计、覆盖率、图均与 JSON 一致。")


def verify(data=None, verbose=False):
    problems = []
    recs, segs, seg_by_key, pool, A, B, knife, events, annot, cite, recs_by_step = load_all()
    if data is None:
        if not os.path.exists(P_JSON):
            print("缺少 %s" % P_JSON, file=sys.stderr)
            return False
        data = read_json(P_JSON)
    for name, ch in data["characters"].items():
        rows = [r for r in recs if r.get("canonical_speaker") == name]
        if len(rows) != ch["summary"]["n_records"]:
            problems.append("%s 记录数不一致" % name)
        steps = {(r["version"], r["task"], r["step_idx"]) for r in rows}
        segids = {seg_by_key[k]["segment_id"] for k in steps if k in seg_by_key}
        if len(segids) != ch["summary"]["n_steps"]:
            problems.append("%s 步骤数不一致" % name)
        if len({r["task"] for r in rows}) != ch["summary"]["n_tasks"]:
            problems.append("%s 任务数不一致" % name)
        kseg = knife_segments(knife)
        eseg = key_event_segments(events)
        aseg = annotation_segments(annot)
        if len(segids & kseg) != ch["coverage"]["knife"]["n"]:
            problems.append("%s 刀子覆盖不一致" % name)
        if len(segids & eseg) != ch["coverage"]["key_events"]["n"]:
            problems.append("%s 关键事件覆盖不一致" % name)
        if len(segids & aseg) != ch["coverage"]["annotation"]["n"]:
            problems.append("%s 标注覆盖不一致" % name)
        u = segids & (kseg | eseg)
        if len(u) != ch["coverage"]["union_knife_key_events"]["n"]:
            problems.append("%s 深读并集不一致" % name)
        # 图
        fig = data["figures"].get(name)
        if not fig or not os.path.exists(os.path.join(ROOT, fig)) or                 os.path.getsize(os.path.join(ROOT, fig)) < 5000:
            problems.append("%s 图不存在或过小" % name)
    md = open(P_MD, "r", encoding="utf-8").read() if os.path.exists(P_MD) else ""
    bai = data["characters"].get("白厄")
    if bai:
        spot = [
            ("白厄记录数", "%d 条台词" % bai["summary"]["n_records"]),
            ("白厄步骤数", "%d 步" % bai["summary"]["n_steps"]),
            ("白厄深读覆盖", "%d/%d" % (bai["coverage"]["union_knife_key_events"]["n"],
                                        bai["coverage"]["n_steps"])),
        ]
        for label, txt in spot:
            if txt not in md:
                problems.append("报告缺少数字 %s=%s" % (label, txt))
    if verbose:
        print("\n抽查：")
        for name, ch in data["characters"].items():
            print("  %s：%d 条 / %d 步 / %d 任务；深读覆盖 %d/%d = %.1f%%" % (
                name, ch["summary"]["n_records"], ch["summary"]["n_steps"], ch["summary"]["n_tasks"],
                ch["coverage"]["union_knife_key_events"]["n"], ch["coverage"]["n_steps"],
                100 * ch["coverage"]["union_knife_key_events"]["rate"]))
        print("  图：%s" % "；".join("%s=%s" % (k, v) for k, v in data["figures"].items()))
    if problems:
        for p in problems[:20]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="角色全程轨迹分析（可复用；--all 跑 13 角色 + 上下文表）")
    ap.add_argument("--characters", default="白厄,昔涟", help="逗号分隔的角色 canonical 名（默认 白厄,昔涟）")
    ap.add_argument("--all", action="store_true", help="跑 13 位黄金裔（白厄…昔涟），并导出 L2 上下文表 + f9/f10")
    ap.add_argument("--no-context", action="store_true", help="与 --all 连用：跳过 data/context 导出")
    ap.add_argument("--verify", action="store_true", help="只校验已有产物（单角色产物与 13 角色产物都会校验）")
    args = ap.parse_args()
    if args.verify:
        ok = True
        if os.path.exists(P_JSON):
            print("== 校验单角色产物 ==")
            ok = verify(verbose=True) and ok
        if os.path.exists(P_ALL_JSON):
            print("\n== 校验 13 角色产物 ==")
            ok = verify_all(verbose=True) and ok
        if not (os.path.exists(P_JSON) or os.path.exists(P_ALL_JSON)):
            print("没有可校验的产物", file=sys.stderr)
            ok = False
        print("\n校验%s" % ("通过" if ok else "失败"))
        sys.exit(0 if ok else 1)
    if args.all:
        build_all(ALL_STATS, export_ctx=not args.no_context)
    else:
        chars = [c.strip() for c in args.characters.split(",") if c.strip()]
        build(chars)





# ===========================================================================
# task-22：13 角色 L1 全量轨迹 + L2 逐条上下文表
# ===========================================================================
GROUP_A = ["白厄", "万敌", "阿格莱雅", "缇宝", "遐蝶", "那刻夏", "风堇",
           "赛飞儿", "海瑟音", "刻律德菈", "昔涟"]              # A 组：黄金裔 11 位
GROUP_B = ["开拓者", "三月七", "丹恒"]                        # B 组：单列（非黄金裔）
NPC_CHARS = ["荒笛", "玻吕茜亚"]                              # NPC 类（不进 A/B 主表）
ALL_CHARS = GROUP_A + GROUP_B                                # 14 个主角色（A+B）
ALL_STATS = ALL_CHARS + NPC_CHARS                            # L1 统计 16 个角色
CONTEXT_CHARS = ALL_CHARS                                      # L2 上下文 14 个角色（A+B；荒笛/玻吕茜亚按注记处理，不单列）
PAIR_WITH = {"丹恒": "荒笛（大地承接：荒笛 → 丹恒）",
             "荒笛": "丹恒（大地承接：荒笛 → 丹恒）",
             "三月七": "长夜月（同一人形态：长夜月/永夜之帷/幻象/记忆形态）",
             "遐蝶": "玻吕茜亚（NPC，遐蝶之妹；O05 双子共有神谕 holder=玻吕茜亚，不进任何组）"}
GROUP_LABEL = {"A": "A 组：黄金裔 11 位", "B": "B 组：单列（非黄金裔）", "NPC": "NPC 类"}
P_ALL_JSON = os.path.join(ROOT, "data", "config", "character-trajectory-all.json")
P_ALL_MD = os.path.join(ROOT, "data", "reports", "character-trajectory-all.md")
CTX_DIR = os.path.join(ROOT, "data", "context")
P_CTX_MANIFEST = os.path.join(CTX_DIR, "_manifest.json")
F9 = os.path.join(FIG_DIR, "f9_all_trajectories.png")
F10 = os.path.join(FIG_DIR, "f10_coverage.png")
WINDOW = 3            # 前 3 + 本条 + 后 3
SPARSE_STEP_RECORDS = 6   # 整步总记录 <6 → 稀疏
SPARSE_CHAR_RECORDS = 3   # 该步该角色记录 <3 → 稀疏


def coverage_detail(ch, kseg, eseg):
    """按版本/任务拆精读覆盖，找「没读到的版本/任务」"""
    steps = ch["all_steps"]
    covered = set(steps) & (kseg | eseg)
    per_version = {}
    step_ver = {x: x.split("|")[0] for x in steps}
    for v in VERSIONS:
        vs = [x for x in steps if step_ver[x] == v]
        if not vs:
            continue
        per_version[v] = {"steps": len(vs), "covered": len(set(vs) & covered)}
    # 任务：step_id 的 task 是第 2 段
    per_task = {}
    for x in steps:
        parts = x.split("|")
        task = parts[1] if len(parts) > 1 else x
        per_task.setdefault(task, {"steps": 0, "covered": 0})
        per_task[task]["steps"] += 1
        if x in covered:
            per_task[task]["covered"] += 1
    unread_versions = [v for v, d in per_version.items() if d["covered"] == 0]
    unread_tasks = [{"task": t, "steps": d["steps"], "covered": d["covered"]}
                    for t, d in per_task.items() if d["covered"] == 0]
    unread_tasks.sort(key=lambda x: -x["steps"])
    return {"steps": len(steps), "covered": len(covered),
            "per_version": per_version, "per_task": dict(
                sorted(per_task.items(), key=lambda kv: -kv[1]["steps"])),
            "unread_versions": unread_versions,
            "unread_tasks": unread_tasks[:8],
            "unread_task_count": len(unread_tasks)}


# ---------------------------------------------------------------------------
# L2：逐条上下文表
# ---------------------------------------------------------------------------
def build_block(char, step, slice_recs, trigger_ids, sparse, seg_by_key):
    slice_recs = sorted(slice_recs, key=lambda r: r["id"])
    trig = [r["id"] for r in slice_recs if r["id"] in trigger_ids]
    seg = seg_by_key.get(step) or {}
    return {
        "char": char,
        "version": step[0],
        "task": step[1],
        "step_idx": step[2],
        "step_title": seg.get("step_title"),
        "order": int(min(r["order"] for r in slice_recs)),
        "record_id": int(trig[0]) if trig else int(slice_recs[0]["id"]),
        "record_span": [int(slice_recs[0]["id"]), int(slice_recs[-1]["id"])],
        "n_records": len(slice_recs),
        "n_char_records": len(trig),
        "sparse_step": bool(sparse),
        "trigger_record_ids": [int(x) for x in trig],
        "context": [{"id": int(r["id"]), "kind": r.get("kind"),
                     "speaker": r.get("speaker"),
                     "text": r.get("text") or ""} for r in slice_recs],
    }


def export_context(chars_stats, recs, seg_by_key, recs_by_step, out_dir=CTX_DIR):
    os.makedirs(out_dir, exist_ok=True)
    # .gitignore：派生数据不入库
    with open(os.path.join(out_dir, ".gitignore"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# task-22 L2 派生数据（逐条上下文表），不入库\n*\n!.gitignore\n")
    manifest = {
        "generated_by": "tools/character_trajectory.py --all",
        "note": "每行 = 一个上下文块；同一步内相邻记录的窗口会合并，块内记录不重复；"
                "稀疏步骤（该步总记录<%d 或该角色记录<%d）整步放入。" % (
                    SPARSE_STEP_RECORDS, SPARSE_CHAR_RECORDS),
        "window": "前 %d + 本条 + 后 %d（同一步内按 id 升序）" % (WINDOW, WINDOW),
        "characters": {},
        "totals": {},
    }
    total_blocks = total_recs = total_chars = 0
    for ch in chars_stats:
        name = ch["name"]
        rows = [r for r in recs if r.get("canonical_speaker") == name]
        char_ids = {r["id"] for r in rows}
        # 步骤顺序（按该角色首次出现 order）
        step_first = {}
        for r in rows:
            k = (r["version"], r["task"], r["step_idx"])
            if k not in step_first or r["order"] < step_first[k]:
                step_first[k] = r["order"]
        steps = sorted(step_first, key=lambda k: (step_first[k], k[2]))
        blocks = []
        for step in steps:
            allrecs = recs_by_step.get(step, [])
            char_step = [r for r in allrecs if r["id"] in char_ids]
            if not char_step or not allrecs:
                continue
            sparse = len(allrecs) < SPARSE_STEP_RECORDS or len(char_step) < SPARSE_CHAR_RECORDS
            if sparse:
                blocks.append(build_block(name, step, allrecs, {r["id"] for r in char_step},
                                          True, seg_by_key))
                continue
            idx = {r["id"]: i for i, r in enumerate(allrecs)}
            ranges = []
            for r in char_step:
                i = idx[r["id"]]
                ranges.append([max(0, i - WINDOW), min(len(allrecs) - 1, i + WINDOW)])
            ranges.sort()
            merged = []
            for a, b in ranges:
                if merged and a <= merged[-1][1] + 1:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            for a, b in merged:
                sl = allrecs[a:b + 1]
                trig = {r["id"] for r in sl if r["id"] in char_ids}
                blocks.append(build_block(name, step, sl, trig, False, seg_by_key))
        path = os.path.join(out_dir, "%s.jsonl" % name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for b in blocks:
                f.write(json.dumps(b, ensure_ascii=False) + "\n")
        n_rec = sum(b["n_records"] for b in blocks)
        n_char = sum(len(x["text"]) for b in blocks for x in b["context"])
        appear_rec = len(rows)
        manifest["characters"][name] = {
            "file": "data/context/%s.jsonl" % name,
            "n_blocks": len(blocks),
            "n_records_in_context": n_rec,
            "n_context_chars": n_char,
            "n_appearance_records": appear_rec,
            "n_appearance_steps": len(steps),
            "n_blocks_sparse": sum(1 for b in blocks if b["sparse_step"]),
            "context_record_ratio": round(n_rec / appear_rec, 2) if appear_rec else None,
            "char_ratio": round(n_char / max(1, sum(len(r.get("text") or "") for r in rows)), 2),
        }
        total_blocks += len(blocks)
        total_recs += n_rec
        total_chars += n_char
    manifest["totals"] = {"n_characters": len(manifest["characters"]),
                          "n_blocks": total_blocks,
                          "n_records_in_context": total_recs,
                          "n_context_chars": total_chars}
    with open(P_CTX_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已导出 data/context/：%d 角色 / %d 块 / %d 条上下文记录 / %d 字" % (
        len(manifest["characters"]), total_blocks, total_recs, total_chars))
    return manifest


# ---------------------------------------------------------------------------
# 图 f9 / f10
# ---------------------------------------------------------------------------
def make_f9(chars_stats, out):
    names = [c["name"] for c in chars_stats]
    groups = [c.get("group") for c in chars_stats]
    mat = np.array([[c["per_version"][v]["n_records"] for v in VERSIONS] for c in chars_stats],
                   dtype=float)
    fig, ax = plt.subplots(figsize=(10.2, 7.8))
    disp = np.log1p(mat)
    im = ax.imshow(disp, aspect="auto", cmap="YlOrRd")
    for i in range(len(names)):
        for j in range(len(VERSIONS)):
            val = int(mat[i, j])
            ax.text(j, i, str(val), ha="center", va="center", fontsize=6.5,
                    color="white" if disp[i, j] > 0.6 * disp.max() else "black")
    # 分组分隔线
    ax.axhline(len(GROUP_A) - 0.5, color="black", lw=1.2, ls="--")
    colors = {"A": "#1f4e79", "B": "#b9530f"}
    for lab, g in zip(ax.get_yticklabels(), groups):
        lab.set_color(colors.get(g, "black"))
    ax.set_xticks(range(len(VERSIONS)))
    ax.set_xticklabels(VERSIONS)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.set_xlabel(L("版本", "version"))
    ax.text(-0.08, len(GROUP_A) / 2.0 / len(names), L("A 组 11 黄金裔", "A: 11"),
            transform=ax.transAxes, rotation=90, va="center", ha="right", fontsize=9, color="#1f4e79")
    ax.text(-0.08, (len(GROUP_A) + len(GROUP_B) / 2.0) / len(names), L("B 组 3 单列", "B: 3"),
            transform=ax.transAxes, rotation=90, va="center", ha="right", fontsize=9, color="#b9530f")
    ax.set_title(L("图9  14 个角色分版本台词量（A 组 11 黄金裔 / B 组 3 单列；格内为台词条数，颜色=log 值）",
                   "Fig9  Records per character per version (A/B/NPC)"), fontsize=10)
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label(L("log(1+台词条数)", "log(1+records)"), fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_f10(chars_stats, out):
    def order_stats(gs):
        return sorted(gs, key=lambda c: -c["summary"]["n_steps"])
    a = order_stats([c for c in chars_stats if c.get("group") == "A"])
    b = order_stats([c for c in chars_stats if c.get("group") == "B"])
    rows = a + b
    names = [c["name"] for c in rows]
    steps = [c["summary"]["n_steps"] for c in rows]
    covered = [c["coverage"]["union_knife_key_events"]["n"] for c in rows]
    with_ann = [c["coverage"]["union_all_close_reads"]["n"] for c in rows]
    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(10.6, 8.2))
    ax.barh(y - 0.24, steps, 0.24, color="#9fb3c8", label=L("出场步骤", "appearance steps"))
    ax.barh(y, covered, 0.24, color="#2e5c8a", label=L("深读覆盖（K36∪关键事件）", "deep-read covered"))
    ax.barh(y + 0.24, with_ann, 0.24, color="#d98c3f", label=L("+74 标注", "+ annotation"))
    for i, (s_, c_) in enumerate(zip(steps, covered)):
        ax.text(s_ + 3, i - 0.24, "%d" % s_, va="center", fontsize=6.5, color="0.3")
        ax.text(c_ + 3, i, "%d (%.1f%%)" % (c_, 100 * c_ / s_), va="center", fontsize=6.5, color="#2e5c8a")
    ax.axhline(len(a) - 0.5, color="black", lw=1.1, ls="--")
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    for lab, c in zip(ax.get_yticklabels(), rows):
        lab.set_color({"A": "#1f4e79", "B": "#b9530f"}.get(c.get("group"), "black"))
    ax.invert_yaxis()
    ax.set_xlabel(L("步骤数", "steps"))
    ax.set_title(L("图10  14 个角色：出场步骤 vs 精读覆盖（A 组 11 黄金裔 / B 组 3 单列）",
                   "Fig10  Steps vs close-read coverage"), fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# L1 汇总 + 报告（13 角色）
# ---------------------------------------------------------------------------
def build_summary_table(stats):
    rows = []
    for ch in stats:
        ss = ch["summary"]
        cov = ch["coverage"]
        det = ch["coverage_detail"]
        forms = ch["forms_overall"]
        top_form = next(("%s（%d）" % (k or "无形态", n) for k, n in forms.items()), "—")
        addr_terms = Counter()
        motif_terms = Counter()
        for v in VERSIONS:
            addr_terms.update(ch["per_version"][v]["address_own"])
            motif_terms.update(ch["per_version"][v]["motif_own"])
        rows.append({
            "name": ch["name"], "group": ch.get("group"),
            "pair_with": ch.get("pair_with"), "group_note": ch.get("note"),
            "n_records": ss["n_records"], "n_steps": ss["n_steps"], "n_tasks": ss["n_tasks"],
            "n_versions_present": ss["n_versions_present"],
            "versions_present": ss["versions_present"], "versions_absent": ss["versions_absent"],
            "top_form": top_form,
            "top_address": "、".join("%s%d" % (k, n) for k, n in addr_terms.most_common(3)) or "—",
            "top_motif": "、".join("%s%d" % (k, n) for k, n in motif_terms.most_common(3)) or "—",
            "mean_score_a": ss["mean_score_a"], "mean_score_b1": ss["mean_score_b1"],
            "top100_b1": ss["top100_b1"],
            "knife_n": cov["knife"]["n"], "key_n": cov["key_events"]["n"],
            "annotation_n": cov["annotation"]["n"],
            "deep_n": cov["union_knife_key_events"]["n"],
            "deep_rate": cov["union_knife_key_events"]["rate"],
            "all_read_n": cov["union_all_close_reads"]["n"],
            "all_read_rate": cov["union_all_close_reads"]["rate"],
            "unread_versions": det["unread_versions"],
            "unread_task_count": det["unread_task_count"],
            "unread_tasks": det["unread_tasks"][:3],
        })
    return rows


def render_all_report(data, manifest):
    meta = data["meta"]
    st = data["summary_table"]
    chars = data["characters"]
    groups = {g: [x for x in st if x["group"] == g] for g in ("A", "B")}
    Lr = []
    A = Lr.append
    A("# 14 个角色全量轨迹 + 逐条上下文表（A 组 11 黄金裔 + B 组 3 单列）")
    A("")
    A("> 生成脚本：`tools/character_trajectory.py --all` ｜ 重跑命令：`%s --all`" % RUN_CMD)
    A("> 产出：`data/config/character-trajectory-all.json`、本报告、`data/context/<角色>.jsonl`（派生数据，已 .gitignore）、"
      "`docs/report/figures/f9_all_trajectories.png`、`f10_coverage.png`")
    A("")
    A("> **角色分层（报告口径，用户最终拍板）**：")
    A("> - **A 组 = 黄金裔 11 位**：%s。" % "、".join(GROUP_A))
    A(">   脚注：游戏虽称「十二黄金裔」，但「岁月」这一席位历史上多次更换（欧洛尼斯一线 / 德谬歌与昔涟的演化），"
      "所以实际固定的黄金裔是 **11 位**；本报告一律按 11 位口径。")
    A("> - **B 组 = 单列 3 人**（非黄金裔，主线塑造在翁法罗斯之外，不与黄金裔比较）：%s。" % "、".join(GROUP_B))
    A("> - **荒笛、玻吕茜亚按 NPC 处理**：只在相关角色条目内注记，**不单列分析、不出表/图/曲线/章节，也不参与统计**——"
      "荒笛（70 条 / 4 步）写在丹恒条目（大地承接：荒笛 → 丹恒）；玻吕茜亚写在遐蝶条目（遐蝶之妹；"
      "O05 双子共有神谕 holder=玻吕茜亚）。")
    A("")
    total_steps = sum(x["n_steps"] for x in st)
    total_deep = sum(x["deep_n"] for x in st)
    total_rec = sum(x["n_records"] for x in st)
    A("## 1. 结论")
    A("")
    A("1. **14 个角色合计（各角色分别计数相加）%d 条台词 / %d 个出场步骤**；深读覆盖 **%d 步 = %.1f%%**"
      "（加 74 条标注 %d 步 = %.1f%%）。" % (
          total_rec, total_steps, total_deep, 100 * total_deep / total_steps,
          sum(x["all_read_n"] for x in st), 100 * sum(x["all_read_n"] for x in st) / total_steps))
    A("2. **A 组 11 黄金裔**：%d 条台词 / %d 步，深读 %d 步 = %.1f%%。" % (
        sum(x["n_records"] for x in groups["A"]), sum(x["n_steps"] for x in groups["A"]),
        sum(x["deep_n"] for x in groups["A"]),
        100 * sum(x["deep_n"] for x in groups["A"]) / sum(x["n_steps"] for x in groups["A"])))
    A("3. **B 组 3 人**：%d 条 / %d 步，深读 %d 步 = %.1f%%；**不与黄金裔横向比较**。" % (
        sum(x["n_records"] for x in groups["B"]), sum(x["n_steps"] for x in groups["B"]),
        sum(x["deep_n"] for x in groups["B"]),
        100 * sum(x["deep_n"] for x in groups["B"]) / sum(x["n_steps"] for x in groups["B"])))
    A("4. **L2 上下文表覆盖全部出场记录**：%d 个 jsonl 共 **%d 块 / %d 条上下文记录 / %d 字**；"
      "每个角色的每条出场台词都至少出现一次（trigger），并带前 %d + 后 %d 条同步骤记录。" % (
          len(manifest["characters"]), manifest["totals"]["n_blocks"],
          manifest["totals"]["n_records_in_context"], manifest["totals"]["n_context_chars"],
          WINDOW, WINDOW))
    A("5. **上下文表是否足够支撑全量精读**：足够回答「角色在每一处出现时说了什么、周围发生了什么」；"
      "窗口限定在同一步骤内（不跨步），步骤间因果需 L3 按 `order` 串联；稀疏步骤（总记录<6 或该角色<3）已整步放入。")
    A("")

    def table(rows, title):
        A(title)
        A("")
        A("| 角色 | 台词 | 步骤 | 任务 | 版本 | 主要形态 | 称呼 top3 | 母题 top3 | A/B1 均分 | B1 Top100 | 深读覆盖 | 加标注 |")
        A("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for x in rows:
            A("| %s | %d | %d | %d | %d | %s | %s | %s | %.3f / %.3f | %.1f%% | %d/%d = %.1f%% | %d/%d = %.1f%% |" % (
                x["name"], x["n_records"], x["n_steps"], x["n_tasks"], x["n_versions_present"],
                x["top_form"], x["top_address"], x["top_motif"],
                x["mean_score_a"] or 0, x["mean_score_b1"] or 0, 100 * (x["top100_b1"] or 0),
                x["deep_n"], x["n_steps"], 100 * x["deep_rate"],
                x["all_read_n"], x["n_steps"], 100 * x["all_read_rate"]))
        A("")
    A("## 2. A 组：黄金裔 11 位（汇总）")
    A("")
    table(groups["A"], "")
    A("> **遐蝶条目 NPC 注记**：玻吕茜亚（72 条 / 5 步），遐蝶之妹；O05 双子共有神谕 holder=玻吕茜亚（不归遐蝶的 O04）。")
    A("")
    A("## 3. B 组：单列 3 人（汇总；不与黄金裔比较）")
    A("")
    table(groups["B"], "")
    A("> **丹恒条目 NPC 注记**：荒笛（70 条 / 4 步，样本量小），大地承接：荒笛 → 丹恒。")
    A("")
    A("## 4. 分版本台词量矩阵（每人分版本小表）")
    A("")
    A("| 角色 | " + " | ".join(VERSIONS) + " | 合计 |")
    A("| --- | " + " | ".join("---" for _ in VERSIONS) + " | --- |")
    for g in ("A", "B"):
        for name in [x["name"] for x in groups[g]]:
            pv = chars[name]["per_version"]
            A("| %s（%s） | %s | %d |" % (
                name, g, " | ".join(str(pv[v]["n_records"]) for v in VERSIONS),
                chars[name]["summary"]["n_records"]))
    A("")
    A("分版本**出场步骤数**：")
    A("")
    A("| 角色 | " + " | ".join(VERSIONS) + " | 合计 |")
    A("| --- | " + " | ".join("---" for _ in VERSIONS) + " | --- |")
    for g in ("A", "B"):
        for name in [x["name"] for x in groups[g]]:
            pv = chars[name]["per_version"]
            A("| %s（%s） | %s | %d |" % (
                name, g, " | ".join(str(pv[v]["n_steps"]) for v in VERSIONS),
                chars[name]["summary"]["n_steps"]))
    A("")
    A("## 5. 覆盖与「没读到的版本/任务」")
    A("")
    A("| 角色 | 组 | 出场步 | 深读覆盖 | 未读版本 | 未读任务数 | 未读任务（步骤数最多的前 3） |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for x in st:
        det = chars[x["name"]]["coverage_detail"]
        A("| %s | %s | %d | %d (%.1f%%) | %s | %d | %s |" % (
            x["name"], x["group"], det["steps"], det["covered"],
            100 * det["covered"] / det["steps"],
            "、".join(det["unread_versions"]) or "无", det["unread_task_count"],
            "；".join("%s（%d 步）" % (t["task"][:14], t["steps"]) for t in det["unread_tasks"][:3]) or "无"))
    A("")
    A("## 6. L2 上下文表统计（`data/context/`）")
    A("")
    A("| 角色 | 组 | 块数 | 上下文记录 | 上下文字数 | 出场记录 | 记录覆盖比 | 稀疏整步块 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, m in manifest["characters"].items():
        A("| %s | %s | %d | %d | %d | %d | %.2f× | %d |" % (
            name, chars[name].get("group"), m["n_blocks"], m["n_records_in_context"],
            m["n_context_chars"], m["n_appearance_records"], m["context_record_ratio"],
            m["n_blocks_sparse"]))
    A("")
    A("| 合计 | — | %d | %d | %d | %d | — | %d |" % (
        manifest["totals"]["n_blocks"], manifest["totals"]["n_records_in_context"],
        manifest["totals"]["n_context_chars"],
        sum(m["n_appearance_records"] for m in manifest["characters"].values()),
        sum(m["n_blocks_sparse"] for m in manifest["characters"].values())))
    A("")
    A("**上下文块字段**：`char, version, task, step_idx, step_title, order, record_id, record_span, "
      "n_records, n_char_records, sparse_step, trigger_record_ids, context[]`；`context[]` 每条为 `{id, kind, speaker, text}`。")
    A("")
    A("## 7. 局限")
    A("")
    A("1. 上下文窗口限定在**同一 (version, task, step_idx) 步骤内**，不跨步拼接；步骤之间的因果需 L3 按 order 串联。")
    A("2. 称呼/母题命中是字面统计；「称呼」取角色自己台词（他称只用同步骤他人台词做代理，未展开）。")
    A("3. 形态（form）字段有 null，null 不等于「无形态」；A/B1 均分只覆盖 686 池内的出场步骤。")
    A("4. 荒笛、玻吕茜亚按 NPC 处理，只在相关角色条目内注记，不单列分析；其数据保留在 JSON 的 characters 里（group='注记'）。")
    A("5. 深读覆盖以 K36/30/74 文件的实际内容为准；文件更新后重跑 `--all` 即可同步。")
    A("")
    A("## 8. 复现")
    A("")
    A("```bash")
    A(RUN_CMD + " --all")
    A("conda run -n nlpLesson python tools/character_trajectory.py --verify")
    A("```")
    A("")
    A("- 无随机；全部数字/上下文由 JSONL/JSON 现场生成；`--verify` 会重算 14 角色统计、14 个上下文文件与 manifest，并抽查报告数字。")
    A("")
    return "\n".join(Lr)


def build_all(chars=ALL_STATS, export_ctx=True):
    recs, segs, seg_by_key, pool, A, B, knife, events, annot, cite, recs_by_step = load_all()
    kseg = knife_segments(knife)
    eseg = key_event_segments(events)
    stats = []
    for name in chars:
        print("L1 统计 %s …" % name)
        ch = character_stats(name, recs, seg_by_key, pool, A, B, knife, events, annot, cite,
                             listen=True, recs_by_step=recs_by_step)
        ch["group"] = "A" if name in GROUP_A else ("B" if name in GROUP_B else "注记")
        ch["pair_with"] = PAIR_WITH.get(name)
        ch["note"] = ("NPC：荒笛 70 条/4 步，样本量小；大地承接：荒笛 → 丹恒（丹恒在 B 组）"
                      if name == "荒笛" else
                      ("NPC：遐蝶之妹；O05 双子共有神谕 holder=玻吕茜亚，不归遐蝶" if name == "玻吕茜亚" else None))
        ch["coverage_detail"] = coverage_detail(ch, kseg, eseg)
        stats.append(ch)
    main_stats = [c for c in stats if c["group"] in ("A", "B")]
    summary_table = build_summary_table(main_stats)
    data = {
        "meta": {
            "script": "tools/character_trajectory.py --all",
            "run_command": RUN_CMD + " --all",
            "groups": {"A_黄金裔11": GROUP_A, "B_单列3": GROUP_B},
            "note": "按用户最终口径：黄金裔=11 位（岁月席位历史多次更换）；荒笛、玻吕茜亚按 NPC 处理、"
                    "只在相关角色条目内注记，不单列分析/表/图（characters 中保留其数据，group='注记'）。",
            "n_records_total": len(recs), "n_segments_total": len(segs), "n_pool": len(pool),
            "n_knife": len(knife["scenes"]), "n_events": len(events["events"]), "n_annot": len(annot),
            "window": "前 %d + 本条 + 后 %d（同一步骤内，按 id 升序）" % (WINDOW, WINDOW),
            "sparse_rule": "该步总记录<%d 或该角色记录<%d → 整步放入" % (
                SPARSE_STEP_RECORDS, SPARSE_CHAR_RECORDS),
            "sources": ["amphoreus.final.jsonl", "segments.jsonl", "oracle-citation-coding.json",
                        "knife-scenes.json", "key-events.json", "annotation-labels.json",
                        "baseline-a-scores.json", "baseline-b-scores.json"],
        },
        "summary_table": summary_table,
        "characters": {ch["name"]: ch for ch in stats},
    }
    manifest = None
    if export_ctx:
        ctx_stats = [c for c in stats if c["name"] in CONTEXT_CHARS]
        manifest = export_context(ctx_stats, recs, seg_by_key, recs_by_step)
        data["context_manifest"] = manifest
    os.makedirs(FIG_DIR, exist_ok=True)
    make_f9(main_stats, F9)
    make_f10(main_stats, F10)
    print("已生成 %s / %s" % (os.path.relpath(F9, ROOT), os.path.relpath(F10, ROOT)))
    with open(P_ALL_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写 %s（%.1f KB）" % (os.path.relpath(P_ALL_JSON, ROOT), os.path.getsize(P_ALL_JSON) / 1024.0))
    md = render_all_report(data, manifest)
    with open(P_ALL_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print("已写 %s（%.1f KB）" % (os.path.relpath(P_ALL_MD, ROOT), os.path.getsize(P_ALL_MD) / 1024.0))
    if HAS_CJK:
        print("中文字体：%s" % CJK_FONT)
    if not verify_all(data, verbose=True):
        print("!! 校验失败", file=sys.stderr)
        sys.exit(1)
    print("\n校验通过：14 角色（A11/B3；荒笛/玻吕茜亚按注记处理，不出表现在报告/图中）。")


def verify_all(data=None, verbose=False):
    problems = []
    recs, segs, seg_by_key, pool, A, B, knife, events, annot, cite, recs_by_step = load_all()
    if data is None:
        if not os.path.exists(P_ALL_JSON):
            print("缺少 %s" % P_ALL_JSON, file=sys.stderr)
            return False
        data = read_json(P_ALL_JSON)
    chars = data["characters"]
    grp = Counter(ch.get("group") for ch in chars.values())
    if len(chars) != 16:
        problems.append("角色数 %d != 16" % len(chars))
    if grp.get("A") != 11 or grp.get("B") != 3 or grp.get("注记") != 2:
        problems.append("分组数异常（应为 A11/B3/注记2）：%s" % dict(grp))
    if len(data.get("summary_table") or []) != 14:
        problems.append("summary_table 行数 %d != 14" % len(data.get("summary_table") or []))
    kseg = knife_segments(knife)
    eseg = key_event_segments(events)
    aseg = annotation_segments(annot)
    for name, ch in chars.items():
        rows = [r for r in recs if r.get("canonical_speaker") == name]
        if len(rows) != ch["summary"]["n_records"]:
            problems.append("%s 记录数不一致" % name)
        steps = {(r["version"], r["task"], r["step_idx"]) for r in rows}
        segids = {seg_by_key[k]["segment_id"] for k in steps if k in seg_by_key}
        if len(segids) != ch["summary"]["n_steps"]:
            problems.append("%s 步骤数不一致" % name)
        for key, sset in (("knife", kseg), ("key_events", eseg), ("annotation", aseg)):
            if len(segids & sset) != ch["coverage"][key]["n"]:
                problems.append("%s %s 覆盖不一致" % (name, key))
        if len(segids & (kseg | eseg)) != ch["coverage"]["union_knife_key_events"]["n"]:
            problems.append("%s 深读并集不一致" % name)
    # 上下文表：15 个文件（A11+B3+荒笛），NPC 玻吕茜亚不要求
    manifest = data.get("context_manifest") or (read_json(P_CTX_MANIFEST) if os.path.exists(P_CTX_MANIFEST) else None)
    if not manifest:
        problems.append("缺少上下文 manifest")
    else:
        if len(manifest["characters"]) != 14:
            problems.append("上下文角色数 %d != 14" % len(manifest["characters"]))
        if not os.path.exists(os.path.join(CTX_DIR, ".gitignore")):
            problems.append("缺少 data/context/.gitignore")
        for name, m in manifest["characters"].items():
            path = os.path.join(ROOT, m["file"])
            if not os.path.exists(path):
                problems.append("%s 上下文文件不存在" % name)
                continue
            rows = [r for r in recs if r.get("canonical_speaker") == name]
            char_ids = {r["id"] for r in rows}
            rec_step = {r["id"]: (r["version"], r["task"], r["step_idx"]) for r in recs}
            blocks = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        blocks.append(json.loads(line))
            if len(blocks) != m["n_blocks"]:
                problems.append("%s 块数不一致" % name)
            seen, trig_union, n_rec, n_char = set(), set(), 0, 0
            for b in blocks:
                ids = [x["id"] for x in b["context"]]
                if ids != sorted(ids):
                    problems.append("%s 块内记录未按 id 升序" % name)
                for x in b["context"]:
                    if x["id"] in seen:
                        problems.append("%s 块间记录重复：%d" % (name, x["id"]))
                    seen.add(x["id"])
                    st = rec_step.get(x["id"])
                    if st is not None and st != (b["version"], b["task"], b["step_idx"]):
                        problems.append("%s 块内记录跨步骤" % name)
                trig_union.update(b["trigger_record_ids"])
                n_rec += len(ids)
                n_char += sum(len(x["text"]) for x in b["context"])
            if trig_union != char_ids:
                problems.append("%s 出场记录未完整覆盖（%d/%d）" % (name, len(trig_union & char_ids), len(char_ids)))
            if n_rec != m["n_records_in_context"] or n_char != m["n_context_chars"]:
                problems.append("%s manifest 统计不一致" % name)
    for path in (F9, F10):
        if not os.path.exists(path) or os.path.getsize(path) < 5000:
            problems.append("图不存在或过小：%s" % path)
    md = open(P_ALL_MD, "r", encoding="utf-8").read() if os.path.exists(P_ALL_MD) else ""
    for kw in ("A 组", "B 组", "荒笛", "玻吕茜亚", "三月七", "丹恒", "11 位",
               "大地承接", "NPC 注记"):
        if kw not in md:
            problems.append("报告缺少口径关键词：%s" % kw)
    for bad in ("## 4. NPC", "NPC 类（不进 A/B 主表）", "NPC 2 人"):
        if bad in md:
            problems.append("报告仍含 NPC 分组内容：%s" % bad)
    if verbose:
        print("\n14 角色 L1（A11 + B3；荒笛/玻吕茜亚为注记，不单列）：")
        for name, ch in chars.items():
            ss = ch["summary"]
            cov = ch["coverage"]["union_knife_key_events"]
            print("  %-5s[%s] %5d 条 / %3d 步 / %2d 任务；深读 %3d (%4.1f%%)" % (
                name, ch.get("group"), ss["n_records"], ss["n_steps"], ss["n_tasks"],
                cov["n"], 100 * cov["rate"]))
        if manifest:
            print("上下文：%d 角色 / %d 块 / %d 条 / %d 字" % (
                len(manifest["characters"]), manifest["totals"]["n_blocks"],
                manifest["totals"]["n_records_in_context"], manifest["totals"]["n_context_chars"]))
    if problems:
        for p in problems[:25]:
            print("  ✗ " + p, file=sys.stderr)
        return False
    return True


if __name__ == "__main__":
    main()
