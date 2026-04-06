# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from pydantic import BaseModel


class JudgeCriterion(BaseModel):
    id: str
    label: str
    description: str
    enabled: bool = True
    weight: float = 1.0
    tags: list[str] = []


class GovernanceProfile(BaseModel):
    """Reusable compliance template — defines which criteria are active and their weights."""

    id: str
    label: str
    description: str
    criteria_enabled: list[str]  # criterion ids to activate
    criteria_weights: dict[str, float]  # criterion_id → weight override


class UseCase(BaseModel):
    """Usage context — applies a governance profile with additional judge configuration."""

    id: str
    label: str
    description: str
    default_profile_id: str | None = None  # points to a GovernanceProfile
    preferred_model: str | None = None  # default model for this context
    expected_language: str | None = None  # e.g. "fr", "en" — judge penalizes deviations
    min_score_threshold: float = 0  # use-case-level override (stricter than global)
    judge_system_prompt: str | None = None  # context-specific judge prompt extension


class JudgeConfig(BaseModel):
    criteria: list[JudgeCriterion]
    profiles: list[GovernanceProfile] = []
    use_cases: list[UseCase] = []
    active_profile_id: str | None = None
    active_use_case_id: str | None = None
    judge_model: str = "ollama/gemma3:1b"
    latency_threshold_ms: float | None = None
    score_threshold: float | None = None
    error_rate_threshold: float | None = None
    policy_rules: str = ""
