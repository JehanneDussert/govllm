# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
from pydantic import BaseModel


class LLMEvent(BaseModel):
    trace_id: str
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    success: bool
