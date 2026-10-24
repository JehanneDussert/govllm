# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""Integration tests: real PostgreSQL and Redis, simulated judge, no LLM call.

They run ONLY against a separate PostgreSQL schema (GOVLLM_DB_SCHEMA ending in "_test")
and a dedicated Redis database (REDIS_URL ending in "/<n>" with n != 0); otherwise they
are skipped, so they can never touch the deployment's data. See tests/integration/README.md.
"""

import json
import os

import pytest
import pytest_asyncio
import redis.asyncio as aioredis

SCHEMA = os.environ.get("GOVLLM_DB_SCHEMA", "govllm")
REDIS_URL = os.environ.get("REDIS_URL", "")
SAFE = SCHEMA.endswith("_test") and REDIS_URL.rsplit("/", 1)[-1].isdigit() and not REDIS_URL.endswith("/0")

pytestmark = pytest.mark.skipif(not SAFE, reason="integration tests need GOVLLM_DB_SCHEMA=*_test and REDIS_URL=.../<n != 0>")


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration" in str(item.fspath) and not SAFE:
            item.add_marker(pytest.mark.skip(reason="not on the test schema / test Redis database"))


@pytest_asyncio.fixture(autouse=True)
async def clean_state():
    """Fresh tables and an empty Redis database for every test."""
    if not SAFE:
        yield
        return
    from db.database import close_pool, get_pool, run_migrations

    await run_migrations()
    pool = await get_pool()
    await pool.execute("TRUNCATE eval_results, model_lifecycle")
    r = await aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.flushdb()
    await r.aclose()
    yield
    await close_pool()


@pytest.fixture
def simulated_judge(monkeypatch):
    """Replace the judge LLM call: every criterion gets the score set in `scores`."""
    import jobs.eval_runner as runner

    state = {"score": 0.9, "per_criterion": {}}

    async def fake_call_judge(prompt, judge_model, extra_system=None):
        from services.judge_config import get_judge_config

        config = await get_judge_config()
        ids = [c.id for c in config.criteria if c.enabled]
        return json.dumps({"scores": {
            cid: {"score": state["per_criterion"].get(cid, state["score"]), "flag": False, "reason": "simulated"}
            for cid in ids}})

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(runner, "_call_judge", fake_call_judge)
    monkeypatch.setattr(runner, "create_trace", noop)
    monkeypatch.setattr(runner, "push_score", noop)
    return state
