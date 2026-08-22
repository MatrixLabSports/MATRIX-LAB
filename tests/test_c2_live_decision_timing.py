from datetime import datetime, timedelta, timezone

import pytest

from app.application.football.live_decision_timing import (
    LiveDecisionTiming,
)


NOW = datetime(
    2026, 8, 22, 19, 0,
    tzinfo=timezone.utc,
)


def test_timing_calculates_freshness_and_latency():
    timing = LiveDecisionTiming(
        state="VIGILAR",
        source_observed_at=NOW,
        captured_at=NOW + timedelta(seconds=2),
        evaluated_at=NOW + timedelta(seconds=3),
    )
    assert timing.data_freshness_ms == 2000
    assert timing.decision_latency_ms == 1000
    assert timing.automatic_wagering is False


def test_bad_signal_chronology_fails_closed():
    with pytest.raises(
        ValueError,
        match="LIVE_SIGNAL_CHRONOLOGY_INVALID",
    ):
        LiveDecisionTiming(
            state="PRESENAL",
            source_observed_at=None,
            captured_at=NOW,
            evaluated_at=NOW,
            signal_first_detected_at=(
                NOW + timedelta(seconds=10)
            ),
            signal_confirmed_at=(
                NOW + timedelta(seconds=5)
            ),
        )
