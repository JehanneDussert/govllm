# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""Regression test: `judge_reliability.py --models paper` must reproduce the arXiv v1 level-2 figures.

The benchmark directory now also holds the 8x8 extension; level 2 (reason consistency)
must only read the files whose generator AND judge are in the selected model set.

Run from the repository root:
    uv run --no-project --with pytest python -m pytest scripts/tests -q
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import judge_reliability as jr  # noqa: E402
from model_registry import select  # noqa: E402


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch):
    # The script uses paths relative to the repository root
    monkeypatch.chdir(ROOT)


def _level2(models: str):
    jr.JUDGES = [j for j in select(models)]
    rows = jr.load_benchmark()
    return rows, jr.compute_consistency(rows)


def test_paper_models_reproduce_v1():
    rows, consistency = _level2("paper")
    per_judge = consistency["per_judge"]
    # Exact v1 values (docs/benchmark/analysis/judge_reliability.json as published):
    # 864 scored criteria per judge, 859 for mistral:7b (5 failed entries in the v1 runs)
    expected_totals = {"phi4-mini": 864, "qwen3-1.7b": 864, "gemma3-4b": 864, "mistral-7b": 859}
    for judge, total in expected_totals.items():
        assert per_judge[judge]["total_scores"] == total, judge
    assert per_judge["phi4-mini"]["consistency_rate"] == pytest.approx(0.916, abs=5e-4)
    assert {r["gen"] for r in rows} <= set(jr.JUDGES)


def test_all_models_unchanged():
    # 8 generators: 1,728 scored criteria per judge at most (some entries failed)
    _, consistency = _level2("all")
    per_judge = consistency["per_judge"]
    assert per_judge["phi4-mini"]["total_scores"] == 1728
    assert per_judge["phi4-mini"]["consistency_rate"] == pytest.approx(0.898, abs=5e-4)
