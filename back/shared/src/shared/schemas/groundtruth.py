# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class GroundTruthCaseCreate(BaseModel):
    """Payload to add a case to the ground truth corpus."""

    criterion: str  # criterion_id, e.g. "transparency"
    prompt: str  # original user question
    response: str  # AI response to evaluate
    source: str | None = None  # origin (CNIL decision ref, etc.)
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
    """One judge's checklist answers for a single corpus case.

    Unusable answers are returned (and stored) too, with status != "ok" and
    score/agreement set to None.
    """

    judge_model: str
    judge_family: str
    answers: dict[str, bool]  # {"q1": True, ...} — True=compliant
    score: float | None  # mean(answers.values()); None if status != "ok"
    agreement: float | None  # fraction matching expected_answers; None if status != "ok"
    reason: str | None
    latency_ms: int | None
    status: str = "ok"  # ok | call_error | json_error | empty | parse_error
    parse_fallback: str | None = None  # positional_list | top_level_keys | None
    run_label: str = "main"  # "main" = the analysed runs; anything else (e.g. retest-r1) is excluded
    model_digest: str | None = None  # Ollama digest of the model that answered
    ollama_version: str | None = None  # Ollama server version that answered


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


class IncoherenceItem(BaseModel):
    """One groundtruth result row where incoherence pattern B is detected."""

    result_id: str
    case_id: str
    prompt_preview: str
    criterion: str
    judge_model: str
    judge_family: str
    answers: dict[str, bool]
    expected_answers: dict[str, bool]
    reason: str | None
    incoherence_validated: bool | None
    question_order: str


class OrderSensitivityEntry(BaseModel):
    """Flip rate and agreement delta for one judge × criterion pair (original vs reversed order)."""

    judge_model: str
    criterion: str
    flip_rate: float  # fraction of cases with ≥1 answer flip
    mean_delta_agreement: float  # mean(agreement_reversed − agreement_original)
    n_cases: int
    flipped_case_ids: list[str]
