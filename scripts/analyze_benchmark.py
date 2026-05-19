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
"""

import json
import math
import datetime
from pathlib import Path
from collections import defaultdict

RESULTS_DIR = Path("docs/benchmark/results")
PROMPTS_FILE = Path("docs/benchmark/prompts.json")
OUTPUT_DIR = Path("docs/benchmark/analysis")

MODEL_SIZES = {
    "qwen3-1.7b": 1.7,
    "phi4-mini": 3.8,
    "gemma3-4b": 4.0,
    "mistral-7b": 7.0,
}

USE_CASES = ["general", "summarization", "translation", "code", "administrative_writing", "analysis"]
BASELINE_USE_CASES = {"general", "summarization"}
SPECIALIZED_USE_CASES = {"translation", "code", "administrative_writing", "analysis"}


def short_name(ollama_name: str) -> str:
    return ollama_name.removeprefix("ollama/").replace(":", "-")


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


def load_all_results() -> list[dict]:
    entries = []
    for fpath in sorted(RESULTS_DIR.glob("*.json")):
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        gen = short_name(data["model"])
        judge = short_name(data["judge_model"])
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
    return entries


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


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = load_all_results()
    prompt_meta = load_prompt_meta()

    all_gens = sorted(MODEL_SIZES.keys())
    all_judges = sorted(set(e["judge"] for e in entries))

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
        "description": "Compare mean score on quality_baseline profile (general+summarization) vs domain-specific profiles per use case",
        "by_generator": delta_by_gen,
        "by_difficulty": delta_by_diff,
    }

    # ── 2. Correlation model size / score ─────────────────────────────────────

    gen_stats: dict[str, dict] = {}
    for gen in all_gens:
        scores = [e["score"] for e in entries if e["gen"] == gen]
        gen_stats[gen] = {
            "size_B": MODEL_SIZES[gen],
            "mean_score": r4(_mean(scores)),
            "stdev": r4(_stdev(scores)),
            "n": len(scores),
        }

    sizes = [MODEL_SIZES[g] for g in all_gens]
    means = [gen_stats[g]["mean_score"] for g in all_gens]
    analysis_2 = {
        "description": "Mean composite score per generator model vs parameter count",
        "models": gen_stats,
        "pearson_size_vs_score": _pearson(sizes, means),
    }

    # ── 3. Inter-judge disagreement by prompt ─────────────────────────────────

    # For each (gen, prompt_id): collect scores across all 4 judges
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
        # SPR: fraction of other generators where judge scores them lower than self
        wins = sum(1 for s in cross if self_score is not None and s is not None and self_score > s)
        spr[judge] = {
            "self_score": self_score,
            "mean_cross_score": r4(cross_mean),
            "self_preference_delta": r4(self_score - cross_mean) if (self_score is not None and cross_mean is not None) else None,
            "spr": round(wins / len(cross), 4) if cross else None,
        }

    analysis_5 = {
        "description": "Mean composite score for each (judge_model, generator_model) pair; diagonal = self-evaluation",
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

    # ── Write output ──────────────────────────────────────────────────────────

    summary = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "n_result_files": len(list(RESULTS_DIR.glob("*.json"))),
        "n_entries_used": len(entries),
        "analysis_1_delta_specialized_vs_baseline": analysis_1,
        "analysis_2_model_size_correlation": analysis_2,
        "analysis_3_interjudge_disagreement_by_prompt": analysis_3,
        "analysis_4_intrajudge_variance_by_domain": analysis_4,
        "analysis_5_judge_generator_bias_matrix": analysis_5,
        "analysis_6_self_eval_vs_cross_eval": analysis_6,
    }

    out = OUTPUT_DIR / "summary.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # ── Quick digest ──────────────────────────────────────────────────────────

    print(f"Written: {out}  ({len(entries)} entries from {summary['n_result_files']} files)")

    print("\n=== 1. Specialized vs baseline (by difficulty) ===")
    for diff, v in analysis_1["by_difficulty"].items():
        print(f"  {diff:<14} baseline={str(v['quality_baseline_mean']):<6}  specialized={str(v['specialized_mean']):<6}  delta={v['delta']}")

    print("\n=== 2. Model size vs score ===")
    for g in all_gens:
        v = analysis_2["models"][g]
        print(f"  {g:<15} {v['size_B']}B  mean={v['mean_score']}")
    print(f"  Pearson r = {analysis_2['pearson_size_vs_score']}")

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
        print(f"  {judge:<15}  self={v['self_score']}  cross={v['mean_cross_score']}  delta={v['self_preference_delta']}  SPR={v['spr']}")

    print("\n=== 6. Self-eval vs cross-eval bias ===")
    for gen, v in analysis_6["by_generator"].items():
        print(f"  {gen:<15}  self={v['self_eval_mean']}  cross={v['cross_eval_mean']}  bias={v['bias_delta']}")


if __name__ == "__main__":
    main()
