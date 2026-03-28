from pydantic import BaseModel


class TraceItem(BaseModel):
    trace_id: str
    model: str
    input_preview: str
    output_preview: str
    latency_ms: float
    eval_score: float | None
    timestamp: str


class TracesResponse(BaseModel):
    traces: list[TraceItem]
    total: int