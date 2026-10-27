# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from pydantic import BaseModel


class InferenceStack(BaseModel):
    """What actually answered a judge call: inference server version, model digests and the
    call parameters LiteLLM applies (CPU threads, context size).

    The same model files can give different answers under another Ollama release or another
    CPU thread count (docs/inference_stack.md), so all of them are recorded with every run.
    """

    ollama_version: str | None = None  # None if Ollama is unreachable
    model_digests: dict[str, str] = {}  # LiteLLM model id ('ollama/phi4-mini') -> Ollama digest
    # LiteLLM model id -> {"num_thread": int | None, "num_ctx": int | None}, from LiteLLM's
    # /model/info (what the proxy sends to Ollama); {} if LiteLLM is unreachable
    model_params: dict[str, dict[str, int | None]] = {}
