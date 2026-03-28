import httpx
from shared.config import get_observability_settings

settings = get_observability_settings()


async def query(promql: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{settings.prometheus_url}/api/v1/query",
            params={"query": promql},
        )
        r.raise_for_status()
    return r.json().get("data", {}).get("result", [])


def _scalar(results: list[dict], default: float = 0.0) -> float:
    if not results:
        return default
    try:
        return float(results[0]["value"][1])
    except (KeyError, IndexError, ValueError):
        return default


async def get_model_metrics(model: str, window: str = "24h") -> dict:
    label = f'requested_model="{model}"'

    request_count = _scalar(await query(
        f'sum(litellm_proxy_total_requests_metric_total{{{label}}})'
    ))
    error_count = _scalar(await query(
        f'sum(litellm_deployment_failure_responses_total{{{label}}})'
    ))
    p50 = _scalar(await query(
        f'histogram_quantile(0.50, sum(rate(litellm_request_total_latency_metric_bucket{{{label}}}[{window}])) by (le))'
    ))
    p95 = _scalar(await query(
        f'histogram_quantile(0.95, sum(rate(litellm_request_total_latency_metric_bucket{{{label}}}[{window}])) by (le))'
    ))
    p99 = _scalar(await query(
        f'histogram_quantile(0.99, sum(rate(litellm_request_total_latency_metric_bucket{{{label}}}[{window}])) by (le))'
    ))
    avg_tokens = _scalar(await query(
        f'sum(litellm_total_tokens_metric_total{{{label}}}) / sum(litellm_proxy_total_requests_metric_total{{{label}}})'
    ))

    error_rate = (error_count / request_count) if request_count > 0 else 0.0

    return {
        "model": model,
        "request_count": int(request_count),
        "error_rate": round(error_rate, 4),
        "latency": {
            "p50_ms": round(p50 * 1000, 1),
            "p95_ms": round(p95 * 1000, 1),
            "p99_ms": round(p99 * 1000, 1),
        },
        "avg_tokens_per_request": round(avg_tokens, 1),
    }