# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
import time
import httpx
from typing import AsyncIterator
from shared.config import get_gateway_settings

settings = get_gateway_settings()

TIMEOUT = httpx.Timeout(
    connect=10.0,
    read=300.0,
    write=30.0,
    pool=10.0,
)


async def chat_completion(
    messages: list[dict],
    model: str,
    stream: bool = True,
) -> dict | AsyncIterator[str]:
    payload = {"model": model, "messages": messages, "stream": stream}
    headers = {
        "Authorization": f"Bearer {settings.litellm_api_key}",
        "Content-Type": "application/json",
    }
    if stream:
        return _stream_completion(payload, headers)
    return await _full_completion(payload, headers)


async def _full_completion(payload: dict, headers: dict) -> dict:
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{settings.litellm_base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
    latency_ms = (time.monotonic() - start) * 1000
    return {
        "content": data["choices"][0]["message"]["content"],
        "model": data.get("model", payload["model"]),
        "usage": data.get("usage", {}),
        "latency_ms": round(latency_ms, 2),
    }


async def _stream_completion(payload: dict, headers: dict) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{settings.litellm_base_url}/chat/completions",
            json=payload,
            headers=headers,
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    yield line[6:]
