# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

import base64
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
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.host}/api/public/traces",
                headers=self._auth_header(),
                params={"limit": limit},
            )
            r.raise_for_status()
        return r.json().get("data", [])

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
            r.raise_for_status()
        return r.json().get("data", [])

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
