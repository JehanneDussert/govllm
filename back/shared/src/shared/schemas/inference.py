# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from pydantic import BaseModel


class InferenceStack(BaseModel):
    """What actually answered a judge call: inference server version + model digests.

    The same model files can give different answers under another Ollama release
    (docs/inference_stack.md), so both are recorded with every evaluation run.
    """

    ollama_version: str | None = None  # None if Ollama is unreachable
    model_digests: dict[str, str] = {}  # LiteLLM model id ('ollama/phi4-mini') -> Ollama digest
