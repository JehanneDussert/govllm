# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

import asyncio
import json
from datetime import datetime, timezone
from shared.schemas.judge import JudgeConfig, JudgeCriterion
from shared.schemas.evaluation import EvalResult, CriterionScore
from services.judge_config import get_judge_config
from services.langfuse_client import push_score, create_trace
import redis.asyncio as aioredis
from shared.config import get_evaluation_settings
from services.judge import _call_judge, _build_judge_prompt, _extract_json
from db.database import get_pool
from services.scores import append_to_cache
import logging

logger = logging.getLogger(__name__)
settings = get_evaluation_settings()

EVAL_RESULT_HOT_TTL = 3600  # eval:result:{trace_id} — hot cache for frontend polling only, eval_results (PostgreSQL) is the source of truth


def same_model(a: str | None, b: str | None) -> bool:
    """True if two model ids designate the same model (provider prefix ignored)."""
    if not a or not b:
        return False
    norm = lambda m: m.strip().lower().removeprefix("ollama/")  # noqa: E731
    return norm(a) == norm(b)


def self_judged_criteria(judge_of: dict[str, str], generator: str) -> list[str]:
    """Criteria scored by the model that generated the answer (self-judging)."""
    return sorted(cid for cid, judge in judge_of.items() if same_model(judge, generator))


def _compute_composite(
    scores: list[CriterionScore],
    criteria: list[JudgeCriterion],
) -> float:
    weight_map = {c.id: c.weight for c in criteria}
    total_weight = sum(weight_map.get(s.criterion_id, 1.0) for s in scores)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(s.score * weight_map.get(s.criterion_id, 1.0) for s in scores)
    return round(weighted_sum / total_weight, 3)


