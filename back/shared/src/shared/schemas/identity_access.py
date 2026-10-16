# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class AccessLogEvent(BaseModel):
    """Normalized access log event — input to the identity/access forensic pipeline."""

    timestamp: datetime
    account_id: str
    action: str  # e.g. "read", "export", "login", "delete"
    resource_scope: str  # e.g. "hr/employee_records", "finance/invoices"
    volume: int = 1  # records or bytes touched by this event
    source_ip: str
    session_id: str


class AccountBaseline(BaseModel):
    """Rolling-window behavioral baseline for one account, computed from AccessLogEvent history."""

    account_id: str
    window_days: int
    sample_count: int
    known_scopes: set[str]  # resource_scopes historically accessed
    known_source_ips: set[str]
    # Volume distribution of per-window totals: history is cut into consecutive
    # windows of volume_window_hours; mean/stddev are over the active ones
    # (>= 1 event). A candidate window's total is compared to this distribution.
    volume_window_hours: float
    volume_window_count: int
    volume_mean: float
    volume_stddev: float
    active_hours: set[int]  # hours-of-day (0-23) with observed activity
    computed_at: datetime


class DeviationFlags(BaseModel):
    """Per-criterion deviation signals, mapped to the identity_access_governance
    profile criteria (scope_conformity, volume_conformity, temporal_conformity,
    session_geo_consistency — sensitive_export_justification is evaluated by the
    judge directly from event content, not a baseline deviation)."""

    scope_deviation: bool
    volume_deviation: bool
    temporal_deviation: bool
    session_geo_deviation: bool


class CandidateWindow(BaseModel):
    """A detected anomaly window — output of the ingestion pipeline, input to the
    forensic orchestration (which hands it to judge_core with the
    identity_access_governance profile)."""

    account_id: str
    window_start: datetime
    window_end: datetime
    events: list[AccessLogEvent]
    deviation_score: float  # 0.0 (no deviation) .. 1.0 (all criteria triggered)
    flags: DeviationFlags
    baseline: AccountBaseline
