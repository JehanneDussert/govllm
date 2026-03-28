from pydantic import BaseModel


class ModelABStats(BaseModel):
    model: str
    sample_size: int
    avg_latency_ms: float
    avg_eval_score: float | None = None
    error_rate: float
    avg_tokens: float


class ABTestResponse(BaseModel):
    model_a: ModelABStats
    model_b: ModelABStats
    window: str
    winner: str | None