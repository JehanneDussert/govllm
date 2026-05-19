# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

import base64
import uuid as _uuid
from datetime import datetime, timezone, timedelta

import httpx


class LangfuseClient:
    def __init__(self, host: str, public_key: str, secret_key: str):
        self.host = host
        self._public_key = public_key
        self._secret_key = secret_key

    def _auth_header(self) -> dict:
        token = base64.b64encode(
            f"{self._public_key}:{self._secret_key}".encode()
        ).decode()
        return {"Authorization": f"Basic {token}"}

    async def get_traces(self, limit: int = 50) -> list[dict]:
        MAX_PER_PAGE = 100  # Langfuse v2 hard cap per request
        all_traces: list[dict] = []
        page = 1
        remaining = limit
        async with httpx.AsyncClient(timeout=30) as client:
            while remaining > 0:
                page_limit = min(remaining, MAX_PER_PAGE)
                r = await client.get(
                    f"{self.host}/api/public/traces",
                    headers=self._auth_header(),
                    params={"limit": page_limit, "page": page},
                )
                r.raise_for_status()
                batch = r.json().get("data", [])
                all_traces.extend(batch)
                remaining -= len(batch)
                if len(batch) < page_limit:
                    break
                page += 1
        return all_traces[:limit]

    async def get_model_from_observation(self, trace_id: str) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{self.host}/api/public/observations",
                headers=self._auth_header(),
                params={"traceId": trace_id, "limit": 1},
            )
            if r.status_code != 200:
                return "unknown"
        obs = r.json().get("data", [])
        return obs[0]["model"] if obs and obs[0].get("model") else "unknown"

    async def get_trace_scores(self, trace_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{self.host}/api/public/scores",
                headers=self._auth_header(),
                params={"traceId": trace_id},
            )
            if r.status_code != 200:
                return []
        return r.json().get("data", [])

    async def create_trace(
        self,
        trace_id: str,
        name: str,
        input: str,
        output: str,
        model: str,
        started_at: str | None = None,
        latency_ms: int | None = None,
        metadata: dict | None = None,
    ) -> None:
        ts = started_at or datetime.now(timezone.utc).isoformat()
        batch: list[dict] = [
            {
                "type": "trace-create",
                "id": str(_uuid.uuid4()),
                "timestamp": ts,
                "body": {
                    "id": trace_id,
                    "name": name,
                    "timestamp": ts,
                    "input": input,
                    "output": output,
                    "metadata": metadata or {},
                },
            }
        ]
        if latency_ms is not None:
            try:
                start_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                end_ts = (start_dt + timedelta(milliseconds=latency_ms)).isoformat()
            except Exception:
                end_ts = ts
            batch.append({
                "type": "generation-create",
                "id": str(_uuid.uuid4()),
                "timestamp": ts,
                "body": {
                    "id": str(_uuid.uuid4()),
                    "traceId": trace_id,
                    "name": "llm-generation",
                    "model": model,
                    "input": [{"role": "user", "content": input}],
                    "output": output,
                    "startTime": ts,
                    "endTime": end_ts,
                },
            })
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{self.host}/api/public/ingestion",
                headers=self._auth_header(),
                json={"batch": batch},
            )

    async def push_score(
        self, trace_id: str, score: float, name: str = "answer_relevancy"
    ) -> None:
        # Only called from the evaluation service — observability is read-only
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self.host}/api/public/scores",
                headers=self._auth_header(),
                json={"name": name, "value": score, "traceId": trace_id},
            )
