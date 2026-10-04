from datetime import datetime, timedelta, timezone

from app.research.football.odds_ledger import FootballOddsLedger, FootballOddsQuote
from tools.api_football_pinnacle_snapshot_age_audit import (
    API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS,
    STRICT_FRESH_SECONDS,
    audit_snapshot_age,
)


UTC = timezone.utc


def _quote(fixture_id: str, age_seconds: int, selection: str) -> FootballOddsQuote:
    captured = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    quoted = captured - timedelta(seconds=age_seconds)
    return FootballOddsQuote(
        provider="api_football",
        provider_event_id=fixture_id,
        fixture_id=fixture_id,
        bookmaker="Pinnacle",
        market_key="match_winner",
        selection_key=selection,
        decimal_odds=2.0,
        quoted_at=quoted,
        captured_at=captured,
        phase="PREMATCH",
        quote_role="REFERENCE",
        source_payload_sha256="a" * 64,
        source_reference=f"test:{fixture_id}:{selection}",
    )


def _shadow():
    rows = []
    for fixture_id in ("1", "2", "3"):
        rows.append({
            "fixture_id": fixture_id,
            "target_key": f"api_football:fixture:{fixture_id}",
            "kickoff_utc": "2026-09-28T18:00:00+00:00",
            "freeze_at_utc": "2026-09-28T12:01:00+00:00",
        })
    return {
        "model_role": "RESEARCH_SHADOW_BASELINE",
        "model_status": "EXPERIMENTAL_NOT_PROMOTED",
        "p_matrix_status": "NOT_GENERATED",
        "protections": {
            "odds_used_to_generate_probability": False,
            "outcomes_used_to_generate_probability": False,
            "real_money": "BLOCKED",
        },
        "rows": rows,
    }


def test_snapshot_age_bands_do_not_change_strict_gate(tmp_path):
    ledger = FootballOddsLedger(tmp_path / "odds.jsonl")
    ledger.append_many([
        _quote("1", STRICT_FRESH_SECONDS, "Home"),
        _quote("2", 3600, "Home"),
        _quote("3", API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS + 1, "Home"),
    ])

    audit, manifest = audit_snapshot_age(shadow=_shadow(), ledger=ledger)

    assert manifest["status"] == "PASS"
    assert manifest["strict_120s_gate_changed"] is False
    assert manifest["strict_fresh_quote_count"] == 1
    assert manifest["within_documented_3h_quote_count"] == 2
    assert manifest["older_than_documented_3h_quote_count"] == 1
    assert manifest["fixture_count_with_strict_fresh_reference"] == 1
    assert manifest["fixture_count_with_reference_within_documented_3h"] == 2
    assert manifest["closing_reference_status"] == "NOT_ESTABLISHED_FROM_API_FOOTBALL_PREMATCH"
    assert manifest["p_matrix_status"] == "NOT_GENERATED"
    assert manifest["real_money"] == "BLOCKED"

    assert audit["governance"]["strict_120s_gate_changed"] is False
    assert audit["governance"]["nominal_3h_band_is_closing_reference"] is False
    assert audit["governance"]["nominal_3h_band_is_execution_reference"] is False
    assert audit["governance"]["nominal_3h_band_may_generate_model_probability"] is False


def test_quote_captured_after_shadow_freeze_is_chronology_rejected(tmp_path):
    ledger = FootballOddsLedger(tmp_path / "odds.jsonl")
    quote = FootballOddsQuote(
        provider="api_football",
        provider_event_id="1",
        fixture_id="1",
        bookmaker="Pinnacle",
        market_key="match_winner",
        selection_key="Home",
        decimal_odds=2.0,
        quoted_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        captured_at=datetime(2026, 9, 28, 12, 2, tzinfo=UTC),
        phase="PREMATCH",
        quote_role="REFERENCE",
        source_payload_sha256="b" * 64,
        source_reference="test:late",
    )
    ledger.append(quote)

    audit, manifest = audit_snapshot_age(shadow=_shadow(), ledger=ledger)

    assert audit["chronologically_eligible_quote_count"] == 0
    assert audit["chronology_rejected_quote_count"] == 1
    assert manifest["strict_fresh_quote_count"] == 0
    assert manifest["fixture_count_with_any_reference"] == 0
