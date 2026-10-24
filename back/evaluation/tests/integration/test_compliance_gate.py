# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""Issue #40, PR 2: the compliance gate is applied in every routing strategy; a missing or
under-sampled score never counts as passing; no eligible model = explicit refusal."""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

STRATEGIES = ["best_score", "progression", "stability", "strict"]


async def _insert(model, use_case, composite, criteria, minutes_ago=0):
    from db.database import get_pool

    pool = await get_pool()
    await pool.execute(
        """INSERT INTO eval_results (trace_id, model, use_case_id, profile_id, composite_score,
                                     criteria_scores, evaluated_at, self_judged)
           VALUES ($1, $2, $3, 'p', $4, $5::jsonb, $6, false)""",
        str(uuid.uuid4()), model, use_case, composite,
        json.dumps([{"criterion_id": c, "score": s, "flag": False, "reason": ""} for c, s in criteria.items()]),
        datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )


async def _setup(theta: float | None = None, strategy: str = "best_score", threshold: float | None = None):
    """Active profile gets θ on its first active criterion; returns (config, use case, criterion, pool)."""
    from services.judge_config import get_judge_config, save_judge_config
    from shared.config import get_evaluation_settings

    config = await get_judge_config()
    cid = next(c.id for c in config.criteria if c.enabled)
    profile = next(p for p in config.profiles if p.id == config.active_profile_id)
    if theta is not None and cid in profile.criteria_config:
        profile.criteria_config[cid].min_score = theta
    for uc in config.use_cases:
        if uc.id == config.active_use_case_id:
            uc.min_score_threshold = threshold
    config.routing_strategy = strategy
    await save_judge_config(config)
    pool = [m for m in get_evaluation_settings().benchmark_models
            if m not in (config.judge_model,)]  # two non-judge models
    return config, config.active_use_case_id, cid, pool


async def test_gate_excludes_a_model_under_theta_in_every_strategy():
    from routers.matrix import get_routing

    for strategy in STRATEGIES:
        config, uc, cid, pool = await _setup(theta=0.7, strategy=strategy)
        a, b = pool[0], pool[1]
        if strategy == STRATEGIES[0]:
            for i in range(6):
                await _insert(a, uc, 0.85, {cid: 0.9}, minutes_ago=10 - i)
                await _insert(b, uc, 0.95, {cid: 0.5}, minutes_ago=10 - i)  # better composite, fails θ
        r = await get_routing()
        models = {m["model"]: m for m in r["models"]}
        assert r["recommended"] == a, strategy
        assert not models[b]["eligible"] and any("< θ 0.70" in x for x in models[b]["exclusion_reasons"])


async def test_insufficient_data_excludes_with_an_explicit_reason():
    from routers.matrix import get_routing

    config, uc, cid, pool = await _setup()
    a, b = pool[0], pool[1]
    for i in range(3):
        await _insert(a, uc, 0.99, {cid: 0.99}, minutes_ago=10 - i)  # best scores, only 3 evaluations
    for i in range(5):
        await _insert(b, uc, 0.80, {cid: 0.80}, minutes_ago=10 - i)
    r = await get_routing()
    models = {m["model"]: m for m in r["models"]}
    assert r["recommended"] == b
    assert models[a]["exclusion_reasons"][0] == "insufficient data: 3 evaluation(s), 5 required"


async def test_no_eligible_model_is_an_explicit_refusal():
    from routers.matrix import get_routing

    config, uc, cid, pool = await _setup(threshold=0.9)
    for m in pool[:2]:
        for i in range(5):
            await _insert(m, uc, 0.6, {cid: 0.6}, minutes_ago=10 - i)
    r = await get_routing()
    assert r["recommended"] is None and r["reason"] == "no_eligible_model"
    assert all(m["exclusion_reasons"] for m in r["models"])


async def test_min_evaluations_is_configurable():
    from routers.matrix import get_routing
    from services.judge_config import get_judge_config, save_judge_config

    config, uc, cid, pool = await _setup()
    for i in range(3):
        await _insert(pool[0], uc, 0.9, {cid: 0.9}, minutes_ago=10 - i)
    assert (await get_routing())["recommended"] is None
    config = await get_judge_config()
    await save_judge_config(config.model_copy(update={"min_evaluations": 3}))
    assert (await get_routing())["recommended"] == pool[0]


async def test_fresh_install_to_first_eligible_model(simulated_judge):
    """New installation: nothing is routable, every model says why; after five evaluated
    answers (MANUAL use, simulated judge) the model becomes eligible and is recommended."""
    from jobs.eval_runner import evaluate_trace
    from routers.matrix import get_routing

    config, uc, cid, pool = await _setup()
    first = await get_routing()
    assert first["recommended"] is None and first["reason"] == "no_eligible_model"
    assert all(m["exclusion_reasons"][0].startswith("insufficient data: 0 evaluation") for m in first["models"])

    simulated_judge["score"] = 0.8
    for _ in range(config.min_evaluations):
        await evaluate_trace(str(uuid.uuid4()), pool[0], "question", "answer")
    after = await get_routing()
    assert after["recommended"] == pool[0] and after["reason"] is None
