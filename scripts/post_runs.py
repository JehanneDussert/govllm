#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Post-run pipeline for the ground truth runs (reversed/permuted orderings of
candidate judges): export -> validity.json -> 3-ordering statistics, CIs and
figures. Unattended and safe: writes files only, never commits or pushes, and
stops at the first failing step.

Modes:
    python scripts/post_runs.py --check      # watcher mode: run the pipeline once, only when the runs
                                             # are finished; otherwise log the progress and exit 0
    python scripts/post_runs.py --force      # run the pipeline now (no readiness check)
    python scripts/post_runs.py --dry-run    # log what would run, change nothing

Must run from the repo root (or a worktree) on the branch holding the analysis
scripts, with matplotlib/numpy available for the figures, e.g.
    uv run --no-project --with matplotlib==3.9.2 --with numpy==2.1.3 python scripts/post_runs.py --check

State (log, markers, summary) lives outside the repo in --state-dir, so the
working tree only changes through the analysis outputs themselves.
"""

import argparse
import datetime as dt
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = ROOT.parent / "govllm-post-runs"
CONTAINER = "evaluation"
RUN_LOG = "/tmp/gt_candidates.log"           # log of the runs inside the container
DONE_LINE = "ALL_DONE"                        # last line written by the chained runs
JUDGES = ["ollama/gemma4:e4b", "ollama/ministral-3:8b"]
JUDGE_SLUGS = "gemma4-e4b,ministral-3-8b"
EVAL_URL = "http://localhost:8003"
EXPECTED_BRANCH = "analysis/8x8"


class Pipeline:
    def __init__(self, state: Path, dry_run: bool):
        self.state = state
        self.dry = dry_run
        state.mkdir(parents=True, exist_ok=True)
        self.log_path = state / "post_runs.log"

    def log(self, msg: str):
        line = f"{dt.datetime.now().astimezone().isoformat(timespec='seconds')}  {msg}"
        print(line, flush=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def run(self, name: str, cmd: list[str], **kw) -> str:
        self.log(f"[{name}] $ {' '.join(cmd)}")
        if self.dry:
            return ""
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=kw.get("env"))
        out_file = self.state / f"step_{name}.out"
        out_file.write_text(p.stdout + ("\n--- stderr ---\n" + p.stderr if p.stderr else ""), encoding="utf-8")
        if p.returncode != 0:
            self.log(f"[{name}] FAILED (exit {p.returncode}) — see {out_file}")
            raise SystemExit(f"step {name} failed")
        self.log(f"[{name}] ok — output in {out_file}")
        return p.stdout


def docker(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def runs_state() -> tuple[str, str]:
    """('done' | 'running' | 'died' | 'unknown', detail)."""
    tail = docker("exec", CONTAINER, "sh", "-c", f"tail -n 3 {RUN_LOG}")
    if tail.returncode != 0:
        return "unknown", f"cannot read {RUN_LOG} in {CONTAINER}: {tail.stderr.strip()[:200]}"
    if DONE_LINE in tail.stdout:
        return "done", tail.stdout.strip().splitlines()[-1]
    # Is a ground truth run process still alive? (pattern split so this probe doesn't match itself)
    probe = ("import os;pat='scripts/ground'+'truth.py';"
             "print(sum(1 for p in os.listdir('/proc') if p.isdigit() and "
             "pat in open(f'/proc/{p}/cmdline','rb').read().decode(errors='ignore')))")
    alive = docker("exec", CONTAINER, "python", "-c", probe)
    n = int(alive.stdout.strip() or 0) if alive.returncode == 0 else -1
    last = tail.stdout.strip().splitlines()[-1] if tail.stdout.strip() else ""
    if n > 0:
        return "running", f"{n} run process(es); last log line: {last[:160]}"
    if n == 0:
        return "died", f"no run process and no {DONE_LINE} line; last log line: {last[:160]}"
    return "unknown", f"process probe failed: {alive.stderr.strip()[:200]}"


def progress() -> str:
    try:
        corpus = json.load(urllib.request.urlopen(f"{EVAL_URL}/groundtruth/corpus", timeout=20))
        return f"corpus reachable ({len(corpus)} cases)"
    except Exception as e:  # informational only
        return f"evaluation service not reachable: {e}"


def preflight(pl: Pipeline):
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    if branch != EXPECTED_BRANCH:
        pl.log(f"[preflight] FAILED: worktree {ROOT} is on '{branch}', expected '{EXPECTED_BRANCH}'")
        raise SystemExit("wrong branch")
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    if dirty.strip():
        pl.log(f"[preflight] FAILED: working tree not clean (refusing to mix outputs with other changes):\n{dirty}")
        raise SystemExit("dirty tree")
    try:
        urllib.request.urlopen(f"{EVAL_URL}/health", timeout=20).read()
    except Exception as e:
        pl.log(f"[preflight] FAILED: evaluation service not healthy: {e}")
        raise SystemExit("service down")
    pl.log(f"[preflight] ok — branch {branch}, clean tree, service healthy")


def summarise(pl: Pipeline):
    stats = json.loads((ROOT / "docs/ground_truth/analysis/groundtruth_stats.json").read_text(encoding="utf-8"))
    lines = [f"# Post-run summary — {dt.datetime.now().astimezone().isoformat(timespec='seconds')}", "",
             "## Agreement pooled over 3 orderings (95% case-level bootstrap CI)", ""]
    pooled = {j: a["pooled"] for j, a in stats["agreement"].items() if "pooled" in a}
    for j, s in sorted(pooled.items(), key=lambda kv: -kv[1]["estimate"]):
        lines.append(f"- {j}: {s['estimate'] * 100:.1f}% [{s['ci95'][0] * 100:.1f}, {s['ci95'][1] * 100:.1f}] "
                     f"(cases={s['n_cases']}, case-runs={s['n_case_runs']})")
    pv = stats.get("paired_vs_top") or {}
    # Project convention: comparisons from a family of tests -> Bonferroni CI + Holm p;
    # unadjusted CI only for single comparisons (the specialised panel).
    def fam(s):
        cb = s["ci_bonferroni"]
        return (f"{s['estimate'] * 100:+.1f} pp, Bonferroni CI [{cb[0] * 100:+.1f}, {cb[1] * 100:+.1f}] "
                f"(k={s['family_size']}), Holm p={s['p_holm']:.3f}")

    if pv:
        lines += ["", f"## Paired difference: {pv['reference']} minus judge (pooled)", ""]
        for j, s in sorted(pv["differences"].items(), key=lambda kv: kv[1]["estimate"]):
            lines.append(f"- {j}: {fam(s)}")
    lines += ["", "## Order effects (ordering minus original, family = all judges x orderings)", ""]
    for name, s in stats.get("order_effects", {}).items():
        lines.append(f"- {name}: {fam(s)}")
    panel = stats.get("specialised_panel") or {}
    if panel:
        pm = panel["panel_minus_best"]
        lines += ["", "## Specialised panel (in-sample selection, single comparison)", "",
                  f"- assignment: {panel['assignment']}",
                  f"- panel {panel['panel_agreement']['estimate'] * 100:.1f}% vs {panel['best_single_judge']}: "
                  f"{pm['estimate'] * 100:+.1f} pp [{pm['ci95'][0] * 100:+.1f}, {pm['ci95'][1] * 100:+.1f}]"]
    changed = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    lines += ["", "## Files written in the worktree (not committed)", "", "```", changed.rstrip(), "```"]
    out = pl.state / "post_runs_summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pl.log(f"[summary] written {out}")


def append_next_steps(pl: Pipeline, status: str):
    ns = ROOT.parent / "govllm" / "docs" / "arxiv" / "draft" / "NEXT_STEPS.md"
    if not ns.exists():
        pl.log(f"[next_steps] {ns} not found — skipped")
        return
    with open(ns, "a", encoding="utf-8") as f:
        f.write(f"\n- {dt.datetime.now().astimezone().isoformat(timespec='minutes')} — post_runs.py: {status} "
                f"(log: {pl.log_path})\n")
    pl.log(f"[next_steps] appended status to {ns} (not committed)")


def pipeline(pl: Pipeline):
    py = sys.executable
    preflight(pl)
    pl.run("export", [py, "scripts/export_groundtruth_results.py",
                      "--order", "reversed", "--order", "permuted", "--judges", JUDGE_SLUGS])
    pl.run("stats_pooled", [py, "scripts/groundtruth_stats.py"])                       # + forest pooled
    pl.run("stats_original", [py, "scripts/groundtruth_stats.py", "--condition", "original"])
    pl.run("stats_paper", [py, "scripts/groundtruth_stats.py", "--models", "paper", "--no-figure"])
    pl.run("order_figure", [py, "scripts/plot_order_sensitivity.py"])
    pl.run("order_figure_paper", [py, "scripts/plot_order_sensitivity.py", "--models", "paper"])
    if not pl.dry:
        summarise(pl)


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--force", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state-dir", default=str(DEFAULT_STATE))
    args = ap.parse_args()

    pl = Pipeline(Path(args.state_dir), dry_run=args.dry_run)
    done_marker = pl.state / "post_runs.done"
    failed_marker = pl.state / "post_runs.failed"
    lock = pl.state / "post_runs.lock"

    if args.check:
        if done_marker.exists() or failed_marker.exists():
            return  # already handled; stay silent so the 15-min task doesn't flood the log
        state, detail = runs_state()
        pl.log(f"[check] runs {state}: {detail}")
        if state == "died":
            failed_marker.write_text(detail, encoding="utf-8")
            append_next_steps(pl, f"runs stopped WITHOUT finishing ({detail}) — pipeline not run, needs a session")
            return
        if state != "done":
            return
    if lock.exists() and not args.dry_run:
        pl.log(f"[lock] {lock} exists — another instance is running or crashed; remove it to retry")
        return

    pl.log(f"=== pipeline start ({'dry-run' if args.dry_run else 'live'}) in {ROOT} ===")
    if not args.dry_run:
        lock.write_text(str(dt.datetime.now()), encoding="utf-8")
    try:
        pipeline(pl)
    except SystemExit as e:
        if not args.dry_run:
            failed_marker.write_text(str(e), encoding="utf-8")
            append_next_steps(pl, f"FAILED ({e}) — see log; nothing committed")
        pl.log(f"=== pipeline stopped: {e} ===")
        raise
    finally:
        if lock.exists() and not args.dry_run:
            lock.unlink()
    if not args.dry_run:
        done_marker.write_text(str(dt.datetime.now()), encoding="utf-8")
        append_next_steps(pl, f"OK — summary in {pl.state / 'post_runs_summary.md'}; outputs uncommitted in {ROOT}")
    pl.log("=== pipeline done ===")


if __name__ == "__main__":
    main()
