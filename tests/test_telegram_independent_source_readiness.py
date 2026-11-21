from datetime import datetime, timezone, timedelta
from tools.telegram_independent_source_readiness import assess


def example(now):
    stamp = now.isoformat()
    return {
        "discovery": {"source_order": ["SOFASCORE", "FLASHSCORE"], "fixture_verified": True, "evidence_path": "evidence/fixture.json"},
        "quote": {"verified": True, "evidence_path": "evidence/quote.json", "colombia_authorized": True, "market": "TOTAL_GOALS_OVER_UNDER", "selection": "OVER_2_5", "fixture_id": "123", "bookmaker": "book", "decimal_odds": 1.9, "p_matrix": 0.65, "kickoff_utc": (now + timedelta(hours=1)).isoformat(), "updated_at_utc": stamp},
        "sharp": {"verified": True, "evidence_path": "evidence/sharp.json", "fixture_id": "123", "updated_at_utc": stamp},
        "governance_pass": True, "correlation_pass": True,
    }


def test_readiness_never_sends():
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    result = assess(example(now), now)
    assert result["status"] == "SHADOW_READINESS_ONLY"
    assert result["paid_api_calls"] == result["independent_api_calls"] == result["telegram_calls"] == 0
    assert result["telegram_delivery_certified"] is False


def test_missing_independent_sources_fail_closed():
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    data = example(now)
    data["discovery"]["source_order"] = ["API_FOOTBALL"]
    data["quote"]["verified"] = False
    result = assess(data, now)
    assert result["status"] == "BLOCKED"
    assert "DISCOVERY_ORDER_UNVERIFIED" in result["blockers"]


def test_stale_quote_fails_closed():
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    data = example(now)
    data["quote"]["updated_at_utc"] = (now - timedelta(minutes=3)).isoformat()
    assert "BOOK_STALE" in assess(data, now)["blockers"]


def test_started_fixture_fails_closed():
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    data = example(now)
    data["quote"]["kickoff_utc"] = (now - timedelta(minutes=1)).isoformat()
    assert "KICKOFF_NOT_FUTURE" in assess(data, now)["blockers"]


def test_ev_gate_fails_closed():
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    data = example(now)
    data["quote"]["decimal_odds"] = 1.51
    assert "PRICE_PROBABILITY_OR_EV_GATE" in assess(data, now)["blockers"]
