# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""Formal self-preference analysis for the judge × generator benchmark.

Two complementary measures per judge j, both computed per prompt u and
*relative to reference judges* R_j (judges from another family than j), so that
a genuinely better output is not mistaken for self-preference:

1. SPR (paper §5.2 definition): share of prompts on which j ranks its own output
   first among all generators (ties share the credit). Reference: how often the
   judges in R_j rank j's output first on the same prompts. Excess = SPR − ref.
   Family variant: same with j's whole family (relevant when a family has
   several members, e.g. gemma3/gemma4, mistral/ministral).

2. Score-level bias (difference-in-differences): on prompt u,
       d_u = [s_j(j) − m_R(j)] − mean_{g ∉ fam(j)} [s_j(g) − m_R(g)]
   where m_R(g) is the mean score the reference judges give to g on u. It removes
   both output quality (m_R) and judge severity (second term). Sibling variant
   replaces j's own output by its family siblings.

Uncertainty: percentile bootstrap over prompts (prompts are the independent
unit), two-sided bootstrap p-value. Each measure is a family of tests across
judges: we report the Holm-adjusted p and the Bonferroni-adjusted CI (level
1 - 0.05/k); ci95 is the unadjusted interval, kept for reference only. One named
seed per (measure, judge), so adding a judge does not change other judges'
numbers. Stdlib only.
"""

import random
from collections import defaultdict


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _bootstrap(values, n_boot, seed):
    rng = random.Random(seed)
    vals = [v for v in values if v is not None]
    n = len(vals)
    if n < 5:
        return None
    est = sum(vals) / n
    means = sorted(sum(rng.choices(vals, k=n)) / n for _ in range(n_boot))
    lo, hi = means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]
    p_le = sum(1 for m in means if m <= 0) / n_boot
    p_ge = sum(1 for m in means if m >= 0) / n_boot
    p = min(1.0, max(2 * min(p_le, p_ge), 1 / n_boot))
    return {"estimate": round(est, 4), "ci95": [round(lo, 4), round(hi, 4)], "p": round(p, 4), "n_prompts": n,
            "_means": means}


def _holm(results: dict[str, dict]):
    items = sorted(((r["p"], k) for k, r in results.items() if r), key=lambda x: x[0])
    m = len(items)
    running = 0.0
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        results[k]["p_holm"] = round(running, 4)
        results[k]["significant"] = running < 0.05
    for r in results.values():
        if not r:
            continue
        means, a = r.pop("_means"), 0.05 / m
        r["ci_bonferroni"] = [round(means[int(a / 2 * len(means))], 4),
                              round(means[int((1 - a / 2) * len(means)) - 1], 4)]
        r["family_size"] = m


def self_preference_analysis(entries, judges, gens, family_of, n_boot=10000, caveats=None):
    S = {(e["judge"], e["gen"], e["id"]): e["score"] for e in entries}
    prompts = sorted({e["id"] for e in entries})
    fam = {m: family_of(m) for m in set(judges) | set(gens)}

    def top_share(k, u, members):
        sc = {g: S.get((k, g, u)) for g in gens}
        sc = {g: s for g, s in sc.items() if s is not None}
        if len(sc) < len(gens):  # need the full ranking for this prompt
            return None
        mx = max(sc.values())
        arg = [g for g, s in sc.items() if s == mx]
        return sum(1 for g in arg if g in members) / len(arg)

    def ref_mean(refs, g, u):
        return _mean([S.get((k, g, u)) for k in refs])

    per = {"spr_self": {}, "spr_family": {}, "score_bias_self": {}, "score_bias_siblings": {}}
    raw_rates = {}
    for j in judges:
        refs = [k for k in judges if fam[k] != fam[j]]
        family = {g for g in gens if fam[g] == fam[j]}
        siblings = family - {j}
        outsiders = [g for g in gens if g not in family]
        if j not in gens or not refs or not outsiders:
            continue

        def did(targets, u):
            """Mean adjusted score j gives to `targets` minus to outsiders, on prompt u."""
            def adjusted(g):
                s, m = S.get((j, g, u)), ref_mean(refs, g, u)
                return None if s is None or m is None else s - m
            t = [x for x in map(adjusted, targets) if x is not None]
            o = [x for x in map(adjusted, outsiders) if x is not None]
            return _mean(t) - _mean(o) if t and o else None

        spr_u, ref_u, fspr_u, d_self, d_sib = [], [], [], [], []
        for u in prompts:
            spr_u.append(top_share(j, u, {j}))
            ref_u.append(_mean([top_share(k, u, {j}) for k in refs]))
            fa = top_share(j, u, family)
            fr = _mean([top_share(k, u, family) for k in refs])
            fspr_u.append(None if fa is None or fr is None else fa - fr)
            d_self.append(did([j], u))
            d_sib.append(did(sorted(siblings), u) if siblings else None)

        excess = [None if a is None or r is None else a - r for a, r in zip(spr_u, ref_u)]
        b = _bootstrap(excess, n_boot, f"spr_self:{j}")
        if b:
            b.update({
                "spr": round(_mean(spr_u), 4),
                "reference": round(_mean(ref_u), 4),
                "excess": b["estimate"],
                "chance": round(1 / len(gens), 4),
            })
        per["spr_self"][j] = b
        bf = _bootstrap(fspr_u, n_boot, f"spr_family:{j}")
        if bf:
            bf.update({"excess": bf["estimate"], "family": fam[j], "family_size": len(family),
                       "chance": round(len(family) / len(gens), 4)})
        per["spr_family"][j] = bf
        per["score_bias_self"][j] = _bootstrap(d_self, n_boot, f"score_bias_self:{j}")
        per["score_bias_siblings"][j] = (
            dict(_bootstrap(d_sib, n_boot, f"score_bias_siblings:{j}") or {}, siblings=sorted(siblings))
            if siblings else None
        )
        raw_rates[j] = {"reference_judges": refs}

    for measure in per.values():
        _holm({k: v for k, v in measure.items() if v})

    by_judge = {}
    for j in per["spr_self"]:
        by_judge[j] = {
            "spr_self": per["spr_self"][j],
            "spr_family": per["spr_family"][j],
            "score_bias_self": per["score_bias_self"][j],
            "score_bias_siblings": per["score_bias_siblings"][j],
            **raw_rates[j],
        }
        if caveats and j in caveats:
            by_judge[j]["caveat"] = caveats[j]

    return {
        "description": (
            "Self-preference relative to reference judges from other families. "
            "spr_self: share of prompts where the judge ranks its own output first (ties split) "
            "vs how often reference judges do; spr_family: same for the judge's family; "
            "score_bias_*: difference-in-differences on composite scores (controls output quality "
            "and judge severity). Percentile bootstrap over prompts, two-sided p; per measure, Holm-adjusted p "
            "and Bonferroni-adjusted CI across judges (ci95 = unadjusted, reference only)."
        ),
        "n_prompts": len(prompts),
        "n_bootstrap": n_boot,
        "by_judge": by_judge,
        "significant_positive": sorted(
            f"{j}:{m}" for j, v in by_judge.items()
            for m in ("spr_self", "spr_family", "score_bias_self", "score_bias_siblings")
            if v.get(m) and v[m].get("significant") and v[m]["estimate"] > 0
        ),
        "significant_negative": sorted(
            f"{j}:{m}" for j, v in by_judge.items()
            for m in ("spr_self", "spr_family", "score_bias_self", "score_bias_siblings")
            if v.get(m) and v[m].get("significant") and v[m]["estimate"] < 0
        ),
    }
