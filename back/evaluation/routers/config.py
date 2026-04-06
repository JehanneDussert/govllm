# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter, HTTPException
from shared.schemas.judge import JudgeConfig
from services.judge_config import get_judge_config, save_judge_config, apply_profile

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/judge", response_model=JudgeConfig)
async def get_config():
    return await get_judge_config()


@router.put("/judge", response_model=JudgeConfig)
async def update_config(config: JudgeConfig):
    await save_judge_config(config)
    return config


@router.post("/judge/use-case/{use_case_id}", response_model=JudgeConfig)
async def activate_use_case(use_case_id: str):
    """Switch active use case and auto-apply its default governance profile."""
    config = await get_judge_config()
    uc = next((uc for uc in config.use_cases if uc.id == use_case_id), None)
    if not uc:
        raise HTTPException(
            status_code=404, detail=f"Use case '{use_case_id}' not found"
        )
    config = config.model_copy(update={"active_use_case_id": use_case_id})
    if uc.default_profile_id:
        config = apply_profile(config, uc.default_profile_id)
    await save_judge_config(config)
    return config


@router.post("/judge/profile/{profile_id}", response_model=JudgeConfig)
async def activate_profile(profile_id: str):
    """Apply a governance profile — updates criteria weights and visibility."""
    config = await get_judge_config()
    updated = apply_profile(config, profile_id)
    if updated.active_profile_id != profile_id:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
    await save_judge_config(updated)
    return updated
