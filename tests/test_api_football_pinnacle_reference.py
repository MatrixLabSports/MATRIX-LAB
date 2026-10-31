import json
from datetime import datetime, timedelta, timezone

from app.application.football.odds_runtime import select_closing_reference_quote
from app.providers.api_football.pinnacle_reference import parse_pinnacle_reference_quotes
from app.research.football.odds_ledger import FootballOddsLedger, FootballOddsQuote

UTC = timezone.utc


def _payload():
    return {
        "errors": [],
        "response": [{
            "fixture": {"id": 123},
            "update": "2026-09-28T07:00:00+00:00",
            "bookmakers": [{
                "id": 4,
                "name": "Pinnacle",
                "bets": [
                    {
                        "id": 1,
                        "name": "Match Winner",
                        "values": [
                            {"value": "Home", "odd": "1.90"},
                            {"value": "Draw", "odd": "3.20"},
                            {"value": "Away", "odd": "4.00"},
                        ],
                    },
                    {
                        "id": 5,
                        "name": "Goals Over/Under",
                        "values": [
                            {"value": "Over 2.5", "odd": "1.95"},
                            {"value": "Under 2.5", "odd": "1.87"},
                        ],
                    },
                ],
            }],
        }],
    }


def test_parse_pinnacle_quotes_as_reference():
    raw = json.dumps(_payload()).encode()
    result = parse_pinnacle_reference_quotes(
        raw,
        captured_at=datetime(2026, 9, 28, 7, 0, 10, tzinfo=UTC),
        source_reference="raw:test",
    )
    assert len(result.quotes) == 5
    assert result.fixture_ids == ("123",)
    assert set(result.market_keys) == {"match_winner", "total_goals"}
    assert all(q.provider == "api_football" for q in result.quotes)
    assert all(q.bookmaker == "Pinnacle" for q in result.quotes)
    assert all(q.quote_role == "REFERENCE" for q in result.quotes)


def test_batch_append_is_hash_verified(tmp_path):
    parsed = parse_pinnacle_reference_quotes(
        json.dumps(_payload()).encode(),
        captured_at=datetime(2026, 9, 28, 7, 0, 10, tzinfo=UTC),
        source_reference="raw:test",
    )
    ledger = FootballOddsLedger(tmp_path / "ledger.jsonl")
    entries = ledger.append_many(parsed.quotes)
    assert len(entries) == 5
    assert len(ledger.load(verify=True)) == 5


def _quote(bookmaker, quoted_at, captured_at, odds):
    return FootballOddsQuote(
        provider="api_football",
        provider_event_id="123",
        fixture_id="123",
        bookmaker=bookmaker,
        market_key="match_winner",
        selection_key="Home",
        decimal_odds=odds,
        quoted_at=quoted_at,
        captured_at=captured_at,
        phase="PREMATCH",
        quote_role="REFERENCE",
        source_payload_sha256="a" * 64,
        source_reference="test",
    )


def test_closing_reference_prefers_pinnacle_when_both_are_valid():
    kickoff = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)
    pinnacle_time = kickoff - timedelta(minutes=5)
    other_time = kickoff - timedelta(minutes=2)
    quotes = [
        _quote("Pinnacle", pinnacle_time, pinnacle_time + timedelta(seconds=1), 1.95),
        _quote("Bet365", other_time, other_time + timedelta(seconds=1), 1.97),
    ]
    selected = select_closing_reference_quote(
        quotes,
        fixture_id="123",
        market_key="match_winner",
        selection_key="Home",
        kickoff_at=kickoff,
    )
    assert selected is not None
    assert selected.bookmaker == "Pinnacle"
    assert selected.decimal_odds == 1.95


def test_odds_never_become_model_probability():
    parsed = parse_pinnacle_reference_quotes(
        json.dumps(_payload()).encode(),
        captured_at=datetime(2026, 9, 28, 7, 0, 10, tzinfo=UTC),
        source_reference="raw:test",
    )
    assert not hasattr(parsed.quotes[0], "model_probability")
