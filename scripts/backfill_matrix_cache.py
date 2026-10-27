"""
Rebuild the eval:scores rolling cache in Redis from eval_results (PostgreSQL, source of truth).

Since issue #40 the evaluation service rebuilds this cache at startup and serves every
cache miss from PostgreSQL (services/scores.py), so this script is rarely needed: use it
to repopulate Redis by hand after a flush without restarting the service.

Run inside the evaluation container: python scripts/backfill_matrix_cache.py
"""

import asyncio

from db.database import close_pool
from services.scores import rebuild_cache


async def main() -> None:
    try:
        written = await rebuild_cache()
        print(f"Rebuilt {written} eval:scores keys from eval_results (self-judged results excluded)")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
