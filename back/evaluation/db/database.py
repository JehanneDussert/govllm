# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import annotations
import os
import re
import asyncpg
from shared.config import get_evaluation_settings

settings = get_evaluation_settings()

# PostgreSQL schema holding the govllm tables: "govllm" in every deployment. The
# integration tests set GOVLLM_DB_SCHEMA=govllm_test to work in a separate schema.
SCHEMA = os.environ.get("GOVLLM_DB_SCHEMA", "govllm")
if not re.fullmatch(r"[a-z_][a-z0-9_]*", SCHEMA):
    raise ValueError(f"Invalid GOVLLM_DB_SCHEMA: {SCHEMA!r}")

_pool: asyncpg.Pool | None = None


async def _init_conn(conn) -> None:
    await conn.execute(f"SET search_path TO {SCHEMA}")


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.arena_db_url,
            # search_path as a connection (startup) parameter: the pool runs RESET ALL when a
            # connection is released, which would otherwise fall back to the database default
            # schema (govllm) after the first query. init alone is not enough.
            server_settings={"search_path": SCHEMA},
            init=_init_conn,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def run_migrations() -> None:
    """Create tables on startup if they don't exist (in SCHEMA)."""
    pool = await get_pool()
    migration_path = __file__.replace("database.py", "migrations.sql")
    with open(migration_path) as f:
        sql = f.read()
    sql = sql.replace("SET search_path TO govllm;", f"SET search_path TO {SCHEMA};", 1)
    async with pool.acquire() as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        await conn.execute(sql)
