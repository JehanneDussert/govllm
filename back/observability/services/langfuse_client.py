# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from shared.langfuse import LangfuseClient
from shared.config import get_observability_settings

_s = get_observability_settings()
_client = LangfuseClient(_s.langfuse_host, _s.langfuse_public_key, _s.langfuse_secret_key)

# Re-export shared methods
get_traces = _client.get_traces
get_model_from_observation = _client.get_model_from_observation
get_trace_scores = _client.get_trace_scores
# push_score is NOT exposed here — observability is read-only on Langfuse


async def get_traces_with_scores(limit: int = 50) -> list[dict]:
    traces = await _client.get_traces(limit=limit)
    for trace in traces:
        raw_model = await _client.get_model_from_observation(trace["id"])
        trace["_model"] = raw_model if raw_model and raw_model != "unknown" else None
        scores = await _client.get_trace_scores(trace["id"])
        composite_vals = [
            s["value"] for s in scores if s.get("name") == "composite" and isinstance(s.get("value"), (int, float))
        ]
        trace["eval_score"] = round(sum(composite_vals) / len(composite_vals), 3) if composite_vals else None
    return traces
