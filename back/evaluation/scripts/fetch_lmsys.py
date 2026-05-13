#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Standalone script — fetch a regulatory subset of LMSYS-Chat-1M from HuggingFace.

Usage:
    uv run python back/evaluation/scripts/fetch_lmsys.py [--max-rows N] [--out PATH]

Requires:
    pip install datasets huggingface-hub
    HF_TOKEN set in env or .env file (for gated LMSYS-1M dataset)

Output:
    data/lmsys_regulatory_subset.json  — list of {prompt, response, topics}
    Each entry has:
        prompt   : first user turn
        response : first assistant turn
        topics   : list of matched governance keywords

The JSON file is read by services/lifecycle.py::run_sas_lmsys() during LMSYS SAS runs.
"""

import argparse
import json
import os
import pathlib
import sys

GOVERNANCE_KEYWORDS = [
    "personal data", "privacy", "transparency", "consent",
    "security", "manipulation", "gdpr", "confidential",
    "sensitive", "personal information", "data protection",
    "inject", "override", "ignore instructions", "jailbreak",
    "medical advice", "legal advice", "financial advice",
    "bias", "discrimination", "oversight",
]

DEFAULT_MAX_ROWS = 50_000   # rows to scan from the dataset
DEFAULT_MIN_MATCHES = 2     # keyword hits required to keep a conversation
DEFAULT_MAX_OUTPUT = 200    # max conversations in output file

_OUTPUT_DEFAULT = pathlib.Path(__file__).parent.parent / "data" / "lmsys_regulatory_subset.json"


def _load_token() -> str | None:
    token = os.environ.get("HF_TOKEN")
    if token:
        return token
    # Try to load from .env in infra/
    env_path = pathlib.Path(__file__).parents[4] / "infra" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("HF_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _keywords_in(text: str) -> list[str]:
    text_lower = text.lower()
    return [kw for kw in GOVERNANCE_KEYWORDS if kw in text_lower]


def main():
    parser = argparse.ArgumentParser(description="Fetch LMSYS governance subset")
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS,
                        help=f"Rows to scan (default {DEFAULT_MAX_ROWS})")
    parser.add_argument("--max-output", type=int, default=DEFAULT_MAX_OUTPUT,
                        help=f"Max conversations to keep (default {DEFAULT_MAX_OUTPUT})")
    parser.add_argument("--min-matches", type=int, default=DEFAULT_MIN_MATCHES,
                        help=f"Min keyword hits to include a conversation (default {DEFAULT_MIN_MATCHES})")
    parser.add_argument("--out", type=pathlib.Path, default=_OUTPUT_DEFAULT,
                        help=f"Output path (default {_OUTPUT_DEFAULT})")
    args = parser.parse_args()

    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: 'datasets' package not installed. Run: pip install datasets huggingface-hub", file=sys.stderr)
        sys.exit(1)

    token = _load_token()
    if not token:
        print("WARNING: HF_TOKEN not found in env or infra/.env — dataset may be inaccessible if gated.")

    print(f"Loading lmsys/lmsys-chat-1m (streaming, scanning up to {args.max_rows} rows)…")
    try:
        ds = load_dataset(
            "lmsys/lmsys-chat-1m",
            split="train",
            streaming=True,
            token=token,
        )
    except Exception as e:
        print(f"ERROR: Could not load dataset: {e}", file=sys.stderr)
        sys.exit(1)

    results: list[dict] = []
    scanned = 0

    for row in ds:
        if scanned >= args.max_rows or len(results) >= args.max_output:
            break
        scanned += 1

        conversation = row.get("conversation", [])
        if not conversation:
            continue

        # Extract first user turn and first assistant turn
        prompt = next((m["content"] for m in conversation if m.get("role") == "user"), None)
        response = next((m["content"] for m in conversation if m.get("role") == "assistant"), None)
        if not prompt or not response:
            continue

        matched = _keywords_in(prompt + " " + response)
        if len(matched) < args.min_matches:
            continue

        results.append({
            "prompt": prompt[:2000],        # cap to avoid very long prompts
            "response": response[:2000],
            "topics": list(dict.fromkeys(matched)),  # deduplicated, order preserved
        })

        if len(results) % 20 == 0:
            print(f"  Kept {len(results)} conversations (scanned {scanned})…")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone. {len(results)} conversations saved to {args.out}")
    print(f"Scanned {scanned} rows from LMSYS-Chat-1M.")


if __name__ == "__main__":
    main()
