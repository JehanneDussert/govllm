# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""Unit tests for services/routing.py (pure functions).

Run inside the evaluation container:  python -m pytest tests/ -q
The effective_judges cases mirror front/src/utils/judges.ts (keep them in sync).
"""

from services.judge_config import DEFAULT_CONFIG
from services.routing import effective_judges, gate_reasons, recommend
from shared.schemas.judge import CriterionConfig, GovernanceProfile, JudgePanel, JudgePanelMember


def _config(panels=(), active_profile="p1"):
    base = DEFAULT_CONFIG.criteria[:3]
    criteria = [
        base[0].model_copy(update={"id": "a", "enabled": True}),
        base[1].model_copy(update={"id": "b", "enabled": True}),
        base[2].model_copy(update={"id": "c", "enabled": False}),
    ]
    profiles = [
        GovernanceProfile(id="p1", label="P1", description="", criteria_config={
            "a": CriterionConfig(enabled=True), "b": CriterionConfig(enabled=True)}),
        GovernanceProfile(id="p2", label="P2", description="", criteria_config={
            "c": CriterionConfig(enabled=True), "a": CriterionConfig(enabled=False)}),
    ]
    return DEFAULT_CONFIG.model_copy(update={
        "criteria": criteria, "profiles": profiles, "panels": list(panels),
        "active_profile_id": active_profile, "judge_model": "G",
    })


def _panel(pid, *members):
    return JudgePanel(profile_id=pid, judges=[
        JudgePanelMember(model=m, assigned_criteria=list(crit)) for m, crit in members])


# ── effective_judges (same 7 cases as the frontend) ──────────────────────────

def test_no_panel_global_judge_only():
    assert effective_judges(_config()) == ["G"]


def test_empty_panel_global_judge_only():
    assert effective_judges(_config([JudgePanel(profile_id="p1", judges=[])])) == ["G"]


def test_full_coverage_members_only():
    cfg = _config([_panel("p1", ("X", "a"), ("Y", "b"))])
    assert sorted(effective_judges(cfg)) == ["X", "Y"]


def test_partial_coverage_adds_global_judge():
    cfg = _config([_panel("p1", ("X", "a"))])
    assert sorted(effective_judges(cfg)) == ["G", "X"]


def test_member_on_inactive_criteria_only_is_not_a_judge():
    cfg = _config([_panel("p1", ("Z", "c"), ("X", "ab"))])
    assert effective_judges(cfg) == ["X"]


def test_non_active_profile_uses_its_criteria_config():
    cfg = _config([_panel("p2", ("Z", "c"))])
    assert effective_judges(cfg, "p2") == ["Z"]


def test_judges_itself():
    assert "G" in effective_judges(_config())
    assert "X" not in effective_judges(_config())


# ── recommend ────────────────────────────────────────────────────────────────

def _m(model, score):
    return {"model": model, "avg_score": score}


POOL = ["A", "J", "B"]


def _ok(*models):
    return {m: [] for m in models}


def test_top_ranked_judge_is_skipped():
    ranked = [_m("J", 0.95), _m("A", 0.90), _m("B", 0.80)]
    r = recommend(ranked, POOL, ["J"], _ok("J", "A", "B"))
    assert r == {"recommended": "A", "reason": None, "excluded_judges": ["J"], "judge_exclusion_fallback": False}


def test_no_judge_in_pool_keeps_the_best_eligible():
    ranked = [_m("A", 0.95), _m("B", 0.80)]
    r = recommend(ranked, ["A", "B"], ["G"], _ok("A", "B"))
    assert r["recommended"] == "A" and r["excluded_judges"] == [] and not r["judge_exclusion_fallback"]


def test_only_judges_eligible_falls_back_with_flag():
    ranked = [_m("J", 0.95), _m("A", 0.60)]
    r = recommend(ranked, ["J", "A"], ["J"], {"J": [], "A": ["composite score 0.600 < threshold 0.80"]})
    assert r["recommended"] == "J" and r["judge_exclusion_fallback"] is True


def test_no_eligible_model_is_an_explicit_refusal():
    ranked = [_m("J", 0.5), _m("A", 0.4)]
    r = recommend(ranked, ["J", "A"], ["J"], {"J": ["x"], "A": ["y"]})
    assert r["recommended"] is None and r["reason"] == "no_eligible_model" and not r["judge_exclusion_fallback"]


def test_no_scores_is_never_a_silent_first_model():
    # Former behaviour: the first configured non-judge model was returned without data.
    ranked = [_m("J", None), _m("A", None)]
    excl = {"J": ["insufficient data: 0 evaluation(s), 5 required"], "A": ["insufficient data: 0 evaluation(s), 5 required"]}
    assert recommend(ranked, ["J", "A"], ["J"], excl)["recommended"] is None


def test_non_judge_eligible_is_recommended_after_a_better_excluded_one():
    ranked = [_m("B", 0.97), _m("J", 0.95), _m("A", 0.85)]
    r = recommend(ranked, ["J", "A", "B"], ["J"], {"B": ["data_privacy: 0.500 < θ 0.70"], "J": [], "A": []})
    assert r["recommended"] == "A" and not r["judge_exclusion_fallback"]


# ── gate_reasons ─────────────────────────────────────────────────────────────

def _g(avg, n, crit=None, crit_n=None):
    return {"avg_score": avg, "sample_size": n, "criteria_scores": crit or {}, "criteria_sample_sizes": crit_n or {}}


def test_gate_eligible():
    m = _g(0.9, 10, {"data_privacy": 0.8}, {"data_privacy": 10})
    assert gate_reasons(m, min_evaluations=5, min_threshold=0.7, criterion_min_scores={"data_privacy": 0.7}) == []


def test_gate_insufficient_data_is_not_a_pass():
    reasons = gate_reasons(_g(0.95, 3), min_evaluations=5, min_threshold=None, criterion_min_scores={})
    assert reasons == ["insufficient data: 3 evaluation(s), 5 required"]
    assert gate_reasons(_g(None, 0), min_evaluations=5, min_threshold=None, criterion_min_scores={})


def test_gate_composite_threshold():
    reasons = gate_reasons(_g(0.6, 10), min_evaluations=5, min_threshold=0.7, criterion_min_scores={})
    assert reasons == ["composite score 0.600 < threshold 0.70"]


def test_gate_criterion_below_theta_and_criterion_without_data():
    m = _g(0.9, 10, {"data_privacy": 0.5, "transparency": None}, {"data_privacy": 10, "transparency": 0})
    reasons = gate_reasons(m, min_evaluations=5, min_threshold=None,
                           criterion_min_scores={"data_privacy": 0.7, "transparency": 0.6})
    assert reasons == ["data_privacy: 0.500 < θ 0.70",
                       "transparency: insufficient data (0 evaluation(s), 5 required)"]


# ── configuration isolation ─────────────────────────────────────────────────

def test_returned_default_config_is_a_copy():
    import asyncio
    from unittest.mock import AsyncMock, patch

    from services import judge_config as jc

    fake = AsyncMock()
    fake.get.return_value = None
    with patch.object(jc, "get_redis", AsyncMock(return_value=fake)):
        cfg = asyncio.run(jc.get_judge_config())
    cfg.profiles[0].criteria_config.clear()
    cfg.criteria[0].weight = 99.0
    assert jc.DEFAULT_CONFIG.profiles[0].criteria_config  # untouched
    assert jc.DEFAULT_CONFIG.criteria[0].weight != 99.0
