from datetime import datetime, timezone
from tools.tennis_monitoring_watchdog import evaluate_runs


NOW=datetime(2026,10,20,6,30,tzinfo=timezone.utc)


def run(created, status="completed", conclusion="success", rid=1):
    return {"id":rid,"created_at":created,"status":status,"conclusion":conclusion,"event":"schedule"}


def test_recent_success_passes():
    r=evaluate_runs([run("2026-10-20T06:15:00Z")],NOW)
    assert r["status"]=="PASS"


def test_recent_in_progress_passes():
    r=evaluate_runs([run("2026-10-20T06:20:00Z","in_progress",None)],NOW)
    assert r["status"]=="PASS"


def test_stale_run_fails():
    r=evaluate_runs([run("2026-10-20T05:40:00Z")],NOW)
    assert r["status"]=="FAIL"
    assert r["reason"]=="LATEST_RUN_STALE"


def test_recent_failed_terminal_fails_without_newer_active():
    r=evaluate_runs([run("2026-10-20T06:20:00Z","completed","failure")],NOW)
    assert r["status"]=="FAIL"
    assert r["reason"]=="LATEST_TERMINAL_RUN_FAILED"


def test_no_runs_fails():
    r=evaluate_runs([],NOW)
    assert r["status"]=="FAIL"
    assert r["reason"]=="NO_RUNS_FOUND"


def test_29_minutes_passes():
    r=evaluate_runs([run("2026-10-20T06:01:00Z")],NOW)
    assert r["status"]=="PASS"


def test_31_minutes_fails():
    r=evaluate_runs([run("2026-10-20T05:59:00Z")],NOW)
    assert r["status"]=="FAIL"
    assert r["reason"]=="LATEST_RUN_STALE"
