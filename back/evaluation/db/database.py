# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import annotations
import asyncpg
from shared.config import get_evaluation_settings

settings = get_evaluation_settings()

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.arena_db_url,
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
    """Create tables on startup if they don't exist."""
    pool = await get_pool()
    migration_path = __file__.replace("database.py", "migrations.sql")
    with open(migration_path) as f:
        sql = f.read()
    async with pool.acquire() as conn:
        await conn.execute(sql)