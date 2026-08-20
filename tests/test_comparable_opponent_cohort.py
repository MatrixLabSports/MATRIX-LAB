from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.comparable_opponent_cohort import (
    build_comparable_opponent_cohort,
    build_comparable_opponent_policy,
)
from app.core.opponent_quality_evidence import (
    SQLiteOpponentQualityLedger,
)


UTC = timezone.utc


def quality(ledger, opponent, value, day, char):
    ledger.append(
        ledger.build_observation(
            sport="tennis",
            opponent_canonical_id=opponent,
            quality_key="rating",
            quality_value=value,
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, day, tzinfo=UTC),
            source_record_fingerprint=char * 64,
        )
    )


def event(opponent, fpchar, competition="ATP:X", available_day=3):
    return SimpleNamespace(
        opponent_canonical_id=opponent,
        event_fingerprint=fpchar * 64,
        competition_key=competition,
        source_available_at=datetime(
            2026, 8, available_day, tzinfo=UTC
        ),
    )


def test_comparable_cohort_uses_configured_quality_delta(tmp_path):
    ledger = SQLiteOpponentQualityLedger(tmp_path / "q.db")
    quality(ledger, "tennis:player:target", 1800, 2, "a")
    quality(ledger, "tennis:player:near", 1825, 2, "b")
    quality(ledger, "tennis:player:far", 1950, 2, "c")

    policy = build_comparable_opponent_policy(
        sport="tennis",
        quality_key="rating",
        max_absolute_quality_delta=50,
    )

    cohort = build_comparable_opponent_cohort(
        events=(
            event("tennis:player:near", "d"),
            event("tennis:player:far", "e"),
        ),
        target_opponent_canonical_id="tennis:player:target",
        target_competition_key=None,
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
        policy=policy,
        quality_ledger=ledger,
    )

    assert cohort.selected_event_fingerprints == ("d" * 64,)
    assert cohort.excluded_quality_delta == 1


def test_historical_quality_is_not_retroactively_leaked(tmp_path):
    ledger = SQLiteOpponentQualityLedger(tmp_path / "q.db")
    quality(ledger, "tennis:player:target", 1800, 2, "a")
    quality(ledger, "tennis:player:hist", 1805, 5, "b")

    policy = build_comparable_opponent_policy(
        sport="tennis",
        quality_key="rating",
        max_absolute_quality_delta=50,
    )

    cohort = build_comparable_opponent_cohort(
        events=(
            event(
                "tennis:player:hist",
                "c",
                available_day=3,
            ),
        ),
        target_opponent_canonical_id="tennis:player:target",
        target_competition_key=None,
        as_of=datetime(2026, 8, 6, tzinfo=UTC),
        policy=policy,
        quality_ledger=ledger,
    )

    assert cohort.selected_event_fingerprints == ()
    assert cohort.excluded_missing_quality == 1


def test_same_competition_policy_is_explicit(tmp_path):
    ledger = SQLiteOpponentQualityLedger(tmp_path / "q.db")
    quality(ledger, "tennis:player:target", 1800, 2, "a")
    quality(ledger, "tennis:player:hist", 1800, 2, "b")

    policy = build_comparable_opponent_policy(
        sport="tennis",
        quality_key="rating",
        max_absolute_quality_delta=0,
        require_same_competition=True,
    )

    cohort = build_comparable_opponent_cohort(
        events=(event("tennis:player:hist", "c", competition="ATP:Y"),),
        target_opponent_canonical_id="tennis:player:target",
        target_competition_key="ATP:X",
        as_of=datetime(2026, 8, 5, tzinfo=UTC),
        policy=policy,
        quality_ledger=ledger,
    )

    assert cohort.excluded_competition == 1
