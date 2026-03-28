from pydantic import BaseModel


class JudgeCriterion(BaseModel):
    id: str
    label: str
    description: str
    enabled: bool = True
    weight: float = 1.0
    tags: list[str] = []


class UseCase(BaseModel):
    id: str
    label: str
    description: str


class GovernanceProfile(BaseModel):
    id: str
    label: str
    description: str
    criteria_weights: dict[str, float]   # criterion_id: weight override
    criteria_enabled: list[str]          # criterion ids to enable


class JudgeConfig(BaseModel):
    criteria: list[JudgeCriterion]
    use_cases: list[UseCase]
    profiles: list[GovernanceProfile] = []
    active_profile_id: str | None = None
    active_use_case_id: str | None = None
    judge_model: str = "ollama/gemma3:1b"
    latency_threshold_ms: float | None = None
    score_threshold: float | None = None
    error_rate_threshold: float | None = None
    policy_rules: str = ""