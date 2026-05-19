# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

import logging
import redis.asyncio as aioredis
from shared.config import get_gateway_settings
from shared.schemas.events import LLMEvent

logger = logging.getLogger(__name__)
settings = get_gateway_settings()

CHANNEL = "llm.events"

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def publish_event(event: LLMEvent) -> None:
    """
    Publish an LLMEvent to the Redis llm.events channel.
    The evaluation service consumes it to score the response.
    Fails silently — Redis is non-critical for the chat path.
    """
    try:
        r = await get_redis()
        await r.publish(CHANNEL, event.model_dump_json())
    except Exception as e:
        logger.warning(f"Redis publish failed (non-critical): {e}")


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
