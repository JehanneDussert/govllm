# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter, HTTPException, Query

from services import groundtruth as gt_service
from shared.schemas.groundtruth import (
    GroundTruthCase,
    GroundTruthCaseCreate,
    GroundTruthRunResult,
    ValidityReport,
)

router = APIRouter(prefix="/groundtruth", tags=["groundtruth"])


@router.post("/corpus", response_model=GroundTruthCase, status_code=201)
async def add_corpus_case(req: GroundTruthCaseCreate):
    """Add a case to the ground truth corpus."""
    if req.criterion not in gt_service.SUPPORTED_CRITERIA:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported criterion '{req.criterion}'. Supported: {gt_service.SUPPORTED_CRITERIA}",
        )
    try:
        return await gt_service.add_case(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/corpus", response_model=list[GroundTruthCase])
async def get_corpus(
    criterion: str | None = Query(None, description="Filter by criterion ID"),
):
    """List corpus cases, optionally filtered by criterion."""
    return await gt_service.list_cases(criterion)


@router.post("/run/{case_id}", response_model=GroundTruthRunResult)
async def run_groundtruth(
    case_id: str,
    judge_models: list[str] | None = Query(None, description="Override judge model list"),
    question_order: str = Query("original", description="Question presentation order: 'original' or 'reversed'"),
):
    """Submit a corpus case to configured judges in checklist mode. Stores results."""
    try:
        return await gt_service.run_checklist(case_id, judge_models=judge_models, question_order=question_order)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{case_id}")
async def get_case_results(
    case_id: str,
    question_order: str | None = Query(None, description="Filter by question_order"),
) -> list[dict]:
    """All stored judge results for a case, optionally filtered by question_order."""
    return await gt_service.get_case_results(case_id, question_order)


@router.get("/validity", response_model=ValidityReport)
async def get_validity():
    """Validity report: agreement rate per judge × criterion × sub-question."""
    return await gt_service.get_validity()
