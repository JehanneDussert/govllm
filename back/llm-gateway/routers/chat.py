# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from shared.schemas.chat import ChatRequest, ChatResponse
from shared.schemas.events import LLMEvent
from shared.config import get_gateway_settings, GatewaySettings
from services import litellm_client
from services.redis_publisher import publish_event

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=None)
async def chat(
    request: ChatRequest,
    settings: GatewaySettings = Depends(get_gateway_settings),
):
    model = request.model or settings.default_model
    messages = [m.model_dump() for m in request.messages]

    if request.stream:

        async def event_generator():
            chunks = []
            async for chunk in await litellm_client.chat_completion(
                messages=messages, model=model, stream=True
            ):
                chunks.append(chunk)
                yield f"data: {chunk}"
            yield "data: [DONE]"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"X-Model": model},
        )

    result = await litellm_client.chat_completion(
        messages=messages, model=model, stream=False
    )

    # (async) Publish event to evaluation (fire-and-forget)
    event = LLMEvent(
        trace_id=request.session_id or str(uuid.uuid4()),
        model=model,
        input=messages[-1].get("content", ""),
        output=result["content"],
        latency_ms=result["latency_ms"],
        usage=result.get("usage", {}),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    await publish_event(event)

    return ChatResponse(**result)
