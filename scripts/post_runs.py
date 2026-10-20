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

Which runs to wait for and export is configurable (defaults = the 2026-10-15 runs):
    --run-log /tmp/gt_candidates2.log --judges granite4,lfm2.5-1.2b-thinking
    --expected-branch analysis/granite-lfm-3orders

Must run from the repo root (or a worktree) on the branch holding the analysis
scripts, with matplotlib/numpy available for the figures, e.g.
    uv run --no-project --with matplotlib==3.9.2 --with numpy==2.1.3 python scripts/post_runs.py --check

State (log, markers, summary) lives outside the repo in --state-dir, so the
working tree only changes through the analysis outputs themselves.
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = ROOT.parent / "govllm-post-runs"
CONTAINER = "evaluation"
# Defaults; overridden by --run-log / --judges / --expected-branch.
RUN_LOG = "/tmp/gt_candidates.log"           # log of the runs inside the container
DONE_LINE = "ALL_DONE"                        # last line written by the chained runs
JUDGE_SLUGS = "gemma4-e4b,ministral-3-8b"
EVAL_URL = "http://localhost:8003"
EXPECTED_BRANCH = "analysis/8x8"


STALE_LOCK_HOURS = 2  # a lock without a readable live PID older than this is stale


def pid_alive(pid: int) -> bool:
    """True if a process with this PID is running (never signals it)."""
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def lock_is_stale(lock: Path) -> tuple[bool, str]:
    """A lock is stale when its PID is no longer running, or (legacy lock without
    PID) when it is older than STALE_LOCK_HOURS."""
    try:
        info = json.loads(lock.read_text(encoding="utf-8"))
        pid = int(info["pid"])
    except (ValueError, KeyError, TypeError, OSError):
        age_h = (dt.datetime.now().timestamp() - lock.stat().st_mtime) / 3600
        return age_h > STALE_LOCK_HOURS, f"legacy lock without PID, {age_h:.1f} h old"
    if pid_alive(pid):
        return False, f"pid {pid} still running (since {info.get('started')})"
    return True, f"pid {pid} no longer running (started {info.get('started')})"


