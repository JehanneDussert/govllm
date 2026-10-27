# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""Integration tests: real PostgreSQL and Redis, simulated judge, no LLM call.

They run ONLY against dedicated, throwaway instances started by run.sh on a private Docker
network that cannot reach the deployment (see tests/integration/README.md). Two layers:

1. Configuration: the DSN and Redis URL must name the test instances (host, port, database,
   schema below); otherwise every integration test is skipped.
2. Every PostgreSQL connection the code opens is checked, on each acquire, against
   properties only the test instance has (cluster_name set at startup, non-default port,
   database name, current schema). The Redis server is checked by port before any flush.
   A mismatch aborts the whole run before any statement is sent.

Background: on 2026-10-24 tests configured for a separate schema of the real database
emptied govllm.eval_results (docs/incident_2026-10-24_eval_results.md).
"""

import json
import os
from urllib.parse import urlparse

import asyncpg
import pytest
import pytest_asyncio
import redis.asyncio as aioredis

# Identity of the throwaway instances (must match run.sh)
PG_HOST, PG_PORT, PG_DB, PG_CLUSTER = "govllm-itest-pg", 5433, "govllm_itest", "govllm-itest"
REDIS_HOST, REDIS_PORT = "govllm-itest-redis", 6380
SCHEMA = os.environ.get("GOVLLM_DB_SCHEMA", "govllm")
EXPECTED_SCHEMA = "govllm_itest"

_dsn = urlparse(os.environ.get("ARENA_DB_URL", ""))
_redis = urlparse(os.environ.get("REDIS_URL", ""))
SAFE = (
    _dsn.hostname == PG_HOST and _dsn.port == PG_PORT and _dsn.path.lstrip("/") == PG_DB
    and SCHEMA == EXPECTED_SCHEMA
    and _redis.hostname == REDIS_HOST and _redis.port == REDIS_PORT
)

pytestmark = pytest.mark.skipif(not SAFE, reason="integration tests run only on the throwaway instances of run.sh")


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration" in str(item.fspath) and not SAFE:
            item.add_marker(pytest.mark.skip(reason="not on the throwaway test instances (run.sh)"))


async def _check_pg(conn) -> None:
    """Abort unless this connection is to the throwaway test instance."""
    row = await conn.fetchrow(
        "SELECT current_database() AS db, current_setting('cluster_name') AS cluster, "
        "inet_server_port() AS port, current_schema() AS schema"
    )
    found = dict(row)
    # schema None: the test schema does not exist yet (before the first migration)
    if (found["db"], found["cluster"], found["port"]) != (PG_DB, PG_CLUSTER, PG_PORT) or (
        found["schema"] not in (EXPECTED_SCHEMA, None)
    ):
        pytest.exit(f"ABORT: connection is not the throwaway test instance: {found}", returncode=3)


if SAFE:
    # Every pool the code creates checks each connection on every acquire (setup callback),
    # and every direct connection once.
    _create_pool = asyncpg.create_pool

    def _guarded_create_pool(*args, **kwargs):
        user_setup = kwargs.pop("setup", None)

        async def setup(conn):
            await _check_pg(conn)
            if user_setup:
                await user_setup(conn)

        return _create_pool(*args, setup=setup, **kwargs)

    asyncpg.create_pool = _guarded_create_pool

    _connect = asyncpg.connect

    async def _guarded_connect(*args, **kwargs):
        conn = await _connect(*args, **kwargs)
        await _check_pg(conn)
        return conn

    asyncpg.connect = _guarded_connect


async def _check_redis(r) -> None:
    info = await r.info("server")
    if int(info.get("tcp_port", 0)) != REDIS_PORT:
        pytest.exit(f"ABORT: Redis server is not the throwaway test instance (port {info.get('tcp_port')})",
                    returncode=3)


@pytest_asyncio.fixture(autouse=True)
async def clean_state():
    """Fresh tables and an empty Redis database for every test."""
    if not SAFE:
        yield
        return
    from db.database import close_pool, get_pool, run_migrations

    await run_migrations()
    pool = await get_pool()
    # The pool guard checks each connection; check the schema in use once more on several
    # connections before the TRUNCATE.
    for _ in range(4):
        async with pool.acquire() as conn:
            if await conn.fetchval("SELECT current_schema()") != EXPECTED_SCHEMA:
                pytest.exit("ABORT: queries do not run in the test schema", returncode=3)
    await pool.execute(f"TRUNCATE {EXPECTED_SCHEMA}.eval_results, {EXPECTED_SCHEMA}.model_lifecycle")
    r = await aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await _check_redis(r)
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
