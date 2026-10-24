# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""A model must not judge its own answers (jobs/eval_runner.py).

Run inside the evaluation container:  python -m pytest tests/ -q
"""

from jobs.eval_runner import same_model, self_judged_criteria


def test_same_model_ignores_provider_prefix_and_case():
    assert same_model("ollama/phi4-mini", "phi4-mini")
    assert same_model("ollama/ministral-3:8b", "OLLAMA/Ministral-3:8b")
    assert not same_model("ollama/mistral:7b", "ollama/ministral-3:8b")
    assert not same_model("ollama/gemma3:4b", "ollama/gemma4:e4b")
    assert not same_model(None, "ollama/phi4-mini")
    assert not same_model("", "")


def test_global_judge_is_the_generator():
    judge_of = {"relevance": "ollama/phi4-mini", "transparency": "ollama/phi4-mini"}
    assert self_judged_criteria(judge_of, "ollama/phi4-mini") == ["relevance", "transparency"]


def test_panel_member_is_the_generator_on_some_criteria():
    judge_of = {
        "data_privacy": "ollama/ministral-3:8b",
        "transparency": "ollama/gemma4:e4b",
        "human_oversight": "ollama/ministral-3:8b",
    }
    assert self_judged_criteria(judge_of, "ollama/ministral-3:8b") == ["data_privacy", "human_oversight"]


def test_no_self_judging():
    judge_of = {"relevance": "ollama/ministral-3:8b"}
    assert self_judged_criteria(judge_of, "ollama/phi4-mini") == []
