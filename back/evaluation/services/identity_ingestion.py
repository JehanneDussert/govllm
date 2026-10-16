# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""
Identity & Access ingestion — baseline computation and statistical deviation
detection for the identity_access_governance forensic module.

Pure computation, no external I/O: takes a list of AccessLogEvent (source
adapter is future work — see CLAUDE.md backlog), computes a per-account
behavioral baseline over a rolling window, and flags candidate windows whose
deviation_score crosses a threshold. The judge only runs on candidate windows
returned here (see routers/identity_access.py for the orchestration step).

Same spirit as services/lifecycle.py::check_drift() — simple statistical
thresholds over a rolling window, not a model.

Volume is compared in consistent units: the history is cut into consecutive
windows of `volume_window_hours`, and the *total* volume of a candidate window
is compared to the distribution of totals over the account's active historical
windows of the same duration (inactive windows are left out, since a candidate
window always contains activity).
"""

from __future__ import annotations
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from shared.schemas.identity_access import (
    AccessLogEvent,
    AccountBaseline,
    CandidateWindow,
    DeviationFlags,
)

VOLUME_ZSCORE_THRESHOLD = 2.0
DEVIATION_SCORE_THRESHOLD = 0.25  # at least 1 of 4 flags triggered
DEFAULT_VOLUME_WINDOW_HOURS = 1.0


def compute_baseline(
    account_id: str,
    events: list[AccessLogEvent],
    window_days: int = 30,
    now: datetime | None = None,
    volume_window_hours: float = DEFAULT_VOLUME_WINDOW_HOURS,
) -> AccountBaseline:
    """Compute a behavioral baseline for one account from its recent event history."""
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_days)
    recent = [
        e for e in events if e.account_id == account_id and e.timestamp >= window_start
    ]

    # Per-window totals over consecutive windows of volume_window_hours.
    window_seconds = volume_window_hours * 3600
    totals: dict[int, int] = defaultdict(int)
    for e in recent:
        totals[int((e.timestamp - window_start).total_seconds() // window_seconds)] += e.volume
    window_totals = list(totals.values())
    volume_mean = statistics.mean(window_totals) if window_totals else 0.0
    volume_stddev = statistics.pstdev(window_totals) if len(window_totals) > 1 else 0.0

    return AccountBaseline(
        account_id=account_id,
        window_days=window_days,
        sample_count=len(recent),
        known_scopes={e.resource_scope for e in recent},
        known_source_ips={e.source_ip for e in recent},
        volume_window_hours=volume_window_hours,
        volume_window_count=len(window_totals),
        volume_mean=volume_mean,
        volume_stddev=volume_stddev,
        active_hours={e.timestamp.hour for e in recent},
        computed_at=now,
    )


def detect_deviation(
    window_events: list[AccessLogEvent],
    baseline: AccountBaseline,
) -> CandidateWindow | None:
    """
    Compare a window of events against the account's baseline. Returns a
    CandidateWindow if deviation_score >= DEVIATION_SCORE_THRESHOLD, else None.

    The window must not span more than baseline.volume_window_hours, otherwise
    its total volume is not comparable to the baseline's per-window totals.
    """
    if not window_events:
        return None

    start = min(e.timestamp for e in window_events)
    end = max(e.timestamp for e in window_events)
    if end - start > timedelta(hours=baseline.volume_window_hours):
        raise ValueError(
            f"window spans {end - start}, longer than the baseline volume window "
            f"({baseline.volume_window_hours:g}h) — split it or recompute the baseline "
            f"with a matching volume_window_hours"
        )

    window_volume = sum(e.volume for e in window_events)
    if baseline.volume_stddev > 0:
        volume_zscore = abs(window_volume - baseline.volume_mean) / baseline.volume_stddev
        volume_deviation = volume_zscore > VOLUME_ZSCORE_THRESHOLD
    else:
        # No historical variance — z-score is undefined. Flag only beyond a
        # minimal tolerance so everyday noise (+/-1 on a small constant
        # baseline) doesn't trigger on every window.
        tolerance = max(baseline.volume_mean * 0.2, 1.0)
        volume_deviation = abs(window_volume - baseline.volume_mean) > tolerance

    flags = DeviationFlags(
        scope_deviation=any(
            e.resource_scope not in baseline.known_scopes for e in window_events
        ),
        volume_deviation=volume_deviation,
        temporal_deviation=any(
            e.timestamp.hour not in baseline.active_hours for e in window_events
        ),
        session_geo_deviation=any(
            e.source_ip not in baseline.known_source_ips for e in window_events
        ),
    )

    deviation_score = sum(
        [
            flags.scope_deviation,
            flags.volume_deviation,
            flags.temporal_deviation,
            flags.session_geo_deviation,
        ]
    ) / 4

    if deviation_score < DEVIATION_SCORE_THRESHOLD:
        return None

    return CandidateWindow(
        account_id=baseline.account_id,
        window_start=start,
        window_end=end,
        events=window_events,
        deviation_score=deviation_score,
        flags=flags,
        baseline=baseline,
    )
