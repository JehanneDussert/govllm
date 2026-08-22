"""
One-shot backfill: reads eval_results (PostgreSQL, source of truth) and rebuilds
the eval:scores:{model}:{use_case} rolling cache in Redis that GET /matrix reads.

Use after the Redis rolling cache has expired or been lost — PostgreSQL keeps the
full history via the dual-write in eval_runner.py, this script just replays it.

Run inside the evaluation container: python scripts/backfill_matrix_cache.py
"""

import asyncio
import json

import asyncpg
import redis

from shared.config import get_evaluation_settings

ROLLING_TTL = 3600 * 24 * 7  # matches EVAL_SCORES_ROLLING_TTL in eval_runner.py


async def main() -> None:
    settings = get_evaluation_settings()

    conn = await asyncpg.connect(dsn=settings.arena_db_url)
    await conn.execute("SET search_path TO govllm")
    try:
        rows = await conn.fetch(
            """SELECT model, use_case_id, composite_score, evaluated_at
               FROM eval_results
               WHERE use_case_id IS NOT NULL
               ORDER BY model, use_case_id, evaluated_at"""
        )
    finally:
        await conn.close()

    print(f"Read {len(rows)} rows from eval_results")

    scores: dict[str, dict[str, list]] = {}
    for row in rows:
        model_scores = scores.setdefault(row["model"], {})
        entries = model_scores.setdefault(row["use_case_id"], [])
        entries.append(
            {"score": float(row["composite_score"]), "ts": row["evaluated_at"].isoformat()}
        )

    r = redis.from_url(settings.redis_url, decode_responses=True)

    existing = r.keys("eval:scores:*")
    if existing:
        r.delete(*existing)
        print(f"Cleared {len(existing)} existing eval:scores keys")

    total_keys = 0
    for model, uc_dict in sorted(scores.items()):
        for uc_id, entries in sorted(uc_dict.items()):
            key = f"eval:scores:{model}:{uc_id}"
            r.setex(key, ROLLING_TTL, json.dumps(entries[-100:]))
            print(f"  {key}: {len(entries)} entries")
            total_keys += 1

    print(f"\nDone. Wrote {total_keys} keys.")


if __name__ == "__main__":
    asyncio.run(main())
