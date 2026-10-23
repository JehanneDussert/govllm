#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Retroactively flag self-judged rows in eval_results (generator == judge).

eval_results does not store the judge. It is recovered, per trace_id, from:
  1. the benchmark result files (docs/benchmark/results/{gen}_{judge}.json), which
     carry the trace_id of every scored entry;
  2. otherwise, the Langfuse trace metadata (`judge_model`, written by eval_runner).
Rows whose judge cannot be recovered are reported and left unflagged.

Dry run by default (prints counts); --apply sets eval_results.self_judged = true.
Afterwards, rebuild the rolling cache without them:
    docker exec -w /app evaluation python scripts/backfill_matrix_cache.py

Run on the host, from the repository root (needs Docker and the langfuse-db container):
    python scripts/mark_self_judged.py            # dry run
    python scripts/mark_self_judged.py --apply
"""

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

from model_registry import slug_of

RESULTS = Path("docs/benchmark/results")
DB = ["docker", "exec", "-i", "langfuse-db", "psql", "-U", "langfuse", "-d", "langfuse", "-At", "-F", "\t"]


def psql(sql: str) -> list[list[str]]:
    out = subprocess.run(DB, input=sql, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [line.split("\t") for line in out.strip().splitlines() if line]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the flags (default: dry run)")
    args = ap.parse_args()

    bench_judge: dict[str, str] = {}
    for f in sorted(RESULTS.glob("*.json")):
        if f.name.endswith(".partial.json"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        for r in d["results"]:
            if r.get("trace_id"):
                bench_judge[r["trace_id"]] = slug_of(d["judge_model"])

    rows = psql(
        "SELECT e.trace_id, e.model, coalesce(t.metadata->>'judge_model', ''), e.self_judged::text "
        "FROM govllm.eval_results e LEFT JOIN public.traces t ON t.id = e.trace_id;"
    )
    flagged, unknown, sources, conflicts = [], 0, Counter(), 0
    for trace_id, model, lf_judge, _ in rows:
        judge = bench_judge.get(trace_id)
        src = "benchmark file"
        if lf_judge and judge and slug_of(lf_judge) != judge:
            conflicts += 1
        if judge is None and lf_judge:
            judge, src = slug_of(lf_judge), "langfuse metadata"
        if judge is None:
            unknown += 1
            continue
        if judge == slug_of(model):
            flagged.append(trace_id)
            sources[src] += 1

    already = sum(1 for r in rows if r[3] == "true")
    print(f"eval_results rows: {len(rows)} (already flagged: {already})")
    print(f"self-judged: {len(flagged)} {dict(sources)}; judge unknown: {unknown}; source conflicts: {conflicts}")
    if not args.apply:
        print("dry run: nothing written (use --apply)")
        return
    ids = ",".join(f"'{t}'" for t in flagged)
    res = psql(f"UPDATE govllm.eval_results SET self_judged = true WHERE trace_id IN ({ids}) AND NOT self_judged;")
    print(f"flagged {res} — now rebuild the cache: docker exec -w /app evaluation python scripts/backfill_matrix_cache.py")


if __name__ == "__main__":
    main()
