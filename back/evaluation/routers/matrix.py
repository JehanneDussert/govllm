# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter
import json
import math
import redis.asyncio as aioredis
from shared.config import get_evaluation_settings
from services.judge_config import get_judge_config

router = APIRouter(prefix="/matrix", tags=["matrix"])
settings = get_evaluation_settings()


async def _get_scores_for_model(r, model: str, use_case_id: str) -> dict:
    key = f"eval:scores:{model}:{use_case_id}"
    raw = await r.get(key)
    if not raw:
        return {
            "avg_score": None,
            "sample_size": 0,
            "trend": None,
            "scores": [],
            "delta_score": None,
            "variance": None,
        }
    values = [s["score"] for s in json.loads(raw)]
    avg = round(sum(values) / len(values), 3) if values else None

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
    r = await aioredis.from_url(settings.redis_url, decode_responses=True)
    matrix = {}
    try:
        for use_case in config.use_cases:
            matrix[use_case.id] = {"label": use_case.label, "models": {}}
            for model in models:
                matrix[use_case.id]["models"][model] = await _get_scores_for_model(
                    r, model, use_case.id
                )
    finally:
        await r.aclose()
    return matrix


@router.get("/routing")
async def get_routing():
    """
    Returns the recommended model for the active profile + use case.
    Routing strategy is read from config: best_score | progression | stability | strict.
    Per-criterion min_score thresholds from the active profile act as a compliance gate.
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

    r = await aioredis.from_url(settings.redis_url, decode_responses=True)
    model_scores = []

    try:
        for model in models:
            data = await _get_scores_for_model(r, model, use_case_id)

            # Per-criterion composite scores
            criteria_scores: dict[str, float | None] = {}
            for criterion in active_criteria:
                ckey = f"eval:scores:{model}:{use_case_id}:{criterion.id}"
                craw = await r.get(ckey)
                if craw:
                    cvals = [s["score"] for s in json.loads(craw)]
                    criteria_scores[criterion.id] = (
                        round(sum(cvals) / len(cvals), 3) if cvals else None
                    )
                else:
                    criteria_scores[criterion.id] = None

            model_scores.append(
                {
                    "model": model,
                    "avg_score": data["avg_score"],
                    "sample_size": data["sample_size"],
                    "trend": data["trend"],
                    "delta_score": data["delta_score"],
                    "variance": data["variance"],
                    "criteria_scores": criteria_scores,
                }
            )
    finally:
        await r.aclose()

    # ── Per-criterion compliance gate ────────────────────────────────────────
    def _passes_criterion_gate(m: dict) -> bool:
        for cid, min_s in criterion_min_scores.items():
            crit_score = m["criteria_scores"].get(cid)
            if crit_score is not None and crit_score < min_s:
                return False
        return True

    def _passes_global_threshold(m: dict) -> bool:
        if min_threshold is None:
            return True
        return m["avg_score"] is not None and m["avg_score"] >= min_threshold

    # ── Apply routing strategy ───────────────────────────────────────────────
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

    elif strategy == "strict":
        eligible = [
            m for m in model_scores
            if _passes_global_threshold(m) and _passes_criterion_gate(m)
        ]
        eligible.sort(
            key=lambda m: m["avg_score"] if m["avg_score"] is not None else -1.0,
            reverse=True,
        )
        # Remaining models sorted by avg_score for display
        model_scores.sort(
            key=lambda m: m["avg_score"] if m["avg_score"] is not None else -1.0,
            reverse=True,
        )
        recommended = eligible[0]["model"] if eligible else None
        for m in model_scores:
            m["meets_threshold"] = _passes_global_threshold(m) and _passes_criterion_gate(m)
        # Remove internal fields before returning
        for m in model_scores:
            m.pop("delta_score", None)
            m.pop("variance", None)
        return {
            "recommended": recommended,
            "use_case_id": use_case_id,
            "profile_id": config.active_profile_id,
            "min_threshold": min_threshold,
            "models": model_scores,
            "active_criteria": [{"id": c.id, "label": c.label} for c in active_criteria],
        }

    else:  # best_score (default)
        model_scores.sort(
            key=lambda m: m["avg_score"] if m["avg_score"] is not None else -1.0,
            reverse=True,
        )

    # ── Flag threshold compliance ─────────────────────────────────────────────
    for m in model_scores:
        m["meets_threshold"] = (
            _passes_global_threshold(m) and _passes_criterion_gate(m)
            if m["avg_score"] is not None
            else None
        )

    recommended = (
        model_scores[0]["model"]
        if model_scores and model_scores[0]["avg_score"] is not None
        else (models[0] if models else None)
    )

    # Remove internal fields before returning
    for m in model_scores:
        m.pop("delta_score", None)
        m.pop("variance", None)

    return {
        "recommended": recommended,
        "use_case_id": use_case_id,
        "profile_id": config.active_profile_id,
        "min_threshold": min_threshold,
        "models": model_scores,
        "active_criteria": [{"id": c.id, "label": c.label} for c in active_criteria],
    }
