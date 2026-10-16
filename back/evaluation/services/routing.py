# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""
Routing helpers — pure functions, no I/O (used by routers/matrix.py, unit-tested).

effective_judges() mirrors the judge dispatch of jobs/eval_runner.py, and
front/src/utils/judges.ts mirrors it on the client: keep the three in sync.

recommend() picks the AUTO-routing recommendation while excluding the effective
judges of the active profile, so that a model is never auto-routed to generate
answers it would then judge itself (measured self-preference for some judges,
see docs/benchmark/README.md). If the exclusion leaves no recommendable model,
the previous behaviour applies and the response is flagged.
"""

from collections.abc import Callable

from shared.schemas.judge import JudgeConfig


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


def recommend(
    ranked: list[dict],
    configured_models: list[str],
    judges: list[str],
    strict: bool,
    passes: Callable[[dict], bool],
) -> dict:
    """AUTO-routing recommendation with the effective judges excluded.

    ranked: model score dicts, already sorted by the routing strategy.
    configured_models: the routing pool in configuration order (fallback when no
        model has scores yet, as before).
    strict: strict strategy — only models passing the thresholds/gates (`passes`)
        can be recommended; otherwise the top-ranked model with a score is.

    Returns {"recommended", "excluded_judges", "judge_exclusion_fallback"}.
    judge_exclusion_fallback is True when excluding the judges left nothing to
    recommend and the unrestricted (previous) recommendation was used instead.
    """

    def pick(scores: list[dict], pool: list[str]) -> str | None:
        if strict:
            eligible = [m for m in scores if passes(m)]
            return eligible[0]["model"] if eligible else None
        if scores and scores[0]["avg_score"] is not None:
            return scores[0]["model"]
        return pool[0] if pool else None

    judge_set = set(judges)
    excluded = [m for m in configured_models if m in judge_set]
    restricted = pick(
        [m for m in ranked if m["model"] not in judge_set],
        [m for m in configured_models if m not in judge_set],
    )
    if restricted is not None:
        return {"recommended": restricted, "excluded_judges": excluded, "judge_exclusion_fallback": False}
    unrestricted = pick(ranked, configured_models)
    return {
        "recommended": unrestricted,
        "excluded_judges": excluded,
        "judge_exclusion_fallback": unrestricted is not None and bool(excluded),
    }
