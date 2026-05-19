# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""Full benchmark pipeline: generate missing model answers, then score with all judges.

Phase 1 — Reference generation
  For each model, checks which prompt IDs are missing from
  docs/benchmark/references/{model}.json and generates the answers via /chat.
  Skips prompts that already have a stored answer — safe to re-run after a crash.

Phase 2 — Fixed evaluation
  For each (model, judge) combination, checks whether the result file covers ALL
  entries in the reference. Evaluates only the missing IDs (incremental update).
  Safe to re-run: skips combos that are already fully evaluated.

Usage:
    python scripts/run_full_benchmark.py
    python scripts/run_full_benchmark.py --models ollama/phi4-mini
    python scripts/run_full_benchmark.py --judges ollama/phi4-mini ollama/gemma3:4b
    python scripts/run_full_benchmark.py --only-generate
    python scripts/run_full_benchmark.py --only-evaluate
    python scripts/run_full_benchmark.py --timeout 180
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

GATEWAY_URL   = "http://localhost:8001"
EVAL_URL      = "http://localhost:8003"
POLL_INTERVAL = 3

ROOT         = Path(__file__).parent.parent
PROMPTS_FILE = ROOT / "docs" / "benchmark" / "prompts.json"
REF_DIR      = ROOT / "docs" / "benchmark" / "references"
RESULTS_DIR  = ROOT / "docs" / "benchmark" / "results"

ALL_MODELS = [
    "ollama/phi4-mini",
    "ollama/mistral:7b",
    "ollama/gemma3:4b",
    "ollama/qwen3:1.7b",
]

