from pydantic import BaseModel


class LLMEvent(BaseModel):
    trace_id: str
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    success: bool