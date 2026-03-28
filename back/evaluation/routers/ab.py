from fastapi import APIRouter, Query, Depends
from statistics import mean
from shared.schemas.ab_test import ABTestResponse, ModelABStats
from shared.config import get_evaluation_settings, EvaluationSettings
from services.langfuse_client import get_traces_with_scores

router = APIRouter(prefix="/ab", tags=["ab-test"])


def _compute_stats(model: str, traces: list[dict]) -> ModelABStats:
    model_traces = [t for t in traces if t.get("_model") == model]

    if not model_traces:
        return ModelABStats(
            model=model, sample_size=0,
            avg_latency_ms=0, error_rate=0, avg_tokens=0,
        )

    latencies = [t.get("latency") or 0 for t in model_traces]
    scores = [t["eval_score"] for t in model_traces if t.get("eval_score") is not None]
    errors = [t for t in model_traces if t.get("level") == "ERROR"]
    tokens = [
        t.get("usage", {}).get("total_tokens", 0)
        for t in model_traces if t.get("usage")
    ]

    return ModelABStats(
        model=model,
        sample_size=len(model_traces),
        avg_latency_ms=round(mean(latencies), 1) if latencies else 0,
        avg_eval_score=round(mean(scores), 3) if scores else None,
        error_rate=round(len(errors) / len(model_traces), 4),
        avg_tokens=round(mean(tokens), 1) if tokens else 0,
    )


def _pick_winner(a: ModelABStats, b: ModelABStats) -> str | None:
    if a.sample_size < 3 or b.sample_size < 3:
        return None
    if a.avg_eval_score is not None and b.avg_eval_score is not None:
        return a.model if a.avg_eval_score >= b.avg_eval_score else b.model
    return a.model if a.avg_latency_ms <= b.avg_latency_ms else b.model


@router.get("/results", response_model=ABTestResponse)
async def get_ab_results(
    limit: int = Query(50, ge=10, le=100),
    settings: EvaluationSettings = Depends(get_evaluation_settings),
):
    all_traces = await get_traces_with_scores(limit=limit)
    model_a, model_b = settings.ab_models[0], settings.ab_models[1]
    stats_a = _compute_stats(model_a, all_traces)
    stats_b = _compute_stats(model_b, all_traces)

    return ABTestResponse(
        model_a=stats_a,
        model_b=stats_b,
        window=f"last {limit} traces",
        winner=_pick_winner(stats_a, stats_b),
    )