PROFILE_ID_MAP  = {"accessibility_inclusion": "accessibility"}
USE_CASE_ID_MAP = {"summarization": "summary", "administrative_writing": "legal"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slug(model: str) -> str:
    return model.removeprefix("ollama/").replace(":", "-").replace("/", "-")


def _load_prompts() -> list[dict]:
    with open(PROMPTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    items = []
    for use_case, entries in data["benchmark_prompts"].items():
        for entry in entries:
            items.append({**entry, "use_case": use_case})
    return items


def _load_reference(model: str) -> tuple[dict, list[dict], set[str]]:
    """Return (raw_doc, entries, existing_ids). raw_doc preserves original metadata."""
    path = REF_DIR / f"{_slug(model)}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        entries = raw.get("entries", [])
    else:
        raw = {"model": model, "n": 0, "entries": []}
        entries = []
    return raw, entries, {e["id"] for e in entries}


def _save_reference(model: str, raw_doc: dict, entries: list[dict]) -> None:
    """Save reference, preserving original metadata fields."""
    REF_DIR.mkdir(parents=True, exist_ok=True)
    raw_doc["entries"] = entries
    raw_doc["n"] = len(entries)
    raw_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = REF_DIR / f"{_slug(model)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw_doc, f, indent=2, ensure_ascii=False)


def _load_results(path: Path) -> tuple[list[dict], set[str]]:
    """Load result entries from a final or partial file."""
    if not path.exists():
        return [], set()
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    results = d.get("results", [])
    return results, {r["id"] for r in results}


def _switch_profile(client: httpx.Client, profile_id: str) -> None:
    client.post(f"{EVAL_URL}/config/judge/profile/{profile_id}", timeout=10).raise_for_status()


def _switch_use_case(client: httpx.Client, use_case_id: str) -> None:
    client.post(f"{EVAL_URL}/config/judge/use-case/{use_case_id}", timeout=10).raise_for_status()


def _chat(client: httpx.Client, prompt: str, model: str, timeout: int = 300) -> str:
    resp = client.post(
        f"{GATEWAY_URL}/chat",
        json={"messages": [{"role": "user", "content": prompt}], "model": model, "stream": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    body = resp.json()
    return body["content"] if "content" in body else body["choices"][0]["message"]["content"]


def _trigger_eval(client: httpx.Client, trace_id: str, model: str, question: str, answer: str) -> None:
    client.post(
        f"{EVAL_URL}/eval/score",
        json={"trace_id": trace_id, "model": model, "question": question, "answer": answer},
        timeout=10,
    ).raise_for_status()


def _poll_result(client: httpx.Client, trace_id: str, timeout: int) -> dict | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"{EVAL_URL}/eval/result/{trace_id}", timeout=10)
        if resp.status_code == 200:
            body = resp.json()
            if body and body.get("composite_score") is not None:
                return body
        time.sleep(POLL_INTERVAL)
    return None


def _set_judge(judge: str) -> None:
    r = httpx.get(f"{EVAL_URL}/config/judge", timeout=10)
    r.raise_for_status()
    config = r.json()
    config["judge_model"] = judge
    httpx.put(f"{EVAL_URL}/config/judge", json=config, timeout=10).raise_for_status()


def _write_results(path: Path, results: list[dict], model: str, judge: str, timeout: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"run_at": datetime.now(timezone.utc).isoformat(), "model": model,
             "judge_model": judge, "timeout": timeout, "fixed_outputs": True,
             "total": len(results), "results": results},
            f, indent=2, ensure_ascii=False,
        )


# ── Phase 1: reference generation ────────────────────────────────────────────

def generate_references(models: list[str], prompts: list[dict], timeout: int = 300) -> None:
    print("\n" + "=" * 70)
    print("PHASE 1 — Reference generation")
    print("=" * 70)

    with httpx.Client() as client:
        for model in models:
            raw_doc, entries, done_ids = _load_reference(model)
            missing = [p for p in prompts if p["id"] not in done_ids]

            if not missing:
                print(f"\n[{_slug(model)}] All {len(entries)} prompts already generated — skip")
                continue

            print(f"\n[{_slug(model)}] {len(done_ids)} already done, {len(missing)} to generate")

            current_profile: str | None = None
            current_use_case: str | None = None

            for i, item in enumerate(missing, start=1):
                pid        = item["id"]
                use_case   = item["use_case"]
                profile    = item["governance_profile"]
                prompt     = item["prompt"]
                profile_id  = PROFILE_ID_MAP.get(profile, profile)
                use_case_id = USE_CASE_ID_MAP.get(use_case, use_case)

                print(f"  [{i:02d}/{len(missing)}] {pid} ({use_case} / {profile_id})", end="  ", flush=True)

                try:
                    if use_case_id != current_use_case:
                        _switch_use_case(client, use_case_id)
                        current_use_case = use_case_id
                        current_profile = None  # use-case switch resets the profile
                    if profile_id != current_profile:
                        _switch_profile(client, profile_id)
                        current_profile = profile_id

                    answer = _chat(client, prompt, model, timeout=timeout)
                    entries.append({
                        "id": pid, "use_case": use_case,
                        "governance_profile": profile,
                        "prompt": prompt, "answer": answer,
                    })
                    _save_reference(model, raw_doc, entries)
                    print(f"OK  ({len(answer)} chars)")

                except Exception as e:
                    print(f"ERR  {e}")
                    # No entry added -> will be retried on next run

    print("\nPhase 1 complete.")


# ── Phase 2: fixed evaluation ─────────────────────────────────────────────────

def evaluate(models: list[str], judges: list[str], timeout: int) -> None:
    print("\n" + "=" * 70)
    print("PHASE 2 — Fixed evaluation")
    print("=" * 70)

    combos = [(m, j) for j in judges for m in models]
    current_judge: str | None = None
    run_idx = 0

    for model, judge in combos:
        _, entries, _ = _load_reference(model)
        if not entries:
            print(f"  SKIP  {_slug(model)} × {_slug(judge)} — no reference file")
            continue

        out_path = RESULTS_DIR / f"{_slug(model)}_{_slug(judge)}.json"
        partial_path = out_path.with_suffix(".partial.json")
        # If a partial exists, it's the authoritative source (final may contain bad entries)
        check_path = partial_path if partial_path.exists() else out_path
        _, done_ids = _load_results(check_path)

        missing_ids = {e["id"] for e in entries} - done_ids
        if not missing_ids and not partial_path.exists():
            print(f"  SKIP  {_slug(model)} × {_slug(judge)} — fully evaluated ({len(entries)} entries)")
            continue

        run_idx += 1
        n_missing = len(missing_ids) if missing_ids else "(partial flush)"
        print(f"\n[{_slug(model)} × {_slug(judge)}] {len(done_ids)} done, {n_missing} to evaluate")

        if judge != current_judge:
            print(f"  -> switching judge to {judge}")
            _set_judge(judge)
            current_judge = judge

        # Convert existing final file to partial so _run_judge can resume from it
        if out_path.exists() and not partial_path.exists():
            out_path.rename(partial_path)
            print(f"    -> converted to partial for incremental update")

        _run_judge(judge, model, entries, timeout, out_path)

    print(f"\nPhase 2 complete — {run_idx} combinations updated.")


def _run_judge(judge: str, model: str, entries: list[dict], timeout: int, out_path: Path) -> None:
    partial_path = out_path.with_suffix(".partial.json")

    results, done_ids = [], set()
    if partial_path.exists():
        results, done_ids = _load_results(partial_path)
        print(f"    Resuming from partial — {len(done_ids)} already done")

    current_profile: str | None = None
    current_use_case: str | None = None

    with httpx.Client() as client:
        for entry in entries:
            pid = entry["id"]
            if pid in done_ids:
                continue

            profile_id  = PROFILE_ID_MAP.get(entry["governance_profile"], entry["governance_profile"])
            use_case_id = USE_CASE_ID_MAP.get(entry["use_case"], entry["use_case"])

            try:
                if use_case_id != current_use_case:
                    _switch_use_case(client, use_case_id)
                    current_use_case = use_case_id
                    current_profile = None  # use-case switch resets the profile
                if profile_id != current_profile:
                    _switch_profile(client, profile_id)
                    current_profile = profile_id
            except Exception as e:
                print(f"      ERR config switch failed for {pid}: {e}")
                results.append({"id": pid, "use_case": entry["use_case"],
                                 "governance_profile": entry["governance_profile"],
                                 "score": None, "status": f"CONFIG_ERROR: {e}",
                                 "prompt": entry["prompt"], "answer": entry["answer"], "eval": None})
                _write_results(partial_path, results, model, judge, timeout)
                continue

            trace_id = str(uuid.uuid4())
            try:
                _trigger_eval(client, trace_id, model, entry["prompt"], entry["answer"])
            except Exception as e:
                print(f"      ERR eval trigger failed for {pid}: {e}")
                results.append({"id": pid, "use_case": entry["use_case"],
                                 "governance_profile": entry["governance_profile"],
                                 "score": None, "status": f"EVAL_TRIGGER_ERROR: {e}",
                                 "trace_id": trace_id, "prompt": entry["prompt"],
                                 "answer": entry["answer"], "eval": None})
                _write_results(partial_path, results, model, judge, timeout)
                continue

            eval_result = _poll_result(client, trace_id, timeout)
            if eval_result is None:
                print(f"      ERR timeout — {pid}")
                results.append({"id": pid, "use_case": entry["use_case"],
                                 "governance_profile": entry["governance_profile"],
                                 "score": None, "status": "TIMEOUT", "trace_id": trace_id,
                                 "prompt": entry["prompt"], "answer": entry["answer"], "eval": None})
            else:
                score = eval_result.get("composite_score")
                print(f"      OK {pid}  score={score}")
                results.append({"id": pid, "use_case": entry["use_case"],
                                 "governance_profile": entry["governance_profile"],
                                 "score": score, "status": "OK", "trace_id": trace_id,
                                 "prompt": entry["prompt"], "answer": entry["answer"],
                                 "eval": eval_result})

            _write_results(partial_path, results, model, judge, timeout)

    _write_results(out_path, results, model, judge, timeout)
    if partial_path.exists():
        partial_path.unlink()

    ok  = sum(1 for r in results if r["status"] == "OK")
    avg = round(sum(r["score"] for r in results if r.get("score") is not None) / ok, 3) if ok else None
    print(f"    -> {ok}/{len(entries)} OK  avg={avg}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Full benchmark: generate missing references, then evaluate")
    parser.add_argument("--models",        nargs="+", default=ALL_MODELS, metavar="MODEL")
    parser.add_argument("--judges",        nargs="+", default=ALL_MODELS, metavar="MODEL")
    parser.add_argument("--timeout",       type=int, default=120)
    parser.add_argument("--only-generate", action="store_true", help="Phase 1 only — no evaluation")
    parser.add_argument("--only-evaluate", action="store_true", help="Phase 2 only — skip generation")
    args = parser.parse_args()

    prompts = _load_prompts()
    print(f"Loaded {len(prompts)} prompts from {PROMPTS_FILE}")
    by_diff: dict[str, list[str]] = {}
    for p in prompts:
        by_diff.setdefault(p.get("difficulty", "?"), []).append(p["id"])
    for diff, ids in sorted(by_diff.items()):
        print(f"  {diff}: {len(ids)} prompts")

    if not args.only_evaluate:
        generate_references(args.models, prompts, timeout=args.timeout)

    if not args.only_generate:
        evaluate(args.models, args.judges, args.timeout)


if __name__ == "__main__":
    main()
