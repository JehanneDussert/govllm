#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Inter-judge disagreement on the benchmark, separating calibration offsets from disagreement.

For each (generator, prompt), sigma = sample std dev of the composite scores given by the
judges (as in analyze_benchmark.py, analysis 3). A judge that scores systematically low
(lfm2.5:1.2b-thinking) inflates sigma without disagreeing about the answer, so sigma is
also computed on judge-centred scores (score minus that judge's mean over all its scores).
Both variants are computed with all judges and without lfm2.5.

Outputs:
    docs/benchmark/analysis/interjudge_sigma.json   per-prompt sigma (4 variants), top 10, adversarial tail
    docs/benchmark/analysis/adversarial_sigma.md    adversarial (prompt, generator) rows sorted by centred sigma,
                                                    with the answer (300 chars) and every judge's score

    docs/benchmark/figures/interjudge_sigma_centred.png               Figure 6 of the v2 (all judges)
    docs/benchmark/figures/interjudge_sigma_centred_without_lfm.png   sensitivity variant (appendix)

Usage: python scripts/interjudge_sigma.py [--models all] [--no-figure]
"""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from model_registry import select, slug_of, label

RESULTS = Path("docs/benchmark/results")
PROMPTS = Path("docs/benchmark/prompts.json")
OUT_JSON = Path("docs/benchmark/analysis/interjudge_sigma.json")
OUT_MD = Path("docs/benchmark/analysis/adversarial_sigma.md")
OUT_ROBUST = Path("docs/benchmark/analysis/interjudge_robustness.md")
LOW_JUDGE = "lfm2.5-1.2b-thinking"
TAIL = 0.15  # sigma threshold used in the paper (Finding 5)
OUT_FIG = Path("docs/benchmark/figures")
DIFF_ORDER = ["easy", "medium", "adversarial", "hard"]


def boxplot(prompt_sigma: dict, meta: dict, path: Path, subtitle: str) -> None:
    """Per-prompt sigma (averaged over generators) by difficulty tier, same style as generate_figures.py."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from generate_figures import CB, DPI, FIGSIZE_SINGLE, base_style

    base_style()
    groups = {d: [v for p, v in prompt_sigma.items() if meta[p]["difficulty"] == d] for d in DIFF_ORDER}
    fig, ax = plt.subplots(figsize=FIGSIZE_SINGLE)
    bp = ax.boxplot([groups[d] for d in DIFF_ORDER], patch_artist=True,
                    medianprops={"color": "white", "linewidth": 2},
                    flierprops={"marker": "o", "markersize": 4, "markeredgecolor": "#888888", "alpha": 0.6})
    for patch, c in zip(bp["boxes"], [CB["green"], CB["sky"], CB["orange"], CB["vermil"]]):
        patch.set_facecolor(c)
        patch.set_alpha(0.75)
    ax.set_xticks(range(1, len(DIFF_ORDER) + 1), [d.capitalize() for d in DIFF_ORDER])
    ax.axhline(TAIL, color="#888888", linestyle=":", linewidth=1)
    ax.set_xlabel("Difficulty tier")
    ax.set_ylabel("Inter-judge σ (judge-centred scores)")
    ax.set_title(f"Judge disagreement by difficulty — {subtitle}")
    ax.grid(axis="y")
    for i, d in enumerate(DIFF_ORDER, 1):
        ax.annotate(f"n={len(groups[d])}", (i, ax.get_ylim()[0]), ha="center", va="bottom", fontsize=8, color="#666666")
    fig.tight_layout()
    OUT_FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved: {path}")


def sd(v):
    v = [x for x in v if x is not None]
    if len(v) < 2:
        return None
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def median(v):
    v = sorted(x for x in v if x is not None)
    n = len(v)
    return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


def mad(v):
    """Median absolute deviation from the median, scaled by 1.4826 (comparable with sigma
    under normality). Robust: one outlying judge barely moves it, unlike sigma."""
    v = [x for x in v if x is not None]
    if len(v) < 2:
        return None
    m = median(v)
    return 1.4826 * median([abs(x - m) for x in v])


def robustness(scores, judge_mean, meta, judges, top_n=10):
    """Leave-one-judge-out ranking of the most discriminating prompts (centred sigma, all
    judges), robust dispersion (MAD) and the share of sigma due to a single judge."""
    def centred(s, drop=None):
        return {j: v - judge_mean[j] for j, v in s.items() if j != drop}

    def prompt_sigma(drop=None):
        per = defaultdict(list)
        for (gen, pid), s in scores.items():
            v = sd(list(centred(s, drop).values()))
            if v is not None:
                per[pid].append(v)
        return {pid: mean(v) for pid, v in per.items()}

    def ranks(ps):
        order = sorted(ps, key=lambda p: -ps[p])
        return {p: i + 1 for i, p in enumerate(order)}

    full = prompt_sigma()
    top = sorted(full, key=lambda p: -full[p])[:top_n]
    loo = {j: ranks(prompt_sigma(drop=j)) for j in judges}
    loo_sigma = {j: prompt_sigma(drop=j) for j in judges}

    rows = []
    for pid in top:
        pairs = [(k, s) for k, s in scores.items() if k[1] == pid]
        mads, shares, dominant = [], [], defaultdict(int)
        for (gen, _), s in pairs:
            c = centred(s)
            sig = sd(list(c.values()))
            mads.append(mad(list(c.values())))
            if sig:
                # judge whose removal lowers sigma the most, and by how much
                best = min(c, key=lambda j: sd([v for k2, v in c.items() if k2 != j]) or 0)
                shares.append(1 - (sd([v for k2, v in c.items() if k2 != best]) or 0) / sig)
                dominant[best] += 1
        dom_judge, dom_n = max(dominant.items(), key=lambda kv: kv[1]) if dominant else (None, 0)
        rows.append({
            "prompt": pid, "difficulty": meta[pid]["difficulty"], "rank": top.index(pid) + 1,
            "sigma_centred": round(full[pid], 4), "mad_centred": round(mean(mads), 4),
            "mad_over_sigma": round(mean(mads) / full[pid], 3),
            "single_judge_share": round(mean(shares), 3),
            "dominant_judge": dom_judge, "dominant_in_n_generators": dom_n, "n_generators": len(pairs),
            "loo_rank": {j: loo[j][pid] for j in judges},
            "loo_rank_worst": max(loo[j][pid] for j in judges),
            "loo_sigma_min": round(min(loo_sigma[j][pid] for j in judges), 4),
        })
    top_set = set(top)
    overlap = {j: len(top_set & set(sorted(loo_sigma[j], key=lambda p: -loo_sigma[j][p])[:top_n]))
               for j in judges}
    leader = {j: min(loo[j], key=loo[j].get) for j in judges}
    return {"top": rows, "top10_overlap_after_drop": overlap, "leader_after_drop": leader}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="all")
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args()
    models = set(select(args.models))

    meta = {}
    for uc, items in json.loads(PROMPTS.read_text(encoding="utf-8"))["benchmark_prompts"].items():
        for p in items:
            meta[p["id"]] = {"difficulty": p["difficulty"], "use_case": uc, "prompt": p["prompt"]}

    # scores[(gen, pid)][judge] = composite score ; answers[(gen, pid)] = answer text
    scores, answers = defaultdict(dict), {}
    for f in sorted(RESULTS.glob("*.json")):
        if f.name.endswith(".partial.json"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        gen, judge = slug_of(d["model"]), slug_of(d["judge_model"])
        if gen not in models or judge not in models:
            continue
        for r in d["results"]:
            if r.get("status") != "OK" or r.get("score") is None:
                continue
            scores[(gen, r["id"])][judge] = r["score"]
            answers[(gen, r["id"])] = r.get("answer") or ""

    judges = sorted({j for s in scores.values() for j in s})
    judge_mean = {j: mean([s[j] for s in scores.values() if j in s]) for j in judges}

    def variant(centred: bool, exclude: set[str]):
        per_pair = {}
        for key, s in scores.items():
            vals = [(v - judge_mean[j]) if centred else v for j, v in s.items() if j not in exclude]
            per_pair[key] = sd(vals)
        per_prompt = defaultdict(list)
        for (gen, pid), v in per_pair.items():
            if v is not None:
                per_prompt[pid].append(v)
        prompt_sigma = {pid: mean(v) for pid, v in per_prompt.items()}
        top = sorted(prompt_sigma.items(), key=lambda kv: -kv[1])[:10]
        by_diff = defaultdict(list)
        for (gen, pid), v in per_pair.items():
            if v is not None:
                by_diff[meta[pid]["difficulty"]].append(v)
        tiers = {d: {"n_pairs": len(v), "median": round(median(v), 4), "mean": round(mean(v), 4),
                     "share_above_tail": round(sum(x > TAIL for x in v) / len(v), 4)}
                 for d, v in sorted(by_diff.items())}
        return per_pair, prompt_sigma, [(pid, round(v, 4)) for pid, v in top], tiers

    variants = {
        "raw_all": variant(False, set()),
        "centred_all": variant(True, set()),
        "raw_without_lfm": variant(False, {LOW_JUDGE}),
        "centred_without_lfm": variant(True, {LOW_JUDGE}),
    }
    out = {
        "description": "Inter-judge sigma per (generator, prompt), averaged per prompt; raw vs judge-centred "
                       "scores (score minus the judge's overall mean), with all judges and without lfm2.5.",
        "judges": judges,
        "judge_mean_score": {j: round(m, 4) for j, m in judge_mean.items()},
        "tail_threshold": TAIL,
        "variants": {k: {"top10_prompts": v[2], "by_difficulty": v[3],
                         "prompt_sigma": {p: round(s, 4) for p, s in sorted(v[1].items())}}
                     for k, v in variants.items()},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    rob = robustness(scores, judge_mean, meta, judges)
    out["robustness_top10_centred_all"] = rob
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Most discriminating prompts — robustness (judge-centred sigma, all judges)", "",
             "Leave-one-judge-out: rank of each top-10 prompt when each judge is removed in turn. "
             "MAD: median absolute deviation from the median (x1.4826), robust to one outlying judge; "
             "MAD/sigma well below 1 means the spread comes from one or two judges, not from a split panel. "
             "Single-judge share: 1 - sigma(without the judge whose removal lowers sigma most) / sigma, "
             "averaged over generators. Generated by `scripts/interjudge_sigma.py`.", "",
             "| rank | prompt | tier | sigma | MAD | MAD/sigma | single-judge share | dominant judge (n gen.) | "
             "worst rank (LOO) | " + " | ".join(f"w/o {label(j)}" for j in judges) + " |",
             "|---|---|---|---|---|---|---|---|---|" + "---|" * len(judges)]
    for r in rob["top"]:
        lines.append(f"| {r['rank']} | {r['prompt']} | {r['difficulty']} | {r['sigma_centred']:.3f} | "
                     f"{r['mad_centred']:.3f} | {r['mad_over_sigma']:.2f} | {r['single_judge_share']:.2f} | "
                     f"{label(r['dominant_judge'])} ({r['dominant_in_n_generators']}/{r['n_generators']}) | "
                     f"{r['loo_rank_worst']} | " + " | ".join(str(r['loo_rank'][j]) for j in judges) + " |")
    lines += ["", "Top-10 overlap after removing each judge: "
              + ", ".join(f"{label(j)} {n}/10" for j, n in rob["top10_overlap_after_drop"].items()),
              "", "First prompt after removing each judge: "
              + ", ".join(f"{label(j)} → {p}" for j, p in rob["leader_after_drop"].items())]
    OUT_ROBUST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("written", OUT_ROBUST)

    # Adversarial table, sorted by centred sigma (all judges)
    cen, raw = variants["centred_all"][0], variants["raw_all"][0]
    cen7 = variants["centred_without_lfm"][0]
    adv = [k for k in scores if meta[k[1]]["difficulty"] == "adversarial"]
    adv.sort(key=lambda k: -(cen[k] or 0))
    n_prompts = len({pid for _, pid in adv})
    lines = [
        "# Adversarial prompts — inter-judge disagreement, sorted by judge-centred σ",
        "",
        f"{n_prompts} adversarial prompts × {len({g for g, _ in adv})} generators = {len(adv)} (prompt, generator) pairs. "
        f"σ = sample standard deviation of the {len(judges)} judges' composite scores for one answer; "
        "centred = each judge's score minus that judge's mean over the whole benchmark. "
        "Generated by `scripts/interjudge_sigma.py`.",
        "",
        "Judge means: " + ", ".join(f"{label(j)} {judge_mean[j]:.3f}" for j in judges),
        "",
        "| # | id | σ centred | σ centred w/o lfm2.5 | σ raw | generator | prompt | answer (300 chars) | "
        + " | ".join(label(j) for j in judges) + " |",
        "|---|---|---|---|---|---|---|---|" + "---|" * len(judges),
    ]
    for i, k in enumerate(adv, 1):
        gen, pid = k
        ans = " ".join(answers[k].split())[:300].replace("|", "\\|")
        prm = meta[pid]["prompt"].replace("|", "\\|")
        sc = " | ".join(f"{scores[k][j]:.2f}" if j in scores[k] else "—" for j in judges)
        lines.append(f"| {i} | {pid} | {cen[k]:.3f} | {cen7[k]:.3f} | {raw[k]:.3f} | {label(gen)} | {prm} | {ans} | {sc} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for k, v in variants.items():
        print(f"== {k}")
        print("  top10:", v[2])
        for d, s in v[3].items():
            print(f"  {d:<12} pairs={s['n_pairs']:<4} median={s['median']:.3f} mean={s['mean']:.3f} "
                  f"share>{TAIL}={s['share_above_tail']:.1%}")
    print(f"written {OUT_JSON}, {OUT_MD} ({len(adv)} adversarial pairs, {n_prompts} prompts)")
    if not args.no_figure:
        boxplot(variants["centred_all"][1], meta, OUT_FIG / "interjudge_sigma_centred.png",
                f"{len(judges)} judges")
        boxplot(variants["centred_without_lfm"][1], meta, OUT_FIG / "interjudge_sigma_centred_without_lfm.png",
                f"{len(judges) - 1} judges (without lfm2.5)")


if __name__ == "__main__":
    main()
