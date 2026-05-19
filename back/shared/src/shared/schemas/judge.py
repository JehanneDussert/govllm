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
 
 
class CriterionConfig(BaseModel):
    """Per-criterion configuration stored inside a governance profile."""
    enabled: bool = True
    weight: float = 1.0
    calibration_notes: str = ""
    min_score: float | None = None  # per-criterion compliance gate θᵢ
 
 
class GovernanceProfile(BaseModel):
    """
    Reusable compliance template.
    Stores its own criteria configuration independently of the active JudgeConfig state.
    Applying a profile copies its criteria_config into JudgeConfig.criteria.
    Editing criteria in Settings modifies JudgeConfig.criteria only — profiles stay intact.
    """
    id: str
    label: str
    description: str
    criteria_config: dict[str, CriterionConfig] = {}  # criterion_id → {enabled, weight}
 
 
class UseCase(BaseModel):
    """Usage context — applies a governance profile with additional judge configuration."""
    id: str
    label: str
    description: str
    default_profile_id: str | None = None     # points to a GovernanceProfile
    preferred_model: str | None = None        # default model for this context
    expected_language: str | None = None      # e.g. "fr", "en" — judge penalizes deviations
    min_score_threshold: float | None = None  # use-case-level override (stricter than global)
    judge_system_prompt: str | None = None    # context-specific judge prompt extension
 
 
class JudgePanelMember(BaseModel):
    """One judge in a per-profile panel — persona-aware, criteria-assigned."""
    model: str                        # e.g. "ollama/gemma3:4b"
    persona_prompt: str = ""          # e.g. "You are a CNIL expert, GDPR specialist..."
    assigned_criteria: list[str] = [] # criterion IDs this judge is responsible for


class JudgePanel(BaseModel):
    """Panel of judges configured for a specific governance profile."""
    profile_id: str
    judges: list[JudgePanelMember] = []


class JudgeConfig(BaseModel):
    criteria: list[JudgeCriterion]
    profiles: list[GovernanceProfile] = []
    use_cases: list[UseCase] = []
    panels: list[JudgePanel] = []
    active_profile_id: str | None = None
    active_use_case_id: str | None = None
    judge_model: str = "ollama/gemma3:4b"
    arena_judge_models: list[str] = []  # empty → fall back to settings.benchmark_models
    routing_strategy: str = "best_score"  # best_score | progression | stability | strict
    alpha: float = 0.5  # progression strategy: weight between avg_score and delta_score
    latency_threshold_ms: float | None = None
    score_threshold: float | None = None
    variance_threshold: float = 0.1
    error_rate_threshold: float | None = None
    policy_rules: str = ""

