from fastapi import APIRouter, Query, Depends
from statistics import mean
from shared.config import get_evaluation_settings, EvaluationSettings
from services.langfuse_client import get_traces_with_scores

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


def _compute_stats(model: str, traces: list[dict]) -> dict:
    model_traces = [t for t in traces if t.get("_model") == model]
    if not model_traces:
        return {
            "model": model, "sample_size": 0,
            "avg_latency_ms": 0, "error_rate": 0,
            "avg_tokens": 0, "avg_eval_score": None,
        }
    latencies = [t.get("latency") or 0 for t in model_traces]
    scores = [t["eval_score"] for t in model_traces if t.get("eval_score") is not None]
    errors = [t for t in model_traces if t.get("level") == "ERROR"]
    tokens = [t.get("usage", {}).get("total_tokens", 0) for t in model_traces if t.get("usage")]
    return {
        "model": model,
        "sample_size": len(model_traces),
        "avg_latency_ms": round(mean(latencies), 1) if latencies else 0,
        "avg_eval_score": round(mean(scores), 3) if scores else None,
        "error_rate": round(len(errors) / len(model_traces), 4),
        "avg_tokens": round(mean(tokens), 1) if tokens else 0,
    }


def _pick_winner(models_stats: list[dict]) -> str | None:
    eligible = [m for m in models_stats if m["sample_size"] >= 3]
    if not eligible:
        return None
    with_scores = [m for m in eligible if m["avg_eval_score"] is not None]
    if with_scores:
        return max(with_scores, key=lambda m: m["avg_eval_score"])["model"]
    return min(eligible, key=lambda m: m["avg_latency_ms"])["model"]


@router.get("/results")
async def get_benchmark_results(
    limit: int = Query(50, ge=10, le=200),
    settings: EvaluationSettings = Depends(get_evaluation_settings),
):
    all_traces = await get_traces_with_scores(limit=limit)
    models_stats = [_compute_stats(m, all_traces) for m in settings.benchmark_models]
    winner = _pick_winner(models_stats)
    return {
        "models": models_stats,
        "winner": winner,
        "window": f"last {limit} traces",
    }