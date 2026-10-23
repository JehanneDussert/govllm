# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from pydantic import BaseModel


class CriterionScore(BaseModel):
    criterion_id: str
    score: float
    flag: bool = False
    reason: str = ""


class EvalResult(BaseModel):
    trace_id: str
    model: str
    use_case_id: str | None
    profile_id: str | None = None
    composite_score: float
    criteria_scores: list[CriterionScore]
    evaluated_at: str
    # True when at least one criterion was scored by the model that generated the
    # answer. Such results are kept and shown, but excluded from the aggregates
    # (Matrix rolling cache, routing, SAS) because of measured self-preference.
    self_judged: bool = False
    self_judged_criteria: list[str] = []
