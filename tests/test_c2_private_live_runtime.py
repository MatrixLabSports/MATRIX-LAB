from datetime import datetime, timezone

from app.application.football.live_evidence import (
    SQLiteFootballLiveEvidenceStore,
)
from app.application.football.private_live_runtime import (
    evaluate_private_live_bundle,
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


def test_private_runtime_records_evidence(tmp_path):
    store = SQLiteFootballLiveEvidenceStore(
        tmp_path / "live.sqlite3"
    )
    result = evaluate_private_live_bundle(
        bundle=_bundle(),
        evidence_store=store,
    )
    assert result.scope_id == "PRIVATE_INTERNAL_ONLY"
    assert result.evidence is not None
    assert result.automatic_wagering is False
    assert (
        result.real_provider_execution_authorized_by_this_module
        is False
    )
