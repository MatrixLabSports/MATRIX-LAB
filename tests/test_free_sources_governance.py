import pytest

from app.providers import free_sources


def test_activation_state_does_not_claim_unverified_source_active(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_ORG_TOKEN", "configured")
    monkeypatch.setenv("LIVE_TENNIS_API_KEY", "configured")
    state = free_sources.activation_state()
    assert state["football-data.org"] == "CONFIGURED_NOT_VERIFIED"
    assert state["Live-Tennis-API-free"] == "CONFIGURED_NOT_VERIFIED"


def test_missing_football_data_token_fails_closed(monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_ORG_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="FOOTBALL_DATA_ORG_TOKEN_MISSING"):
        free_sources.football_data_matches("2026-10-06", "2026-10-06")


def test_missing_live_tennis_key_fails_closed(monkeypatch):
    monkeypatch.delenv("LIVE_TENNIS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LIVE_TENNIS_API_KEY_MISSING"):
        free_sources.live_tennis_fixtures("itf", "singles")


def test_thesportsdb_is_explicitly_secondary():
    state = free_sources.activation_state()
    assert state["TheSportsDB-v1-free"] == "PUBLIC_FREE_KEY_AVAILABLE"


def test_source_response_is_immutable():
    response = free_sources.SourceResponse("test", "2026-10-06T00:00:00Z", {"ok": True})
    with pytest.raises(Exception):
        response.source = "changed"
