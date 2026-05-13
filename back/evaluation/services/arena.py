# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import annotations
import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from statistics import variance

logger = logging.getLogger(__name__)


from shared.schemas.judge import JudgeCriterion
from shared.config import get_evaluation_settings
from services.judge_config import get_judge_config
from services.judge import call_judge_for_criteria
from db.database import get_pool
from db.models import (
    ArenaJudge,
    ArenaRunRequest,
    ArenaRunResponse,
    ArenaCriterionScore,
    ArenaSession,
)


settings = get_evaluation_settings()

# ── Judge family detection ────────────────────────────────────

FAMILY_MAP = {
    "qwen":     "qwen",
    "gemma":    "gemma",
    "llama":    "llama",
    "deepseek": "deepseek",
    "mistral":  "mistral",
}


def _detect_family(model_name: str) -> str:
    name = model_name.lower()
    for key, family in FAMILY_MAP.items():
        if key in name:
            return family
    return "unknown"


# ── Criterion assignment per judge ────────────────────────────

def _assign_criteria(
    judges: list[str],
    active_criteria: list[JudgeCriterion],
) -> dict[str, list[JudgeCriterion]]:
    """
    Assign each criterion to its "primary" judge based on domain specialisation.
    This assignment is metadata only — all judges still evaluate all criteria.
    The primary assignment is stored in ArenaJudge.assigned_criteria for display.

    Specialisation logic:
      - security tags   → deepseek (reasoning model) if available
      - compliance tags → qwen (multilingual) if available
      - ethics tags     → gemma if available
      - quality/rest    → llama if available
      - fallback        → round-robin
    """
    DOMAIN_PREFERENCES: dict[str, list[str]] = {
        "security":   ["deepseek", "llama", "qwen", "gemma"],
        "compliance": ["qwen", "gemma", "llama", "deepseek"],
        "ethics":     ["gemma", "qwen", "llama", "deepseek"],
        "ai_act":     ["gemma", "qwen", "llama", "deepseek"],
        "rgpd":       ["qwen", "gemma", "llama", "deepseek"],
        "quality":    ["llama", "qwen", "gemma", "deepseek"],
        "inclusion":  ["qwen", "gemma", "llama", "deepseek"],
    }

    families = {m: _detect_family(m) for m in judges}

    def _preferred_judge(tags: list[str]) -> str:
        for tag in tags:
            prefs = DOMAIN_PREFERENCES.get(tag, [])
            for preferred_family in prefs:
                for model, family in families.items():
                    if family == preferred_family:
                        return model
        return judges[0]  # fallback

    assignment: dict[str, list[JudgeCriterion]] = {j: [] for j in judges}
    for criterion in active_criteria:
        primary = _preferred_judge(criterion.tags)
        assignment[primary].append(criterion)

    # Ensure no judge has zero criteria (redistribute if needed)
    unassigned_judges = [j for j, crits in assignment.items() if not crits]
    if unassigned_judges and active_criteria:
        for i, j in enumerate(unassigned_judges):
            assignment[j] = [active_criteria[i % len(active_criteria)]]

    return assignment


# ── Inter-judge variance ──────────────────────────────────────

def _compute_sigma(judges: list[ArenaJudge]) -> float | None:
    """
    Mean per-criterion variance across all judges.
    Each criterion must have been scored by ≥ 2 judges to contribute.
    This is meaningful only when all judges evaluate the same criteria set.
    """
    by_criterion: dict[str, list[float]] = {}
    for judge in judges:
        for score in judge.scores:
            by_criterion.setdefault(score.criterion_id, []).append(score.score)

    variances = [
        variance(scores)
        for scores in by_criterion.values()
        if len(scores) >= 2
    ]
    if not variances:
        return None
    return round(sum(variances) / len(variances), 4)


# ── Persist session to PostgreSQL ─────────────────────────────

