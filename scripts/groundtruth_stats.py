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
4. Order effects: reversed/permuted minus original, paired by case, per judge.
5. Specialised panel (paper Finding 9): each criterion assigned to the judge with
   the highest pooled agreement on that criterion, compared with the best single
   judge. The assignment is selected on the same cases it is evaluated on
   (in-sample), which favours the panel; reported as a single comparison.
6. Forest plot of (1).
7. Usable-answer rate per judge and ordering: share of corpus cases for which the
   judge returned a complete true/false answer vector (status "ok"); the other
   statuses (call_error, json_error, empty, parse_error, not_recorded) are counted.
8. Sensitivity of (1) to unusable answers: agreement excluding them (the headline
   figure, as in 1) vs worst case, where every unusable answer counts as a full
   disagreement (agreement 0 for that case). A judge is flagged when the worst-case
   estimate falls outside the 95% CI of the headline estimate.

Multiple comparisons: every family of tests (2, 3, 4) reports the unadjusted 95% CI,
a Holm-adjusted p-value and a Bonferroni-adjusted CI (level 1 - 0.05/k, k = tests in
the family). Each comparison has its own seed derived from its name, so adding a judge
does not change the other judges' numbers.

Usage:
    python scripts/groundtruth_stats.py                        # pooled (judges with all 3 orderings)
    python scripts/groundtruth_stats.py --condition original   # original order only (all judges)
    python scripts/groundtruth_stats.py --models paper         # the 4 judges of arXiv v1 (README figures)

Writes docs/ground_truth/analysis/groundtruth_stats[_<models>][_<condition>].json and
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


def load_entries(slug, order):
    """All entries of an exported file (full corpus grid, every status), or None."""
    path = RESULTS / f"{slug}_{order}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["results"]


def load(slug, order):
    """case -> agreement, usable answers only (status ok)."""
    entries = load_entries(slug, order)
    if entries is None:
        return None
    return {case_key(r): r["agreement"] for r in entries if r.get("status", "ok") == "ok"}


def load_worst_case(slug, order):
    """case -> agreement, every unusable answer counted as a full disagreement (0)."""
    entries = load_entries(slug, order)
    if entries is None:
        return None
    return {case_key(r): (r["agreement"] if r.get("status", "ok") == "ok" else 0.0) for r in entries}


def load_fewshot(slug):
    path = RESULTS / f"{MODELS[slug].get('file_slug', slug)}_fewshot.json"
    if not path.exists():
        return None
    return {case_key(r): float(r["agreement"]) for r in json.loads(path.read_text(encoding="utf-8"))["results"]
            if r.get("agreement") is not None}


def cluster_bootstrap(by_case: dict, n_boot: int, seed: str):
    """by_case: case -> list of values (one per ordering). Mean over all values."""
    rng = random.Random(seed)
    # Sorted, so the CI does not depend on the order of the cases in the result files
    cases = sorted(c for c, vs in by_case.items() if vs)
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
        "_means": means,
    }


def strip(d: dict) -> dict:
    d.pop("_means", None)
    return d


def holm(d: dict):
    """Holm-adjusted p and Bonferroni-adjusted CI over the family of tests in d."""
    k = len(d)
    items = sorted((v["p_two_sided_vs_0"], name) for name, v in d.items())
    running = 0.0
    for i, (p, name) in enumerate(items):
        running = max(running, min(1.0, (k - i) * p))
        d[name]["p_holm"] = round(running, 4)
    for v in d.values():
        means, a = v["_means"], 0.05 / k
        v["ci_bonferroni"] = [round(means[int(a / 2 * len(means))], 6),
                              round(means[int((1 - a / 2) * len(means)) - 1], 6)]
        v["ci_bonferroni_level"] = round(1 - a, 4)
        v["family_size"] = k
        strip(v)


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


