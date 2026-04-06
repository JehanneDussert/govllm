# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
import base64
import httpx
from shared.config import get_evaluation_settings

settings = get_evaluation_settings()


def _auth_header() -> dict:
    token = base64.b64encode(
        f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
    ).decode()
    return {"Authorization": f"Basic {token}"}


async def get_traces(limit: int = 50) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{settings.langfuse_host}/api/public/traces",
            headers=_auth_header(),
            params={"limit": limit},
        )
        r.raise_for_status()
    return r.json().get("data", [])


async def _get_model_from_observation(trace_id: str) -> str:
    """Lit la première observation de la trace pour extraire le modèle."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{settings.langfuse_host}/api/public/observations",
            headers=_auth_header(),
            params={"traceId": trace_id, "limit": 1},
        )
        if r.status_code != 200:
            return "unknown"
    obs = r.json().get("data", [])
    if obs and obs[0].get("model"):
        return obs[0]["model"]
    return "unknown"


async def push_score(
    trace_id: str, score: float, name: str = "answer_relevancy"
) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{settings.langfuse_host}/api/public/scores",
            headers=_auth_header(),
            json={"name": name, "value": score, "traceId": trace_id},
        )


async def get_traces_with_scores(limit: int = 50) -> list[dict]:
    traces = await get_traces(limit=limit)
    for trace in traces:
        # Get observation model
        trace["_model"] = await _get_model_from_observation(trace["id"])

        # Get scores
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{settings.langfuse_host}/api/public/scores",
                headers=_auth_header(),
                params={"traceId": trace["id"]},
            )
            r.raise_for_status()
            scores = r.json().get("data", [])
        trace["eval_score"] = next(
            (
                s["value"]
                for s in scores
                if s.get("name") in ("answer_relevancy", "hallucination", "overall")
            ),
            None,
        )
    return traces
