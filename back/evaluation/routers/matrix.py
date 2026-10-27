# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter
import math
from shared.config import get_evaluation_settings
from services.judge_config import get_judge_config
from services.routing import effective_judges, gate_reasons, recommend
from services.scores import recent_criterion_scores, recent_scores

router = APIRouter(prefix="/matrix", tags=["matrix"])
settings = get_evaluation_settings()


async def _get_scores_for_model(model: str, use_case_id: str) -> dict:
    # Persisted scores (eval_results), served through the rebuildable cache
    values = await recent_scores(model, use_case_id)
    if not values:
        return {
            "avg_score": None,
            "sample_size": 0,
            "trend": None,
            "scores": [],
            "delta_score": None,
            "variance": None,
        }
    avg = round(sum(values) / len(values), 3)

    trend = None
    delta_score = None
    if len(values) >= 4:
        mid = len(values) // 2
        first_half = sum(values[:mid]) / mid
        second_half = sum(values[mid:]) / (len(values) - mid)
        diff = second_half - first_half
        delta_score = round(diff, 4)
        trend = "up" if diff > 0.05 else "down" if diff < -0.05 else "stable"

    variance = None
    if len(values) >= 2:
        mean = sum(values) / len(values)
        variance = round(sum((x - mean) ** 2 for x in values) / len(values), 4)

    return {
        "avg_score": avg,
        "sample_size": len(values),
        "trend": trend,
        "scores": values[-10:],
        "delta_score": delta_score,
        "variance": variance,
    }


@router.get("")
async def get_matrix():
    config = await get_judge_config()
    models = settings.benchmark_models
    matrix = {}
    for use_case in config.use_cases:
        matrix[use_case.id] = {"label": use_case.label, "models": {}}
        for model in models:
            matrix[use_case.id]["models"][model] = await _get_scores_for_model(
                model, use_case.id
            )
    return matrix


@router.get("/routing")
async def get_routing():
    """
    Returns the recommended model for the active profile + use case.

    1. Compliance gate (every strategy): a model is excluded when it has fewer than
       `min_evaluations` evaluations ("insufficient data"), a composite score under
       the use-case threshold, or a criterion under its θ (or without enough
       evaluations). Each model carries `eligible` and `exclusion_reasons`.
    2. Strategy (best_score | progression | stability | strict) ranks the models;
       `strict` now ranks like best_score, since the gate applies everywhere.
    3. The effective judges of the active profile are not recommended (a model never
       generates answers it would judge); if only judges are eligible, the best one
       is returned with judge_exclusion_fallback=true.
    4. No eligible model: recommended=None and reason="no_eligible_model". There is
       no silent fallback.
    """
    config = await get_judge_config()
    models = settings.benchmark_models
    use_case_id = config.active_use_case_id or "general"
    active_criteria = [c for c in config.criteria if c.enabled]
    strategy = config.routing_strategy
    alpha = max(0.0, min(1.0, config.alpha))

    # Use-case composite threshold
    active_uc = next((uc for uc in config.use_cases if uc.id == use_case_id), None)
    min_threshold = active_uc.min_score_threshold if active_uc else None

    # Per-criterion min_score from active profile
    active_profile = next(
        (p for p in config.profiles if p.id == config.active_profile_id), None
    )
    criterion_min_scores: dict[str, float] = {}
    if active_profile:
        for cid, cc in active_profile.criteria_config.items():
            if cc.min_score is not None:
                criterion_min_scores[cid] = cc.min_score

    model_scores = []
    for model in models:
        data = await _get_scores_for_model(model, use_case_id)

        # Per-criterion mean scores (persisted per-criterion results)
        criteria_scores: dict[str, float | None] = {}
        criteria_sample_sizes: dict[str, int] = {}
        for criterion in active_criteria:
            cvals = await recent_criterion_scores(model, use_case_id, criterion.id)
            criteria_scores[criterion.id] = round(sum(cvals) / len(cvals), 3) if cvals else None
            criteria_sample_sizes[criterion.id] = len(cvals)

        model_scores.append(
            {
                "model": model,
                "avg_score": data["avg_score"],
                "sample_size": data["sample_size"],
                "trend": data["trend"],
                "delta_score": data["delta_score"],
                "variance": data["variance"],
                "criteria_scores": criteria_scores,
                "criteria_sample_sizes": criteria_sample_sizes,
            }
        )

    # ── Compliance gate: eliminates, in every strategy ──────────────────────
    # A missing score, or one based on fewer than min_evaluations evaluations, never
    # counts as passing ("insufficient data").
    min_evaluations = config.min_evaluations
    exclusions = {
        m["model"]: gate_reasons(
            m,
            min_evaluations=min_evaluations,
            min_threshold=min_threshold,
            criterion_min_scores=criterion_min_scores,
        )
        for m in model_scores
    }
    judges = effective_judges(config)

    # ── Routing strategy: ranks (eligible models are picked from this order) ──
    def _avg(m: dict) -> float:
        return m["avg_score"] if m["avg_score"] is not None else -1.0

    if strategy == "progression":

        def _progression_key(m: dict) -> float:
            avg = m["avg_score"] if m["avg_score"] is not None else 0.0
            delta = m["delta_score"] if m["delta_score"] is not None else 0.0
            return alpha * avg + (1.0 - alpha) * delta

        model_scores.sort(key=_progression_key, reverse=True)
    elif strategy == "stability":
        model_scores.sort(
            key=lambda m: m["variance"] if m["variance"] is not None else math.inf
        )
    else:  # best_score (default) and strict (the gate now applies to every strategy)
        model_scores.sort(key=_avg, reverse=True)

    routing = recommend(model_scores, models, judges, exclusions)
    for m in model_scores:
        m["eligible"] = not exclusions[m["model"]]
        m["exclusion_reasons"] = exclusions[m["model"]]
        m["meets_threshold"] = m["eligible"]  # kept for the existing UI
        m["is_judge"] = m["model"] in judges
        m.pop("delta_score", None)
        m.pop("variance", None)

    return {
        **routing,
        "strategy": strategy,
        "use_case_id": use_case_id,
        "profile_id": config.active_profile_id,
        "min_threshold": min_threshold,
        "min_evaluations": min_evaluations,
        "criterion_thresholds": criterion_min_scores,
        "models": model_scores,
        "active_criteria": [{"id": c.id, "label": c.label} for c in active_criteria],
    }
