# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from pydantic import BaseModel


class LLMEvent(BaseModel):
    trace_id: str
    model: str
    input: str
    output: str
    latency_ms: float
    usage: dict = {}
    timestamp: str
