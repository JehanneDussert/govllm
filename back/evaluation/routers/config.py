# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter, HTTPException
from shared.schemas.judge import JudgeConfig
from services.judge_config import (
    DEFAULT_JUDGE_MODEL,
    apply_profile,
    get_judge_config,
    save_judge_config,
)
from services.inference_stack import get_inference_stack
from shared.config import get_evaluation_settings
from shared.schemas.inference import InferenceStack

router = APIRouter(prefix="/config", tags=["config"])
_settings = get_evaluation_settings()


@router.get("/models/available")
async def get_available_models() -> dict:
    return {"models": _settings.benchmark_models}


@router.get("/inference-stack", response_model=InferenceStack)
async def inference_stack(models: str | None = None) -> InferenceStack:
    """Ollama version + model digests (comma-separated LiteLLM ids, or every installed model).

    Read by the benchmark and few-shot scripts, which store it in their result files.
    """
    return await get_inference_stack(models.split(",") if models else None)


@router.get("/judge", response_model=JudgeConfig)
async def get_config():
    return await get_judge_config()


@router.get("/judge/defaults")
async def get_config_defaults() -> dict:
    """Versioned defaults, so clients can show when the saved config drifted from them."""
    return {"judge_model": DEFAULT_JUDGE_MODEL}


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
