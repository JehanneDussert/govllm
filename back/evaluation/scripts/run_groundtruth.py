#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Run ground-truth checklist evaluations and print per-case, per-judge results.

Usage:
    python run_groundtruth.py
    python run_groundtruth.py --criterion transparency data_privacy
    python run_groundtruth.py --cases 9dea1b2c d025ba36 --question-order reversed
    python run_groundtruth.py --criterion transparency --question-order reversed --compare

Env vars:
    EVALUATION_URL    evaluation service base URL (default: http://localhost:8003)
"""

import argparse
import asyncio
import os
from collections import defaultdict

import httpx

EVALUATION_URL = os.environ.get("EVALUATION_URL", "http://localhost:8003")

_NEGATIVE_PATTERNS = [
    "does not", "do not", "fails to", "fail to", "no ",
    "violation", "fails", "missing", "lacks", "lack ",
    "without", "never", "absent", "not signal", "not provide",
    "not mention", "not invite", "not distinguish",
]


def _find_negative_snippet(reason: str) -> str | None:
    if not reason:
        return None
    r_lower = reason.lower()
    for pat in _NEGATIVE_PATTERNS:
        idx = r_lower.find(pat)
        if idx != -1:
            start = max(0, idx)
            end = min(len(reason), idx + len(pat) + 35)
            return reason[start:end].strip()
    return None


def _print_case_result(case_id: str, crit: str, prompt: str, judge_short: str,
                       agreement: float, answers: dict, expected: dict, reason: str,
                       summary: dict, question_order: str = "original") -> None:
    prompt_preview = prompt[:70]
    order_tag = f"  [order={question_order}]" if question_order != "original" else ""
    print(f"{'─'*80}")
    print(f"  case    : {case_id[:8]}…  [{crit}]{order_tag}")
    print(f"  prompt  : {prompt_preview}{'…' if len(prompt) > 70 else ''}")
    print(f"  judge   : {judge_short}   agreement={agreement:.2f}")
    print()

    case_has_pattern_b = False
    for qid in sorted(expected):
        got = answers.get(qid)
        exp = expected[qid]
        match_str = "✓" if got == exp else "← MISMATCH"
        got_str = f"{'True ':5}" if got else f"{'False':5}"
        exp_str = "True " if exp else "False"
        line = f"    {qid}: {got_str} (expected: {exp_str}) {match_str}"
        if got is True:
            snippet = _find_negative_snippet(reason)
            if snippet:
                case_has_pattern_b = True
                line += f'  + ⚠ INCOHERENCE B (reason: "…{snippet}…")'
        print(line)

    if reason:
        print(f'    reason: "{reason}"')
    print()

    key = (judge_short, crit)
    summary[key]["agreements"].append(agreement)
    summary[key]["total"] += 1
    if case_has_pattern_b:
        summary[key]["pattern_b"] += 1


async def _print_comparison(client: httpx.AsyncClient, run_results: list[dict]) -> None:
    """For each case in run_results, fetch original answers from DB and show side-by-side."""
    print("\n" + "=" * 90)
    print("COMPARISON — original (q1→q4) vs reversed (q4→q1) — qid rows, order columns")
    print("=" * 90)

    for item in run_results:
        case_id = item["case_id"]
        crit = item["criterion"]
        expected = item["expected_answers"]
        prompt_preview = item["prompt"][:60]

        r = await client.get(f"/groundtruth/results/{case_id}")
        r.raise_for_status()
        stored = r.json()

        # Group by (judge, order)
        by_judge: dict[str, dict[str, dict]] = defaultdict(dict)
        for row in stored:
            jm = row["judge_model"].split("/")[-1]
            by_judge[jm][row["question_order"]] = row

        for judge_short, orders in sorted(by_judge.items()):
            orig = orders.get("original")
            rev  = orders.get("reversed")
            if not orig or not rev:
                continue

            print(f"\n  [{crit}] {case_id[:8]}…  judge={judge_short}")
            print(f"  prompt: {prompt_preview}…")
            print(f"  {'qid':<4}  {'expected':<8}  {'original':<10}  {'reversed':<10}  delta")
            print(f"  {'─'*4}  {'─'*8}  {'─'*10}  {'─'*10}  {'─'*5}")

            flips = 0
            for qid in sorted(expected):
                exp  = expected[qid]
                o_ans = orig["answers"].get(qid)
                r_ans = rev["answers"].get(qid)
                exp_s = "True " if exp   else "False"
                o_s   = "True " if o_ans else "False"
                r_s   = "True " if r_ans else "False"
                flip  = "FLIP" if o_ans != r_ans else "—"
                if o_ans != r_ans:
                    flips += 1
                print(f"  {qid:<4}  {exp_s:<8}  {o_s:<10}  {r_s:<10}  {flip}")

            o_agr = orig["agreement"]
            r_agr = rev["agreement"]
            delta = r_agr - o_agr
            sign  = "+" if delta >= 0 else ""
            print(f"  agreement: original={o_agr:.2f}  reversed={r_agr:.2f}  delta={sign}{delta:.2f}  flips={flips}/4")


async def main(
    criteria: list[str] | None,
    judges: list[str] | None,
    case_prefixes: list[str] | None,
    question_order: str,
    compare: bool,
) -> None:
    async with httpx.AsyncClient(base_url=EVALUATION_URL, timeout=300) as client:
        if criteria:
            cases = []
            for c in criteria:
                r = await client.get(f"/groundtruth/corpus?criterion={c}")
                r.raise_for_status()
                cases += r.json()
        else:
            r = await client.get("/groundtruth/corpus")
            r.raise_for_status()
            cases = r.json()

        if case_prefixes:
            cases = [c for c in cases if any(c["id"].startswith(p) for p in case_prefixes)]

        if not cases:
            print("No cases found.")
            return

        print(f"\n{len(cases)} case(s) — running checklists…  [question_order={question_order}]\n")
        if judges:
            print(f"Judges override: {judges}\n")

        summary: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"agreements": [], "pattern_b": 0, "total": 0}
        )
        run_results: list[dict] = []

        for case in cases:
            case_id  = case["id"]
            crit     = case["criterion"]
            expected = case["expected_answers"]

            params: list[str] = []
            if judges:
                params += [f"judge_models={j}" for j in judges]
            if question_order != "original":
                params.append(f"question_order={question_order}")
            run_url = f"/groundtruth/run/{case_id}" + (f"?{'&'.join(params)}" if params else "")

            r = await client.post(run_url)
            r.raise_for_status()
            result = r.json()

            for judge in result["judges"]:
                short   = judge["judge_model"].split("/")[-1]
                answers = judge["answers"]
                reason  = (judge.get("reason") or "").strip()
                _print_case_result(
                    case_id, crit, case["prompt"], short,
                    judge["agreement"], answers, expected, reason,
                    summary, question_order,
                )

            if compare:
                run_results.append({
                    "case_id": case_id,
                    "criterion": crit,
                    "expected_answers": expected,
                    "prompt": case["prompt"],
                })

        # ── Summary ────────────────────────────────────────────────────────────
        print("=" * 90)
        print(f"SUMMARY — mean agreement & incoherence-B rate  by judge × criterion  [order={question_order}]")
        print("=" * 90)
        print(f"  {'judge':<30}  {'criterion':<22}  {'agreement':>10}  {'incoherence_B':>14}  {'n':>4}")
        print(f"  {'-'*30}  {'-'*22}  {'-'*10}  {'-'*14}  {'-'*4}")

        by_criterion: dict[str, list] = defaultdict(list)
        for (judge, crit), stats in sorted(summary.items()):
            by_criterion[crit].append((judge, stats))

        for crit in sorted(by_criterion):
            for judge, stats in sorted(by_criterion[crit]):
                values = stats["agreements"]
                mean_a = sum(values) / len(values) if values else 0.0
                inc_r  = stats["pattern_b"] / stats["total"] if stats["total"] else 0.0
                print(f"  {judge:<30}  {crit:<22}  {mean_a:>9.1%}  {inc_r:>13.1%}  {len(values):>4}")
            print()

        if compare and run_results:
            await _print_comparison(client, run_results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--criterion", nargs="+", default=None, metavar="CRITERION",
                        help="Filter by criterion (one or more). Omit for all.")
    parser.add_argument("--judges", nargs="+", default=None, metavar="MODEL",
                        help="Override judge model list (e.g. ollama/gemma3:4b ollama/phi4-mini)")
    parser.add_argument("--cases", nargs="+", default=None, metavar="ID_PREFIX",
                        help="Run only on cases whose ID starts with these prefixes (8 chars)")
    parser.add_argument("--question-order", choices=["original", "reversed"], default="original",
                        dest="question_order",
                        help="Question presentation order in the checklist prompt")
    parser.add_argument("--compare", action="store_true",
                        help="After the run, fetch original results and show original vs reversed comparison")
    args = parser.parse_args()
    asyncio.run(main(args.criterion, args.judges, args.cases, args.question_order, args.compare))
