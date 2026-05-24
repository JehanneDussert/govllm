# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from db.database import get_pool
from services.judge_config import get_judge_config
from db.models import (
    ArenaRunRequest,
    ArenaRunResponse,
    ArenaSession,
    ArenaJudge,
    ArenaCriterionScore,
    ArenaVoteRequest,
    VarianceHistory,
    VariancePoint,
    BiasMatrix,
    BiasMatrixCell,
    IncoherenceScore,
    IncoherenceReport,
)
from services.arena import run_arena, run_arena_stream

router = APIRouter(prefix="/arena", tags=["arena"])


@router.post("/run/stream", status_code=200)
async def arena_run_stream(request: ArenaRunRequest):
    """
    SSE streaming endpoint — emits judge results as they complete.
    Events: init | judge_done | complete | error  (newline-delimited JSON, text/event-stream).
    """
    return StreamingResponse(
        run_arena_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/run", response_model=ArenaRunResponse, status_code=201)
async def arena_run(request: ArenaRunRequest):
    """
    Trigger a new Arena session.
    Sends the prompt to N specialised judges in parallel,
    computes inter-judge variance, persists to DB, returns scores.
    """
    try:
        return await run_arena(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/vote", status_code=200)
async def arena_vote(request: ArenaVoteRequest):
    """Record the user's preferred model after score reveal."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE arena_sessions SET user_vote = $1 WHERE session_id = $2",
            request.chosen_model,
            request.session_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@router.get("/sessions", response_model=list[ArenaSession])
async def list_sessions(
    profile_id: str | None = Query(None),
    high_variance: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    """List recent Arena sessions with full judge scores."""
    config = await get_judge_config()
    variance_threshold = config.variance_threshold

    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions = []
        params: list = [limit]
        if profile_id:
            params.append(profile_id)
            conditions.append(f"s.profile_id = ${len(params)}")
        if high_variance:
            params.append(variance_threshold)
            conditions.append(f"s.sigma >= ${len(params)}")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sessions_rows = await conn.fetch(
            f"""
            SELECT s.session_id, s.prompt, s.profile_id, s.use_case_id,
                   s.sigma, s.user_vote, s.created_at
            FROM arena_sessions s
            {where}
            ORDER BY s.created_at DESC
            LIMIT $1
            """,
            *params,
        )

        sessions = []
        for row in sessions_rows:
            judge_rows = await conn.fetch(
                """
                SELECT j.id, j.model_name, j.model_family,
                       j.assigned_criteria, j.global_score, j.latency_ms
                FROM arena_judges j
                WHERE j.session_id = $1
                """,
                row["session_id"],
            )
            judges = []
            for jr in judge_rows:
                score_rows = await conn.fetch(
                    """
                    SELECT criterion_id, score, flag, reason
                    FROM arena_criterion_scores
                    WHERE judge_id = $1
                    """,
                    jr["id"],
                )
                judges.append(
                    ArenaJudge(
                        judge_id=jr["id"],
                        model_name=jr["model_name"],
                        model_family=jr["model_family"],
                        assigned_criteria=jr["assigned_criteria"],
                        global_score=jr["global_score"],
                        latency_ms=jr["latency_ms"],
                        scores=[ArenaCriterionScore(**dict(sr)) for sr in score_rows],
                    )
                )
            s_sigma = row["sigma"]
            sessions.append(
                ArenaSession(
                    session_id=row["session_id"],
                    prompt=row["prompt"],
                    profile_id=row["profile_id"],
                    use_case_id=row["use_case_id"],
                    sigma=s_sigma,
                    high_variance=s_sigma is not None and s_sigma >= variance_threshold,
                    user_vote=row["user_vote"],
                    created_at=row["created_at"],
                    judges=judges,
                )
            )
        return sessions


@router.get("/variance", response_model=VarianceHistory)
async def variance_history(
    profile_id: str | None = Query(None),
    window_days: int = Query(30, ge=1, le=365),
):
    """Time series of inter-judge variance — feeds Figure 1 of the paper."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        where = "AND profile_id = $2" if profile_id else ""
        params: list = [window_days, profile_id] if profile_id else [window_days]
        rows = await conn.fetch(
            f"""
            SELECT session_id, prompt, profile_id, sigma, created_at
            FROM arena_sessions
            WHERE sigma IS NOT NULL
              AND created_at >= now() - make_interval(days => $1)
              {where}
            ORDER BY created_at ASC
            """,
            *params,
        )
    return VarianceHistory(
        points=[
            VariancePoint(
                session_id=r["session_id"],
                created_at=r["created_at"],
                sigma=r["sigma"],
                profile_id=r["profile_id"],
                prompt_preview=r["prompt"][:80],
            )
            for r in rows
        ],
        profile_id=profile_id,
        window_days=window_days,
    )


@router.get("/bias-matrix", response_model=BiasMatrix)
async def bias_matrix(
    profile_id: str | None = Query(None),
    criterion_id: str | None = Query(None),
):
    """
    Cross-tabulation of judge family × evaluated model — feeds Figure 2 of the paper.
    Diagonal cells = self-preference (judge family == evaluated model family).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Join sessions → judges → scores, filter by profile and criterion
        profile_filter = "AND s.profile_id = $1" if profile_id else ""
        criterion_filter = "AND cs.criterion_id = $2" if criterion_id else ""
        params: list = []
        if profile_id:
            params.append(profile_id)
        if criterion_id:
            params.append(criterion_id)

        rows = await conn.fetch(
            f"""
            SELECT
                j.model_family                          AS judge_family,
                j.model_name                            AS evaluated_model,
                AVG(cs.score)                           AS mean_score,
                COUNT(cs.score)                         AS sample_size
            FROM arena_sessions s
            JOIN arena_judges j     ON j.session_id = s.session_id
            JOIN arena_criterion_scores cs ON cs.judge_id = j.id
            WHERE 1=1
              {profile_filter}
              {criterion_filter}
            GROUP BY j.model_family, j.model_name
            ORDER BY j.model_family, j.model_name
            """,
            *params,
        )

    cells = [
        BiasMatrixCell(
            judge_family=r["judge_family"],
            evaluated_model=r["evaluated_model"],
            mean_score=round(float(r["mean_score"]), 3),
            sample_size=int(r["sample_size"]),
            is_self_preference=r["judge_family"] in r["evaluated_model"].lower(),
        )
        for r in rows
    ]

    return BiasMatrix(
        cells=cells,
        criterion_id=criterion_id,
        profile_id=profile_id,
        judge_families=sorted({c.judge_family for c in cells}),
        evaluated_models=sorted({c.evaluated_model for c in cells}),
    )


@router.get("/incoherence", response_model=IncoherenceReport)
async def incoherence_report(
    profile_id: str | None = Query(None),
    score_threshold: float = Query(0.5, ge=0.0, le=1.0),
    reason_min_len: int = Query(20, ge=0),
):
    """
    Intra-judge incoherence rate per model over all stored sessions.
    Incoherent = flag=True AND score < threshold AND len(reason) < reason_min_len.
    This is a structural contradiction observable in the JSON output — distinct
    from Jung et al. who escalate on self-declared confidence.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        profile_filter = "AND s.profile_id = $3" if profile_id else ""
        params: list = [score_threshold, reason_min_len]
        if profile_id:
            params.append(profile_id)
        rows = await conn.fetch(
            f"""
            SELECT
                j.model_name,
                j.model_family,
                COUNT(cs.id)                                              AS total_scores,
                SUM(CASE WHEN cs.flag = true
                              AND cs.score < $1
                              AND length(coalesce(cs.reason, '')) < $2
                         THEN 1 ELSE 0 END)                              AS incoherent_count
            FROM arena_sessions s
            JOIN arena_judges j            ON j.session_id = s.session_id
            JOIN arena_criterion_scores cs ON cs.judge_id = j.id
            WHERE 1=1
              {profile_filter}
            GROUP BY j.model_name, j.model_family
            ORDER BY incoherent_count DESC
            """,
            *params,
        )
    judges = [
        IncoherenceScore(
            model_name=r["model_name"],
            model_family=r["model_family"],
            total_scores=int(r["total_scores"]),
            incoherent_count=int(r["incoherent_count"]),
            incoherence_rate=round(
                int(r["incoherent_count"]) / int(r["total_scores"]), 3
            )
            if int(r["total_scores"]) > 0
            else 0.0,
        )
        for r in rows
    ]
    return IncoherenceReport(
        judges=judges,
        score_threshold=score_threshold,
        reason_min_len=reason_min_len,
    )


@router.get("/variance/export")
async def export_variance(
    profile_id: str | None = Query(None),
    window_days: int = Query(30),
):
    """CSV export for paper figures."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    history = await variance_history(profile_id=profile_id, window_days=window_days)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "session_id",
            "created_at",
            "sigma",
            "profile_id",
            "prompt_preview",
        ],
    )
    writer.writeheader()
    for p in history.points:
        writer.writerow(p.model_dump())
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=variance.csv"},
    )


@router.get("/bias-matrix/export")
async def export_bias_matrix(
    profile_id: str | None = Query(None),
    criterion_id: str | None = Query(None),
):
    """CSV export for paper figures."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    matrix = await bias_matrix(profile_id=profile_id, criterion_id=criterion_id)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "judge_family",
            "evaluated_model",
            "mean_score",
            "sample_size",
            "is_self_preference",
        ],
    )
    writer.writeheader()
    for c in matrix.cells:
        writer.writerow(c.model_dump())
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bias_matrix.csv"},
    )
