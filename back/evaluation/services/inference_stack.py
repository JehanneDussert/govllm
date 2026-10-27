# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""Inference server version, model digests and call parameters, recorded with every judge run.

Single source for the ground-truth service (one row per call) and, through
GET /config/inference-stack, for the host scripts (benchmark, few-shot), which store
it in their result files. Fail-silent: an unreachable Ollama gives None / {}.
"""

import logging

import httpx
from shared.config import get_evaluation_settings
from shared.schemas.inference import InferenceStack

logger = logging.getLogger(__name__)
settings = get_evaluation_settings()


def resolve_digest(model: str, tags: list[dict]) -> str | None:
    """Ollama digest of a LiteLLM model id ('ollama/phi4-mini') from /api/tags entries."""
    name = model.removeprefix("ollama/")
    candidates = {name, name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"}
    for tag in tags:
        if tag.get("name") in candidates or tag.get("model") in candidates:
            return tag.get("digest")
    return None


async def ollama_tags() -> list[dict]:
    """Installed Ollama models (name, digest). [] if Ollama is unreachable."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            r.raise_for_status()
            return r.json().get("models", [])
    except Exception as e:
        logger.warning(f"[inference_stack] Could not read Ollama model digests: {e}")
        return []


async def ollama_version() -> str | None:
    """Version of the Ollama server ('0.32.15'). None if Ollama is unreachable."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/version")
            r.raise_for_status()
            return r.json().get("version")
    except Exception as e:
        logger.warning(f"[inference_stack] Could not read the Ollama version: {e}")
        return None


PARAMS = ("num_thread", "num_ctx")


async def litellm_model_params() -> dict[str, dict[str, int | None]]:
    """Per LiteLLM model id, the Ollama parameters the proxy applies (num_thread, num_ctx).
    {} if LiteLLM is unreachable."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{settings.litellm_base_url.rstrip('/')}/model/info",
                                 headers={"Authorization": f"Bearer {settings.litellm_api_key}"})
            r.raise_for_status()
            return {m["model_name"]: {k: (m.get("litellm_params") or {}).get(k) for k in PARAMS}
                    for m in r.json().get("data", []) if m.get("model_name")}
    except Exception as e:
        logger.warning(f"[inference_stack] Could not read LiteLLM model parameters: {e}")
        return {}


async def get_inference_stack(models: list[str] | None = None) -> InferenceStack:
    """Ollama version, digest and LiteLLM call parameters of each requested model
    (every installed model if None)."""
    tags = await ollama_tags()
    params = await litellm_model_params()
    if models is None:
        # The models LiteLLM serves (its ids), or every installed Ollama model if it is unreachable
        models = list(params) or [f"ollama/{t['name']}" for t in tags if t.get("name")]
    digests = {m: d for m in models if (d := resolve_digest(m, tags))}
    return InferenceStack(ollama_version=await ollama_version(), model_digests=digests,
                          model_params={m: params[m] for m in models if m in params})
