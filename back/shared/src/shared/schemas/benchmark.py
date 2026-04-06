# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from pydantic import BaseModel


class ModelBenchmarkStats(BaseModel):
    model: str
    sample_size: int
    avg_latency_ms: float
    avg_eval_score: float | None = None
    error_rate: float
    avg_tokens: float


class BenchmarkResponse(BaseModel):
    model_a: ModelBenchmarkStats
    model_b: ModelBenchmarkStats
    window: str
    winner: str | None
