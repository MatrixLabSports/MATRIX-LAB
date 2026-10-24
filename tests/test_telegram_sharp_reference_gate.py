from tools.telegram_green_signal_alerts import (
    augment_sharp_diagnostic_with_api_football_fallback,
    sharp_reference_gate_state,
)


def test_pinnacle_single_fresh_reference_passes_primary_sharp_gate():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "SINGLE_SHARP_REFERENCE_ONLY",
            "sharp_rows": [
                {"source": "pinnacle", "quote_age_seconds": 45}
            ],
        }
    })
    assert state == "PASS_SHARP_REFERENCE_GATE"
    assert detail["pinnacle_present"] is True
    assert detail["fanduel_counts_as_sharp"] is False
    assert detail["p_matrix_mutated_by_odds"] is False


def test_fanduel_context_never_satisfies_sharp_gate():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "INSUFFICIENT_SHARP_COVERAGE",
            "sharp_rows": [],
            "market_context_rows": [
                {"source": "fanduel", "quote_age_seconds": 20}
            ],
        }
    })
    assert state == "BLOCKED_NO_FRESH_PINNACLE_REFERENCE"
    assert detail["pinnacle_present"] is False


def test_circa_without_pinnacle_does_not_replace_primary_sharp():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "SINGLE_SHARP_REFERENCE_ONLY",
            "sharp_rows": [
                {"source": "circa", "quote_age_seconds": 30}
            ],
        }
    })
    assert state == "BLOCKED_NO_FRESH_PINNACLE_REFERENCE"
    assert detail["circa_present"] is True
    assert detail["pinnacle_present"] is False


def test_pinnacle_plus_circa_contradiction_blocks_signal():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "CONTRADICTION_REVIEW",
            "sharp_rows": [
                {"source": "pinnacle", "quote_age_seconds": 25},
                {"source": "circa", "quote_age_seconds": 35},
            ],
        }
    })
    assert state == "BLOCKED_SHARP_CONTRADICTION"
    assert detail["pinnacle_present"] is True
    assert detail["circa_present"] is True


def test_pinnacle_plus_betfair_aligned_passes():
    state, detail = sharp_reference_gate_state({
        "sharp_consensus": {
            "status": "PASS_ALIGNED",
            "sharp_rows": [
                {"source": "pinnacle", "quote_age_seconds": 15},
                {"source": "betfair", "quote_age_seconds": 10},
            ],
        }
    })
    assert state == "PASS_SHARP_REFERENCE_GATE"
    assert detail["betfair_present"] is True


class _FakeResponse:
    status_code = 200

    def json(self):
        return {
            "errors": {},
            "response": [
                {
                    "update": "2026-10-24T09:59:30+00:00",
                    "bookmakers": [
                        {
                            "id": 4,
                            "name": "Pinnacle",
                            "bets": [
                                {
                                    "id": 5,
                                    "name": "Goals Over/Under",
                                    "values": [
                                        {"value": "Over 2.5", "odd": "1.91"},
                                        {"value": "Under 2.5", "odd": "1.95"},
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }


class _FakeSession:
    def get(self, url, headers=None, params=None, timeout=None):
        assert params == {"fixture": "123", "bookmaker": 4}
        return _FakeResponse()


def test_api_football_pinnacle_fallback_can_satisfy_primary_sharp_gate(monkeypatch):
    from datetime import datetime, timezone
    import tools.telegram_green_signal_alerts as mod

    monkeypatch.setattr(
        mod,
        "now_utc",
        lambda: datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc),
    )
    diagnostic = {
        "sharp_quote_rows": [],
        "sharp_consensus": {
            "status": "INSUFFICIENT_SHARP_COVERAGE",
            "sharp_rows": [],
        },
    }
    out = augment_sharp_diagnostic_with_api_football_fallback(
        diagnostic,
        session=_FakeSession(),
        api_key="x",
        fixture_id="123",
        p=0.67,
    )
    state, detail = sharp_reference_gate_state(out)
    assert state == "PASS_SHARP_REFERENCE_GATE"
    assert detail["pinnacle_present"] is True
    assert out["api_football_pinnacle_fallback"]["status"] == "PASS_FRESH_PINNACLE_REFERENCE"
    assert out["api_football_pinnacle_fallback"]["provider_quote_age_seconds"] == 30
    assert out["sharp_consensus"]["status"] == "SINGLE_SHARP_REFERENCE_ONLY"


def test_api_football_pinnacle_fallback_remains_fail_closed_when_stale(monkeypatch):
    from datetime import datetime, timezone
    import tools.telegram_green_signal_alerts as mod

    monkeypatch.setattr(
        mod,
        "now_utc",
        lambda: datetime(2026, 10, 24, 10, 3, 0, tzinfo=timezone.utc),
    )
    diagnostic = {
        "sharp_quote_rows": [],
        "sharp_consensus": {
            "status": "INSUFFICIENT_SHARP_COVERAGE",
            "sharp_rows": [],
        },
    }
    out = augment_sharp_diagnostic_with_api_football_fallback(
        diagnostic,
        session=_FakeSession(),
        api_key="x",
        fixture_id="123",
        p=0.67,
    )
    state, detail = sharp_reference_gate_state(out)
    assert state == "BLOCKED_NO_FRESH_PINNACLE_REFERENCE"
    assert detail["pinnacle_present"] is False
    assert out["api_football_pinnacle_fallback"]["status"] == "BLOCKED_STALE_PINNACLE_REFERENCE"
