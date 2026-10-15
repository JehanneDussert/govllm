#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Ground truth statistics with uncertainty, from docs/ground_truth/results/.

1. Agreement per judge, per ordering and pooled over the three orderings, with a
   95% case-level cluster bootstrap CI (a case is resampled with all its orderings).
2. Paired differences vs the top judge (same cases, same orderings).
3. Few-shot gains: few-shot vs original-order baseline on the same evaluable cases,
   paired bootstrap CI, two-sided p, Holm across judges.
4. Forest plot of (1).

Usage:
    python scripts/groundtruth_stats.py                        # pooled (judges with all 3 orderings)
    python scripts/groundtruth_stats.py --condition original   # original order only (all judges)

Writes docs/ground_truth/analysis/groundtruth_stats.json and
docs/ground_truth/figures/agreement_forest_<condition>.{png,pdf}. The figure needs matplotlib;
the statistics are stdlib only.
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from model_registry import MODELS, select, label, color

RESULTS = Path("docs/ground_truth/results")
OUT_JSON = Path("docs/ground_truth/analysis/groundtruth_stats.json")
OUT_FIG = Path("docs/ground_truth/figures")
ORDERS = ["original", "reversed", "permuted"]


def case_key(r):
    # Few-shot files store the prompt truncated to 120 chars; the 120-char prefix
    # is unique per criterion in corpus.json, so it is used as the join key everywhere.
    return (r["criterion"], r["prompt"][:120])


def load(slug, order):
    path = RESULTS / f"{slug}_{order}.json"
    if not path.exists():
        return None
    return {case_key(r): r["agreement"] for r in json.loads(path.read_text(encoding="utf-8"))["results"]}


def load_fewshot(slug):
    path = RESULTS / f"{MODELS[slug].get('file_slug', slug)}_fewshot.json"
    if not path.exists():
        return None
    return {case_key(r): float(r["agreement"]) for r in json.loads(path.read_text(encoding="utf-8"))["results"]
            if r.get("agreement") is not None}


def cluster_bootstrap(by_case: dict, n_boot: int, rng: random.Random):
    """by_case: case -> list of values (one per ordering). Mean over all values."""
    cases = [c for c, vs in by_case.items() if vs]
    allv = [v for c in cases for v in by_case[c]]
    est = sum(allv) / len(allv)
    means = []
    for _ in range(n_boot):
        s = n = 0
        for c in rng.choices(cases, k=len(cases)):
            s += sum(by_case[c])
            n += len(by_case[c])
        means.append(s / n)
    means.sort()
    p_le = sum(1 for m in means if m <= 0) / n_boot
    p_ge = sum(1 for m in means if m >= 0) / n_boot
    return {
        "estimate": round(est, 6),
        "ci95": [round(means[int(0.025 * n_boot)], 6), round(means[int(0.975 * n_boot) - 1], 6)],
        "p_two_sided_vs_0": round(min(1.0, max(2 * min(p_le, p_ge), 1 / n_boot)), 4),
        "n_cases": len(cases),
        "n_case_runs": len(allv),
    }


def holm(d: dict):
    items = sorted((v["p_two_sided_vs_0"], k) for k, v in d.items())
    running = 0.0
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (len(items) - i) * p))
        d[k]["p_holm"] = round(running, 4)


