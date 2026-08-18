from datetime import datetime, timezone

from app.providers.the_odds_api.adapter import adapt_the_odds_api_event

UTC = timezone.utc


def sample_event():
    return {
        "id": "event-123",
        "sport_key": "soccer_epl",
        "commence_time": "2026-08-18T19:00:00Z",
        "home_team": "Alpha",
        "away_team": "Beta",
        "bookmakers": [
            {
                "key": "pinnacle",
                "title": "Pinnacle",
                "last_update": "2026-08-18T18:55:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Alpha", "price": 2.10},
                            {"name": "Beta", "price": 3.20},
                            {"name": "Draw", "price": 3.00},
                        ],
                    },
                    {"key": "unsupported", "outcomes": [{"name": "x", "price": 2.0}]},
                ],
            }
        ],
    }


def test_adapter_creates_canonical_quotes_with_provider_timestamp():
    captured = datetime(2026, 8, 18, 18, 55, 2, tzinfo=UTC)
    quotes = adapt_the_odds_api_event(sample_event(), fixture_id="fx-1", captured_at=captured)
    assert len(quotes) == 3
    assert all(q.provider == "the_odds_api" for q in quotes)
    assert all(q.quoted_at.isoformat() == "2026-08-18T18:55:00+00:00" for q in quotes)
    assert all(q.captured_at == captured for q in quotes)
    assert {q.selection_key for q in quotes} == {"Alpha", "Beta", "Draw"}


def test_adapter_source_hash_changes_if_payload_changes():
    captured = datetime(2026, 8, 18, 18, 55, 2, tzinfo=UTC)
    event = sample_event()
    first = adapt_the_odds_api_event(event, fixture_id="fx-1", captured_at=captured)[0]
    event["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = 2.20
    second = adapt_the_odds_api_event(event, fixture_id="fx-1", captured_at=captured)[0]
    assert first.source_payload_sha256 != second.source_payload_sha256
