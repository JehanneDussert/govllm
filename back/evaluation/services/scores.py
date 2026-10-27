# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Recent evaluation scores per (model, use case) and per criterion — the data behind the
Matrix, AUTO routing, the SAS and the drift watcher.

PostgreSQL (`eval_results`) is the source of truth; Redis is a read-through cache that
can always be rebuilt. A cache miss (expired key, Redis flush or restart) falls back to
the database and repopulates the key, so no aggregate silently runs on empty data.

The window is a number of evaluations (WINDOW, the last N non-self-judged results), not
an age: an idle week no longer empties the Matrix. The cache TTL only bounds memory; it
never changes what the aggregates see.

Cache format (unchanged): JSON list of {"score": float, "ts": iso8601}, oldest first.
    eval:scores:{model}:{use_case}               composite score
    eval:scores:{model}:{use_case}:{criterion}   per-criterion score
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import redis.asyncio as aioredis

from db.database import get_pool
from shared.config import get_evaluation_settings

logger = logging.getLogger(__name__)
settings = get_evaluation_settings()

WINDOW = 100  # default window (JudgeConfig.score_window), same size as the former rolling cache
CACHE_MAX = 1000  # entries kept per key: serves any configured window (score_window <= 1000)
CACHE_TTL = 3600 * 24 * 7  # memory bound only; a miss is served from PostgreSQL


def _key(model: str, use_case_id: str, criterion_id: str | None = None) -> str:
    base = f"eval:scores:{model}:{use_case_id}"
    return f"{base}:{criterion_id}" if criterion_id else base


def _iso(ts) -> str:
    return ts.isoformat() if isinstance(ts, datetime) else str(ts)


async def _from_db(model: str, use_case_id: str, criterion_id: str | None, n: int) -> list[dict]:
    pool = await get_pool()
    if criterion_id is None:
        rows = await pool.fetch(
            """SELECT composite_score AS score, evaluated_at FROM eval_results
               WHERE model = $1 AND use_case_id = $2 AND NOT self_judged
               ORDER BY evaluated_at DESC LIMIT $3""",
            model, use_case_id, n,
        )
    else:
        rows = await pool.fetch(
            """SELECT (cs->>'score')::float AS score, e.evaluated_at FROM eval_results e,
                      jsonb_array_elements(e.criteria_scores) cs
               WHERE e.model = $1 AND e.use_case_id = $2 AND NOT e.self_judged
                 AND cs->>'criterion_id' = $3
               ORDER BY e.evaluated_at DESC LIMIT $4""",
            model, use_case_id, criterion_id, n,
        )
    return [{"score": r["score"], "ts": _iso(r["evaluated_at"])} for r in reversed(rows)]


async def _recent(model: str, use_case_id: str, criterion_id: str | None, n: int) -> list[dict]:
    key = _key(model, use_case_id, criterion_id)
    r = await aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = None
        try:
            raw = await r.get(key)
        except Exception as e:  # Redis down: serve from the database
            logger.warning(f"[scores] cache read failed for {key}: {e}")
        if raw is not None:
            return json.loads(raw)[-n:]
        entries = await _from_db(model, use_case_id, criterion_id, CACHE_MAX)
        try:
            await r.setex(key, CACHE_TTL, json.dumps(entries))
        except Exception as e:
            logger.warning(f"[scores] cache write failed for {key}: {e}")
        return entries[-n:]
    finally:
        await r.aclose()


async def _window(n: int | None) -> int:
    if n is not None:
        return n
    from services.judge_config import get_judge_config

    return (await get_judge_config()).score_window


async def recent_scores(model: str, use_case_id: str, n: int | None = None) -> list[float]:
    """Last n composite scores (oldest first; default: the configured score_window),
    self-judged results excluded."""
    return [e["score"] for e in await _recent(model, use_case_id, None, await _window(n))]


async def recent_criterion_scores(
    model: str, use_case_id: str, criterion_id: str, n: int | None = None
) -> list[float]:
    """Last n scores on one criterion (oldest first; default: the configured score_window),
    self-judged results excluded."""
    return [e["score"] for e in await _recent(model, use_case_id, criterion_id, await _window(n))]


async def append_to_cache(
    model: str, use_case_id: str, composite: float, criteria: dict[str, float], ts: str
) -> None:
    """Write-through after a result has been stored in eval_results.

    Only keys already cached are extended; a missing key is rebuilt from the database on
    its next read (which then includes this result), so the cache never holds a partial
    window. Fail-silent: the database remains the reference.
    """
    r = await aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        updates = {_key(model, use_case_id): composite}
        updates.update({_key(model, use_case_id, cid): s for cid, s in criteria.items()})
        for key, score in updates.items():
            raw = await r.get(key)
            if raw is None:
                continue
            entries = json.loads(raw)
            entries.append({"score": score, "ts": ts})
            await r.setex(key, CACHE_TTL, json.dumps(entries[-CACHE_MAX:]))
    except Exception as e:
        logger.warning(f"[scores] cache write-through failed for {model}/{use_case_id}: {e}")
    finally:
        await r.aclose()


async def rebuild_cache() -> int:
    """Rebuild every eval:scores key from eval_results (startup, or after a Redis loss).

    Returns the number of keys written. Self-judged results are excluded.
    """
    pool = await get_pool()
    pairs = await pool.fetch(
        "SELECT DISTINCT model, use_case_id FROM eval_results "
        "WHERE use_case_id IS NOT NULL AND NOT self_judged"
    )
    crit_rows = await pool.fetch(
        """SELECT DISTINCT e.model, e.use_case_id, cs->>'criterion_id' AS criterion_id
           FROM eval_results e, jsonb_array_elements(e.criteria_scores) cs
           WHERE e.use_case_id IS NOT NULL AND NOT e.self_judged"""
    )
    r = await aioredis.from_url(settings.redis_url, decode_responses=True)
    written = 0
    try:
        for p in pairs:
            entries = await _from_db(p["model"], p["use_case_id"], None, CACHE_MAX)
            await r.setex(_key(p["model"], p["use_case_id"]), CACHE_TTL, json.dumps(entries))
            written += 1
        for c in crit_rows:
            entries = await _from_db(c["model"], c["use_case_id"], c["criterion_id"], CACHE_MAX)
            await r.setex(
                _key(c["model"], c["use_case_id"], c["criterion_id"]), CACHE_TTL, json.dumps(entries)
            )
            written += 1
    finally:
        await r.aclose()
    logger.info(f"[scores] cache rebuilt from eval_results: {written} keys")
    return written