async def _persist_session(
    session_id: uuid.UUID,
    request: ArenaRunRequest,
    judges: list[ArenaJudge],
    sigma: float | None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO arena_sessions
                    (session_id, prompt, profile_id, use_case_id, sigma)
                VALUES ($1, $2, $3, $4, $5)
                """,
                session_id,
                request.prompt,
                request.profile_id,
                request.use_case_id,
                sigma,
            )
            for judge in judges:
                await conn.execute(
                    """
                    INSERT INTO arena_judges
                        (id, session_id, model_name, model_family,
                         assigned_criteria, global_score, latency_ms)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    judge.judge_id,
                    session_id,
                    judge.model_name,
                    judge.model_family,
                    judge.assigned_criteria,
                    judge.global_score,
                    judge.latency_ms,
                )
                for score in judge.scores:
                    await conn.execute(
                        """
                        INSERT INTO arena_criterion_scores
                            (session_id, judge_id, criterion_id, score, flag, reason)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        session_id,
                        judge.judge_id,
                        score.criterion_id,
                        score.score,
                        score.flag,
                        score.reason,
                    )


# ── Main entry point ──────────────────────────────────────────

async def run_arena(request: ArenaRunRequest) -> ArenaRunResponse:
    config = await get_judge_config()

    # Resolve profile
    profile = next((p for p in config.profiles if p.id == request.profile_id), None)
    if profile is None:
        raise ValueError(f"Profile '{request.profile_id}' not found")

    # Active criteria for this profile
    # Active criteria — read weights from profile.criteria_config
    active_criteria = [
        c.model_copy(update={
            "enabled": True,
            "weight": profile.criteria_config[c.id].weight,
        })
        for c in config.criteria
        if c.id in profile.criteria_config and profile.criteria_config[c.id].enabled
    ]
    if not active_criteria:
        raise ValueError(f"Profile '{request.profile_id}' has no active criteria")

    # Judge models
    judge_models = request.judge_models or config.arena_judge_models or settings.benchmark_models

    # Use case context prompt
    active_uc = next(
        (uc for uc in config.use_cases if uc.id == request.use_case_id),
        None,
    )
    uc_prompt = active_uc.judge_system_prompt if active_uc else None

    # Assign criteria to judges
    assignment = _assign_criteria(judge_models, active_criteria)

    # All judges evaluate all active criteria — assignment is specialisation metadata only
    weight_map = {c.id: c.weight for c in active_criteria}
    total_weight = sum(weight_map.values()) or 1.0

    logger.info(f"[arena] Starting session — profile={request.profile_id} judges={len(assignment)} criteria={len(active_criteria)}")
    results_by_model: dict[str, tuple] = {}
    for model in assignment:
        logger.info(f"[arena] Calling judge {model} on {len(active_criteria)} criteria")
        scores, latency = await call_judge_for_criteria(
            prompt=request.prompt,
            answer=request.answer,
            criteria=active_criteria,
            judge_model=model,
            context_system_prompt=uc_prompt,
        )
        logger.info(f"[arena] Judge {model} done — {len(scores)} scores, {latency}ms")
        results_by_model[model] = (scores, latency)

    # Build judge objects
    session_id = uuid.uuid4()
    judges: list[ArenaJudge] = []

    for model, assigned_criteria in assignment.items():
        scores, latency_ms = results_by_model.get(model, ([], 0))

        global_score = (
            round(
                sum(s.score * weight_map.get(s.criterion_id, 1.0) for s in scores)
                / total_weight,
                3,
            )
            if scores else None
        )

        judges.append(ArenaJudge(
            judge_id=uuid.uuid4(),
            model_name=model,
            model_family=_detect_family(model),
            assigned_criteria=[c.id for c in assigned_criteria],  # primary specialisation label
            global_score=global_score,
            latency_ms=latency_ms,
            scores=scores,
        ))

    sigma = _compute_sigma(judges)
    logger.info(f"[arena] Session {session_id} complete — sigma={sigma}")

    # Persist
    await _persist_session(session_id, request, judges, sigma)

    # Criteria labels for the frontend
    criteria_labels = {c.id: c.label for c in active_criteria}

    return ArenaRunResponse(
        session_id=session_id,
        prompt=request.prompt,
        profile_id=request.profile_id,
        sigma=sigma,
        judges=judges,
        criteria_labels=criteria_labels,
    )


# ── Streaming entry point ─────────────────────────────────────

async def run_arena_stream(
    request: ArenaRunRequest,
) -> AsyncGenerator[str, None]:
    """
    Streaming variant of run_arena.
    Yields SSE-formatted events as each judge completes so the frontend
    can render cards progressively without waiting for all judges.

    Events:
      {"type": "init",       "judges": [...]}
      {"type": "judge_done", "judge":  {...}}
      {"type": "complete",   "session_id": ..., "sigma": ..., "criteria_labels": {...}}
      {"type": "error",      "detail": "..."}
    """
    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, default=str)}\n\n"

    config = await get_judge_config()

    profile = next((p for p in config.profiles if p.id == request.profile_id), None)
    if profile is None:
        yield _sse({"type": "error", "detail": f"Profile '{request.profile_id}' not found"})
        return

    active_criteria = [
        c.model_copy(update={
            "enabled": True,
            "weight": profile.criteria_config[c.id].weight,
        })
        for c in config.criteria
        if c.id in profile.criteria_config and profile.criteria_config[c.id].enabled
    ]
    if not active_criteria:
        yield _sse({"type": "error", "detail": f"Profile '{request.profile_id}' has no active criteria"})
        return

    judge_models = request.judge_models or config.arena_judge_models or settings.benchmark_models
    active_uc = next((uc for uc in config.use_cases if uc.id == request.use_case_id), None)
    uc_prompt = active_uc.judge_system_prompt if active_uc else None

    assignment = _assign_criteria(judge_models, active_criteria)

    # Immediately announce all judge cards so the frontend can render shells
    yield _sse({
        "type": "init",
        "judges": [
            {
                "model_name": model,
                "model_family": _detect_family(model),
                "assigned_criteria": [c.id for c in crits],
            }
            for model, crits in assignment.items()
        ],
    })

    # All judges evaluate all active criteria — assignment is specialisation metadata only
    weight_map = {c.id: c.weight for c in active_criteria}
    total_weight = sum(weight_map.values()) or 1.0

    session_id = uuid.uuid4()
    judges: list[ArenaJudge] = []

    for model, assigned_criteria in assignment.items():
        logger.info(f"[arena/stream] Judge {model} — {len(active_criteria)} criteria")
        scores, latency = await call_judge_for_criteria(
            prompt=request.prompt,
            answer=request.answer,
            criteria=active_criteria,
            judge_model=model,
            context_system_prompt=uc_prompt,
        )

        global_score = (
            round(
                sum(s.score * weight_map.get(s.criterion_id, 1.0) for s in scores)
                / total_weight,
                3,
            )
            if scores else None
        )

        judge = ArenaJudge(
            judge_id=uuid.uuid4(),
            model_name=model,
            model_family=_detect_family(model),
            assigned_criteria=[c.id for c in assigned_criteria],  # primary specialisation label
            global_score=global_score,
            latency_ms=latency,
            scores=scores,
        )
        judges.append(judge)
        logger.info(f"[arena/stream] Judge {model} done — score={global_score}")
        yield _sse({"type": "judge_done", "judge": judge.model_dump(mode="json")})

    sigma = _compute_sigma(judges)
    logger.info(f"[arena/stream] Session {session_id} complete — sigma={sigma}")
    await _persist_session(session_id, request, judges, sigma)

    yield _sse({
        "type": "complete",
        "session_id": str(session_id),
        "sigma": sigma,
        "criteria_labels": {c.id: c.label for c in active_criteria},
    })