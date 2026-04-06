# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from pydantic import BaseModel


class TraceItem(BaseModel):
    trace_id: str
    model: str
    input_preview: str
    output_preview: str
    latency_ms: float
    eval_score: float | None
    timestamp: str


class TracesResponse(BaseModel):
    traces: list[TraceItem]
    total: int
