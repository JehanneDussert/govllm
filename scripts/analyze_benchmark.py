#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Benchmark analysis — produces docs/benchmark/analysis/summary.json

Analyses:
  1. Delta specialized profile vs quality_baseline (single judge)
  2. Correlation model size / score
  3. Inter-judge disagreement by prompt (top 10 highest variance)
  4. Intra-judge variance by domain
  5. Judge × generator bias matrix (self-preference)
  6. Self-eval vs cross-eval bias
  7. Formal self-preference: SPR (paper definition) + score-level bias,
     both relative to the other judges, with bootstrap CIs and Holm-corrected tests

Models come from docs/benchmark/models.json (see scripts/model_registry.py).

Usage:
    python scripts/analyze_benchmark.py                 # all registered models -> summary_all.json
    python scripts/analyze_benchmark.py --models paper  # the 4 models of arXiv v1 -> summary.json
"""

import argparse
import json
import math
import datetime
from pathlib import Path
from collections import defaultdict

from model_registry import MODELS, SETS, select, slug_of, family
from self_preference import self_preference_analysis

RESULTS_DIR = Path("docs/benchmark/results")
PROMPTS_FILE = Path("docs/benchmark/prompts.json")
OUTPUT_DIR = Path("docs/benchmark/analysis")

USE_CASES = ["general", "summarization", "translation", "code", "administrative_writing", "analysis"]
BASELINE_USE_CASES = {"general", "summarization"}
SPECIALIZED_USE_CASES = {"translation", "code", "administrative_writing", "analysis"}


def _mean(values: list) -> float | None:
    v = [x for x in values if x is not None]
    return sum(v) / len(v) if v else None


def _stdev(values: list) -> float | None:
    v = [x for x in values if x is not None]
    if len(v) < 2:
        return None
    m = _mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def _pearson(xs: list, ys: list) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 2:
        return None
    mx = _mean([p[0] for p in pairs])
    my = _mean([p[1] for p in pairs])
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den = math.sqrt(sum((x - mx) ** 2 for x, _ in pairs) * sum((y - my) ** 2 for _, y in pairs))
    return round(num / den, 4) if den else None


def load_all_results(models: set[str]) -> tuple[list[dict], int]:
    entries = []
    n_files = 0
    for fpath in sorted(RESULTS_DIR.glob("*.json")):
        if fpath.name.endswith(".partial.json"):
            continue
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        gen = slug_of(data["model"])
        judge = slug_of(data["judge_model"])
        if gen not in models or judge not in models:
            continue
        n_files += 1
        for r in data["results"]:
            if r.get("status") != "OK" or r.get("score") is None:
                continue
            entries.append({
                "gen": gen,
                "judge": judge,
                "id": r["id"],
                "use_case": r["use_case"],
                "profile": r["governance_profile"],
                "score": r["score"],
                "criteria_scores": (r.get("eval") or {}).get("criteria_scores", []),
            })
    return entries, n_files


def load_prompt_meta() -> dict[str, dict]:
    with open(PROMPTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    meta = {}
    for uc, prompts in data["benchmark_prompts"].items():
        for p in prompts:
            meta[p["id"]] = {
                "use_case": uc,
                "difficulty": p.get("difficulty", "unknown"),
                "prompt": p.get("prompt", ""),
            }
    return meta


def r4(v) -> float | None:
    return round(v, 4) if v is not None else None


def difficulty_tests(entries, prompt_meta, tiers, n_boot=10000):
    """Specialised vs baseline profiles per difficulty tier, with uncertainty.

    Unit = prompt (mean score over all generator x judge pairs for that prompt);
    the two groups are different prompts (baseline use cases vs specialised ones),
    so the bootstrap is unpaired, resampling prompts within each group. Seed per
    tier. Holm-adjusted p and Bonferroni CI across the tiers tested.
    """
    import random

    per_prompt = defaultdict(list)
    for e in entries:
        per_prompt[e["id"]].append(e["score"])
    tests = {}
    for tier in tiers:
        ids = [pid for pid in per_prompt if prompt_meta.get(pid, {}).get("difficulty") == tier]
        base = [_mean(per_prompt[p]) for p in ids if prompt_meta[p]["use_case"] in BASELINE_USE_CASES]
        spec = [_mean(per_prompt[p]) for p in ids if prompt_meta[p]["use_case"] in SPECIALIZED_USE_CASES]
        if len(base) < 2 or len(spec) < 2:
            continue
        rng = random.Random(f"difficulty:{tier}")
        means = sorted(
            _mean(rng.choices(spec, k=len(spec))) - _mean(rng.choices(base, k=len(base)))
            for _ in range(n_boot)
        )
        p_le = sum(1 for m in means if m <= 0) / n_boot
        p_ge = sum(1 for m in means if m >= 0) / n_boot
        tests[tier] = {
            "delta": r4(_mean(spec) - _mean(base)),
            "ci95": [r4(means[int(0.025 * n_boot)]), r4(means[int(0.975 * n_boot) - 1])],
            "p": round(min(1.0, max(2 * min(p_le, p_ge), 1 / n_boot)), 4),
            "n_prompts_specialized": len(spec),
            "n_prompts_baseline": len(base),
            "_means": means,
        }
    k = len(tests)
    running = 0.0
    for i, (pv, tier) in enumerate(sorted((v["p"], t) for t, v in tests.items())):
        running = max(running, min(1.0, (k - i) * pv))
        tests[tier]["p_holm"] = round(running, 4)
    for v in tests.values():
        means, a = v.pop("_means"), 0.05 / k
        v["ci_bonferroni"] = [r4(means[int(a / 2 * n_boot)]), r4(means[int((1 - a / 2) * n_boot) - 1])]
        v["family_size"] = k
    return tests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="all",
                        help=f"'all', a set from models.json {sorted(SETS)}, or comma-separated slugs")
    parser.add_argument("--bootstrap", type=int, default=10000)
    args = parser.parse_args()

    selected = select(args.models)
    out_name = "summary.json" if args.models == "paper" else f"summary_{args.models.replace(',', '_')}.json"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    entries, n_files = load_all_results(set(selected))
    prompt_meta = load_prompt_meta()

    all_gens = sorted(set(e["gen"] for e in entries))
    all_judges = sorted(set(e["judge"] for e in entries))
    # Finding A in the paper uses the nominal size from the model name.
    model_sizes = {g: MODELS[g]["size_b_nominal"] for g in all_gens}

    # ── 1. Delta specialized profile vs quality_baseline ─────────────────────

    delta_by_gen: dict[str, dict] = {}
    for gen in all_gens:
        gen_e = [e for e in entries if e["gen"] == gen]
        baseline = [e["score"] for e in gen_e if e["use_case"] in BASELINE_USE_CASES]
        by_uc = {}
        for uc in sorted(SPECIALIZED_USE_CASES):
            s = [e["score"] for e in gen_e if e["use_case"] == uc]
            bm = _mean(baseline)
            sm = _mean(s)
            by_uc[uc] = {
                "mean": r4(sm),
                "delta_vs_baseline": r4(sm - bm) if (sm is not None and bm is not None) else None,
                "n": len(s),
            }
        delta_by_gen[gen] = {
            "quality_baseline_mean": r4(_mean(baseline)),
            "quality_baseline_n": len(baseline),
            "specialized": by_uc,
        }

    difficulties = ["easy", "medium", "medium-hard", "adversarial", "hard"]
    delta_by_diff: dict[str, dict] = {}
    for diff in difficulties:
        bl = [e["score"] for e in entries if prompt_meta.get(e["id"], {}).get("difficulty") == diff and e["use_case"] in BASELINE_USE_CASES]
        sp = [e["score"] for e in entries if prompt_meta.get(e["id"], {}).get("difficulty") == diff and e["use_case"] in SPECIALIZED_USE_CASES]
        bm, sm = _mean(bl), _mean(sp)
        delta_by_diff[diff] = {
            "quality_baseline_mean": r4(bm),
            "quality_baseline_n": len(bl),
            "specialized_mean": r4(sm),
            "specialized_n": len(sp),
            "delta": r4(sm - bm) if (sm is not None and bm is not None) else None,
        }

    analysis_1 = {
        "description": "Compare mean score on quality_baseline profile (general+summarization) vs domain-specific profiles per use case. "
                       "by_difficulty_tests: prompt-level unpaired bootstrap per tier, Holm p and Bonferroni CI across tiers "
                       "(tiers with fewer than 2 prompts in a group are skipped).",
        "by_generator": delta_by_gen,
        "by_difficulty": delta_by_diff,
        "by_difficulty_tests": difficulty_tests(entries, prompt_meta, difficulties, n_boot=args.bootstrap),
    }

    # ── 2. Correlation model size / score ─────────────────────────────────────

    gen_stats: dict[str, dict] = {}
    for gen in all_gens:
        scores = [e["score"] for e in entries if e["gen"] == gen]
        gen_stats[gen] = {
            "size_B": model_sizes[gen],
            "size_B_reported": MODELS[gen]["size_b"],
            "mean_score": r4(_mean(scores)),
            "stdev": r4(_stdev(scores)),
            "n": len(scores),
        }

    sizes = [model_sizes[g] for g in all_gens]
    means = [gen_stats[g]["mean_score"] for g in all_gens]
    analysis_2 = {
        "description": "Mean composite score per generator model vs parameter count "
                       "(size_B = nominal size from the model name; size_B_reported = total parameters per `ollama show`)",
        "models": gen_stats,
        "pearson_size_vs_score": _pearson(sizes, means),
        "pearson_reported_size_vs_score": _pearson([MODELS[g]["size_b"] for g in all_gens], means),
        "n_models": len(all_gens),
    }

    # ── 3. Inter-judge disagreement by prompt ─────────────────────────────────

    # For each (gen, prompt_id): collect scores across all judges
    by_gen_prompt: dict[tuple, list[float]] = defaultdict(list)
    for e in entries:
        by_gen_prompt[(e["gen"], e["id"])].append(e["score"])

    # Aggregate per prompt_id across all generators
    by_prompt: dict[str, list[float]] = defaultdict(list)
    for (gen, pid), scores in by_gen_prompt.items():
        sd = _stdev(scores)
        if sd is not None:
            by_prompt[pid].append(sd)

    prompt_disagreement: dict[str, dict] = {}
    for pid, stdevs in by_prompt.items():
        meta = prompt_meta.get(pid, {})
        prompt_disagreement[pid] = {
            "use_case": meta.get("use_case", "?"),
            "difficulty": meta.get("difficulty", "?"),
            "mean_interjudge_stdev": r4(_mean(stdevs)),
            "n_generators": len(stdevs),
        }

    top10 = sorted(
        prompt_disagreement.items(),
        key=lambda x: x[1]["mean_interjudge_stdev"] or 0,
        reverse=True,
    )[:10]

    analysis_3 = {
        "description": "Std dev of composite scores across 4 judges per prompt (per generator, then averaged)",
        "all_prompts": prompt_disagreement,
        "top10_highest_disagreement": [{"id": pid, **meta} for pid, meta in top10],
    }

    # ── 4. Intra-judge variance by domain ─────────────────────────────────────

    intrajudge: dict[str, dict] = {}
    for judge in all_judges:
        intrajudge[judge] = {}
        for uc in USE_CASES:
            scores = [e["score"] for e in entries if e["judge"] == judge and e["use_case"] == uc]
            intrajudge[judge][uc] = {
                "mean": r4(_mean(scores)),
                "stdev": r4(_stdev(scores)),
                "n": len(scores),
            }

    analysis_4 = {
        "description": "Mean and std dev of scores per judge model × use case (across all generators × prompts)",
        "by_judge_and_domain": intrajudge,
    }

    # ── 5. Judge × generator bias matrix ──────────────────────────────────────

    matrix: dict[str, dict] = {}
    for judge in all_judges:
        matrix[judge] = {}
        for gen in all_gens:
            scores = [e["score"] for e in entries if e["judge"] == judge and e["gen"] == gen]
            matrix[judge][gen] = {
                "mean_score": r4(_mean(scores)),
                "n": len(scores),
                "is_self": judge == gen,
            }

    spr: dict[str, dict] = {}
    for judge in all_judges:
        self_score = matrix[judge].get(judge, {}).get("mean_score")
        cross = [matrix[judge][g]["mean_score"] for g in all_gens if g != judge and matrix[judge][g]["mean_score"] is not None]
        cross_mean = _mean(cross)
        # Legacy (arXiv v1) "SPR": fraction of other generators whose *mean* score is
        # below the judge's self score. Model-level, no quality control, no test —
        # kept for reproducibility only; see analysis_7 for the formal SPR.
        wins = sum(1 for s in cross if self_score is not None and s is not None and self_score > s)
        spr[judge] = {
            "self_score": self_score,
            "mean_cross_score": r4(cross_mean),
            "self_preference_delta": r4(self_score - cross_mean) if (self_score is not None and cross_mean is not None) else None,
            "spr": round(wins / len(cross), 4) if cross else None,
        }

    analysis_5 = {
        "description": "Mean composite score for each (judge_model, generator_model) pair; diagonal = self-evaluation. "
                       "self_preference_rate.spr is the legacy model-level measure used in arXiv v1 — see analysis_7.",
        "matrix": matrix,
        "self_preference_rate": spr,
    }

    # ── 6. Self-eval vs cross-eval bias ───────────────────────────────────────

    self_eval_bias: dict[str, dict] = {}
    for gen in all_gens:
        self_s = [e["score"] for e in entries if e["gen"] == gen and e["judge"] == gen]
        cross_s = [e["score"] for e in entries if e["gen"] == gen and e["judge"] != gen]
        sm, cm = _mean(self_s), _mean(cross_s)
        self_eval_bias[gen] = {
            "self_eval_mean": r4(sm),
            "cross_eval_mean": r4(cm),
            "bias_delta": r4(sm - cm) if (sm is not None and cm is not None) else None,
            "self_n": len(self_s),
            "cross_n": len(cross_s),
        }

    analysis_6 = {
        "description": "Comparison of self-evaluation (judge==generator) vs cross-evaluation scores per model",
        "by_generator": self_eval_bias,
    }

    # ── 7. Formal self-preference ────────────────────────────────────────────

    analysis_7 = self_preference_analysis(
        entries, all_judges, all_gens, family, n_boot=args.bootstrap,
        caveats={m: MODELS[m]["caveat"] for m in all_judges if MODELS[m].get("caveat")},
    )

    # ── Write output ──────────────────────────────────────────────────────────

    summary = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "models": all_gens,
        "n_result_files": n_files,
        "n_entries_used": len(entries),
        "analysis_1_delta_specialized_vs_baseline": analysis_1,
        "analysis_2_model_size_correlation": analysis_2,
        "analysis_3_interjudge_disagreement_by_prompt": analysis_3,
        "analysis_4_intrajudge_variance_by_domain": analysis_4,
        "analysis_5_judge_generator_bias_matrix": analysis_5,
        "analysis_6_self_eval_vs_cross_eval": analysis_6,
        "analysis_7_self_preference_formal": analysis_7,
    }

    out = OUTPUT_DIR / out_name
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # ── Quick digest ──────────────────────────────────────────────────────────

    print(f"Written: {out}  ({len(entries)} entries from {summary['n_result_files']} files)")

    print("\n=== 1. Specialized vs baseline (by difficulty) ===")
    for diff, v in analysis_1["by_difficulty"].items():
        print(f"  {diff:<14} baseline={str(v['quality_baseline_mean']):<6}  specialized={str(v['specialized_mean']):<6}  delta={v['delta']}")
    for diff, v in analysis_1["by_difficulty_tests"].items():
        print(f"  test {diff:<12} delta={v['delta']:+.4f} CI95 {v['ci95']} Bonferroni {v['ci_bonferroni']} "
              f"p={v['p']:.3f} p_holm={v['p_holm']:.3f} (n={v['n_prompts_specialized']}+{v['n_prompts_baseline']}, k={v['family_size']})")

    print("\n=== 2. Model size vs score ===")
    for g in all_gens:
        v = analysis_2["models"][g]
        print(f"  {g:<22} {v['size_B']}B (reported {v['size_B_reported']}B)  mean={v['mean_score']}")
    print(f"  Pearson r = {analysis_2['pearson_size_vs_score']} (nominal)  "
          f"{analysis_2['pearson_reported_size_vs_score']} (reported)  n={len(all_gens)}")

    print("\n=== 3. Top 10 prompts by inter-judge disagreement ===")
    for item in analysis_3["top10_highest_disagreement"]:
        print(f"  {item['id']:<14} uc={item['use_case']:<25} diff={item['difficulty']:<12} stdev={item['mean_interjudge_stdev']}")

    print("\n=== 4. Intra-judge stdev by domain ===")
    header = "  " + " " * 16 + "  ".join(uc[:6] for uc in USE_CASES)
    print(header)
    for judge in all_judges:
        row = f"  {judge:<16}"
        for uc in USE_CASES:
            v = intrajudge[judge][uc]
            row += f"  {str(v['stdev']):<6}"
        print(row)

    print("\n=== 5. Self-preference delta ===")
    for judge, v in analysis_5["self_preference_rate"].items():
        print(f"  {judge:<22}  self={v['self_score']}  cross={v['mean_cross_score']}  delta={v['self_preference_delta']}  legacy SPR={v['spr']}")

    print("\n=== 6. Self-eval vs cross-eval bias ===")
    for gen, v in analysis_6["by_generator"].items():
        print(f"  {gen:<22}  self={v['self_eval_mean']}  cross={v['cross_eval_mean']}  bias={v['bias_delta']}")

    print("\n=== 7. Formal self-preference (relative to other judges; Bonferroni CI and Holm p across judges) ===")
    for judge, v in analysis_7["by_judge"].items():
        s, b = v["spr_self"], v["score_bias_self"]
        line = (f"  {judge:<22} SPR={s['spr']:.3f} ref={s['reference']:.3f} excess={s['excess']:+.3f} "
                f"Bonferroni [{s['ci_bonferroni'][0]:+.3f},{s['ci_bonferroni'][1]:+.3f}] p_holm={s['p_holm']:.3f} | "
                f"score bias={b['estimate']:+.4f} Bonferroni [{b['ci_bonferroni'][0]:+.4f},{b['ci_bonferroni'][1]:+.4f}] "
                f"p_holm={b['p_holm']:.3f}")
        sib = v.get("score_bias_siblings")
        if sib:
            line += f" | siblings bias={sib['estimate']:+.4f} p_holm={sib['p_holm']:.3f}"
        print(line)


if __name__ == "__main__":
    main()
