from datetime import datetime, timezone
from types import SimpleNamespace
import sqlite3

import pytest

from app.application.football.history_profile_evidence import (
    record_football_history_profile,
)
from app.application.football.professional_history_profile import (
    build_football_history_profile,
)
from app.application.tennis.history_profile_evidence import (
    record_tennis_history_profile,
)
from app.application.tennis.professional_history_profile import (
    build_tennis_history_profile,
)
from app.core.history_profile_evidence import (
    SQLiteHistoryProfileEvidenceStore,
)
from app.core.point_in_time_history import (
    build_point_in_time_history,
)


UTC = timezone.utc


def tennis_profile():
    event = SimpleNamespace(
        event_key="T:1",
        event_at=datetime(
            2026,
            8,
            1,
            10,
            tzinfo=UTC,
        ),
        season_key="2026",
        competition_key="ATP:X",
        opponent_canonical_id="tennis:player:op",
        outcome="W",
        completed=True,
        retirement=False,
        surface="hard",
        indoor=False,
        metrics={"aces": 5},
        source_record_fingerprint="a" * 64,
        source_available_at=datetime(
            2026,
            8,
            1,
            12,
            tzinfo=UTC,
        ),
        event_fingerprint="b" * 64,
    )
    history = build_point_in_time_history(
        sport="tennis",
        canonical_id="tennis:player:subject",
        events=(event,),
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        season_key="2026",
    )
    return build_tennis_history_profile(
        history=history,
        target_surface="hard",
    )


def football_profile():
    event = SimpleNamespace(
        event_key="F:1",
        event_at=datetime(
            2026,
            8,
            1,
            10,
            tzinfo=UTC,
        ),
        season_key="2026",
        competition_key="L:X",
        opponent_canonical_id="football:team:op",
        outcome="W",
        completed=True,
        venue="home",
        metrics={"goals_for": 2},
        source_record_fingerprint="c" * 64,
        source_available_at=datetime(
            2026,
            8,
            1,
            12,
            tzinfo=UTC,
        ),
        event_fingerprint="d" * 64,
    )
    history = build_point_in_time_history(
        sport="football",
        canonical_id="football:team:subject",
        events=(event,),
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
        season_key="2026",
    )
    return build_football_history_profile(
        history=history,
        target_venue="home",
    )


def test_tennis_profile_evidence_is_durable(tmp_path):
    store = SQLiteHistoryProfileEvidenceStore(
        tmp_path / "history.db"
    )
    profile = tennis_profile()

    evidence = record_tennis_history_profile(
        store=store,
        profile=profile,
    )

    assert evidence.sport == "tennis"
    assert store.audit_integrity().ok is True


def test_football_profile_evidence_is_durable(tmp_path):
    store = SQLiteHistoryProfileEvidenceStore(
        tmp_path / "history.db"
    )
    profile = football_profile()

    evidence = record_football_history_profile(
        store=store,
        profile=profile,
    )

    assert evidence.sport == "football"


def test_exact_replay_is_idempotent(tmp_path):
    store = SQLiteHistoryProfileEvidenceStore(
        tmp_path / "history.db"
    )
    profile = tennis_profile()

    first = store.record_profile(profile)
    second = store.record_profile(profile)

    assert first.evidence_id == second.evidence_id
    assert store.audit_integrity().records == 1


def test_cross_sport_adapter_rejects_profile(tmp_path):
    store = SQLiteHistoryProfileEvidenceStore(
        tmp_path / "history.db"
    )

    with pytest.raises(
        ValueError,
        match="SPORT_BOUNDARY_VIOLATION",
    ):
        record_football_history_profile(
            store=store,
            profile=tennis_profile(),
        )


def test_tampering_is_detected(tmp_path):
    path = tmp_path / "history.db"
    store = SQLiteHistoryProfileEvidenceStore(path)
    profile = tennis_profile()
    store.record_profile(profile)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE history_profile_evidence
            SET payload_json = ?
            WHERE profile_fingerprint = ?
            """,
            (
                '{"tampered":true}\n',
                profile.profile_fingerprint,
            ),
        )
        connection.commit()

    assert store.audit_integrity().ok is False
