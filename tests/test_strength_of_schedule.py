from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.opponent_quality_evidence import (
    SQLiteOpponentQualityLedger,
)
from app.core.point_in_time_history import (
    build_point_in_time_history,
)
from app.core.strength_of_schedule import (
    build_strength_of_schedule_profile,
)


UTC = timezone.utc


def test_strength_of_schedule_reports_coverage_not_fake_zero(tmp_path):
    ledger = SQLiteOpponentQualityLedger(tmp_path / "q.db")
    ledger.append(
        ledger.build_observation(
            sport="football",
            opponent_canonical_id="football:team:op1",
            quality_key="rating",
            quality_value=1700,
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 2, tzinfo=UTC),
            source_record_fingerprint="a" * 64,
        )
    )

    events = (
        SimpleNamespace(
            event_key="M1",
            event_at=datetime(2026, 8, 1, tzinfo=UTC),
            season_key="2026",
            completed=True,
            opponent_canonical_id="football:team:op1",
            source_available_at=datetime(2026, 8, 2, tzinfo=UTC),
            source_record_fingerprint="b" * 64,
            event_fingerprint="c" * 64,
        ),
        SimpleNamespace(
            event_key="M2",
            event_at=datetime(2026, 8, 3, tzinfo=UTC),
            season_key="2026",
            completed=True,
            opponent_canonical_id="football:team:missing",
            source_available_at=datetime(2026, 8, 4, tzinfo=UTC),
            source_record_fingerprint="d" * 64,
            event_fingerprint="e" * 64,
        ),
    )

    history = build_point_in_time_history(
        sport="football",
        canonical_id="football:team:subject",
        events=events,
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
        season_key="2026",
    )

    profile = build_strength_of_schedule_profile(
        history=history,
        quality_key="rating",
        quality_ledger=ledger,
    )

    assert profile.career["sample_size"] == 2
    assert profile.career["quality_observed"] == 1
    assert profile.career["quality_missing"] == 1
    assert profile.career["mean_quality"] == 1700.0
    assert profile.payload()["recency_weighting_applied"] is False


def test_strength_of_schedule_uses_historical_quality_as_available_then(tmp_path):
    ledger = SQLiteOpponentQualityLedger(tmp_path / "q.db")
    ledger.append(
        ledger.build_observation(
            sport="tennis",
            opponent_canonical_id="tennis:player:op1",
            quality_key="rating",
            quality_value=1800,
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 5, tzinfo=UTC),
            source_record_fingerprint="a" * 64,
        )
    )

    event = SimpleNamespace(
        event_key="M1",
        event_at=datetime(2026, 8, 1, tzinfo=UTC),
        season_key="2026",
        completed=True,
        opponent_canonical_id="tennis:player:op1",
        source_available_at=datetime(2026, 8, 2, tzinfo=UTC),
        source_record_fingerprint="b" * 64,
        event_fingerprint="c" * 64,
    )

    history = build_point_in_time_history(
        sport="tennis",
        canonical_id="tennis:player:subject",
        events=(event,),
        as_of=datetime(2026, 8, 6, tzinfo=UTC),
        season_key="2026",
    )

    profile = build_strength_of_schedule_profile(
        history=history,
        quality_key="rating",
        quality_ledger=ledger,
    )

    assert profile.career["quality_observed"] == 0
    assert profile.career["mean_quality"] is None
