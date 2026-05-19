"""
One-shot migration: read all eval:result:{trace_id} keys from Redis
and insert them into the eval_results PostgreSQL table.
Skips entries already present (by trace_id).
Run inside the evaluation container:
  python scripts/migrate_redis_to_pg.py
"""
import asyncio
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

import redis.asyncio as aioredis
from shared.config import get_evaluation_settings
from db.database import get_pool

settings = get_evaluation_settings()


async def main() -> None:
    r = await aioredis.from_url(settings.redis_url, decode_responses=True)
    pool = await get_pool()

    try:
        keys = await r.keys("eval:result:*")
        print(f"Found {len(keys)} eval:result:* keys in Redis")

        inserted = 0
        skipped = 0
        errors = 0

        async with pool.acquire() as conn:
            existing = await conn.fetch("SELECT trace_id FROM eval_results")
            existing_ids = {row["trace_id"] for row in existing}
            print(f"Already in PostgreSQL: {len(existing_ids)} rows")

            for key in keys:
                trace_id = key.removeprefix("eval:result:")
                if trace_id in existing_ids:
                    skipped += 1
                    continue

                raw = await r.get(key)
                if not raw:
                    errors += 1
                    continue

                try:
                    data = json.loads(raw)
                except Exception as e:
                    print(f"  SKIP {key}: JSON parse error — {e}")
                    errors += 1
                    continue

                try:
                    criteria_scores = data.get("criteria_scores", [])
                    raw_ts = data.get("evaluated_at")
                    evaluated_at = datetime.fromisoformat(raw_ts) if raw_ts else datetime.now(timezone.utc)
                    await conn.execute(
                        """INSERT INTO eval_results
                           (trace_id, model, use_case_id, profile_id, composite_score, criteria_scores, evaluated_at)
                           VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)""",
                        trace_id,
                        data.get("model", ""),
                        data.get("use_case_id"),
                        data.get("profile_id"),
                        float(data.get("composite_score", 0.0)),
                        json.dumps(criteria_scores),
                        evaluated_at,
                    )
                    inserted += 1
                except Exception as e:
                    print(f"  ERR {trace_id}: {e}")
                    errors += 1

        print(f"\nDone. inserted={inserted}  skipped={skipped}  errors={errors}")

    finally:
        await r.aclose()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
