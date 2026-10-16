# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""Unit tests for services/routing.py (pure functions).

Run inside the evaluation container:  python -m pytest tests/ -q
The effective_judges cases mirror front/src/utils/judges.ts (keep them in sync).
"""

from services.judge_config import DEFAULT_CONFIG
from services.routing import effective_judges, recommend
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
ALWAYS = lambda m: True  # noqa: E731


def test_top_ranked_judge_is_skipped():
    ranked = [_m("J", 0.95), _m("A", 0.90), _m("B", 0.80)]
    r = recommend(ranked, POOL, ["J"], strict=False, passes=ALWAYS)
    assert r == {"recommended": "A", "excluded_judges": ["J"], "judge_exclusion_fallback": False}


def test_no_judge_in_pool_keeps_previous_behaviour():
    ranked = [_m("A", 0.95), _m("B", 0.80)]
    r = recommend(ranked, ["A", "B"], ["G"], strict=False, passes=ALWAYS)
    assert r["recommended"] == "A" and r["excluded_judges"] == [] and not r["judge_exclusion_fallback"]


def test_all_models_are_judges_falls_back_with_flag():
    ranked = [_m("J", 0.95), _m("K", 0.90)]
    r = recommend(ranked, ["J", "K"], ["J", "K"], strict=False, passes=ALWAYS)
    assert r["recommended"] == "J" and r["judge_exclusion_fallback"] is True


def test_no_scores_uses_first_configured_non_judge():
    ranked = [_m("J", None), _m("A", None), _m("B", None)]
    r = recommend(ranked, ["J", "A", "B"], ["J"], strict=False, passes=ALWAYS)
    assert r["recommended"] == "A" and not r["judge_exclusion_fallback"]


def test_strict_only_judge_eligible_falls_back_with_flag():
    ranked = [_m("J", 0.95), _m("A", 0.60)]
    r = recommend(ranked, ["J", "A"], ["J"], strict=True, passes=lambda m: m["avg_score"] >= 0.8)
    assert r["recommended"] == "J" and r["judge_exclusion_fallback"] is True


def test_strict_nothing_eligible_returns_none_without_flag():
    ranked = [_m("J", 0.5), _m("A", 0.4)]
    r = recommend(ranked, ["J", "A"], ["J"], strict=True, passes=lambda m: m["avg_score"] >= 0.8)
    assert r["recommended"] is None and r["judge_exclusion_fallback"] is False


def test_strict_non_judge_eligible_is_recommended():
    ranked = [_m("J", 0.95), _m("A", 0.85)]
    r = recommend(ranked, ["J", "A"], ["J"], strict=True, passes=lambda m: m["avg_score"] >= 0.8)
    assert r["recommended"] == "A" and not r["judge_exclusion_fallback"]
