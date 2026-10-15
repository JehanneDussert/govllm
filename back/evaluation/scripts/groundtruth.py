#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Ground truth corpus tool — single entry point replacing seed/run/extend scripts.

Subcommands:
    seed    Drop + recreate tables, then insert all corpus cases.
    run     Run checklist evaluations on the corpus and print results.
    extend  Add new cases from a JSON file and evaluate them.

Usage:
    python groundtruth.py seed
    python groundtruth.py run
    python groundtruth.py run --order reversed
    python groundtruth.py run --criterion transparency data_privacy
    python groundtruth.py run --judges ollama/phi4-mini ollama/qwen3:1.7b
    python groundtruth.py run --order reversed --compare
    python groundtruth.py extend new_cases.json
    python groundtruth.py extend new_cases.json --skip-run

Env vars:
    ARENA_DB_URL    asyncpg DSN (seed only)
                    default: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
    EVALUATION_URL  evaluation service base URL  (default: http://localhost:8003)
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

ARENA_DB_URL = os.environ.get(
    "ARENA_DB_URL", "postgresql://langfuse:langfuse@langfuse-db:5432/langfuse"
)
EVALUATION_URL = os.environ.get("EVALUATION_URL", "http://localhost:8003")

# ── DB schema (seed only) ─────────────────────────────────────────────────────

_DROP_SQL = """
DROP TABLE IF EXISTS groundtruth_results CASCADE;
DROP TABLE IF EXISTS groundtruth_cases CASCADE;
"""

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS groundtruth_cases (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    criterion   TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    response    TEXT NOT NULL,
    source      TEXT,
    expected    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS groundtruth_results (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id               UUID NOT NULL REFERENCES groundtruth_cases(id) ON DELETE CASCADE,
    judge_model           TEXT NOT NULL,
    judge_family          TEXT NOT NULL,
    answers               TEXT NOT NULL,
    score                 FLOAT NOT NULL,
    agreement             FLOAT NOT NULL,
    reason                TEXT,
    latency_ms            INT,
    question_order        TEXT    NOT NULL DEFAULT 'original',
    incoherence_validated BOOLEAN          DEFAULT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gt_cases_criterion ON groundtruth_cases(criterion);
CREATE INDEX IF NOT EXISTS idx_gt_results_case    ON groundtruth_results(case_id);
CREATE INDEX IF NOT EXISTS idx_gt_results_judge   ON groundtruth_results(judge_model);
"""

# ── Shared helpers ────────────────────────────────────────────────────────────

_NEGATIVE_PATTERNS = [
    # English
    "does not",
    "do not",
    "fails to",
    "fail to",
    "no ",
    "violation",
    "fails",
    "missing",
    "lacks",
    "lack ",
    "without",
    "never",
    "absent",
    "not signal",
    "not provide",
    "not mention",
    "not invite",
    "not distinguish",
    # French
    "n'est pas",
    "ne pas",
    "n'indique",
    "n'invite",
    "ne mentionne",
    "ne fourni",
    "ne signale",
    "ne précise",
    "ne distingue",
    "ne propose",
    "sans ",
    "aucun",
    "jamais",
    "manque",
    "n'explicite",
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


def _print_case_result(
    case_id: str,
    crit: str,
    prompt: str,
    judge_short: str,
    agreement: float,
    answers: dict,
    expected: dict,
    reason: str,
    summary: dict,
    question_order: str = "original",
) -> None:
    order_tag = f"  [order={question_order}]" if question_order != "original" else ""
    print(f"{'─' * 80}")
    print(f"  case    : {case_id[:8]}…  [{crit}]{order_tag}")
    print(f"  prompt  : {prompt[:70]}{'…' if len(prompt) > 70 else ''}")
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


def _print_summary(summary: dict, order_label: str) -> None:
    print("=" * 90)
    print(
        f"SUMMARY — mean agreement & incoherence-B rate  by judge × criterion  [{order_label}]"
    )
    print("=" * 90)
    print(
        f"  {'judge':<30}  {'criterion':<22}  {'agreement':>10}  {'incoherence_B':>14}  {'n':>4}"
    )
    print(f"  {'-' * 30}  {'-' * 22}  {'-' * 10}  {'-' * 14}  {'-' * 4}")

    by_criterion: dict[str, list] = defaultdict(list)
    for (judge, crit), stats in sorted(summary.items()):
        by_criterion[crit].append((judge, stats))

    for crit in sorted(by_criterion):
        for judge, stats in sorted(by_criterion[crit]):
            values = stats["agreements"]
            mean_a = sum(values) / len(values) if values else 0.0
            inc_r = stats["pattern_b"] / stats["total"] if stats["total"] else 0.0
            print(
                f"  {judge:<30}  {crit:<22}  {mean_a:>9.1%}  {inc_r:>13.1%}  {len(values):>4}"
            )
        print()


# ── seed ──────────────────────────────────────────────────────────────────────


async def cmd_seed(args: argparse.Namespace) -> None:
    import asyncpg

    db_url = args.db_url or ARENA_DB_URL
    eval_url = args.eval_url or EVALUATION_URL

    print(f"DB : {db_url}")
    print("Dropping and recreating groundtruth tables…")
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("SET search_path TO govllm")
        await conn.execute(_DROP_SQL)
        await conn.execute(_CREATE_SQL)
    finally:
        await conn.close()
    print("Tables reset.\n")

    corpus_path = Path("/app/docs_ground_truth/corpus.json")
    corpus_data = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = [
        {
            "criterion": c["criterion"],
            "prompt": c["prompt"],
            "response": c["response"],
            "source": c.get("source"),
            "expected_answers": c["expected"],
        }
        for c in corpus_data["cases"]
    ]

    print(f"Seeding {len(cases)} cases from {corpus_path} → {eval_url}/groundtruth/corpus")
    async with httpx.AsyncClient(base_url=eval_url, timeout=30) as client:
        for case in cases:
            r = await client.post("/groundtruth/corpus", json=case)
            r.raise_for_status()
            data = r.json()
            print(f"  [{data['criterion']}] {data['id']}  {data['prompt'][:60]}…")
    print(f"\n{len(cases)} cases inserted.")


# ── run ───────────────────────────────────────────────────────────────────────


async def _print_comparison(client: httpx.AsyncClient, run_results: list[dict]) -> None:
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

        by_judge: dict[str, dict[str, dict]] = defaultdict(dict)
        for row in stored:
            jm = row["judge_model"].split("/")[-1]
            by_judge[jm][row["question_order"]] = row

        for judge_short, orders in sorted(by_judge.items()):
            orig = orders.get("original")
            rev = orders.get("reversed")
            if not orig or not rev:
                continue

            print(f"\n  [{crit}] {case_id[:8]}…  judge={judge_short}")
            print(f"  prompt: {prompt_preview}…")
            print(
                f"  {'qid':<4}  {'expected':<8}  {'original':<10}  {'reversed':<10}  delta"
            )
            print(f"  {'─' * 4}  {'─' * 8}  {'─' * 10}  {'─' * 10}  {'─' * 5}")

            flips = 0
            for qid in sorted(expected):
                exp = expected[qid]
                o_ans = orig["answers"].get(qid)
                r_ans = rev["answers"].get(qid)
                exp_s = "True " if exp else "False"
                o_s = "True " if o_ans else "False"
                r_s = "True " if r_ans else "False"
                flip = "FLIP" if o_ans != r_ans else "—"
                if o_ans != r_ans:
                    flips += 1
                print(f"  {qid:<4}  {exp_s:<8}  {o_s:<10}  {r_s:<10}  {flip}")

            o_agr = orig["agreement"]
            r_agr = rev["agreement"]
            delta = r_agr - o_agr
            sign = "+" if delta >= 0 else ""
            print(
                f"  agreement: original={o_agr:.2f}  reversed={r_agr:.2f}  delta={sign}{delta:.2f}  flips={flips}/4"
            )


async def cmd_run(args: argparse.Namespace) -> None:
    eval_url = args.eval_url or EVALUATION_URL
    question_order = args.order

    async with httpx.AsyncClient(base_url=eval_url, timeout=None) as client:
        # Resolve the default judge list once, mirroring the server's own fallback
        # (config.arena_judge_models or [config.judge_model]) — needed so the
        # per-judge skip logic below works even when --judges isn't passed.
        default_judges: list[str] = []
        if not args.judges:
            cfg_r = await client.get("/config/judge")
            cfg_r.raise_for_status()
            cfg = cfg_r.json()
            default_judges = cfg.get("arena_judge_models") or [cfg["judge_model"]]

        if args.criterion:
            cases = []
            for c in args.criterion:
                r = await client.get(f"/groundtruth/corpus?criterion={c}")
                r.raise_for_status()
                cases += r.json()
        else:
            r = await client.get("/groundtruth/corpus")
            r.raise_for_status()
            cases = r.json()

        if args.cases:
            cases = [c for c in cases if any(c["id"].startswith(p) for p in args.cases)]

        if not cases:
            print("No cases found.")
            return

        print(
            f"\n{len(cases)} case(s) — running checklists…  [question_order={question_order}]\n"
        )
        if args.judges:
            print(f"Judges override: {args.judges}\n")

        summary: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"agreements": [], "pattern_b": 0, "total": 0}
        )
        run_results: list[dict] = []

        for case in cases:
            case_id = case["id"]
            crit = case["criterion"]
            expected = case["expected_answers"]

            # Per-judge skip: only run judges not yet evaluated for this (case, order)
            existing_r = await client.get(
                f"/groundtruth/results/{case_id}?question_order={question_order}"
            )
            evaluated_judges: set[str] = set()
            if existing_r.status_code == 200 and existing_r.json():
                evaluated_judges = {row["judge_model"] for row in existing_r.json()}

            target_judges = args.judges if args.judges else default_judges
            judges_to_run = [j for j in target_judges if j not in evaluated_judges]

            if not judges_to_run:
                print(
                    f"  [skip] {case_id[:8]}… all requested judges already evaluated for order={question_order}"
                )
                continue

            for judge_model in judges_to_run if judges_to_run else [None]:
                params: list[str] = []
                if judge_model:
                    params.append(f"judge_models={judge_model}")
                if question_order != "original":
                    params.append(f"question_order={question_order}")
                run_url = f"/groundtruth/run/{case_id}" + (
                    f"?{'&'.join(params)}" if params else ""
                )

                r = await client.post(run_url)
                r.raise_for_status()
                result = r.json()

                for judge in result["judges"]:
                    short = judge["judge_model"].split("/")[-1]
                    answers = judge["answers"]
                    reason = (judge.get("reason") or "").strip()
                    _print_case_result(
                        case_id,
                        crit,
                        case["prompt"],
                        short,
                        judge["agreement"],
                        answers,
                        expected,
                        reason,
                        summary,
                        question_order,
                    )

            if args.compare:
                run_results.append(
                    {
                        "case_id": case_id,
                        "criterion": crit,
                        "expected_answers": expected,
                        "prompt": case["prompt"],
                    }
                )

        _print_summary(summary, f"order={question_order}")

        if args.compare and run_results:
            await _print_comparison(client, run_results)


# ── extend ────────────────────────────────────────────────────────────────────


async def cmd_extend(args: argparse.Namespace) -> None:
    eval_url = args.eval_url or EVALUATION_URL
    cases_path = Path(args.cases_json)

    if not cases_path.exists():
        print(f"Error: {cases_path} not found.", file=sys.stderr)
        sys.exit(1)

    with cases_path.open() as f:
        new_cases: list[dict] = json.load(f)

    print(f"Adding {len(new_cases)} new cases from {cases_path.name}…")

    async with httpx.AsyncClient(base_url=eval_url, timeout=600) as client:
        added: list[dict] = []
        for case in new_cases:
            r = await client.post("/groundtruth/corpus", json=case)
            r.raise_for_status()
            data = r.json()
            added.append(
                {
                    "id": data["id"],
                    "criterion": data["criterion"],
                    "prompt": case["prompt"],
                    "expected_answers": case["expected_answers"],
                }
            )
            print(f"  [{data['criterion']}] {data['id']}  {case['prompt'][:55]}…")

        print(f"\n{len(added)} cases added.\n")

        if args.skip_run:
            print("--skip-run: skipping evaluation.")
            return

        orders = ("original", "reversed") if args.both_orders else (args.order,)
        summary: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"agreements": [], "pattern_b": 0, "total": 0}
        )

        for order in orders:
            print(f"\n{'=' * 80}")
            print(f"RUNNING question_order={order} on {len(added)} new cases")
            print(f"{'=' * 80}\n")

            for item in added:
                params: list[str] = []
                if args.judges:
                    params += [f"judge_models={j}" for j in args.judges]
                if order != "original":
                    params.append(f"question_order={order}")
                run_url = f"/groundtruth/run/{item['id']}"
                if params:
                    run_url += "?" + "&".join(params)

                r = await client.post(run_url)
                r.raise_for_status()
                result = r.json()

                for judge in result["judges"]:
                    short = judge["judge_model"].split("/")[-1]
                    answers = judge["answers"]
                    reason = (judge.get("reason") or "").strip()
                    _print_case_result(
                        item["id"],
                        item["criterion"],
                        item["prompt"],
                        short,
                        judge["agreement"],
                        answers,
                        item["expected_answers"],
                        reason,
                        summary,
                        order,
                    )

        _print_summary(
            summary, "both orders" if args.both_orders else f"order={args.order}"
        )


# ── CLI ───────────────────────────────────────────────────────────────────────


def _add_eval_url_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--eval-url",
        default=None,
        metavar="URL",
        help=f"Evaluation service URL (default: {EVALUATION_URL})",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groundtruth",
        description="Ground truth corpus tool for govllm.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # seed
    p_seed = sub.add_parser(
        "seed", help="Drop + recreate tables and insert all corpus cases."
    )
    p_seed.add_argument(
        "--db-url",
        default=None,
        metavar="DSN",
        help=f"asyncpg DSN (default: {ARENA_DB_URL})",
    )
    _add_eval_url_arg(p_seed)

    # run
    p_run = sub.add_parser("run", help="Run checklist evaluations on the corpus.")
    p_run.add_argument(
        "--criterion",
        nargs="+",
        default=None,
        metavar="CRITERION",
        help="Filter by criterion (one or more). Omit for all.",
    )
    p_run.add_argument(
        "--judges",
        nargs="+",
        default=None,
        metavar="MODEL",
        help="Override judge model list (e.g. ollama/gemma3:4b ollama/phi4-mini).",
    )
    p_run.add_argument(
        "--cases",
        nargs="+",
        default=None,
        metavar="ID_PREFIX",
        help="Run only on cases whose ID starts with these prefixes.",
    )
    p_run.add_argument(
        "--order",
        choices=["original", "reversed", "permuted"],
        default="original",
        help="Question presentation order (default: original). 'permuted' = q2→q4→q1→q3.",
    )
    p_run.add_argument(
        "--compare",
        action="store_true",
        help="After the run, show original vs reversed comparison per case.",
    )
    _add_eval_url_arg(p_run)

    # extend
    p_ext = sub.add_parser(
        "extend", help="Add new cases from a JSON file and evaluate them."
    )
    p_ext.add_argument(
        "cases_json",
        metavar="CASES_JSON",
        help="Path to a JSON file containing a list of new cases.",
    )
    p_ext.add_argument(
        "--skip-run",
        action="store_true",
        help="Only insert cases, do not evaluate them.",
    )
    p_ext.add_argument(
        "--judges",
        nargs="+",
        default=None,
        metavar="MODEL",
        help="Override judge model list.",
    )
    p_ext.add_argument(
        "--order",
        choices=["original", "reversed"],
        default="original",
        help="Question order to run (ignored if --both-orders is set).",
    )
    p_ext.add_argument(
        "--both-orders",
        action="store_true",
        help="Run both original and reversed orders (default for corpus extension).",
    )
    _add_eval_url_arg(p_ext)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "seed":
        asyncio.run(cmd_seed(args))
    elif args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "extend":
        asyncio.run(cmd_extend(args))


if __name__ == "__main__":
    main()