async def evaluate_trace(
    trace_id: str,
    model: str,
    question: str,
    answer: str,
    chat_mode: bool = True,
    latency_ms: int | None = None,
    started_at: str | None = None,
) -> EvalResult | None:
    config: JudgeConfig = await get_judge_config()

    active_criteria = [c for c in config.criteria if c.enabled]
    if not active_criteria:
        return None

    active_uc = next(
        (u for u in config.use_cases if u.id == config.active_use_case_id), None
    )
    use_case_label = active_uc.label if active_uc else None
    uc_prompt = active_uc.judge_system_prompt if active_uc else None

    # Calibration notes keyed by criterion_id from the active profile
    active_profile = next(
        (p for p in config.profiles if p.id == config.active_profile_id), None
    )
    calibration_notes: dict[str, str] = {}
    if active_profile:
        for cid, cc in active_profile.criteria_config.items():
            if cc.calibration_notes:
                calibration_notes[cid] = cc.calibration_notes

    # Clear previous result before dispatching
    r_clean = await aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await r_clean.delete(f"eval:result:{trace_id}")
    finally:
        await r_clean.aclose()

    async def _score_with_judge(
        judge_criteria: list[JudgeCriterion],
        judge_model: str,
        extra_system: str | None,
    ) -> list[CriterionScore]:
        cal = {
            cid: v
            for cid, v in calibration_notes.items()
            if cid in {c.id for c in judge_criteria}
        }
        prompt = _build_judge_prompt(
            question=question,
            answer=answer,
            criteria=judge_criteria,
            use_case_label=use_case_label,
            policy_rules=config.policy_rules,
            use_case_system_prompt=extra_system,
            calibration_notes=cal or None,
        )
        raw = await _call_judge(prompt, judge_model, extra_system)
        logger.info(f"[eval] RAW {judge_model}: {raw!r}")
        parsed = _extract_json(raw) if raw else None
        if parsed is None:
            raw2 = await _call_judge(prompt, judge_model, extra_system)
            logger.info(f"[eval] RAW retry {judge_model}: {raw2!r}")
            if raw2:
                parsed = _extract_json(raw2)
        if parsed is None:
            logger.warning(
                f"[eval] JSON parse failed — judge={judge_model} model={model} raw={raw[:200]!r}"
            )
            return []
        scores_raw = parsed.get("scores", {})
        if isinstance(scores_raw, list):
            scores_raw = {
                s.get("id") or s.get("criterion_id", ""): s
                for s in scores_raw
                if isinstance(s, dict)
            }
        if not scores_raw:
            # Some models flatten the structure instead of nesting under "scores":
            # {"relevance": 0.9, "hallucination": 0.0, "flag": false, "reason": "..."}
            # with one shared flag/reason for all criteria, rather than per-criterion.
            criterion_ids = {c.id for c in judge_criteria}
            flat_hits = {k: v for k, v in parsed.items() if k in criterion_ids}
            if flat_hits:
                shared_flag = parsed.get("flag", False)
                shared_reason = parsed.get("reason", "")
                scores_raw = {
                    cid: v
                    if isinstance(v, dict)
                    else {"score": v, "flag": shared_flag, "reason": shared_reason}
                    for cid, v in flat_hits.items()
                }
        result = []
        for c in judge_criteria:
            s = scores_raw.get(c.id, {})
            if not isinstance(s, dict):
                s = {}
            result.append(
                CriterionScore(
                    criterion_id=c.id,
                    score=float(s.get("score", 0.0)),
                    flag=bool(s.get("flag", False)),
                    reason=str(s.get("reason", "")),
                )
            )
        return result

    criteria_scores: list[CriterionScore] = []
    judge_of: dict[str, str] = {}  # criterion_id -> judge model actually used

    active_panel = next(
        (p for p in config.panels if p.profile_id == config.active_profile_id), None
    )

    if active_panel and active_panel.judges:
        # Panel dispatch: each member evaluates their assigned criteria in parallel
        tasks = []
        covered_ids: set[str] = set()
        for member in active_panel.judges:
            member_criteria = [
                c for c in active_criteria if c.id in member.assigned_criteria
            ]
            if not member_criteria:
                continue
            covered_ids |= {c.id for c in member_criteria}
            judge_of.update({c.id: member.model for c in member_criteria})
            sys_prompt = (
                "\n".join(filter(None, [uc_prompt, member.persona_prompt])) or None
            )
            tasks.append(_score_with_judge(member_criteria, member.model, sys_prompt))
        results = await asyncio.gather(*tasks)
        criteria_scores = [cs for member_scores in results for cs in member_scores]
        # Fallback to global judge for any criteria not covered by the panel
        uncovered = [c for c in active_criteria if c.id not in covered_ids]
        if uncovered:
            judge_of.update({c.id: config.judge_model for c in uncovered})
            fallback = await _score_with_judge(uncovered, config.judge_model, uc_prompt)
            criteria_scores.extend(fallback)
    else:
        judge_of = {c.id: config.judge_model for c in active_criteria}
        criteria_scores = await _score_with_judge(
            active_criteria, config.judge_model, uc_prompt
        )

    # A model must not judge its own answers: the result is kept (and shown) but
    # flagged, and left out of every aggregate (rolling cache -> Matrix, routing, SAS).
    self_judged = self_judged_criteria(judge_of, model)
    if self_judged:
        logger.warning(
            f"[eval] self-judged result — generator={model} judged its own answer on "
            f"{self_judged}; excluded from aggregates (trace={trace_id})"
        )

    if not criteria_scores:
        r_err = await aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            error_result = EvalResult(
                trace_id=trace_id,
                model=model,
                use_case_id=config.active_use_case_id,
                profile_id=config.active_profile_id,
                composite_score=0.0,
                criteria_scores=[],
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )
            await r_err.setex(
                f"eval:result:{trace_id}",
                EVAL_RESULT_HOT_TTL,
                error_result.model_dump_json(),
            )
        finally:
            await r_err.aclose()
        return None

    composite = _compute_composite(criteria_scores, active_criteria)

    result = EvalResult(
        trace_id=trace_id,
        model=model,
        use_case_id=config.active_use_case_id,
        profile_id=config.active_profile_id,
        composite_score=composite,
        criteria_scores=criteria_scores,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        self_judged=bool(self_judged),
        self_judged_criteria=self_judged,
    )

    r_client = await aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await r_client.setex(
            f"eval:result:{trace_id}", EVAL_RESULT_HOT_TTL, result.model_dump_json()
        )
    finally:
        await r_client.aclose()

    # eval_results is the source of truth for every aggregate (services/scores.py);
    # the rolling cache is only extended once the row is stored.
    stored = False
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO eval_results
                   (trace_id, model, use_case_id, profile_id, composite_score, criteria_scores,
                    evaluated_at, self_judged)
                   VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)""",
                trace_id,
                model,
                config.active_use_case_id,
                config.active_profile_id,
                composite,
                json.dumps([cs.model_dump() for cs in criteria_scores]),
                datetime.fromisoformat(result.evaluated_at),
                bool(self_judged),
            )
        stored = True
    except Exception as exc:
        logger.warning(f"[eval] PostgreSQL write failed for {trace_id}: {exc}")

    if stored and config.active_use_case_id and not self_judged:
        await append_to_cache(
            model,
            config.active_use_case_id,
            composite,
            {cs.criterion_id: cs.score for cs in criteria_scores},
            result.evaluated_at,
        )

    await create_trace(
        trace_id=trace_id,
        name="chat",
        input=question,
        output=answer,
        model=model,
        started_at=started_at,
        latency_ms=latency_ms,
        metadata={
            "model": model,
            "use_case_id": config.active_use_case_id,
            "profile_id": config.active_profile_id,
            "judge_model": config.judge_model,
            "self_judged": bool(self_judged),
            "self_judged_criteria": self_judged,
        },
    )
    await push_score(trace_id, composite, name="composite")
    for cs in criteria_scores:
        if cs.flag:
            await push_score(trace_id, cs.score, name=cs.criterion_id)

    return result


async def get_eval_result(trace_id: str) -> EvalResult | None:
    r_client = await aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = await r_client.get(f"eval:result:{trace_id}")
        if raw:
            return EvalResult.model_validate_json(raw)
        return None
    finally:
        await r_client.aclose()
