# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


# ── Input ─────────────────────────────────────────────────────

class ArenaRunRequest(BaseModel):
    """Payload to trigger a new Arena session."""
    prompt: str
    profile_id: str
    use_case_id: str | None = None
    # If not provided, all models in benchmark_models are used as judges
    judge_models: list[str] | None = None


class ArenaVoteRequest(BaseModel):
    session_id: UUID
    chosen_model: str  # model_name the user preferred


# ── Stored entities ───────────────────────────────────────────

class ArenaCriterionScore(BaseModel):
    criterion_id: str
    score: float
    flag: bool = False
    reason: str | None = None


class ArenaJudge(BaseModel):
    judge_id: UUID
    model_name: str
    model_family: str
    assigned_criteria: list[str]
    global_score: float | None
    latency_ms: int | None
    scores: list[ArenaCriterionScore] = []


class ArenaSession(BaseModel):
    session_id: UUID
    prompt: str
    profile_id: str
    use_case_id: str | None
    sigma: float | None          # inter-judge variance
    user_vote: str | None
    created_at: datetime
    judges: list[ArenaJudge] = []


# ── API responses ─────────────────────────────────────────────

class ArenaRunResponse(BaseModel):
    session_id: UUID
    prompt: str
    profile_id: str
    sigma: float | None
    judges: list[ArenaJudge]
    # Pre-computed for the frontend
    criteria_labels: dict[str, str]   # criterion_id → label


class VariancePoint(BaseModel):
    """One data point for the variance explorer time series."""
    session_id: UUID
    created_at: datetime
    sigma: float
    profile_id: str
    prompt_preview: str   # first 80 chars


class VarianceHistory(BaseModel):
    points: list[VariancePoint]
    profile_id: str | None
    window_days: int


class BiasMatrixCell(BaseModel):
    judge_family: str
    evaluated_model: str
    mean_score: float
    sample_size: int
    is_self_preference: bool   # judge_family matches evaluated model family


class BiasMatrix(BaseModel):
    cells: list[BiasMatrixCell]
    criterion_id: str | None   # None = aggregated across all criteria
    profile_id: str | None
    judge_families: list[str]
    evaluated_models: list[str]