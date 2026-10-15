# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter

from services import identity_access as ia_service
from shared.schemas.identity_access import CandidateWindow

router = APIRouter(prefix="/identity-access", tags=["identity-access"])


@router.post("/evaluate")
async def evaluate_window(window: CandidateWindow):
    """
    Evaluate a candidate access window (output of the ingestion/deviation
    pipeline, see services/identity_ingestion.py) against the
    identity_access_governance profile. Returns per-criterion verdicts and
    an overall notification_threshold_reached flag.
    """
    return await ia_service.evaluate_candidate_window(window)
