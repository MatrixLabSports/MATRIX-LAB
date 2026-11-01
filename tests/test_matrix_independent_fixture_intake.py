from datetime import datetime, timedelta, timezone

from tools.matrix_independent_fixture_intake import ingest


NOW = datetime(2026, 11, 1, 15, 0, tzinfo=timezone.utc)


def snapshot(provider="SofaScore", **overrides):
    data = {
        "provider": provider,
        "capture_authorized": True,
        "physical_capture_verified": True,
        "source_url": ("https://www.flashscore.co/" if provider == "Flashscore"
                       else "https://www.sofascore.com/es/football/"),
        "captured_at_utc": (NOW - timedelta(minutes=5)).isoformat(),
        "fixtures": [{
            "home": "Home FC", "away": "Away FC",
            "kickoff_utc": (NOW + timedelta(hours=2)).isoformat(),
        }],
    }
    data.update(overrides)
    return data


def test_authorized_snapshot_remains_discovery_only():
    result = ingest([snapshot()], now_utc=NOW)
    assert result["accepted_count"] == 1
    row = result["fixtures"][0]
    assert row["p_matrix"] is None
    assert row["decimal_odds"] is None
    assert row["signal_generation_authorized"] is False
    assert result["provider_network_calls"] == 0
    assert result["real_money"] == "BLOCKED"


def test_rejects_unverified_and_unauthorized_sources():
    result = ingest([
        snapshot(provider="Unknown"),
        snapshot(physical_capture_verified=False),
        snapshot(capture_authorized=False),
    ], now_utc=NOW)
    assert result["accepted_count"] == 0
    assert len(result["rejected"]) == 3


def test_rejects_stale_capture_and_past_kickoff():
    result = ingest([
        snapshot(captured_at_utc=(NOW - timedelta(hours=2)).isoformat()),
        snapshot(fixtures=[{"home": "A", "away": "B", "kickoff_utc": NOW.isoformat()}]),
    ], now_utc=NOW)
    assert result["accepted_count"] == 0


def test_deduplicates_cross_provider_without_inventing_fixture_id():
    result = ingest([snapshot(), snapshot(provider="Flashscore")], now_utc=NOW)
    assert result["accepted_count"] == 1
    assert result["fixtures"][0]["source_providers"] == ["SofaScore", "Flashscore"]


def test_rejects_naive_kickoff_and_missing_team():
    result = ingest([snapshot(fixtures=[
        {"home": "A", "away": "B", "kickoff_utc": "2026-11-01T17:00:00"},
        {"home": "A", "away": "", "kickoff_utc": (NOW + timedelta(hours=2)).isoformat()},
    ])], now_utc=NOW)
    assert result["accepted_count"] == 0
    assert len(result["rejected"]) == 2


def test_rejects_mismatched_provider_domain():
    result = ingest([snapshot(provider="Flashscore", source_url="https://www.sofascore.com/es/football/")], now_utc=NOW)
    assert result["accepted_count"] == 0
    assert result["rejected"][0]["reason"] == "SOURCE_URL_REQUIRED"
