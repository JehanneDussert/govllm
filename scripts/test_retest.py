# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""Test-retest reliability of the ground-truth judges (protocol validated before the run).

Design: 8 judges x 49 cases, temperature 0. Original order repeated K = 5 times
(run_label retest-orig-r1..r5), plus 2 repetitions in reversed order and 2 in permuted
order (retest-rev-r1..r2, retest-perm-r1..r2) as the order control. The paper's runs
(run_label main) are not part of the protocol; they only appear in the sections marked
exploratory.

Protocol metrics (descriptive, unadjusted 95% CI, case-level cluster bootstrap):
  - flip rate per sub-question between repetitions (mean over the 10 pairs of the
    5 original repetitions) and raw agreement (= 1 - flip rate);
  - Krippendorff's alpha (binary/nominal, unusable answers = missing), units = (case,
    sub-question), coders = the 5 original repetitions;
  - dispersion of validity (agreement with the ground truth) between the 5 original
    repetitions: SD and range;
  - unusable-answer rate per repetition.
Family 1, "order effect beyond repetition" (8 tests, one per judge): per case,
  mean |validity difference| between an original and an alternative-order repetition
  (5 x 4 pairs) minus mean |validity difference| between two original repetitions
  (10 pairs). > 0 = changing the order moves validity more than repeating the call.
Family 2, "majority vote vs single call" (8 tests): per case, validity of the
  per-sub-question majority over the 5 original repetitions minus the mean validity of
  a single call.
Each family: Holm-adjusted p and Bonferroni-adjusted CI (groundtruth_stats.holm).

Input: a CSV export of govllm.groundtruth_results joined with groundtruth_cases (read
only), e.g.

  docker exec langfuse-db psql -U langfuse -d langfuse -c "COPY (SELECT r.run_label,
    r.question_order, r.judge_model, r.case_id, c.criterion, r.status, r.answers,
    c.expected, r.agreement, r.created_at, r.model_digest FROM govllm.groundtruth_results r JOIN
    govllm.groundtruth_cases c ON c.id = r.case_id ORDER BY r.created_at)
    TO STDOUT WITH CSV HEADER" > gt_all.csv

Usage:
  python scripts/test_retest.py gt_all.csv [--bootstrap 10000]
Validity for the v2 (section "validity"): agreement with the ground truth from the
repeated runs only (they carry the model digest), per judge and ordering = mean over the
repetitions of that ordering (5 original, 2 reversed, 2 permuted), then pooled over the
three orderings per case; unusable answers excluded, worst case (unusable = 0) reported.

