# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""Unit tests for services/identity_ingestion.py (pure computation, no I/O).

Run inside the evaluation container:  python -m pytest tests/ -q
"""

from datetime import datetime, timedelta, timezone

import pytest

from services.identity_ingestion import compute_baseline, detect_deviation
from shared.schemas.identity_access import AccessLogEvent

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def _event(days_ago=1, hour=10, volume=5, scope="hr/records", ip="10.0.0.1", account="acc-1", minute=0):
    ts = (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=minute)
    return AccessLogEvent(
        timestamp=ts,
        account_id=account,
        action="read",
        resource_scope=scope,
        volume=volume,
        source_ip=ip,
        session_id="s-1",
    )


def _history(volumes=(4, 5, 6, 5, 4, 6, 5, 5)):
    return [_event(days_ago=i + 1, volume=v) for i, v in enumerate(volumes)]


def test_baseline_only_uses_account_events_inside_window():
    events = _history() + [
        _event(days_ago=45, scope="old/scope"),  # outside 30-day window
        _event(account="other", scope="other/scope"),  # other account
    ]
    b = compute_baseline("acc-1", events, now=NOW)
    assert b.sample_count == 8
    assert b.known_scopes == {"hr/records"}
    assert b.known_source_ips == {"10.0.0.1"}
    assert b.active_hours == {10}
    assert b.volume_mean == pytest.approx(5.0)
    assert b.volume_stddev > 0


def test_normal_single_event_window_is_not_flagged():
    b = compute_baseline("acc-1", _history(), now=NOW)
    assert detect_deviation([_event(days_ago=0, volume=5)], b) is None


def test_empty_window_returns_none():
    b = compute_baseline("acc-1", _history(), now=NOW)
    assert detect_deviation([], b) is None


def test_anomalous_window_flags_all_baseline_criteria():
    b = compute_baseline("acc-1", _history(), now=NOW)
    window = [_event(days_ago=0, hour=3, volume=5000, scope="finance/payroll", ip="203.0.113.9")]
    cand = detect_deviation(window, b)
    assert cand is not None
    assert cand.deviation_score == 1.0
    assert cand.flags.scope_deviation
    assert cand.flags.volume_deviation
    assert cand.flags.temporal_deviation
    assert cand.flags.session_geo_deviation


def test_zero_variance_baseline_still_detects_massive_volume():
    # Regression: a constant baseline used to neutralize the z-score (5 -> 5000 ignored).
    b = compute_baseline("acc-1", _history(volumes=(5,) * 8), now=NOW)
    assert b.volume_stddev == 0
    cand = detect_deviation([_event(days_ago=0, volume=5000)], b)
    assert cand is not None and cand.flags.volume_deviation


def test_zero_variance_baseline_tolerates_small_noise():
    # Regression: the first fix flagged any +/-1 change on a constant baseline.
    b = compute_baseline("acc-1", _history(volumes=(5,) * 8), now=NOW)
    assert detect_deviation([_event(days_ago=0, volume=6)], b) is None


def test_single_flag_reaches_threshold():
    b = compute_baseline("acc-1", _history(), now=NOW)
    cand = detect_deviation([_event(days_ago=0, ip="203.0.113.9")], b)
    assert cand is not None
    assert cand.deviation_score == 0.25
    assert cand.flags.session_geo_deviation and not cand.flags.volume_deviation


def _busy_history(per_hour_totals=(50, 45, 55, 50, 48, 52, 50, 50)):
    """Each day, 10 events in the 10:00 hour whose volumes add up to the given total."""
    events = []
    for day, total in enumerate(per_hour_totals, start=1):
        events += [_event(days_ago=day, minute=5 * i, volume=total // 10) for i in range(9)]
        events.append(_event(days_ago=day, minute=50, volume=total - 9 * (total // 10)))
    return events


def test_baseline_volume_is_per_window_total():
    b = compute_baseline("acc-1", _busy_history(), now=NOW)
    assert b.volume_window_hours == 1.0
    assert b.volume_window_count == 8
    assert b.volume_mean == pytest.approx(50.0)


def test_multi_event_normal_window_is_not_flagged():
    # Regression (units bug): the window total used to be compared to the per-event
    # mean, so 10 ordinary events (total 50) were flagged against a mean of 5.
    b = compute_baseline("acc-1", _busy_history(), now=NOW)
    window = [_event(days_ago=0, minute=5 * i, volume=5) for i in range(10)]
    assert detect_deviation(window, b) is None


def test_multi_event_window_with_abnormal_total_is_flagged():
    b = compute_baseline("acc-1", _busy_history(), now=NOW)
    window = [_event(days_ago=0, minute=5 * i, volume=50) for i in range(10)]  # total 500
    cand = detect_deviation(window, b)
    assert cand is not None and cand.flags.volume_deviation


def test_window_longer_than_baseline_window_is_rejected():
    b = compute_baseline("acc-1", _busy_history(), now=NOW)
    window = [_event(days_ago=0, hour=10), _event(days_ago=0, hour=13)]
    with pytest.raises(ValueError):
        detect_deviation(window, b)
