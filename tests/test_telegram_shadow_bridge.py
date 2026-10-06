from datetime import datetime, timezone
from tools.telegram_shadow_bridge import adjudicate

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def base_payload():
    return {
        "target_date_bogota": "2026-10-05",
        "model_status": {"daily_p_matrix": "GENERATED", "real_money": "BLOCKED"},
        "protections": {"automatic_wagering": False, "real_money": "BLOCKED"},
        "candidates": [{
            "match": "A vs B", "market": "OVER_2_5", "adjudication": "AUTHORIZED_SHADOW",
            "p_matrix": 0.62, "observed_decimal_odds": 1.80,
            "freeze_timestamp_utc": "2026-10-05T11:30:00Z",
            "event_start_utc": "2026-10-05T18:00:00Z"
        }]
    }


def test_valid_shadow_candidate_is_eligible():
    r = adjudicate(base_payload(), NOW)
    assert r["status"] == "ELIGIBLE"
    assert r["eligible_count"] == 1
    assert r["real_money"] == "BLOCKED"
    assert r["automatic_wagering"] is False


def test_missing_daily_p_matrix_fails_closed():
    p = base_payload(); p["model_status"]["daily_p_matrix"] = "NOT_GENERATED"
    r = adjudicate(p, NOW)
    assert r["status"] == "BLOCKED"
    assert "P_MATRIX_NOT_GENERATED" in r["global_block_reasons"]


def test_research_signal_never_promoted():
    p = base_payload(); p["candidates"][0]["adjudication"] = "RESEARCH_SIGNAL_NOT_EXECUTION_AUTHORIZED"
    assert adjudicate(p, NOW)["eligible_count"] == 0


def test_odds_floor_is_strictly_above_150():
    p = base_payload(); p["candidates"][0]["observed_decimal_odds"] = 1.50
    assert adjudicate(p, NOW)["eligible_count"] == 0


def test_post_start_is_blocked():
    p = base_payload(); p["candidates"][0]["event_start_utc"] = "2026-10-05T10:00:00Z"
    assert adjudicate(p, NOW)["eligible_count"] == 0


def test_nonpositive_ev_is_blocked():
    p = base_payload(); p["candidates"][0]["p_matrix"] = 0.51; p["candidates"][0]["observed_decimal_odds"] = 1.80
    assert adjudicate(p, NOW)["eligible_count"] == 0
