from datetime import datetime, timezone
import sqlite3

from app.application.football.live_evidence import (
    SQLiteFootballLiveEvidenceStore,
)
from app.application.football.live_snapshot import (
    derive_live_pressure_features,
    snapshot_from_api_football_bundle,
)
from app.providers.api_football.live_service import (
    ApiFootballLiveBundle,
)


NOW = datetime(
    2026, 8, 22, 19, 0,
    tzinfo=timezone.utc,
)


def _bundle():
    return ApiFootballLiveBundle(
        fixture_id=100,
        captured_at=NOW,
        fixture={
            "fixture": {
                "status": {
                    "short": "1H",
                    "elapsed": 32,
                }
            },
            "teams": {
                "home": {"id": 1, "name": "Home"},
                "away": {"id": 2, "name": "Away"},
            },
            "goals": {"home": 0, "away": 0},
        },
        statistics=(),
        events=(),
        live_odds=(),
        payload_fingerprints={
            "fixture": "1" * 64,
            "statistics": "2" * 64,
            "events": "3" * 64,
        },
        live_odds_requested=False,
    )


def test_live_evidence_is_durable_and_idempotent(tmp_path):
    snapshot = snapshot_from_api_football_bundle(
        _bundle()
    )
    features = derive_live_pressure_features(
        snapshot
    )
    store = SQLiteFootballLiveEvidenceStore(
        tmp_path / "live.sqlite3"
    )
    first = store.record(
        snapshot=snapshot,
        pressure_features=features,
    )
    second = store.record(
        snapshot=snapshot,
        pressure_features=features,
    )
    assert first == second
    assert store.audit_integrity() is True


def test_live_evidence_detects_storage_tamper(tmp_path):
    snapshot = snapshot_from_api_football_bundle(
        _bundle()
    )
    features = derive_live_pressure_features(
        snapshot
    )
    path = tmp_path / "live.sqlite3"
    store = SQLiteFootballLiveEvidenceStore(path)
    evidence = store.record(
        snapshot=snapshot,
        pressure_features=features,
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_live_evidence
            SET payload_json = ?
            WHERE evidence_id = ?
            """,
            ("{}", evidence.evidence_id),
        )
        connection.commit()

    assert store.audit_integrity() is False
