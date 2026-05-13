#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Compare qwen3:1.7b no_think vs thinking mode on ground-truth cases.

Calls LiteLLM directly — does NOT write to the database.
Results are for empirical validation only (Jayarao et al. 2025).

Usage:
    python test_thinking_mode.py [--criterion transparency]

Env vars:
    EVALUATION_URL  evaluation service base URL (default: http://localhost:8003)
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, "/app")  # allow imports from the evaluation service

import httpx

# Import the helpers directly from the service — no DB calls at import time
from services.groundtruth import (
    _build_checklist_prompt,
    _compute_agreement,
    _extract_checklist_json,
    settings,
)

MODEL          = "ollama/qwen3:1.7b"
EVALUATION_URL = os.environ.get("EVALUATION_URL", "http://localhost:8003")


async def _call_litellm(prompt: str, no_think: bool) -> tuple[dict[str, bool] | None, str | None]:
    suffix = " /no_think" if no_think else ""
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            r = await client.post(
                f"{settings.litellm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.litellm_api_key}"},
                json={
                    "model": MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a regulatory compliance evaluator. "
                                "Answer binary checklist questions about AI responses. "
                                "Always respond with valid JSON only. Never add markdown."
                            ),
                        },
                        {"role": "user", "content": prompt + suffix},
                    ],
                    "stream": False,
                    "temperature": 0.0,
                },
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  [ERROR] {e}", flush=True)
            return None, None

    parsed = _extract_checklist_json(raw)
    if not parsed:
        return None, None
    answers = {k: bool(v) for k, v in parsed.get("answers", {}).items() if isinstance(k, str)}
    reason  = str(parsed.get("reason") or "")[:500] or None
    return answers, reason


async def main(criterion: str | None) -> None:
    async with httpx.AsyncClient(base_url=EVALUATION_URL, timeout=30) as client:
        url = "/groundtruth/corpus" + (f"?criterion={criterion}" if criterion else "")
        r = await client.get(url)
        r.raise_for_status()
        cases = r.json()

    if not cases:
        print("No cases found.")
        return

    crit_label = criterion or "all"
    print(f"\n{len(cases)} case(s) [{crit_label}] — qwen3:1.7b  no_think vs thinking\n")
    print("Running… (2 LLM calls per case, results NOT persisted)\n")

    rows: list[tuple[str, str, float, float, dict, dict, str | None, str | None]] = []

    for case in cases:
        case_id  = case["id"]
        crit     = case["criterion"]
        expected = case["expected_answers"]
        preview  = case["prompt"][:55]

        print(f"  [{crit}] {preview}…", flush=True)

        checklist_prompt = _build_checklist_prompt(crit, case["prompt"], case["response"])

        print(f"    no_think … ", end="", flush=True)
        ans_nt, rsn_nt = await _call_litellm(checklist_prompt, no_think=True)
        agr_nt = _compute_agreement(ans_nt or {}, expected)
        print(f"{agr_nt:.2f}", flush=True)

        print(f"    thinking … ", end="", flush=True)
        ans_th, rsn_th = await _call_litellm(checklist_prompt, no_think=False)
        agr_th = _compute_agreement(ans_th or {}, expected)
        print(f"{agr_th:.2f}", flush=True)

        rows.append((case_id, crit, agr_nt, agr_th, ans_nt or {}, ans_th or {}, rsn_nt, rsn_th))

    # ── Per-case comparison ────────────────────────────────────────────────────
    print("\n" + "=" * 92)
    print(f"COMPARISON — {MODEL}  no_think vs thinking  [{crit_label}]")
    print("=" * 92)
    col = "{:<38}  {:<22}  {:>10}  {:>10}  {:>8}"
    print(col.format("case_id", "criterion", "no_think", "thinking", "delta"))
    print("-" * 92)

    by_crit: dict[str, list[tuple[float, float]]] = {}
    for case_id, crit, nt, th, *_ in rows:
        delta = th - nt
        sym   = "▲" if delta > 0 else ("▼" if delta < 0 else "=")
        print(col.format(case_id[:36], crit, f"{nt:.2f}", f"{th:.2f}", f"{sym} {delta:+.2f}"))
        by_crit.setdefault(crit, []).append((nt, th))

    # ── Per-criterion summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY BY CRITERION")
    print("=" * 60)
    print(f"{'criterion':<22}  {'no_think':>10}  {'thinking':>10}  {'delta':>8}  {'n':>4}")
    print("-" * 60)

    for crit in sorted(by_crit):
        pairs = by_crit[crit]
        mean_nt = sum(p[0] for p in pairs) / len(pairs)
        mean_th = sum(p[1] for p in pairs) / len(pairs)
        delta   = mean_th - mean_nt
        sym     = "▲" if delta > 0 else ("▼" if delta < 0 else "=")
        print(f"{crit:<22}  {mean_nt:>10.3f}  {mean_th:>10.3f}  {sym}{delta:>+7.3f}  {len(pairs):>4}")

    # ── Global conclusion ──────────────────────────────────────────────────────
    all_nt = [r[2] for r in rows]
    all_th = [r[3] for r in rows]
    g_nt   = sum(all_nt) / len(all_nt)
    g_th   = sum(all_th) / len(all_th)
    g_d    = g_th - g_nt

    print("-" * 60)
    print(f"{'GLOBAL':<22}  {g_nt:>10.3f}  {g_th:>10.3f}  {'▲' if g_d > 0 else '▼' if g_d < 0 else '='}{g_d:>+7.3f}  {len(rows):>4}")
    print()

    verdict = (
        f"thinking mode {'IMPROVES' if g_d > 0 else 'DEGRADES'} agreement "
        f"by {abs(g_d)*100:.1f} pp ({g_d:+.3f}) on {len(rows)} cases."
    )
    print(f"Conclusion: {verdict}")
    if g_d > 0.05:
        print("→ Consider moving ollama/qwen3:1.7b from _NO_THINK_MODELS to _THINK_MODELS.")
    elif g_d < -0.05:
        print("→ Keep ollama/qwen3:1.7b in _NO_THINK_MODELS (thinking degrades accuracy).")
    else:
        print("→ Effect size < 5 pp — not conclusive. Extend corpus before deciding.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--criterion", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.criterion))
