# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Test-retest run of the ground truth judges (protocol approved by the author, 2026-10-23).

Design: 8 judges x 49 cases, temperature 0 (the production setting), stored under run
labels so that no analysis of the main runs ('main') reads them:
    retest-orig-r1..r5   original order, K = 5 repetitions
    retest-rev-r1..r2    reversed order (order control)
    retest-perm-r1..r2   permuted order q2->q4->q1->q3 (same permutation as the main runs)
Steps are interleaved (orig r1, rev r1, perm r1, orig r2, rev r2, perm r2, orig r3..r5) so
that the order control is complete early and time drift is spread across conditions.
Within a step: judge by judge, every case; the judge is unloaded from Ollama at the end of
its block, so each repetition starts from a fresh model load.

Each stored row carries run_label, model_digest (Ollama), created_at, latency_ms and the raw
response (see services/groundtruth.py).

Resume: safe to interrupt and relaunch. `groundtruth.py run` skips the (case, judge, order,
run label) already stored, so a relaunch continues where it stopped. Unusable answers are
stored with their status and are not retried (one attempt per repetition).

Usage (inside the evaluation container):
    python scripts/retest.py                 # run / resume, log to stdout
    python scripts/retest.py --dry-run       # print the plan
Last line on completion: ALL_DONE
"""

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

from shared.config import get_evaluation_settings

settings = get_evaluation_settings()

PLAN = [
    ("retest-orig-r1", "original"), ("retest-rev-r1", "reversed"), ("retest-perm-r1", "permuted"),
    ("retest-orig-r2", "original"), ("retest-rev-r2", "reversed"), ("retest-perm-r2", "permuted"),
    ("retest-orig-r3", "original"), ("retest-orig-r4", "original"), ("retest-orig-r5", "original"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def unload(model: str) -> None:
    """Ask Ollama to drop the model from memory (keep_alive 0), so the next block reloads it."""
    body = json.dumps({"model": model.removeprefix("ollama/"), "keep_alive": 0}).encode()
    req = urllib.request.Request(f"{settings.ollama_base_url}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:  # not fatal: the next judge evicts it anyway
        print(f"{now()} WARN unload {model}: {e}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    judges = settings.benchmark_models
    print(f"{now()} START retest — {len(PLAN)} steps x {len(judges)} judges x 49 cases", flush=True)
    for label, order in PLAN:
        print(f"{now()} STEP_START {label} order={order}", flush=True)
        for judge in judges:
            cmd = [sys.executable, "-u", "scripts/groundtruth.py", "run", "--order", order,
                   "--judges", judge, "--run-label", label]
            print(f"{now()} RUN {label} {judge}", flush=True)
            if args.dry_run:
                continue
            rc = subprocess.run(cmd).returncode
            if rc != 0:
                # Stop rather than skip: a relaunch resumes this judge where it stopped
                print(f"{now()} FAILED {label} {judge} exit={rc}", flush=True)
                sys.exit(rc)
            unload(judge)
        print(f"{now()} STEP_DONE {label}", flush=True)
    print(f"{now()} ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
