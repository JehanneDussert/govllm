#!/usr/bin/env python3
"""Export ground truth results from the evaluation service into per-judge JSON files,
then rebuild docs/ground_truth/validity.json from those files.

Usage:
    python scripts/export_groundtruth_results.py --order permuted
    python scripts/export_groundtruth_results.py --order original --order reversed --order permuted
    python scripts/export_groundtruth_results.py --validity-only   # rebuild validity.json from files, no service needed

validity.json: per order, per judge x criterion agreement (mean of per-case agreement)
and n_cases; "validity" = the same pooled over every order available for that judge
(weighted by case-runs, i.e. the exact mean over all case-runs). "orders" lists the
orderings each judge has. Rounding is applied once, at write time; globals keep 6 decimals
so that displaying them to 0.1 pp never double-rounds (e.g. 32.5/47 = 69.149%, not 69.15% -> 69.2%).

Every exported file covers the full corpus grid: one entry per case, with a "status".
"ok" entries carry the agreement; unusable answers (call_error, json_error, empty,
parse_error) and cases with no stored row at all ("not_recorded", i.e. failures from
runs made before failures were stored) have agreement null. Agreement aggregates only
use "ok" entries; the usable-answer rate is n_usable / n_cases_expected. When a
(case, judge, order) has several rows (retried failures), the latest "ok" row wins,
otherwise the latest failure.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

from model_registry import MODELS, slug_of, family

BASE_URL = "http://localhost:8003"
OUT_DIR  = Path("docs/ground_truth/results")
VALIDITY_FILE = Path("docs/ground_truth/validity.json")
ORDERS = ["original", "reversed", "permuted"]


def fetch(path: str) -> list | dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def export_order(order: str, corpus: list[dict], only: set[str] | None = None) -> None:
    # Index corpus by case_id
    case_index: dict[str, dict] = {c["id"]: c for c in corpus}

    # Collect all results for this order across all cases
    # Structure: {judge_model: [result_row, ...]}
    judge_results: dict[str, list[dict]] = defaultdict(list)

    for case in corpus:
        case_id = case["id"]
        try:
            rows = fetch(f"/groundtruth/results/{case_id}?question_order={order}")
        except urllib.error.URLError as e:
            print(f"  WARN: {case_id} → {e}", file=sys.stderr)
            continue

        by_judge: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            judge = row.get("judge_model")
            if judge and (only is None or slug_of(judge) in only):
                by_judge[judge].append(row)
        for judge, judge_rows in by_judge.items():
            # Rows come ordered by created_at: keep the latest usable one, else the latest failure
            usable = [r for r in judge_rows if r.get("status", "ok") == "ok"]
            row = dict((usable or judge_rows)[-1])
            row["n_attempts"] = len(judge_rows)
            judge_results[judge].append((case, row))

    if not judge_results:
        print(f"No results found for order={order}", file=sys.stderr)
        return

    for judge_model, pairs in judge_results.items():
        slug = slug_of(judge_model)
        judge_family = family(slug)

        # Cases with no stored row for this judge and order: failures of runs made
        # before unusable answers were stored. Kept in the grid as "not_recorded".
        seen = {case["id"] for case, _ in pairs}
        pairs = pairs + [
            (case, {"status": "not_recorded", "answers": {}, "n_attempts": 0})
            for case in corpus if case["id"] not in seen
        ]

        # Build per-criterion stats
        by_criterion: dict[str, dict] = defaultdict(lambda: {"total": 0, "agreement_sum": 0.0})

        results_list = []
        for case, row in pairs:
            criterion = case["criterion"]
            expected  = case["expected_answers"]
            answers   = row.get("answers") or {}
            reason    = row.get("reason") or ""
            # The results API returns neither score nor created_at: recompute the
            # score with the server formula (mean of normalised answers).
            score     = row.get("score")
            if score is None and answers:
                score = round(sum(bool(v) for v in answers.values()) / len(answers), 4)
            created   = row.get("created_at")
            status    = row.get("status", "ok")

            # Compute per-answer agreement (usable answers only)
            if status != "ok":
                agreement = None
                score = None
            elif answers and expected:
                n_match = sum(1 for k in expected if answers.get(k) == expected[k])
                agreement = round(n_match / len(expected), 4)
            else:
                agreement = 0.0

            if agreement is not None:
                by_criterion[criterion]["total"] += 1
                by_criterion[criterion]["agreement_sum"] += agreement

            results_list.append({
                "criterion":     criterion,
                "prompt":        case["prompt"],
                "response":      case["response"],
                "source":        case.get("source", ""),
                "expected":      expected,
                "judge_model":   judge_model,
                "judge_family":  judge_family,
                "answers":       answers,
                "score":         score,
                "agreement":     agreement,
                "reason":        reason,
                "question_order": order,
                "created_at":    created,
                "status":        status,
                "parse_fallback": row.get("parse_fallback"),
                "n_attempts":    row.get("n_attempts", 1),
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

        status_counts: dict[str, int] = defaultdict(int)
        for r in results_list:
            status_counts[r["status"]] += 1
        n_usable = status_counts.get("ok", 0)

        out = {
            "judge_model":       judge_model,
            "question_order":    order,
            "n_results":         n_usable,  # usable answers (status ok); kept for backward compatibility
            "n_cases_expected":  len(results_list),
            "usable_rate":       round(n_usable / len(results_list), 6) if results_list else None,
            "status_counts":     dict(sorted(status_counts.items())),
            "global_agreement":  global_agreement,
            "by_criterion":      by_criterion_out,
            "results":           results_list,
        }

        out_path = OUT_DIR / f"{slug}_{order}.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  wrote {out_path}  ({n_usable}/{len(results_list)} usable, global={global_agreement:.1%})")


def build_validity() -> None:
    """Rebuild validity.json from the exported {slug}_{order}.json files."""
    criteria: set[str] = set()
    sums: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0])))
    for slug in MODELS:
        for order in ORDERS:
            path = OUT_DIR / f"{slug}_{order}.json"
            if not path.exists():
                continue
            for r in json.loads(path.read_text(encoding="utf-8"))["results"]:
                if r.get("status", "ok") != "ok":
                    continue
                cell = sums[slug][order][r["criterion"]]
                cell[0] += r["agreement"]
                cell[1] += 1
                criteria.add(r["criterion"])

    def agg(cells):
        s = sum(c[0] for c in cells)
        n = sum(c[1] for c in cells)
        return s / n if n else None

    corpus = json.loads(Path("docs/ground_truth/corpus.json").read_text(encoding="utf-8"))
    cases = corpus.get("cases", corpus) if isinstance(corpus, dict) else corpus
    out = {
        "description": "Agreement per judge x criterion (mean of per-case agreement). by_order: one ordering; "
                       "validity: pooled over all orderings available for that judge (see 'orders'). "
                       "Built by scripts/export_groundtruth_results.py from docs/ground_truth/results/.",
        "orders_included": ORDERS,
        "corpus_size": len(cases),
        "judges": [s for s in MODELS if s in sums],
        "criteria": sorted(criteria),
        "orders": {s: [o for o in ORDERS if o in sums[s]] for s in MODELS if s in sums},
        "by_order": {},
        "validity": {},
    }
    for order in ORDERS:
        block = {}
        for slug in out["judges"]:
            if order not in sums[slug]:
                continue
            per = sums[slug][order]
            block[slug] = {c: {"agreement": round(agg([per[c]]), 3), "n_cases": per[c][1]} for c in sorted(per)}
            block[slug]["global"] = round(agg(list(per.values())), 6)
        out["by_order"][order] = block
    for slug in out["judges"]:
        cells_by_crit = defaultdict(list)
        for order in sums[slug]:
            for c, cell in sums[slug][order].items():
                cells_by_crit[c].append(cell)
        v = {c: {"agreement": round(agg(cells), 3), "n": sum(x[1] for x in cells)} for c, cells in sorted(cells_by_crit.items())}
        v["global"] = round(agg([x for cells in cells_by_crit.values() for x in cells]), 6)
        out["validity"][slug] = v
    VALIDITY_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {VALIDITY_FILE}  judges={out['judges']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--order", action="append", default=[],
        choices=ORDERS,
        help="Question order(s) to export (repeatable). Default: permuted",
    )
    parser.add_argument("--judges", default=None,
                        help="Comma-separated judges (slugs or ollama ids) to export; default: all. "
                             "Existing files of other judges are left untouched.")
    parser.add_argument("--validity-only", action="store_true",
                        help="Skip the export; rebuild validity.json from the existing files")
    args = parser.parse_args()
    if args.validity_only:
        build_validity()
        return
    orders = args.order or ["permuted"]

    print("Fetching corpus…")
    corpus = fetch("/groundtruth/corpus")
    print(f"  {len(corpus)} cases")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for order in orders:
        print(f"\nExporting order={order}…")
        export_order(order, corpus, {slug_of(j.strip()) for j in args.judges.split(",")} if args.judges else None)

    print("\nRebuilding validity.json…")
    build_validity()
    print("\nDone.")


if __name__ == "__main__":
    main()