def _fmt(s):
    ci, cb = s["ci95"], s["ci_bonferroni"]
    return (f"{s['estimate'] * 100:+5.1f} pp  CI95 [{ci[0] * 100:+5.1f}, {ci[1] * 100:+5.1f}]  "
            f"Bonferroni [{cb[0] * 100:+5.1f}, {cb[1] * 100:+5.1f}]  "
            f"p={s['p_two_sided_vs_0']:.3f} p_holm={s['p_holm']:.3f}  n={s['n_cases']}  (k={s['family_size']})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="all")
    parser.add_argument("--condition", choices=["pooled", "original"], default="pooled")
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--no-figure", action="store_true")
    args = parser.parse_args()

    data = {j: {o: load(j, o) for o in ORDERS} for j in select(args.models)}

    # 1. Agreement with CI, per ordering and pooled
    agreement = defaultdict(dict)
    for j, by_order in data.items():
        for o in ORDERS:
            if by_order[o]:
                agreement[j][o] = strip(cluster_bootstrap({c: [v] for c, v in by_order[o].items()},
                                                          args.bootstrap, f"agreement:{j}:{o}"))
        if all(by_order[o] for o in ORDERS):
            pooled = defaultdict(list)
            for o in ORDERS:
                for c, v in by_order[o].items():
                    pooled[c].append(v)
            agreement[j]["pooled"] = strip(cluster_bootstrap(pooled, args.bootstrap, f"agreement:{j}:pooled"))

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
            paired[j] = cluster_bootstrap(diff, args.bootstrap, f"paired:{cond}:{top}-{j}")
        holm(paired)
        paired = {"reference": top, "condition": cond, "differences": paired}

    # 3. Few-shot gains
    fewshot = {}
    for j, by_order in data.items():
        fs, base = load_fewshot(j), by_order["original"]
        if not fs or not base:
            continue
        common = [c for c in fs if c in base]
        d = cluster_bootstrap({c: [fs[c] - base[c]] for c in common}, args.bootstrap, f"fewshot:{j}")
        d["baseline"] = round(sum(base[c] for c in common) / len(common), 4)
        d["fewshot"] = round(sum(fs[c] for c in common) / len(common), 4)
        d["unmatched_fewshot_cases"] = len(fs) - len(common)
        fewshot[j] = d
    if fewshot:
        holm(fewshot)

    # 5. Specialised panel vs best single judge (pooled, judges with 3 orderings)
    panel = {}
    full = {j: data[j] for j in data if all(data[j][o] for o in ORDERS)}
    if len(full) >= 2:
        crit_agr = defaultdict(dict)
        for j, by_order in full.items():
            per = defaultdict(list)
            for o in ORDERS:
                for c, v in by_order[o].items():
                    per[c[0]].append(v)
            for crit, vals in per.items():
                crit_agr[crit][j] = sum(vals) / len(vals)
        assignment = {crit: max(js, key=js.get) for crit, js in crit_agr.items()}
        best = max(full, key=lambda j: agreement[j]["pooled"]["estimate"])
        diff = defaultdict(list)
        for o in ORDERS:
            for c, v in full[best][o].items():
                pj = assignment[c[0]]
                if c in full[pj][o]:
                    diff[c].append(full[pj][o][c] - v)
        panel_vals = defaultdict(list)
        for o in ORDERS:
            for c in full[best][o]:
                pj = assignment[c[0]]
                if c in full[pj][o]:
                    panel_vals[c].append(full[pj][o][c])
        panel = {
            "assignment": assignment,
            "best_single_judge": best,
            "panel_agreement": strip(cluster_bootstrap(panel_vals, args.bootstrap, "panel:agreement")),
            "panel_minus_best": strip(cluster_bootstrap(diff, args.bootstrap, f"panel:minus:{best}")),
            "note": "in-sample selection: the assignment is chosen on the same cases; single comparison",
        }

    # 4. Order effects (alternative ordering minus original, paired by case)
    order_effects = {}
    for j, by_order in data.items():
        base = by_order["original"]
        for alt in ("reversed", "permuted"):
            if base and by_order[alt]:
                common = [c for c in by_order[alt] if c in base]
                order_effects[f"{j}:{alt}"] = cluster_bootstrap(
                    {c: [by_order[alt][c] - base[c]] for c in common}, args.bootstrap, f"order:{j}:{alt}")
    if order_effects:
        holm(order_effects)

    # 7. Usable-answer rate per judge and ordering
    usable = defaultdict(dict)
    for j in data:
        for o in ORDERS:
            entries = load_entries(j, o)
            if not entries:
                continue
            counts = defaultdict(int)
            for r in entries:
                counts[r.get("status", "ok")] += 1
            usable[j][o] = {"n_usable": counts.get("ok", 0), "n_expected": len(entries),
                            "rate": round(counts.get("ok", 0) / len(entries), 6),
                            "status_counts": dict(sorted(counts.items()))}

    # 8. Sensitivity to unusable answers: excluded (headline) vs counted as disagreements
    sensitivity = defaultdict(dict)
    for j in data:
        worst = {o: load_worst_case(j, o) for o in ORDERS}
        conditions = [o for o in ORDERS if worst[o]]
        if all(worst[o] for o in ORDERS):
            conditions.append("pooled")
        for o in conditions:
            if o not in agreement[j]:
                continue
            orders = ORDERS if o == "pooled" else [o]
            by_case = defaultdict(list)
            for oo in orders:
                for c, v in worst[oo].items():
                    by_case[c].append(v)
            w = strip(cluster_bootstrap(by_case, args.bootstrap, f"worst:{j}:{o}"))
            h = agreement[j][o]
            sensitivity[j][o] = {
                "excluding_unusable": {k: h[k] for k in ("estimate", "ci95", "n_cases", "n_case_runs")},
                "unusable_as_disagreement": w,
                "difference_pp": round((h["estimate"] - w["estimate"]) * 100, 2),
                "flag": not (h["ci95"][0] <= w["estimate"] <= h["ci95"][1]),
            }

    out = {
        "description": "Agreement with ground truth: mean of per-case agreement; 95% CI = case-level cluster "
                       "bootstrap (all orderings of a case resampled together). 'pooled' only for judges with "
                       "all three orderings. Few-shot: same evaluable cases, original order; paired bootstrap; "
                       "Holm across judges.",
        "n_bootstrap": args.bootstrap,
        "agreement": agreement,
        "paired_vs_top": paired,
        "fewshot_gain": fewshot,
        "order_effects": order_effects,
        "specialised_panel": panel,
        "usable_answers": usable,
        "sensitivity_unusable": sensitivity,
    }
    # One file per (models, condition): pooled + all models keeps the historical name.
    suffix = ("" if args.models == "all" else f"_{args.models}") + ("" if cond == "pooled" else f"_{cond}")
    out_json = OUT_JSON.with_name(f"groundtruth_stats{suffix}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {out_json}")

    print(f"\n=== Agreement ({cond}) ===")
    for j, s in sorted(in_cond.items(), key=lambda kv: -kv[1]["estimate"]):
        print(f"  {j:<22} {s['estimate'] * 100:5.1f}%  [{s['ci95'][0] * 100:5.1f}, {s['ci95'][1] * 100:5.1f}]  "
              f"cases={s['n_cases']} runs={s['n_case_runs']}")
    if missing:
        print(f"  (not in '{cond}': {', '.join(missing)})")
    if paired:
        print(f"\n=== Paired difference: {paired['reference']} minus judge ({cond}) ===")
        for j, s in sorted(paired["differences"].items(), key=lambda kv: kv[1]["estimate"]):
            print(f"  {j:<22} {_fmt(s)}")
    print("\n=== Few-shot gain (original order, same cases) ===")
    for j, s in sorted(fewshot.items(), key=lambda kv: -kv[1]["estimate"]):
        print(f"  {j:<22} {s['baseline'] * 100:5.1f}% -> {s['fewshot'] * 100:5.1f}%  {_fmt(s)}")
    if panel:
        pa, pm = panel["panel_agreement"], panel["panel_minus_best"]
        print(f"\n=== Specialised panel (in-sample) vs best single judge ({panel['best_single_judge']}) ===")
        print(f"  assignment: {panel['assignment']}")
        print(f"  panel {pa['estimate'] * 100:.2f}%  panel - best {pm['estimate'] * 100:+.2f} pp  "
              f"CI95 [{pm['ci95'][0] * 100:+.2f}, {pm['ci95'][1] * 100:+.2f}]  p={pm['p_two_sided_vs_0']:.3f}")
    print("\n=== Order effects (ordering minus original, paired by case) ===")
    for name, s in order_effects.items():
        print(f"  {name:<32} {_fmt(s)}")
    print("\n=== Usable answers (status ok / corpus cases) ===")
    for j, by_o in usable.items():
        cells = "  ".join(f"{o} {u['n_usable']}/{u['n_expected']}" for o, u in by_o.items())
        print(f"  {j:<22} {cells}")
    print("\n=== Sensitivity: excluding unusable vs counted as disagreements ===")
    for j, by_o in sensitivity.items():
        for o, s in by_o.items():
            h, w = s["excluding_unusable"], s["unusable_as_disagreement"]
            if s["difference_pp"] or s["flag"]:
                print(f"  {j:<22} {o:<9} {h['estimate'] * 100:5.1f}% vs {w['estimate'] * 100:5.1f}%  "
                      f"({s['difference_pp']:+.1f} pp){'  FLAG' if s['flag'] else ''}")

    if not args.no_figure and in_cond:
        forest(in_cond, cond, f"agreement_forest_{cond}")


if __name__ == "__main__":
    main()
