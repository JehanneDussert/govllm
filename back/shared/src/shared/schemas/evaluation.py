from pydantic import BaseModel


class CriterionScore(BaseModel):
    criterion_id: str
    score: float
    flag: bool = False
    reason: str = ""


class EvalResult(BaseModel):
    trace_id: str
    model: str
    use_case_id: str | None
    profile_id: str | None = None
    composite_score: float
    criteria_scores: list[CriterionScore]
    evaluated_at: str