# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""
Routing helpers — pure functions, no I/O (used by routers/matrix.py, unit-tested).

effective_judges() mirrors the judge dispatch of jobs/eval_runner.py, and
front/src/utils/judges.ts mirrors it on the client: keep the three in sync.

gate_reasons() is the compliance gate: it lists why a model cannot be routed to
(not enough evaluations, composite score under the use-case threshold, a criterion
under its threshold θᵢ or without enough evaluations). It applies to every routing
strategy: the gate eliminates, the strategy ranks what remains.

recommend() picks the AUTO-routing recommendation among the eligible models while
excluding the effective judges of the active profile, so that a model is never
auto-routed to generate answers it would then judge itself (measured
self-preference for some judges, see docs/benchmark/README.md). If only judges are
eligible, the best one is returned and the response is flagged. If no model is
eligible, nothing is recommended and the response says why: there is no silent
fallback.
"""

from shared.schemas.judge import JudgeConfig

INSUFFICIENT_DATA = "insufficient data"
NO_ELIGIBLE_MODEL = "no_eligible_model"


def effective_judges(config: JudgeConfig, profile_id: str | None = None) -> list[str]:
    """Models that will actually judge an output under `profile_id` (default: active).

    Panel with members: each member judges its assigned criteria among the active
    ones; the global judge_model takes any active criterion no member covers.
    No panel (or an empty one): judge_model judges everything.
    Active criteria: the globally enabled criteria for the active profile (what
    eval_runner uses), or the profile's enabled criteria_config for another profile.
    """
    pid = config.active_profile_id if profile_id is None else profile_id
    if pid == config.active_profile_id:
        active = [c.id for c in config.criteria if c.enabled]
    else:
        profile = next((p for p in config.profiles if p.id == pid), None)
        active = [cid for cid, cc in (profile.criteria_config if profile else {}).items() if cc.enabled]

    panel = next((p for p in config.panels if p.profile_id == pid), None)
    if not panel or not panel.judges:
        return [config.judge_model]

    judges: list[str] = []
    covered: set[str] = set()
    for member in panel.judges:
        mine = [cid for cid in member.assigned_criteria if cid in active]
        if not mine:
            continue
        if member.model not in judges:
            judges.append(member.model)
        covered.update(mine)
    if any(cid not in covered for cid in active) and config.judge_model not in judges:
        judges.append(config.judge_model)
    return judges


def gate_reasons(
    m: dict,
    *,
    min_evaluations: int,
    min_threshold: float | None,
    criterion_min_scores: dict[str, float],
) -> list[str]:
    """Why model `m` is excluded by the compliance gate ([] = eligible).

    m: {"avg_score", "sample_size", "criteria_scores", "criteria_sample_sizes"}.
    A missing score, or one based on fewer than `min_evaluations` evaluations, never
    counts as passing.
    """
    reasons: list[str] = []
    n = m.get("sample_size") or 0
    if n < min_evaluations or m.get("avg_score") is None:
        reasons.append(f"{INSUFFICIENT_DATA}: {n} evaluation(s), {min_evaluations} required")
    elif min_threshold is not None and m["avg_score"] < min_threshold:
        reasons.append(f"composite score {m['avg_score']:.3f} < threshold {min_threshold:.2f}")
    sizes = m.get("criteria_sample_sizes") or {}
    scores = m.get("criteria_scores") or {}
    for cid, theta in sorted(criterion_min_scores.items()):
        n_c = sizes.get(cid, 0)
        s = scores.get(cid)
        if n_c < min_evaluations or s is None:
            reasons.append(f"{cid}: {INSUFFICIENT_DATA} ({n_c} evaluation(s), {min_evaluations} required)")
        elif s < theta:
            reasons.append(f"{cid}: {s:.3f} < θ {theta:.2f}")
    return reasons


def recommend(
    ranked: list[dict],
    configured_models: list[str],
    judges: list[str],
    exclusions: dict[str, list[str]],
) -> dict:
    """AUTO-routing recommendation among the models the gate lets through.

    ranked: model score dicts, already sorted by the routing strategy.
    configured_models: the routing pool (to report which pool models are judges).
    exclusions: gate_reasons() per model ([] = eligible).

    Returns {"recommended", "reason", "excluded_judges", "judge_exclusion_fallback"}:
    - recommended: the best-ranked eligible model that is not a judge of the active
      profile; if only judges are eligible, the best of them, with
      judge_exclusion_fallback = True;
    - no eligible model at all: recommended = None and reason = "no_eligible_model"
      (never a silent fallback; the per-model reasons are in `exclusions`).
    """
    judge_set = set(judges)
    excluded = [m for m in configured_models if m in judge_set]
    eligible = [m for m in ranked if not exclusions.get(m["model"])]
    if not eligible:
        return {"recommended": None, "reason": NO_ELIGIBLE_MODEL,
                "excluded_judges": excluded, "judge_exclusion_fallback": False}
    non_judges = [m for m in eligible if m["model"] not in judge_set]
    if non_judges:
        return {"recommended": non_judges[0]["model"], "reason": None,
                "excluded_judges": excluded, "judge_exclusion_fallback": False}
    return {"recommended": eligible[0]["model"], "reason": None,
            "excluded_judges": excluded, "judge_exclusion_fallback": True}
