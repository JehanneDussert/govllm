# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""Model digest lookup for ground truth runs (services/groundtruth.py, pure function).

Run inside the evaluation container:  python -m pytest tests/ -q
"""

from services.groundtruth import resolve_digest

TAGS = [
    {"name": "phi4-mini:latest", "model": "phi4-mini:latest", "digest": "78fad5d182a7"},
    {"name": "gemma4:e4b", "model": "gemma4:e4b", "digest": "c6eb396dbd59"},
    {"name": "hf.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF:latest", "digest": "c1f3e0033aa7"},
]


def test_implicit_latest_tag():
    assert resolve_digest("ollama/phi4-mini", TAGS) == "78fad5d182a7"


def test_explicit_tag():
    assert resolve_digest("ollama/gemma4:e4b", TAGS) == "c6eb396dbd59"


def test_hf_path_with_tag():
    assert resolve_digest("ollama/hf.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF:latest", TAGS) == "c1f3e0033aa7"


def test_unknown_model():
    assert resolve_digest("ollama/granite4", TAGS) is None
    assert resolve_digest("ollama/gemma4:e4b", []) is None
