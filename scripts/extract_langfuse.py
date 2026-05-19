#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Extract latency and token data from Langfuse for all benchmark result entries.

Reads:  docs/benchmark/results/*.json  (trace_id field per result entry)
Writes: docs/benchmark/analysis/latency_score.json
        docs/benchmark/analysis/latency_summary.json

Usage:
    python scripts/extract_langfuse.py [--env-file infra/.env] [--delay 0.1]

Requires environment variables (from infra/.env or shell):
    LANGFUSE_HOST         e.g. http://localhost:3000
    LANGFUSE_PUBLIC_KEY   pk-lf-...
    LANGFUSE_SECRET_KEY   sk-lf-...
"""

import argparse
import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "docs" / "benchmark" / "results"
ANALYSIS_DIR = ROOT / "docs" / "benchmark" / "analysis"


def load_env(env_file: str) -> None:
    path = Path(env_file)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = value


def auth_header(public_key: str, secret_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


# ---------------------------------------------------------------------------
# Langfuse fetch helpers
# ---------------------------------------------------------------------------

def fetch_trace(client: httpx.Client, host: str, headers: dict, trace_id: str) -> dict[str, Any] | None:
    try:
        r = client.get(f"{host}/api/public/traces/{trace_id}", headers=headers, timeout=15)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"  [warn] trace {trace_id}: {exc}")
        return None


def fetch_observations(client: httpx.Client, host: str, headers: dict, trace_id: str) -> list[dict]:
    try:
        r = client.get(
            f"{host}/api/public/observations",
            headers=headers,
            params={"traceId": trace_id, "limit": 10},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as exc:
        print(f"  [warn] observations {trace_id}: {exc}")
        return []


def extract_usage(observations: list[dict]) -> dict[str, int | None]:
    prompt_tokens = completion_tokens = total_tokens = None
    for obs in observations:
        usage = obs.get("usage") or {}
        if usage.get("promptTokens") is not None:
            prompt_tokens = (prompt_tokens or 0) + usage["promptTokens"]
        if usage.get("completionTokens") is not None:
            completion_tokens = (completion_tokens or 0) + usage["completionTokens"]
        if usage.get("totalTokens") is not None:
            total_tokens = (total_tokens or 0) + usage["totalTokens"]
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


# ---------------------------------------------------------------------------
# Load benchmark results
# ---------------------------------------------------------------------------

def load_results() -> list[dict]:
    rows = []
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        model = data.get("model", "")
        judge_model = data.get("judge_model", "")
        for entry in data.get("results", []):
            trace_id = entry.get("trace_id")
            if not trace_id:
                continue
            rows.append({
                "result_file": path.name,
                "model": model,
                "judge_model": judge_model,
                "id": entry.get("id"),
                "use_case": entry.get("use_case"),
                "governance_profile": entry.get("governance_profile"),
                "score": entry.get("score"),
                "status": entry.get("status"),
                "trace_id": trace_id,
            })
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default="infra/.env", help="Path to .env file")
    parser.add_argument("--delay", type=float, default=0.05, help="Seconds between Langfuse requests (default: 0.05)")
    args = parser.parse_args()

    load_env(args.env_file)

    host = os.environ.get("LANGFUSE_HOST", "").rstrip("/")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")

    if not host or not public_key or not secret_key:
        raise SystemExit(
            "Missing env vars: LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY.\n"
            f"Loaded from: {args.env_file}"
        )

    if "pk-lf-..." in public_key or "sk-lf-..." in secret_key:
        raise SystemExit("Langfuse keys are still placeholders — fill in infra/.env first.")

    headers = auth_header(public_key, secret_key)
    rows = load_results()

    if not rows:
        raise SystemExit(f"No result entries found in {RESULTS_DIR}")

    print(f"Loaded {len(rows)} result entries from {RESULTS_DIR.name}/")

    # Deduplicate trace_ids to minimise Langfuse requests
    unique_trace_ids = list(dict.fromkeys(r["trace_id"] for r in rows))
    print(f"Fetching {len(unique_trace_ids)} unique traces from {host} ...")

    trace_cache: dict[str, dict] = {}

    with httpx.Client() as client:
        for i, trace_id in enumerate(unique_trace_ids, 1):
            if i % 50 == 0:
                print(f"  {i}/{len(unique_trace_ids)} ...")
            trace = fetch_trace(client, host, headers, trace_id)
            obs = fetch_observations(client, host, headers, trace_id) if trace else []
            trace_cache[trace_id] = {
                "latency_ms": round(trace["latency"] * 1000) if trace and trace.get("latency") else None,
                **extract_usage(obs),
            }
            if args.delay:
                time.sleep(args.delay)

    # Join
    enriched: list[dict] = []
    for row in rows:
        extra = trace_cache.get(row["trace_id"], {})
        enriched.append({**row, **extra})

    # Summary: group by (model, judge_model, use_case, governance_profile)
    from collections import defaultdict

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in enriched:
        key = (row["model"], row["judge_model"], row["use_case"], row["governance_profile"])
        groups[key].append(row)

    summary = []
    for (model, judge_model, use_case, profile), group_rows in sorted(groups.items()):
        latencies = [r["latency_ms"] for r in group_rows if r.get("latency_ms") is not None]
        completion_tokens = [r["completion_tokens"] for r in group_rows if r.get("completion_tokens") is not None]
        scores = [r["score"] for r in group_rows if r.get("score") is not None]
        summary.append({
            "model": model,
            "judge_model": judge_model,
            "use_case": use_case,
            "governance_profile": profile,
            "n": len(group_rows),
            "latency_ms_mean": round(sum(latencies) / len(latencies)) if latencies else None,
            "latency_ms_p50": _percentile(latencies, 50),
            "latency_ms_p95": _percentile(latencies, 95),
            "completion_tokens_mean": round(sum(completion_tokens) / len(completion_tokens)) if completion_tokens else None,
            "score_mean": round(sum(scores) / len(scores), 4) if scores else None,
            "n_latency": len(latencies),
            "n_tokens": len(completion_tokens),
        })

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    out_detail = ANALYSIS_DIR / "latency_score.json"
    out_summary = ANALYSIS_DIR / "latency_summary.json"

    out_detail.write_text(json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8")
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    n_with_latency = sum(1 for r in enriched if r.get("latency_ms") is not None)
    n_with_tokens = sum(1 for r in enriched if r.get("completion_tokens") is not None)

    print(f"\nDone.")
    print(f"  {n_with_latency}/{len(enriched)} entries with latency data")
    print(f"  {n_with_tokens}/{len(enriched)} entries with completion token data")
    print(f"  Written: {out_detail.relative_to(ROOT)}")
    print(f"  Written: {out_summary.relative_to(ROOT)}")


def _percentile(values: list[float], p: int) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = (len(sorted_vals) - 1) * p / 100
    lo = int(idx)
    hi = lo + 1
    if hi >= len(sorted_vals):
        return round(sorted_vals[lo])
    frac = idx - lo
    return round(sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo]))


if __name__ == "__main__":
    main()