Writes docs/ground_truth/analysis/test_retest.json. Stdlib only.
"""

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from groundtruth_stats import cluster_bootstrap, holm, strip
from model_registry import label, slug_of

OUT = Path("docs/ground_truth/analysis/test_retest.json")
ORIG = [f"retest-orig-r{i}" for i in range(1, 6)]
ALT = ["retest-rev-r1", "retest-rev-r2", "retest-perm-r1", "retest-perm-r2"]
ALT_ORDER = {"retest-rev-r1": "reversed", "retest-rev-r2": "reversed",
             "retest-perm-r1": "permuted", "retest-perm-r2": "permuted"}


def load(path):
    """(judge, run_label) -> case -> {"criterion", "status", "answers", "expected", "agreement"}."""
    data = defaultdict(dict)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ok = r["status"] == "ok"
            answers = json.loads(r["answers"]) if ok and r["answers"] else None
            expected = json.loads(r["expected"])
            agreement = None
            if ok:
                agreement = sum(answers.get(q) == v for q, v in expected.items()) / len(expected)
                stored = float(r["agreement"])
                assert abs(agreement - stored) < 1e-9, (r["case_id"], agreement, stored)
            run = r["run_label"]
            if run == "main":  # the paper's runs: one row per (case, order)
                run = f"main-{r['question_order']}"
            key = (slug_of(r["judge_model"]), run)
            assert r["case_id"] not in data[key], ("duplicate", key, r["case_id"])
            data[key][r["case_id"]] = {"criterion": r["criterion"], "status": r["status"],
                                       "order": r["question_order"], "answers": answers,
                                       "expected": expected, "agreement": agreement,
                                       "digest": r.get("model_digest") or None}
    return data


def alpha_parts(values):
    """Per unit (list of usable binary values): (o01, n0, n1) of the coincidence matrix."""
    m = len(values)
    if m < 2:
        return 0.0, 0, 0
    n1 = sum(values)
    n0 = m - n1
    return n0 * n1 / (m - 1), n0, n1


def alpha_from(o01, n0, n1):
    n = n0 + n1
    if n0 == 0 or n1 == 0:
        return None
    return 1 - (n - 1) * o01 / (n0 * n1)


def bootstrap_ratio(per_case, n_boot, seed, fn):
    """Cluster bootstrap of a statistic computed from summed per-case tuples."""
    import random
    rng = random.Random(seed)
    cases = sorted(per_case)
    k = len(per_case[cases[0]])

    def stat(sample):
        tot = [0.0] * k
        for c in sample:
            for i, v in enumerate(per_case[c]):
                tot[i] += v
        return fn(*tot)

    est = stat(cases)
    vals = sorted(v for v in (stat(rng.choices(cases, k=len(cases))) for _ in range(n_boot)) if v is not None)
    return {"estimate": None if est is None else round(est, 6),
            "ci95": [round(vals[int(0.025 * len(vals))], 6), round(vals[int(0.975 * len(vals)) - 1], 6)]
            if vals else None, "n_cases": len(cases)}


def bootstrap_sd(by_case_runs, n_boot, seed):
    """SD and range of the global validity across runs, with a case bootstrap of the SD."""
    import random
    rng = random.Random(seed)
    cases = sorted(by_case_runs)

    def per_run(sample):
        k = len(by_case_runs[cases[0]])
        return [sum(by_case_runs[c][i] for c in sample) / len(sample) for i in range(k)]

    g = per_run(cases)
    sds = sorted(statistics.stdev(per_run(rng.choices(cases, k=len(cases)))) for _ in range(n_boot))
    return {"validity_per_run": [round(x, 6) for x in g], "sd": round(statistics.stdev(g), 6),
            "range": round(max(g) - min(g), 6),
            "sd_ci95": [round(sds[int(0.025 * n_boot)], 6), round(sds[int(0.975 * n_boot) - 1], 6)]}


def majority_agreement(rows):
    expected = rows[0]["expected"]
    hits = 0
    for q, v in expected.items():
        votes = [r["answers"].get(q) for r in rows]
        maj = sum(1 for x in votes if x is True) > len(votes) / 2
        hits += maj == v
    return hits / len(expected)


RUNS_BY_ORDER = {"original": ORIG, "reversed": ["retest-rev-r1", "retest-rev-r2"],
                 "permuted": ["retest-perm-r1", "retest-perm-r2"]}


def validity(data, judges, B):
    """Validity of each judge from the repeated runs (the v2 source), with case-bootstrap CIs."""
    res = {}
    for j in judges:
        runs = {o: [data[(j, r)] for r in rr] for o, rr in RUNS_BY_ORDER.items()}
        digests = sorted({row["digest"] for rs in runs.values() for run in rs for row in run.values()
                          if row["digest"]})
        cases = sorted(runs["original"][0])
        per_case = {o: {} for o in runs}
        worst = {o: {} for o in runs}
        for o, rs in runs.items():
            for c in cases:
                v = [run[c]["agreement"] for run in rs if run[c]["agreement"] is not None]
                if v:
                    per_case[o][c] = statistics.mean(v)
                worst[o][c] = statistics.mean(run[c]["agreement"] or 0.0 for run in rs)
        crit_of = {c: runs["original"][0][c]["criterion"] for c in cases}
        jr = {"digests": digests, "orders": {}}
        for o in runs:
            est = strip(cluster_bootstrap({c: [v] for c, v in per_case[o].items()}, B, f"validity:{j}:{o}"))
            est.pop("p_two_sided_vs_0", None)
            est["n_usable_cases"] = len(per_case[o])
            est["worst_case"] = round(statistics.mean(worst[o].values()), 6)
            est["per_criterion"] = {
                cr: round(statistics.mean(v for c, v in per_case[o].items() if crit_of[c] == cr), 6)
                for cr in sorted(set(crit_of.values()))}
            jr["orders"][o] = est
        pooled = strip(cluster_bootstrap({c: [per_case[o][c] for o in runs if c in per_case[o]] for c in cases},
                                         B, f"validity:{j}:pooled"))
        pooled.pop("p_two_sided_vs_0", None)
        pooled["per_criterion"] = {
            cr: round(statistics.mean(per_case[o][c] for o in runs for c in cases
                                      if c in per_case[o] and crit_of[c] == cr), 6)
            for cr in sorted(set(crit_of.values()))}
        jr["pooled"] = pooled
        res[label(j)] = jr
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--bootstrap", type=int, default=10000)
    args = ap.parse_args()
    B = args.bootstrap
    data = load(args.csv)
    judges = sorted({j for j, _ in data}, key=lambda s: s)
    out = {"protocol": {}, "exploratory": {}}
    P, E = out["protocol"], out["exploratory"]

    # ── Unusable answers ──────────────────────────────────────────────────────
    unusable = []
    rate = defaultdict(dict)
    for (j, run), cases in data.items():
        if run.startswith("main"):
            continue
        bad = [c for c, r in cases.items() if r["status"] != "ok"]
        rate[label(j)][run] = {"unusable": len(bad), "n": len(cases)}
        for c in bad:
            r = cases[c]
            unusable.append({"judge": label(j), "run": run, "order": r["order"], "status": r["status"],
                             "criterion": r["criterion"], "case_id": c})
    P["unusable"] = {"total": len(unusable), "items": sorted(unusable, key=lambda x: (x["judge"], x["run"])),
                     "by_judge_order": dict(Counter(f"{u['judge']} | {u['order']}" for u in unusable)),
                     "rate_per_run": rate}

    per_judge, fam1, fam2 = {}, {}, {}
    e_flip_fam, e_main, e_crit, e_signed = {}, {}, {}, {}
    for j in judges:
        reps = [data[(j, r)] for r in ORIG]
        cases = sorted(reps[0])
        assert all(sorted(r) == cases for r in reps), j

        # Flip rate between the 5 original repetitions (per sub-question, mean over pairs)
        flips_case = {}
        per_q = Counter()
        per_q_n = Counter()
        for c in cases:
            vals = []
            for a, b in combinations(range(5), 2):
                ra, rb = reps[a][c], reps[b][c]
                if ra["answers"] is None or rb["answers"] is None:
                    continue
                for q in ra["expected"]:
                    d = ra["answers"].get(q) != rb["answers"].get(q)
                    vals.append(d)
                    per_q[q] += d
                    per_q_n[q] += 1
            flips_case[c] = vals
        # mean over pairs = mean over all (pair, unit) when no answer is missing (true here: 0 unusable)
        flip = strip(cluster_bootstrap({c: [float(v) for v in vs] for c, vs in flips_case.items()},
                                       B, f"retest:flip:{j}"))
        flip.pop("p_two_sided_vs_0", None)
        cases_with_flip = sum(1 for c in cases if any(flips_case[c]))

        # Krippendorff's alpha over the 5 original repetitions
        parts = {}
        for c in cases:
            o01 = n0 = n1 = 0.0
            for q in reps[0][c]["expected"]:
                v = [r[c]["answers"][q] for r in reps if r[c]["answers"] is not None and q in r[c]["answers"]]
                v = [1 if x is True else 0 for x in v]
                a, b0, b1 = alpha_parts(v)
                o01 += a
                n0 += b0
                n1 += b1
            parts[c] = (o01, n0, n1)
        alpha = bootstrap_ratio(parts, B, f"retest:alpha:{j}", alpha_from)

        # Dispersion of validity across the 5 original repetitions
        disp = bootstrap_sd({c: [r[c]["agreement"] for r in reps] for c in cases}, B, f"retest:sd:{j}")

        identical_runs = all(reps[0][c]["answers"] == r[c]["answers"] for r in reps[1:] for c in cases)
        per_judge[label(j)] = {
            "flip_rate": {"estimate": flip["estimate"], "ci95": flip["ci95"]},
            "raw_agreement": round(1 - flip["estimate"], 6),
            "flip_rate_per_subquestion": {q: round(per_q[q] / per_q_n[q], 6) for q in sorted(per_q)},
            "cases_with_any_flip": cases_with_flip,
            "krippendorff_alpha": alpha,
            "validity_dispersion": disp,
            "five_runs_identical": identical_runs,
            "n_cases": len(cases),
        }

        # Family 1: order effect beyond repetition (|Δ validity|, paired by case)
        alts = [data[(j, r)] for r in ALT]
        f1 = {}
        f1_flip = {}
        for c in cases:
            v_orig = [r[c]["agreement"] for r in reps]
            v_alt = [r[c]["agreement"] for r in alts if r[c]["agreement"] is not None]
            if not v_alt:
                continue
            d_rep = statistics.mean(abs(a - b) for a, b in combinations(v_orig, 2))
            d_ord = statistics.mean(abs(a - b) for a in v_orig for b in v_alt)
            f1[c] = [d_ord - d_rep]
            # exploratory variant on sub-question flips
            qs = list(reps[0][c]["expected"])
            fr = statistics.mean(reps[a][c]["answers"].get(q) != reps[b][c]["answers"].get(q)
                                 for a, b in combinations(range(5), 2) for q in qs)
            fo = statistics.mean(ro[c]["answers"].get(q) != ra[c]["answers"].get(q)
                                 for ro in reps for ra in alts if ra[c]["answers"] is not None for q in qs)
            f1_flip[c] = [fo - fr]
        fam1[label(j)] = cluster_bootstrap(f1, B, f"retest:fam1:{j}")
        e_flip_fam[label(j)] = cluster_bootstrap(f1_flip, B, f"retest:fam1flip:{j}")

        # Family 2: majority vote over the 5 original repetitions vs single call
        f2 = {c: [majority_agreement([r[c] for r in reps]) - statistics.mean(r[c]["agreement"] for r in reps)]
              for c in cases}
        fam2[label(j)] = cluster_bootstrap(f2, B, f"retest:fam2:{j}")
        fam2[label(j)]["majority_validity"] = round(
            statistics.mean(majority_agreement([r[c] for r in reps]) for c in cases), 6)
        fam2[label(j)]["single_call_validity"] = round(
            statistics.mean(r[c]["agreement"] for r in reps for c in cases), 6)

        # ── Exploratory ───────────────────────────────────────────────────────
        # (a) paper run vs repetitions: computed after the loop (main rows are keyed per order)
        # (b) per criterion: original (mean of 5) vs reversed / permuted (mean of 2), + repetition range
        crit = defaultdict(dict)
        for cr in sorted({reps[0][c]["criterion"] for c in cases}):
            cs = [c for c in cases if reps[0][c]["criterion"] == cr]
            per_rep = [statistics.mean(r[c]["agreement"] for c in cs) for r in reps]

            def mean_alt(runs):
                v = [data[(j, rr)][c]["agreement"] for rr in runs for c in cs
                     if data[(j, rr)][c]["agreement"] is not None]
                return statistics.mean(v)
            o = statistics.mean(per_rep)
            rv = mean_alt(["retest-rev-r1", "retest-rev-r2"])
            pm = mean_alt(["retest-perm-r1", "retest-perm-r2"])
            alt_runs = [statistics.mean(data[(j, rr)][c]["agreement"] for c in cs
                                        if data[(j, rr)][c]["agreement"] is not None) for rr in ALT]
            crit[cr] = {"n": len(cs), "original_mean5": round(o, 4),
                        "original_range5": round(max(per_rep) - min(per_rep), 4),
                        "reversed_mean2": round(rv, 4), "permuted_mean2": round(pm, 4),
                        "delta_rev": round(rv - o, 4), "delta_perm": round(pm - o, 4),
                        "alt_runs": [round(x, 4) for x in alt_runs]}
        e_crit[label(j)] = crit

        # (c) signed global order effect on the retest data (alt-order mean minus original mean)
        for alt, runs in (("reversed", ["retest-rev-r1", "retest-rev-r2"]),
                          ("permuted", ["retest-perm-r1", "retest-perm-r2"])):
            d = {}
            for c in cases:
                va = [data[(j, rr)][c]["agreement"] for rr in runs if data[(j, rr)][c]["agreement"] is not None]
                if va:
                    d[c] = [statistics.mean(va) - statistics.mean(r[c]["agreement"] for r in reps)]
            e_signed[f"{label(j)}:{alt}"] = cluster_bootstrap(d, B, f"retest:signed:{j}:{alt}")

    holm(fam1)
    holm(fam2)
    holm(e_flip_fam)
    holm(e_signed)
    P["per_judge"] = per_judge
    P["family1_order_beyond_repetition"] = fam1
    P["family2_majority_vs_single"] = fam2

    # (a) paper run (main, original order) vs the 5 repetitions
    for j in judges:
        reps = [data[(j, r)] for r in ORIG]
        mo = {c: r["answers"] for c, r in data[(j, "main-original")].items() if r["answers"] is not None}
        cs = sorted(mo)
        same = sum(1 for c in cs if all(mo[c] == r[c]["answers"] for r in reps))
        sub = [mo[c].get(q) != r[c]["answers"].get(q) for c in cs for r in reps for q in r[c]["expected"]]
        e_main[label(j)] = {
            "n_cases": len(cs), "cases_identical_to_all_5": same,
            "flip_rate_main_vs_reps": round(statistics.mean(sub), 6),
            "validity_main": round(statistics.mean(data[(j, "main-original")][c]["agreement"] for c in cs), 6),
            "validity_reps_mean": round(statistics.mean(r[c]["agreement"] for r in reps for c in cs), 6)}
    E["a_main_run_vs_repetitions"] = e_main
    E["b_per_criterion_retest"] = e_crit
    E["c_signed_order_effect_retest_holm16"] = e_signed
    E["d_family1_on_subquestion_flips"] = e_flip_fam

    out["validity"] = validity(data, judges, B)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
