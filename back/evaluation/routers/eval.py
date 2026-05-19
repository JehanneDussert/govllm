# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from shared.schemas.evaluation import EvalResult
from jobs.eval_runner import evaluate_trace, get_eval_result

router = APIRouter(prefix="/eval", tags=["eval"])


class EvalRequest(BaseModel):
    trace_id: str
    model: str
    question: str
    answer: str
    latency_ms: int | None = None
    started_at: str | None = None


@router.post("/score", status_code=202)
async def trigger_eval(req: EvalRequest, background_tasks: BackgroundTasks):
    """Set evaluation as a background task."""
    background_tasks.add_task(
        evaluate_trace,
        trace_id=req.trace_id,
        model=req.model,
        question=req.question,
        answer=req.answer,
        latency_ms=req.latency_ms,
        started_at=req.started_at,
    )
    return {"status": "evaluating", "trace_id": req.trace_id}


@router.get("/result/{trace_id}", response_model=EvalResult | None)
async def get_result(trace_id: str):
    """Poll this endpoint after /score to get the result."""
    return await get_eval_result(trace_id)
