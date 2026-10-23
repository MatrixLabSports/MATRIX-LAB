from datetime import datetime, timezone

from tools.telegram_green_signal_alerts import (
    ODDS_API_NET_EVENT_SEARCH_WINDOW_SECONDS,
    build_blocker_recovery_audit,
)


def test_odds_event_search_window_is_two_hours_each_side():
    assert ODDS_API_NET_EVENT_SEARCH_WINDOW_SECONDS == 7200


def test_blocker_audit_never_marks_past_kickoff_quote_gap_recoverable():
    now = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
    key = "k"
    ledger = {
        "pre_send_gate": {
            key: {
                "state": "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25",
                "checked_at_utc": "2026-10-23T17:56:32+00:00",
                "odds_api_net_diagnostic": {
                    "status": "BLOCKED_EVENT_NOT_COVERED",
                    "discard_reasons": {},
                },
            }
        }
    }
    candidates = {
        key: {
            "sport": "football",
            "fixture_id": "123",
            "match": "A vs B",
            "league_id": "1",
            "kickoff": "2026-10-23T17:00:00+00:00",
            "p_matrix": 0.64,
            "house": "MULTIBOOK_REVALIDATION",
            "odds": None,
            "ev": None,
        }
    }
    out = build_blocker_recovery_audit(ledger, candidates, set(), now)
    assert out["summary"]["counts_by_recoverability"] == {
        "NOT_RECOVERABLE_NO_BACKFILL": 1
    }
    row = out["records"][0]
    assert row["time_state_at_audit"] == "PAST_KICKOFF"
    assert row["final_disposition"] == "PAST_KICKOFF_NO_BACKFILL"
    assert row["sources_available_for_recovery"] == []
