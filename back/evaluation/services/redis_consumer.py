# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

import asyncio
import json
import logging
import redis.asyncio as aioredis
from shared.config import get_evaluation_settings
from shared.schemas.events import LLMEvent

logger = logging.getLogger(__name__)
settings = get_evaluation_settings()

CHANNEL = "llm.events"


async def consume_events(handler) -> None:
    """
    Subscribes to the Redis channel `llm.events` and calls `handler(event)`
    for each message received. Automatic reconnection in the event of an error.
    """
    while True:
        try:
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(CHANNEL)
            logger.info(f"Subscribed to Redis channel: {CHANNEL}")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    event = LLMEvent(**data)
                    await handler(event)
                except Exception as e:
                    logger.error(f"Event handling error: {e}")

        except Exception as e:
            logger.error(f"Redis consumer error, reconnecting in 5s: {e}")
            await asyncio.sleep(5)