class Pipeline:
    """Runs the steps in order. Completed steps are recorded in post_runs.steps.json,
    so a pipeline interrupted mid-way (PC shut down, sleep, killed task) resumes at
    the first unfinished step on the next start. The record is tied to the run
    parameters (fingerprint) and cleared once the whole pipeline has succeeded."""

    def __init__(self, state: Path, dry_run: bool, fingerprint: str = ""):
        self.state = state
        self.dry = dry_run
        state.mkdir(parents=True, exist_ok=True)
        self.log_path = state / "post_runs.log"
        self.steps_path = state / "post_runs.steps.json"
        self.fingerprint = fingerprint
        self.done_steps: list[str] = []
        if self.steps_path.exists():
            try:
                rec = json.loads(self.steps_path.read_text(encoding="utf-8"))
                if rec.get("fingerprint") == fingerprint:
                    self.done_steps = rec.get("done", [])
            except ValueError:
                pass

    def mark_done(self, name: str):
        self.done_steps.append(name)
        self.steps_path.write_text(json.dumps({"fingerprint": self.fingerprint, "done": self.done_steps,
                                               "updated": dt.datetime.now().isoformat(timespec="seconds")},
                                              indent=2), encoding="utf-8")

    def clear_steps(self):
        if self.steps_path.exists():
            self.steps_path.unlink()

    def log(self, msg: str):
        line = f"{dt.datetime.now().astimezone().isoformat(timespec='seconds')}  {msg}"
        print(line, flush=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def run(self, name: str, cmd: list[str], **kw) -> str:
        if name in self.done_steps and not self.dry:
            self.log(f"[{name}] already done in an interrupted previous start — skipped (resume)")
            return ""
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
        self.mark_done(name)
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
    usable = stats.get("usable_answers") or {}
    if usable:
        lines += ["", "## Usable answers (status ok / corpus cases)", ""]
        for j, by_o in usable.items():
            lines.append(f"- {j}: " + ", ".join(f"{o} {u['n_usable']}/{u['n_expected']}" for o, u in by_o.items()))
    sens = stats.get("sensitivity_unusable") or {}
    rows = [(j, o, s) for j, by_o in sens.items() for o, s in by_o.items() if s["difference_pp"]]
    if rows:
        lines += ["", "## Sensitivity: unusable answers excluded vs counted as full disagreements", ""]
        for j, o, s in rows:
            lines.append(f"- {j} {o}: {s['excluding_unusable']['estimate'] * 100:.1f}% vs "
                         f"{s['unusable_as_disagreement']['estimate'] * 100:.1f}% ({s['difference_pp']:+.1f} pp)"
                         + ("  **outside the 95% CI**" if s["flag"] else ""))
    panel = stats.get("specialised_panel") or {}
    if panel:
        pm = panel["panel_minus_best"]
        lines += ["", "## Specialised panel (in-sample selection, single comparison)", "",
                  f"- assignment: {panel['assignment']}",
                  f"- panel {panel['panel_agreement']['estimate'] * 100:.1f}% vs {panel['best_single_judge']}: "
                  f"{pm['estimate'] * 100:+.1f} pp [{pm['ci95'][0] * 100:+.1f}, {pm['ci95'][1] * 100:+.1f}]"]
    changed = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    # Caveats for the judges of this run (and any other judge in the results) from models.json
    from model_registry import MODELS
    flagged = [s for s in MODELS if MODELS[s].get("caveat")
               and (s in JUDGE_SLUGS.split(",") or s in stats["agreement"])]
    if flagged:
        lines += ["", "## Caveats — interpret with caution", ""]
        for s in flagged:
            lines.append(f"- **{s}**: {MODELS[s]['caveat']}")
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
    # Every judge, every ordering: each file then carries the full corpus grid with a
    # status per case (needed for the usable-answer rate and the sensitivity analysis).
    pl.run("export", [py, "scripts/export_groundtruth_results.py",
                      "--order", "original", "--order", "reversed", "--order", "permuted"])
    pl.run("stats_pooled", [py, "scripts/groundtruth_stats.py"])                       # + forest pooled
    pl.run("stats_original", [py, "scripts/groundtruth_stats.py", "--condition", "original"])
    pl.run("stats_paper", [py, "scripts/groundtruth_stats.py", "--models", "paper", "--no-figure"])
    pl.run("order_figure", [py, "scripts/plot_order_sensitivity.py"])
    pl.run("order_figure_paper", [py, "scripts/plot_order_sensitivity.py", "--models", "paper"])
    if not pl.dry:
        summarise(pl)


def main():
    global RUN_LOG, JUDGE_SLUGS, EXPECTED_BRANCH
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--force", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state-dir", default=str(DEFAULT_STATE))
    ap.add_argument("--run-log", default=RUN_LOG, help="log of the chained runs inside the container")
    ap.add_argument("--judges", default=JUDGE_SLUGS, help="comma-separated slugs to export (models.json)")
    ap.add_argument("--expected-branch", default=EXPECTED_BRANCH, help="branch the worktree must be on")
    args = ap.parse_args()
    RUN_LOG, JUDGE_SLUGS, EXPECTED_BRANCH = args.run_log, args.judges, args.expected_branch

    fingerprint = f"{RUN_LOG}|{JUDGE_SLUGS}|{EXPECTED_BRANCH}"
    pl = Pipeline(Path(args.state_dir), dry_run=args.dry_run, fingerprint=fingerprint)
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
        stale, why = lock_is_stale(lock)
        if not stale:
            pl.log(f"[lock] {lock} held: {why} — not starting")
            return
        pl.log(f"[lock] stale lock removed: {why}")
        lock.unlink()

    resume = f", resuming after {pl.done_steps}" if pl.done_steps else ""
    pl.log(f"=== pipeline start ({'dry-run' if args.dry_run else 'live'}) in {ROOT}{resume} ===")
    if not args.dry_run:
        lock.write_text(json.dumps({"pid": os.getpid(), "started": dt.datetime.now().isoformat(timespec="seconds")}),
                        encoding="utf-8")
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
        pl.clear_steps()
        done_marker.write_text(str(dt.datetime.now()), encoding="utf-8")
        append_next_steps(pl, f"OK — summary in {pl.state / 'post_runs_summary.md'}; outputs uncommitted in {ROOT}")
    pl.log("=== pipeline done ===")


if __name__ == "__main__":
    main()
