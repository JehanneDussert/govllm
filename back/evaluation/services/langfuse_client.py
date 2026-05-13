# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from shared.langfuse import LangfuseClient
from shared.config import get_evaluation_settings

_s = get_evaluation_settings()
_client = LangfuseClient(_s.langfuse_host, _s.langfuse_public_key, _s.langfuse_secret_key)

# Re-export shared methods
get_traces = _client.get_traces
# push_score is intentionally only exposed here (evaluation pushes scores; observability is read-only)
push_score = _client.push_score


async def get_traces_with_scores(limit: int = 50) -> list[dict]:
    traces = await _client.get_traces(limit=limit)
    for trace in traces:
        trace["_model"] = await _client.get_model_from_observation(trace["id"])
        scores = await _client.get_trace_scores(trace["id"])
        trace["eval_score"] = next(
            (
                s["value"]
                for s in scores
                if s.get("name") in ("answer_relevancy", "hallucination", "overall")
            ),
            None,
        )
    return traces
