# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter, Query
from shared.schemas.traces import TracesResponse, TraceItem
from services.langfuse_client import get_traces_with_scores

router = APIRouter(prefix="/traces", tags=["traces"])


def _extract_model(trace: dict) -> str:
    metadata = trace.get("metadata") or {}
    for key in ("model", "model_group", "deployment", "deployment_model_name"):
        if metadata.get(key):
            return metadata[key]

    raw_input = trace.get("input")
    if isinstance(raw_input, dict):
        for key in ("model_group", "deployment", "deployment_model_name", "model"):
            if raw_input.get(key):
                return raw_input[key]

    return "unknown"


@router.get("", response_model=TracesResponse)
async def get_traces(
    limit: int = Query(50, ge=1, le=200),
    model: str | None = Query(None),
):
    raw = await get_traces_with_scores(limit=limit)

    traces = []
    for t in raw:
        # Exclude judge's traces (system prompt JSON-only)
        raw_input = t.get("input") or {}
        if isinstance(raw_input, dict):
            messages = raw_input.get("messages", [])
            if any(
                m.get("role") == "system" and "JSON-only" in str(m.get("content", ""))
                for m in messages
            ):
                continue

        detected_model = t.get("_model") or _extract_model(t)
        if model and model not in detected_model:
            continue
        traces.append(
            TraceItem(
                trace_id=t["id"],
                model=detected_model,
                input_preview=str(t.get("input", ""))[:100],
                output_preview=str(t.get("output", ""))[:100],
                latency_ms=t.get("latency") or 0,
                eval_score=t.get("eval_score"),
                timestamp=t.get("timestamp", ""),
            )
        )

    return TracesResponse(traces=traces, total=len(traces))
