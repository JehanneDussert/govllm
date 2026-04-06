# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter, Query, Depends
from shared.schemas.metrics import MetricsResponse, ModelMetrics, LatencyStats
from shared.config import get_observability_settings, ObservabilitySettings
from services import prometheus_client

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse)
async def get_metrics(
    window: str = Query("1h", pattern="^[0-9]+[smhd]$"),
    settings: ObservabilitySettings = Depends(get_observability_settings),
):
    results = []
    models = settings.benchmark_models or []
    for model in models:
        try:
            raw = await prometheus_client.get_model_metrics(model=model, window=window)
            results.append(
                ModelMetrics(
                    model=raw["model"],
                    request_count=raw["request_count"],
                    error_rate=raw["error_rate"],
                    latency=LatencyStats(**raw["latency"]),
                    avg_tokens_per_request=raw["avg_tokens_per_request"],
                )
            )
        except Exception:
            results.append(
                ModelMetrics(
                    model=model,
                    request_count=0,
                    error_rate=0.0,
                    latency=LatencyStats(p50_ms=0, p95_ms=0, p99_ms=0),
                    avg_tokens_per_request=0.0,
                )
            )
    return MetricsResponse(models=results, window=window)
