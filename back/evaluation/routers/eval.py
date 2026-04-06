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


@router.post("/score", status_code=202)
async def trigger_eval(req: EvalRequest, background_tasks: BackgroundTasks):
    """Déclenche l'évaluation en arrière-plan. Retourne 202 immédiatement."""
    background_tasks.add_task(
        evaluate_trace,
        trace_id=req.trace_id,
        model=req.model,
        question=req.question,
        answer=req.answer,
    )
    return {"status": "evaluating", "trace_id": req.trace_id}


@router.get("/result/{trace_id}", response_model=EvalResult | None)
async def get_result(trace_id: str):
    """Poll ce endpoint après /score pour récupérer le résultat."""
    return await get_eval_result(trace_id)
