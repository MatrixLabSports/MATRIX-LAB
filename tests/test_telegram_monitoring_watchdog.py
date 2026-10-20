from datetime import datetime, timedelta, timezone

from tools.telegram_monitoring_watchdog import evaluate_watchdog


NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _ledger(last_run_minutes_ago: int = 10) -> dict:
    return {
        "run_history": [
            {"run_at_utc": (NOW - timedelta(minutes=last_run_minutes_ago)).isoformat()}
        ],
        "candidate_lifecycle": {},
    }


def test_watchdog_passes_when_supervisor_is_fresh_and_no_critical_gap():
    ledger = _ledger()
    ledger["candidate_lifecycle"]["a"] = {
        "fixture_id": "fx-a",
        "match": "A vs B",
        "kickoff": (NOW + timedelta(minutes=90)).isoformat(),
        "final_revalidation_attempts": 0,
        "monitoring_breach": False,
    }
    report = evaluate_watchdog(ledger, NOW)
    assert report["summary"]["status"] == "PASS"
    assert report["summary"]["failures"] == 0


def test_watchdog_fails_closed_when_supervisor_is_stale():
    report = evaluate_watchdog(_ledger(last_run_minutes_ago=36), NOW)
    assert report["summary"]["status"] == "FAIL_CLOSED"
    assert any(x["code"] == "SUPERVISOR_STALE" for x in report["failures"])


def test_watchdog_fails_when_candidate_is_under_30_minutes_without_revalidation():
    ledger = _ledger()
    ledger["candidate_lifecycle"]["critical"] = {
        "fixture_id": "fx-critical",
        "match": "C vs D",
        "kickoff": (NOW + timedelta(minutes=20)).isoformat(),
        "final_revalidation_attempts": 0,
        "monitoring_breach": False,
    }
    report = evaluate_watchdog(ledger, NOW)
    assert report["summary"]["status"] == "FAIL_CLOSED"
    assert report["summary"]["critical_unresolved_candidates"] == 1
    assert any(x["code"] == "CRITICAL_PREMATCH_WITHOUT_REVALIDATION" for x in report["failures"])


def test_watchdog_accepts_critical_candidate_after_revalidation_attempt():
    ledger = _ledger()
    ledger["candidate_lifecycle"]["critical"] = {
        "fixture_id": "fx-critical",
        "match": "C vs D",
        "kickoff": (NOW + timedelta(minutes=20)).isoformat(),
        "final_revalidation_attempts": 1,
        "monitoring_breach": False,
    }
    report = evaluate_watchdog(ledger, NOW)
    assert report["summary"]["status"] == "PASS"


def test_watchdog_fails_if_any_real_monitoring_breach_is_persisted():
    ledger = _ledger()
    ledger["candidate_lifecycle"]["breach"] = {
        "fixture_id": "fx-breach",
        "match": "E vs F",
        "kickoff": (NOW - timedelta(minutes=1)).isoformat(),
        "final_revalidation_attempts": 0,
        "monitoring_breach": True,
    }
    report = evaluate_watchdog(ledger, NOW)
    assert report["summary"]["status"] == "FAIL_CLOSED"
    assert report["summary"]["monitoring_breaches"] == 1
    assert any(x["code"] == "NEW_MONITORING_BREACH_PRESENT" for x in report["failures"])