def forest(stats, condition, path_stem):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    items = sorted(stats.items(), key=lambda kv: kv[1]["estimate"])
    fig, ax = plt.subplots(figsize=(6.5, 0.45 * len(items) + 1.4))
    for i, (j, s) in enumerate(items):
        lo, hi = s["ci95"]
        ax.plot([lo * 100, hi * 100], [i, i], color=color(j), linewidth=2.2, solid_capstyle="round")
        ax.plot(s["estimate"] * 100, i, "o", color=color(j), markeredgecolor="#333333",
                markeredgewidth=0.6, markersize=7)
        ax.text(hi * 100 + 0.8, i, f"{s['estimate'] * 100:.1f}%  [{lo * 100:.1f}, {hi * 100:.1f}]",
                va="center", fontsize=8, color="#333333")
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels([f"{label(j)}  (n={s['n_cases']})" for j, s in items])
    ax.set_xlabel("Agreement with ground truth (%), 95% case-level bootstrap CI")
    title = {"pooled": "pooled over 3 question orderings", "original": "original question order only"}
    ax.set_title(f"Judge validity — {title.get(condition, condition)}")
    ax.grid(axis="x", color="#dddddd", linestyle="--", linewidth=0.6)
    xmin = min(s["ci95"][0] for s in stats.values()) * 100 - 3
    ax.set_xlim(max(0, xmin), 105)
    fig.tight_layout()
    OUT_FIG.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        p = OUT_FIG / f"{path_stem}.{ext}"
        fig.savefig(p, dpi=300, bbox_inches="tight", facecolor="white")
        print(f"  Saved: {p}")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="all")
    parser.add_argument("--condition", choices=["pooled", "original"], default="pooled")
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--no-figure", action="store_true")
    args = parser.parse_args()
    rng = random.Random(0)

    data = {j: {o: load(j, o) for o in ORDERS} for j in select(args.models)}

    # 1. Agreement with CI, per ordering and pooled
    agreement = defaultdict(dict)
    for j, by_order in data.items():
        for o in ORDERS:
            if by_order[o]:
                agreement[j][o] = cluster_bootstrap({c: [v] for c, v in by_order[o].items()}, args.bootstrap, rng)
        if all(by_order[o] for o in ORDERS):
            pooled = defaultdict(list)
            for o in ORDERS:
                for c, v in by_order[o].items():
                    pooled[c].append(v)
            agreement[j]["pooled"] = cluster_bootstrap(pooled, args.bootstrap, rng)

    cond = args.condition
    in_cond = {j: a[cond] for j, a in agreement.items() if cond in a}
    missing = [j for j in data if j not in in_cond]

    # 2. Paired differences vs the top judge
    paired = {}
    if in_cond:
        top = max(in_cond, key=lambda j: in_cond[j]["estimate"])
        orders = ORDERS if cond == "pooled" else [cond]
        for j in in_cond:
            if j == top:
                continue
            diff = defaultdict(list)
            for o in orders:
                for c, v in data[top][o].items():
                    if c in data[j][o]:
                        diff[c].append(v - data[j][o][c])
            paired[j] = cluster_bootstrap(diff, args.bootstrap, rng)
        holm(paired)
        paired = {"reference": top, "condition": cond, "differences": paired}

    # 3. Few-shot gains
    fewshot = {}
    for j, by_order in data.items():
        fs, base = load_fewshot(j), by_order["original"]
        if not fs or not base:
            continue
        common = [c for c in fs if c in base]
        d = cluster_bootstrap({c: [fs[c] - base[c]] for c in common}, args.bootstrap, rng)
        d["baseline"] = round(sum(base[c] for c in common) / len(common), 4)
        d["fewshot"] = round(sum(fs[c] for c in common) / len(common), 4)
        d["unmatched_fewshot_cases"] = len(fs) - len(common)
        fewshot[j] = d
    if fewshot:
        holm(fewshot)

    out = {
        "description": "Agreement with ground truth: mean of per-case agreement; 95% CI = case-level cluster "
                       "bootstrap (all orderings of a case resampled together). 'pooled' only for judges with "
                       "all three orderings. Few-shot: same evaluable cases, original order; paired bootstrap; "
                       "Holm across judges.",
        "n_bootstrap": args.bootstrap,
        "agreement": agreement,
        "paired_vs_top": paired,
        "fewshot_gain": fewshot,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {OUT_JSON}")

    print(f"\n=== Agreement ({cond}) ===")
    for j, s in sorted(in_cond.items(), key=lambda kv: -kv[1]["estimate"]):
        print(f"  {j:<22} {s['estimate'] * 100:5.1f}%  [{s['ci95'][0] * 100:5.1f}, {s['ci95'][1] * 100:5.1f}]  "
              f"cases={s['n_cases']} runs={s['n_case_runs']}")
    if missing:
        print(f"  (not in '{cond}': {', '.join(missing)})")
    if paired:
        print(f"\n=== Paired difference: {paired['reference']} minus judge ({cond}) ===")
        for j, s in sorted(paired["differences"].items(), key=lambda kv: kv[1]["estimate"]):
            print(f"  {j:<22} {s['estimate'] * 100:+5.1f} pp  [{s['ci95'][0] * 100:+5.1f}, {s['ci95'][1] * 100:+5.1f}]  "
                  f"p_holm={s['p_holm']:.3f}")
    print("\n=== Few-shot gain (original order, same cases) ===")
    for j, s in sorted(fewshot.items(), key=lambda kv: -kv[1]["estimate"]):
        print(f"  {j:<22} {s['baseline'] * 100:5.1f}% -> {s['fewshot'] * 100:5.1f}%  "
              f"{s['estimate'] * 100:+5.1f} pp  [{s['ci95'][0] * 100:+5.1f}, {s['ci95'][1] * 100:+5.1f}]  "
              f"n={s['n_cases']}  p_holm={s['p_holm']:.3f}")

    if not args.no_figure and in_cond:
        forest(in_cond, cond, f"agreement_forest_{cond}")


if __name__ == "__main__":
    main()
