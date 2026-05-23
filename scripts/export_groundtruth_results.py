#!/usr/bin/env python3
"""Export ground truth results from the evaluation service into per-judge JSON files.

Usage:
    python scripts/export_groundtruth_results.py --order permuted
    python scripts/export_groundtruth_results.py --order original --order reversed --order permuted
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8003"
OUT_DIR  = Path("docs/ground_truth/results")

JUDGE_SLUG = {
    "ollama/qwen3:1.7b":  "qwen3-1.7b",
    "ollama/gemma3:4b":   "gemma3-4b",
    "ollama/phi4-mini":   "phi4-mini",
    "ollama/mistral:7b":  "mistral-7b",
}

JUDGE_FAMILY = {
    "ollama/qwen3:1.7b":  "qwen",
    "ollama/gemma3:4b":   "gemma",
    "ollama/phi4-mini":   "phi",
    "ollama/mistral:7b":  "mistral",
}


def fetch(path: str) -> list | dict:
    r = httpx.get(f"{BASE_URL}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def export_order(order: str, corpus: list[dict]) -> None:
    # Index corpus by case_id
    case_index: dict[str, dict] = {c["id"]: c for c in corpus}

    # Collect all results for this order across all cases
    # Structure: {judge_model: [result_row, ...]}
    judge_results: dict[str, list[dict]] = defaultdict(list)

    for case in corpus:
        case_id = case["id"]
        try:
            rows = fetch(f"/groundtruth/results/{case_id}?question_order={order}")
        except httpx.HTTPStatusError as e:
            print(f"  WARN: {case_id} → {e}", file=sys.stderr)
            continue

        for row in rows:
            judge = row.get("judge_model")
            if judge:
                judge_results[judge].append((case, row))

    if not judge_results:
        print(f"No results found for order={order}", file=sys.stderr)
        return

    for judge_model, pairs in judge_results.items():
        slug = JUDGE_SLUG.get(judge_model, judge_model.replace("/", "_").replace(":", "-"))
        family = JUDGE_FAMILY.get(judge_model, "unknown")

        # Build per-criterion stats
        by_criterion: dict[str, dict] = defaultdict(lambda: {"total": 0, "agreement_sum": 0.0})

        results_list = []
        for case, row in pairs:
            criterion = case["criterion"]
            expected  = case["expected_answers"]
            answers   = row.get("answers") or {}
            reason    = row.get("reason") or ""
            score     = row.get("score")
            created   = row.get("created_at", "")

            # Compute per-answer agreement
            if answers and expected:
                n_match = sum(1 for k in expected if answers.get(k) == expected[k])
                agreement = round(n_match / len(expected), 4)
            else:
                agreement = 0.0

            by_criterion[criterion]["total"] += 1
            by_criterion[criterion]["agreement_sum"] += agreement

            results_list.append({
                "criterion":     criterion,
                "prompt":        case["prompt"],
                "response":      case["response"],
                "source":        case.get("source", ""),
                "expected":      expected,
                "judge_model":   judge_model,
                "judge_family":  family,
                "answers":       answers,
                "score":         score,
                "agreement":     agreement,
                "reason":        reason,
                "question_order": order,
                "created_at":    created,
            })

        # Sort results: by criterion then by prompt (stable, matches other files)
        results_list.sort(key=lambda r: (r["criterion"], r["prompt"]))

        # Aggregate
        by_criterion_out: dict[str, dict] = {}
        total_agreement = 0.0
        total_n = 0
        for crit, stats in sorted(by_criterion.items()):
            n = stats["total"]
            agg = round(stats["agreement_sum"] / n, 3) if n else 0.0
            by_criterion_out[crit] = {"agreement": agg, "n_cases": n}
            total_agreement += stats["agreement_sum"]
            total_n += n

        global_agreement = round(total_agreement / total_n, 3) if total_n else 0.0

        out = {
            "judge_model":       judge_model,
            "question_order":    order,
            "n_results":         len(results_list),
            "global_agreement":  global_agreement,
            "by_criterion":      by_criterion_out,
            "results":           results_list,
        }

        out_path = OUT_DIR / f"{slug}_{order}.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  wrote {out_path}  ({len(results_list)} results, global={global_agreement:.1%})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--order", action="append", default=[],
        choices=["original", "reversed", "permuted"],
        help="Question order(s) to export (repeatable). Default: permuted",
    )
    args = parser.parse_args()
    orders = args.order or ["permuted"]

    print("Fetching corpus…")
    corpus = fetch("/groundtruth/corpus")
    print(f"  {len(corpus)} cases")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for order in orders:
        print(f"\nExporting order={order}…")
        export_order(order, corpus)

    print("\nDone.")


if __name__ == "__main__":
    main()
