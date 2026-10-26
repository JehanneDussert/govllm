#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Rebuild govllm.eval_results from the benchmark result files after the 2026-10-24 loss
(docs/incident_2026-10-24_eval_results.md).

Every benchmark entry with status OK carries the exact row eval_runner wrote:
trace_id, generator model, use case, profile, composite score, per-criterion scores and
evaluated_at (`eval` field of docs/benchmark/results/{gen}_{judge}.json). Rows are
rebuilt from there, nothing is estimated. Rows not from the benchmark (chat, discarded
runs) cannot be rebuilt exactly and are not restored (decision of 2026-10-25, option b).

Steps (one transaction):
  1. delete the integration-test rows (model = 'ollama/test-generator');
  2. insert every benchmark evaluation whose trace_id is not already in the table
     (idempotent), self_judged = false, restored_from = 'benchmark_files' and
     restored_at = now() (same timestamp for the whole batch). Run mark_self_judged.py
     afterwards. The provenance columns must exist (migrations.sql); the script checks.

Dry run by default. --container selects the PostgreSQL container, so the whole
procedure can first be rehearsed on a throwaway restore of the dump.

    python scripts/restore_eval_results.py --container pg-restore-test --user postgres          # dry run
    python scripts/restore_eval_results.py --container pg-restore-test --user postgres --apply
    python scripts/restore_eval_results.py --apply                                               # langfuse-db
"""

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

RESULTS = Path("docs/benchmark/results")
TEST_MODEL = "ollama/test-generator"
RESTORED_FROM = "benchmark_files"


def psql(args, sql: str) -> str:
    cmd = ["docker", "exec", "-i", args.container, "psql", "-U", args.user, "-d", args.database,
           "-At", "-v", "ON_ERROR_STOP=1"]
    return subprocess.run(cmd, input=sql, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def lit(v) -> str:
    """SQL literal (dollar-quoting would break on '$$' inside reasons)."""
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def benchmark_rows() -> list[dict]:
    rows, seen = [], set()
    for f in sorted(RESULTS.glob("*.json")):
        if f.name.endswith(".partial.json"):
            continue
        for r in json.loads(f.read_text(encoding="utf-8"))["results"]:
            e = r.get("eval")
            if r.get("status") != "OK" or not e:
                continue
            assert e["trace_id"] == r["trace_id"], (f.name, r["id"])
            assert e["trace_id"] not in seen, ("duplicate trace_id", e["trace_id"])
            seen.add(e["trace_id"])
            rows.append(e)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", default="langfuse-db")
    ap.add_argument("--user", default="langfuse")
    ap.add_argument("--database", default="langfuse")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = ap.parse_args()

    rows = benchmark_rows()
    cols = set(psql(args, "SELECT column_name FROM information_schema.columns WHERE table_schema = 'govllm' "
                          "AND table_name = 'eval_results';").split())
    if not {"restored_from", "restored_at"} <= cols:
        raise SystemExit("eval_results has no restored_from/restored_at columns: apply the migration first")
    present = set(psql(args, "SELECT trace_id FROM govllm.eval_results;").split())
    n_test = int(psql(args, f"SELECT count(*) FROM govllm.eval_results WHERE model = {lit(TEST_MODEL)};"))
    n_before = int(psql(args, "SELECT count(*) FROM govllm.eval_results;"))
    todo = [e for e in rows if e["trace_id"] not in present]
    by_month = Counter(e["evaluated_at"][:7] for e in todo)

    print(f"target: {args.container}/{args.database} — eval_results rows now: {n_before}")
    print(f"test rows to delete ({TEST_MODEL}): {n_test}")
    print(f"benchmark evaluations: {len(rows)}; already present: {len(rows) - len(todo)}; to insert: {len(todo)} "
          f"{dict(sorted(by_month.items()))}")
    if not args.apply:
        print("dry run: nothing written (use --apply)")
        return

    values = ",\n".join(
        "(" + ", ".join([
            lit(e["trace_id"]), lit(e["model"]), lit(e.get("use_case_id")), lit(e.get("profile_id")),
            repr(float(e["composite_score"])), lit(json.dumps(e.get("criteria_scores") or [])) + "::jsonb",
            lit(e["evaluated_at"]) + "::timestamptz", "false", lit(RESTORED_FROM), "now()",
        ]) + ")"
        for e in todo
    )
    sql = (
        "BEGIN;\n"
        f"DELETE FROM govllm.eval_results WHERE model = {lit(TEST_MODEL)};\n"
        + (
            "INSERT INTO govllm.eval_results (trace_id, model, use_case_id, profile_id, composite_score, "
            f"criteria_scores, evaluated_at, self_judged, restored_from, restored_at) VALUES\n{values};\n"
            if todo else ""
        )
        + "COMMIT;\n"
    )
    psql(args, sql)
    n_after = int(psql(args, "SELECT count(*) FROM govllm.eval_results;"))
    print(f"written: eval_results rows {n_before} -> {n_after} (expected {n_before - n_test + len(todo)})")


if __name__ == "__main__":
    main()
