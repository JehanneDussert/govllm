# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""Issue #40, PR 1: the aggregates (Matrix, routing, SAS, drift watcher) read the persisted
evaluation results; Redis is a cache that can be lost without losing any aggregate."""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import redis.asyncio as aioredis

REDIS_URL = os.environ.get("REDIS_URL", "")

pytestmark = pytest.mark.asyncio

MODEL = "ollama/test-generator"
OTHER = "ollama/test-other"


async def _flush_cache():
    r = await aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.flushdb()
    await r.aclose()


async def _insert(model, use_case, score, *, minutes_ago=0, self_judged=False, criteria=None):
    from db.database import get_pool

    pool = await get_pool()
    crit = criteria or {"relevance": score}
    await pool.execute(
        """INSERT INTO eval_results (trace_id, model, use_case_id, profile_id, composite_score,
                                     criteria_scores, evaluated_at, self_judged)
           VALUES ($1, $2, $3, 'p', $4, $5::jsonb, $6, $7)""",
        str(uuid.uuid4()), model, use_case, score,
        json.dumps([{"criterion_id": c, "score": s, "flag": False, "reason": ""} for c, s in crit.items()]),
        datetime.now(timezone.utc) - timedelta(minutes=minutes_ago), self_judged,
    )


async def test_cache_miss_is_served_from_the_database_and_repopulates_the_cache():
    from services.scores import recent_scores

    for i, s in enumerate([0.5, 0.6, 0.7]):
        await _insert(MODEL, "general", s, minutes_ago=10 - i)
    assert await recent_scores(MODEL, "general") == [0.5, 0.6, 0.7]  # oldest first
    r = await aioredis.from_url(REDIS_URL, decode_responses=True)
    cached = json.loads(await r.get(f"eval:scores:{MODEL}:general"))
    await r.aclose()
    assert [e["score"] for e in cached] == [0.5, 0.6, 0.7]


async def test_losing_redis_loses_no_aggregate():
    from routers.matrix import _get_scores_for_model

    for i in range(6):
        await _insert(MODEL, "general", 0.8, minutes_ago=10 - i)
    before = await _get_scores_for_model(MODEL, "general")
    await _flush_cache()
    after = await _get_scores_for_model(MODEL, "general")
    assert before == after and after["sample_size"] == 6 and after["avg_score"] == 0.8


async def test_self_judged_results_are_excluded():
    from services.scores import recent_scores

    await _insert(MODEL, "general", 0.4, minutes_ago=3)
    await _insert(MODEL, "general", 1.0, minutes_ago=2, self_judged=True)
    assert await recent_scores(MODEL, "general") == [0.4]


async def test_window_is_a_number_of_evaluations():
    from services.scores import WINDOW, recent_scores

    for i in range(WINDOW + 20):
        await _insert(MODEL, "general", round(i / 1000, 3), minutes_ago=WINDOW + 20 - i)
    scores = await recent_scores(MODEL, "general")
    assert len(scores) == WINDOW and scores[-1] == round((WINDOW + 19) / 1000, 3)


async def test_per_criterion_scores_are_persisted_and_read():
    from services.scores import recent_criterion_scores

    await _insert(MODEL, "general", 0.7, criteria={"data_privacy": 0.4, "transparency": 1.0})
    await _flush_cache()
    assert await recent_criterion_scores(MODEL, "general", "data_privacy") == [0.4]
    assert await recent_criterion_scores(MODEL, "general", "transparency") == [1.0]


async def test_rebuild_cache_writes_composite_and_criterion_keys():
    from services.scores import rebuild_cache

    await _insert(MODEL, "general", 0.7, criteria={"data_privacy": 0.4})
    await _insert(OTHER, "general", 0.9, criteria={"data_privacy": 0.9}, self_judged=True)
    assert await rebuild_cache() == 2  # composite + data_privacy for MODEL; OTHER is self-judged


async def test_end_to_end_evaluation_feeds_the_matrix_with_a_simulated_judge(simulated_judge):
    """Real evaluate_trace (judge call simulated) -> eval_results -> Matrix, before and after a cache loss."""
    from jobs.eval_runner import evaluate_trace
    from routers.matrix import _get_scores_for_model
    from services.judge_config import get_judge_config

    config = await get_judge_config()
    use_case = config.active_use_case_id
    simulated_judge["score"] = 0.6
    for _ in range(5):
        result = await evaluate_trace(str(uuid.uuid4()), MODEL, "question", "answer")
        assert result is not None and not result.self_judged
    cell = await _get_scores_for_model(MODEL, use_case)
    assert cell["sample_size"] == 5 and cell["avg_score"] == 0.6
    await _flush_cache()
    assert (await _get_scores_for_model(MODEL, use_case))["sample_size"] == 5


async def test_sas_reads_the_persisted_history():
    from services.judge_config import get_judge_config
    from services.lifecycle import run_sas

    config = await get_judge_config()
    for i in range(5):
        await _insert(MODEL, config.use_cases[0].id, 0.95, minutes_ago=10 - i)
    await _flush_cache()
    result = await run_sas(MODEL)
    assert result.sample_size == 5 and result.avg_score == 0.95


async def test_drift_is_detected_on_persisted_data_after_a_cache_loss():
    """Production model whose recent scores degrade -> quarantined, even with an empty cache."""
    from services.judge_config import get_judge_config
    from services.lifecycle import check_drift, get_status, set_zone
    from shared.config import get_evaluation_settings

    settings = get_evaluation_settings()
    model = settings.benchmark_models[0]
    config = await get_judge_config()
    await set_zone(model, "production", operator="test", note="integration test")
    for i in range(10):  # degraded series, well under the threshold
        await _insert(model, config.use_cases[0].id, 0.3, minutes_ago=20 - i)
    await _flush_cache()
    assert model in await check_drift()
    status = {s.model: s.zone for s in await get_status([model])}
    assert status[model] == "quarantine"


async def test_window_follows_the_configuration():
    """score_window (Settings > Routing) sets how many evaluations the aggregates use."""
    from routers.matrix import _get_scores_for_model
    from services.judge_config import get_judge_config, save_judge_config

    for i in range(30):
        await _insert(MODEL, "general", 0.2 if i < 20 else 1.0, minutes_ago=30 - i)
    config = await get_judge_config()
    assert (await _get_scores_for_model(MODEL, "general"))["sample_size"] == 30  # default 100
    await save_judge_config(config.model_copy(update={"score_window": 10}))
    cell = await _get_scores_for_model(MODEL, "general")
    assert cell["sample_size"] == 10 and cell["avg_score"] == 1.0  # only the 10 most recent
