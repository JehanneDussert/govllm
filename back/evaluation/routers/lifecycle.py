# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter, HTTPException, Query
from db.database import get_pool
from db.models import (
    ModelLifecycleStatus,
    LifecycleTransition,
    LifecycleHistory,
    SasRequest,
    SasResult,
    SasLmsysResult,
)
from services.lifecycle import get_status, set_zone, run_sas, run_sas_lmsys
from shared.config import get_evaluation_settings

router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])
settings = get_evaluation_settings()


@router.get("/status", response_model=list[ModelLifecycleStatus])
async def lifecycle_status():
    """Current zone for every configured model."""
    return await get_status(settings.benchmark_models)


@router.post("/validate/{model}", response_model=LifecycleTransition)
async def validate_model(model: str, note: str | None = Query(None)):
    """Human validation — promotes model from 'validation' zone to 'production'."""
    statuses = await get_status([model])
    current_zone = statuses[0].zone if statuses else "test"
    if current_zone not in ("validation", "quarantine", "test"):
        raise HTTPException(
            status_code=400,
            detail=f"Model is already in '{current_zone}' — validate is a no-op.",
        )
    return await set_zone(model, "production", operator="human", note=note or "Human validation")


@router.post("/quarantine/{model}", response_model=LifecycleTransition)
async def quarantine_model(model: str, note: str | None = Query(None), criterion_id: str | None = Query(None)):
    """Manual quarantine — suspends the model from production routing."""
    return await set_zone(
        model, "quarantine", operator="human",
        criterion_id=criterion_id,
        note=note or "Manual quarantine",
    )


@router.post("/sas", response_model=SasResult)
async def sas(req: SasRequest):
    """
    Sas de qualification — scores the model against Redis eval history,
    compares to score_threshold and advances or quarantines accordingly.
    """
    if req.model not in settings.benchmark_models:
        raise HTTPException(status_code=404, detail=f"Model '{req.model}' not in benchmark_models.")
    return await run_sas(req.model, req.profile_id)


@router.post("/sas/lmsys", response_model=SasLmsysResult)
async def sas_lmsys(req: SasRequest, n_prompts: int = Query(10, ge=1, le=20)):
    """
    LMSYS-style SAS — runs the model on a curated governance corpus
    (data/lmsys_regulatory_subset.json if available, built-in fallback otherwise),
    evaluates each response with the judge, returns per-criterion breakdown.
    """
    if req.model not in settings.benchmark_models:
        raise HTTPException(status_code=404, detail=f"Model '{req.model}' not in benchmark_models.")
    return await run_sas_lmsys(req.model, req.profile_id, n_prompts)


@router.get("/history", response_model=LifecycleHistory)
async def lifecycle_history(
    model: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Full transition history, optionally filtered to one model."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        where = "WHERE model = $2" if model else ""
        params = [limit, model] if model else [limit]
        rows = await conn.fetch(
            f"""
            SELECT id, model, zone, score, criterion_id, profile_id, operator, note, created_at
            FROM model_lifecycle
            {where}
            ORDER BY created_at DESC
            LIMIT $1
            """,
            *params,
        )
    return LifecycleHistory(
        model=model,
        transitions=[LifecycleTransition(**dict(r)) for r in rows],
    )
