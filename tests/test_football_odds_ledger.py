from datetime import datetime, timedelta, timezone
import json

import pytest

from app.research.football.odds_ledger import FootballOddsLedger, FootballOddsQuote
from app.application.football.odds_runtime import (
    FootballOddsSourcePolicy,
    assess_odds_quote,
    decimal_clv,
    select_closing_reference_quote,
)

UTC = timezone.utc


def quote(**overrides):
    quoted = datetime(2026, 8, 18, 18, 0, tzinfo=UTC)
    data = dict(
        provider="the_odds_api",
        provider_event_id="evt-1",
        fixture_id="fx-1",
        bookmaker="pinnacle",
        market_key="h2h",
        selection_key="Home",
        decimal_odds=2.05,
        quoted_at=quoted,
        captured_at=quoted + timedelta(seconds=2),
        phase="PREMATCH",
        quote_role="REFERENCE",
        source_payload_sha256="a" * 64,
        source_reference="provider:test",
    )
    data.update(overrides)
    return FootballOddsQuote(**data)


def test_quote_requires_timezone_and_valid_role():
    with pytest.raises(ValueError):
        quote(quoted_at=datetime(2026, 8, 18, 18, 0))
    with pytest.raises(ValueError):
        quote(quote_role="UNKNOWN")


def test_odds_gate_accepts_authorized_fresh_quote():
    decision = assess_odds_quote(quote())
    assert decision.accepted is True
    assert decision.blocked_reasons == ()


def test_odds_gate_rejects_unauthorized_provider_and_stale_capture():
    q = quote(provider="unknown", captured_at=datetime(2026, 8, 18, 18, 3, tzinfo=UTC))
    decision = assess_odds_quote(q)
    assert decision.accepted is False
    assert "odds_provider_not_authorized" in decision.blocked_reasons
    assert "odds_capture_delay_exceeded" in decision.blocked_reasons


def test_odds_ledger_append_and_verify(tmp_path):
    ledger = FootballOddsLedger(tmp_path / "odds.jsonl")
    first = ledger.append(quote())
    second = ledger.append(quote(quoted_at=quote().quoted_at + timedelta(minutes=1), captured_at=quote().captured_at + timedelta(minutes=1)))
    assert first.sequence == 1
    assert second.sequence == 2
    assert len(ledger.load()) == 2


def test_odds_ledger_rejects_duplicate_identity(tmp_path):
    ledger = FootballOddsLedger(tmp_path / "odds.jsonl")
    ledger.append(quote())
    with pytest.raises(ValueError, match="duplicate"):
        ledger.append(quote(decimal_odds=2.10))


def test_odds_ledger_detects_tampering(tmp_path):
    ledger = FootballOddsLedger(tmp_path / "odds.jsonl")
    ledger.append(quote())
    raw = json.loads((tmp_path / "odds.jsonl").read_text(encoding="utf-8"))
    raw["quote"]["decimal_odds"] = 9.99
    (tmp_path / "odds.jsonl").write_text(json.dumps(raw) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        ledger.load()


def test_select_closing_reference_quote_uses_latest_valid_prekickoff():
    kickoff = datetime(2026, 8, 18, 19, 0, tzinfo=UTC)
    quotes = [
        quote(quoted_at=kickoff - timedelta(minutes=9), captured_at=kickoff - timedelta(minutes=9) + timedelta(seconds=1)),
        quote(quoted_at=kickoff - timedelta(minutes=2), captured_at=kickoff - timedelta(minutes=2) + timedelta(seconds=1), decimal_odds=1.95),
        quote(quoted_at=kickoff + timedelta(seconds=1), captured_at=kickoff + timedelta(seconds=2), decimal_odds=1.90),
    ]
    closing = select_closing_reference_quote(
        quotes,
        fixture_id="fx-1",
        market_key="h2h",
        selection_key="Home",
        kickoff_at=kickoff,
    )
    assert closing is not None
    assert closing.decimal_odds == 1.95


def test_select_closing_reference_quote_rejects_too_old():
    kickoff = datetime(2026, 8, 18, 19, 0, tzinfo=UTC)
    closing = select_closing_reference_quote(
        [quote(quoted_at=kickoff - timedelta(minutes=20), captured_at=kickoff - timedelta(minutes=20) + timedelta(seconds=1))],
        fixture_id="fx-1",
        market_key="h2h",
        selection_key="Home",
        kickoff_at=kickoff,
    )
    assert closing is None


def test_decimal_clv():
    assert decimal_clv(2.10, 2.00) == pytest.approx(0.05)
    with pytest.raises(ValueError):
        decimal_clv(1.0, 2.0)
