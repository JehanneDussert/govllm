from fastapi import APIRouter
import json
import redis.asyncio as aioredis
from shared.config import get_evaluation_settings
from services.judge_config import get_judge_config

router = APIRouter(prefix="/matrix", tags=["matrix"])
settings = get_evaluation_settings()


async def _get_scores_for_model(r, model: str, use_case_id: str) -> dict:
    key = f"eval:scores:{model}:{use_case_id}"
    raw = await r.get(key)
    
    if not raw:
        return {"avg_score": None, "sample_size": 0, "trend": None, "scores": []}
    
    values = [s["score"] for s in json.loads(raw)]
    avg = round(sum(values) / len(values), 3) if values else None
    trend = None
    
    if len(values) >= 4:
        mid = len(values) // 2
        first_half = sum(values[:mid]) / mid
        second_half = sum(values[mid:]) / (len(values) - mid)
        diff = second_half - first_half
        trend = "up" if diff > 0.05 else "down" if diff < -0.05 else "stable"

    return {"avg_score": avg, "sample_size": len(values), "trend": trend, "scores": values[-10:]}


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
                matrix[use_case.id]["models"][model] = await _get_scores_for_model(r, model, use_case.id)
    
    finally:
        await r.aclose()

    return matrix


@router.get("/routing")
async def get_routing():
    """
    Returns the recommended model for the active profile + use case,
    with scores for all models and the active criteria breakdown.
    """
    config = await get_judge_config()
    models = settings.benchmark_models
    use_case_id = config.active_use_case_id or "general"
    active_criteria = [c for c in config.criteria if c.enabled]

    r = await aioredis.from_url(settings.redis_url, decode_responses=True)
    model_scores = []

    try:
        for model in models:
            data = await _get_scores_for_model(r, model, use_case_id)

            # Per-criterion scores from Redis
            criteria_scores = {}
            for criterion in active_criteria:
                ckey = f"eval:scores:{model}:{use_case_id}:{criterion.id}"
                craw = await r.get(ckey)
                if craw:
                    cvals = [s["score"] for s in json.loads(craw)]
                    criteria_scores[criterion.id] = round(sum(cvals) / len(cvals), 3) if cvals else None
                else:
                    criteria_scores[criterion.id] = None

            model_scores.append({
                "model": model,
                "avg_score": data["avg_score"],
                "sample_size": data["sample_size"],
                "trend": data["trend"],
                "criteria_scores": criteria_scores,
            })
    
    finally:
        await r.aclose()

    # Sort by avg_score descending, None last
    model_scores.sort(key=lambda x: x["avg_score"] if x["avg_score"] is not None else -1, reverse=True)

    recommended = model_scores[0]["model"] if model_scores and model_scores[0]["avg_score"] is not None else models[0]

    return {
        "recommended": recommended,
        "use_case_id": use_case_id,
        "profile_id": config.active_profile_id,
        "models": model_scores,
        "active_criteria": [{"id": c.id, "label": c.label} for c in active_criteria],
    }