# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

import json
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from shared.schemas.chat import ChatRequest, ChatResponse
from shared.schemas.events import LLMEvent
from shared.config import get_gateway_settings, GatewaySettings
from services import litellm_client
from services.redis_publisher import publish_event, get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

JUDGE_CONFIG_KEY = "config:judge"


async def _governance_system_prompt() -> str | None:
    """Read active profile + use case from Redis and return a system prompt string.
    Returns None silently on any error — never blocks the chat path."""
    try:
        r = await get_redis()
        raw = await r.get(JUDGE_CONFIG_KEY)
        if not raw:
            return None
        cfg = json.loads(raw)
        active_profile_id = cfg.get("active_profile_id")
        active_use_case_id = cfg.get("active_use_case_id")
        profile_label = next(
            (
                p["label"]
                for p in cfg.get("profiles", [])
                if p["id"] == active_profile_id
            ),
            active_profile_id,
        )
        uc_label = next(
            (
                u["label"]
                for u in cfg.get("use_cases", [])
                if u["id"] == active_use_case_id
            ),
            active_use_case_id,
        )
        if not profile_label and not uc_label:
            return None
        return (
            f"You are an AI assistant. "
            f"Task type: {uc_label}. "
            f"Governance framework: {profile_label}. "
            f"Respond clearly and accurately."
        )
    except Exception as e:
        logger.warning(f"Could not build governance system prompt: {e}")
        return None


@router.post("", response_model=None)
async def chat(
    request: ChatRequest,
    settings: GatewaySettings = Depends(get_gateway_settings),
):
    model = request.model or settings.default_model
    messages = [m.model_dump() for m in request.messages]

    # Prepend governance system prompt unless the caller already sent one
    if not any(m["role"] == "system" for m in messages):
        system_prompt = await _governance_system_prompt()
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

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
