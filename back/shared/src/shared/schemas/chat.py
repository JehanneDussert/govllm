from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str
    stream: bool = False


class ChatResponse(BaseModel):
    content: str
    model: str
    latency_ms: float