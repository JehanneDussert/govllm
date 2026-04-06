# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
from pydantic import BaseModel


# Latency percentile
class LatencyStats(BaseModel):
    p50_ms: float
    p95_ms: float
    p99_ms: float


class ModelMetrics(BaseModel):
    model: str
    request_count: int
    error_rate: float
    latency: LatencyStats
    avg_tokens_per_request: float


class MetricsResponse(BaseModel):
    models: list[ModelMetrics]
    window: str
