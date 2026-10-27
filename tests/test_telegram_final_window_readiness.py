from datetime import datetime, timezone

from tools.telegram_final_window_readiness import build, next_quarter_hour


def test_next_quarter_hour_preserves_exact_boundary():
    dt = datetime(2026, 10, 27, 10, 30, tzinfo=timezone.utc)
    assert next_quarter_hour(dt) == dt


def test_waiting_candidate_is_covered_inside_120m_window_without_backfill():
    payload = {
        "records": [{
            "fixture_id": "1647233",
            "match": "Asia Talas vs OshMU Aldier",
            "kickoff": "2026-10-27T12:30:00+00:00",
            "gate_state": "WAITING_FINAL_REVALIDATION_WINDOW",
            "sources_available_for_recovery": [
                "API-Football", "odds-api.net", "Betano", "BetPlay", "Betsson", "Bwin",
                "Codere", "Luckia", "MrYoker", "Rivalo", "Rushbet", "Sportium",
                "Stake", "Wplay", "YaJuego", "Zamba"
            ],
        }]
    }
    out = build(payload, datetime(2026, 10, 27, 10, 8, tzinfo=timezone.utc))
    assert out["status"] == "PASS"
    assert out["summary"]["waiting_candidates"] == 1
    row = out["candidates"][0]
    assert row["window_opens_utc"] == "2026-10-27T10:30:00+00:00"
    assert row["next_supervisor_cycle_utc"] == "2026-10-27T10:30:00+00:00"
    assert row["window_covered_by_15m_supervisor"] is True
    assert row["source_contract_pass"] is True


def test_missing_programmatic_quote_source_fails_closed():
    payload = {
        "records": [{
            "fixture_id": "x",
            "match": "A vs B",
            "kickoff": "2026-10-27T13:00:00+00:00",
            "gate_state": "WAITING_FINAL_REVALIDATION_WINDOW",
            "sources_available_for_recovery": ["API-Football", "Betano"],
        }]
    }
    out = build(payload, datetime(2026, 10, 27, 10, 8, tzinfo=timezone.utc))
    assert out["status"] == "FAIL_CLOSED"
    assert out["failures"][0]["code"] == "PROGRAMMATIC_QUOTE_SOURCE_CONTRACT_MISSING"


def test_physical_books_are_not_misrepresented_as_live_api_queries():
    payload = {"records": []}
    out = build(payload, datetime(2026, 10, 27, 10, 8, tzinfo=timezone.utc))
    assert out["source_scope"]["physical_sources_are_not_claimed_as_live_api_queries"] is True
    assert out["contracts"]["automatic_wagering"] is False
    assert out["contracts"]["real_money"] == "BLOCKED"
