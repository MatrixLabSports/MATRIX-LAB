from datetime import datetime, timezone

import pytest

from app.core.opponent_quality_evidence import (
    SQLiteOpponentQualityLedger,
)


UTC = timezone.utc


def test_quality_resolves_point_in_time(tmp_path):
    ledger = SQLiteOpponentQualityLedger(tmp_path / "quality.db")
    obs = ledger.build_observation(
        sport="tennis",
        opponent_canonical_id="tennis:player:op1",
        quality_key="rating",
        quality_value=1800.0,
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 2, tzinfo=UTC),
        source_record_fingerprint="a" * 64,
    )
    ledger.append(obs)

    assert ledger.resolve_as_of(
        sport="tennis",
        opponent_canonical_id="tennis:player:op1",
        quality_key="rating",
        as_of=datetime(2026, 8, 1, 23, tzinfo=UTC),
    ) is None

    resolved = ledger.resolve_as_of(
        sport="tennis",
        opponent_canonical_id="tennis:player:op1",
        quality_key="rating",
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
    )
    assert resolved["quality_value"] == 1800.0


def test_later_quality_correction_does_not_rewrite_past(tmp_path):
    ledger = SQLiteOpponentQualityLedger(tmp_path / "quality.db")

    for value, day, char in (
        (1800.0, 2, "a"),
        (1850.0, 5, "b"),
    ):
        ledger.append(
            ledger.build_observation(
                sport="football",
                opponent_canonical_id="football:team:op1",
                quality_key="rating",
                quality_value=value,
                observed_at=datetime(2026, 8, 1, tzinfo=UTC),
                available_at=datetime(2026, 8, day, tzinfo=UTC),
                source_record_fingerprint=char * 64,
            )
        )

    earlier = ledger.resolve_as_of(
        sport="football",
        opponent_canonical_id="football:team:op1",
        quality_key="rating",
        as_of=datetime(2026, 8, 4, tzinfo=UTC),
    )
    later = ledger.resolve_as_of(
        sport="football",
        opponent_canonical_id="football:team:op1",
        quality_key="rating",
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
    )

    assert earlier["quality_value"] == 1800.0
    assert later["quality_value"] == 1850.0


def test_same_time_conflicting_quality_fails_closed(tmp_path):
    ledger = SQLiteOpponentQualityLedger(tmp_path / "quality.db")

    for value, char in ((1800.0, "a"), (1900.0, "b")):
        ledger.append(
            ledger.build_observation(
                sport="tennis",
                opponent_canonical_id="tennis:player:op2",
                quality_key="rating",
                quality_value=value,
                observed_at=datetime(2026, 8, 1, tzinfo=UTC),
                available_at=datetime(2026, 8, 2, tzinfo=UTC),
                source_record_fingerprint=char * 64,
            )
        )

    with pytest.raises(
        ValueError,
        match="AMBIGUOUS_OPPONENT_QUALITY_AS_OF",
    ):
        ledger.resolve_as_of(
            sport="tennis",
            opponent_canonical_id="tennis:player:op2",
            quality_key="rating",
            as_of=datetime(2026, 8, 2, tzinfo=UTC),
        )


def test_nonfinite_quality_rejected(tmp_path):
    ledger = SQLiteOpponentQualityLedger(tmp_path / "quality.db")

    with pytest.raises(
        ValueError,
        match="NONFINITE_QUALITY_VALUE",
    ):
        ledger.build_observation(
            sport="tennis",
            opponent_canonical_id="tennis:player:op3",
            quality_key="rating",
            quality_value=float("inf"),
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 1, tzinfo=UTC),
            source_record_fingerprint="c" * 64,
        )
