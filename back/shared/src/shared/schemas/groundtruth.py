# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class GroundTruthCaseCreate(BaseModel):
    """Payload to add a case to the ground truth corpus."""
    criterion: str               # criterion_id, e.g. "transparency"
    prompt: str                  # original user question
    response: str                # AI response to evaluate
    source: str | None = None    # origin (CNIL decision ref, etc.)
    expected_answers: dict[str, bool]  # {"q1": True, ...} — True=compliant


class GroundTruthCase(BaseModel):
    """Corpus case with expert-validated expected answers."""
    id: str
    criterion: str
    prompt: str
    response: str
    source: str | None
    expected_answers: dict[str, bool]
    created_at: datetime


class JudgeChecklistResult(BaseModel):
    """One judge's checklist answers for a single corpus case."""
    judge_model: str
    judge_family: str
    answers: dict[str, bool]   # {"q1": True, ...} — True=compliant
    score: float               # mean(answers.values())
    agreement: float           # fraction matching expected_answers
    reason: str | None
    latency_ms: int | None


class GroundTruthRunResult(BaseModel):
    """Outcome of running a corpus case through all configured judges."""
    case_id: str
    criterion: str
    expected_answers: dict[str, bool]
    judges: list[JudgeChecklistResult]


class ValidityEntry(BaseModel):
    """Agreement rate for one judge × criterion × sub-question cell."""
    judge_model: str
    judge_family: str
    criterion: str
    question_id: str
    agreement_rate: float
    sample_size: int


class ValidityReport(BaseModel):
    """Aggregated validity metrics across the full corpus."""
    entries: list[ValidityEntry]
    criteria: list[str]
    judge_models: list[str]
