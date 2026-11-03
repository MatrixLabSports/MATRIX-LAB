from datetime import datetime,timedelta,timezone
import pytest
from tools.matrix_browser_capture_watchdog import check

NOW=datetime(2026,11,3,18,8,tzinfo=timezone.utc)

def row(age,status="completed",conclusion="success",identifier=10):
    return {"id":identifier,"created_at":(NOW-timedelta(seconds=age)).isoformat(),
            "status":status,"conclusion":conclusion}

def test_fresh_success_does_not_repeat_capture():
    d=check([row(300)],now=NOW)
    assert not d["dispatch"]
    assert d["reason"]=="RECENT_SUCCESSFUL_BROWSER_RUN"

def test_missing_browser_workflow_after_window_activates_backup():
    d=check([row(1600)],now=NOW)
    assert d["dispatch"]
    assert d["reason"]=="LAST_BROWSER_RUN_STALE"

def test_failed_capture_requires_backup_immediately():
    d=check([row(250,"completed","failure")],now=NOW)
    assert d["dispatch"]
    assert d["reason"]=="LAST_BROWSER_RUN_NOT_SUCCESSFUL"

def test_busy_windows_runner_never_cascades_dispatches():
    d=check([row(2500,"in_progress",None)],now=NOW)
    assert not d["dispatch"]
    assert d["reason"]=="BROWSER_RUN_ALREADY_PENDING"

def test_most_recent_run_wins_and_no_second_dispatch():
    d=check([row(5000,identifier=20),row(70,identifier=30)],now=NOW)
    assert not d["dispatch"]
    assert d["last_run_id"]==30

def test_future_timestamp_fail_closed():
    x={"id":15,"created_at":(NOW+timedelta(minutes=8)).isoformat(),
       "status":"completed","conclusion":"success"}
    d=check([x],now=NOW)
    assert not d["dispatch"]
    assert d["reason"]=="CLOCK_DRIFT_OR_FUTURE_PROVIDER_TIMESTAMP"

def test_unknown_provider_state_is_not_permission_to_dispatch():
    d=check([row(2000,"queued_unknown",None)],now=NOW)
    assert not d["dispatch"]

def test_empty_runner_history_requests_one_backup_run():
    assert check([],now=NOW)["dispatch"]

def test_naive_timestamp_denied():
    with pytest.raises(ValueError,match="NO_VALID_PROVIDER_RUNS"):
        check([{"id":1,"created_at":"2026-11-03T17:00:00"}],now=NOW)
