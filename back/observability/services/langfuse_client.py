import base64
import httpx
from shared.config import get_observability_settings

settings = get_observability_settings()


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


async def get_model_from_observation(trace_id: str) -> str:
    """Lit la première observation pour extraire le modèle réel."""
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


async def get_trace_scores(trace_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{settings.langfuse_host}/api/public/scores",
            headers=_auth_header(),
            params={"traceId": trace_id},
        )
        r.raise_for_status()
    return r.json().get("data", [])


async def get_traces_with_scores(
    limit: int = 50,
    model_filter: str | None = None,
) -> list[dict]:
    traces = await get_traces(limit=limit)
    for trace in traces:
        # Model from observation
        trace["_model"] = await get_model_from_observation(trace["id"])

        # Scores
        scores = await get_trace_scores(trace["id"])
        trace["eval_score"] = next(
            (s["value"] for s in scores if s.get("name") in ("composite", "hallucination", "overall")),
            None,
        )
    return traces