from datetime import datetime, timedelta, timezone

from tools.matrix_quote_transport_readiness import build


NOW = datetime(2026, 11, 3, 3, 0, tzinfo=timezone.utc)


def quota_blocked():
    return {"http_status": 429,
            "decision": {"stage": "BLOCKED_EXHAUSTED", "api_calls_allowed": False}}


def test_exhausted_paid_source_without_local_runner_is_no_go():
    result = build(quota=quota_blocked(), browser_health=None,
                   browser_collection=None, workflow_runs=None, checked_at=NOW)
    assert result["status"] == "NO_GO_REAL_QUOTE_TRANSPORT_NOT_CERTIFIED"
    assert "LAST_VERIFIED_ODDS_API_NET_MONTHLY_QUOTA_EXCEEDED" in result["failures"]
    assert "NO_RECENT_PHYSICAL_CDP_BROWSER_HEALTH_PROOF" in result["failures"]
    assert "NO_RECENT_PHYSICAL_BROWSER_QUOTE_COLLECTION_PROOF" in result["failures"]
    assert result["signal_emission_authorized"] is False
    assert result["exact_bookmaker_over25_quotes_verified_by_this_diagnostic"] == 0
    assert result["telegram_messages_sent"] == 0
    assert result["real_money"] == "BLOCKED"


def test_long_queued_self_hosted_job_is_observed_without_claiming_runner_offline():
    r = build(quota=quota_blocked(), browser_health=None, browser_collection=None,
              workflow_runs={"workflow_runs":[{
                  "id": 123, "status": "queued", "conclusion": None,
                  "created_at": (NOW - timedelta(minutes=25)).isoformat(),
              }]}, checked_at=NOW)
    assert r["stalled_self_hosted_run_ids"] == [123]
    assert "SELF_HOSTED_WORKFLOW_QUEUE_OLDER_THAN_15_MINUTES" in r["failures"]
    assert r["runner_offline_proven"] is False


def test_healthy_infrastructure_does_not_certify_exact_betting_quote():
    recent = (NOW - timedelta(minutes=3)).isoformat()
    r = build(
        quota={"http_status": 200,"decision":{"stage":"NORMAL", "api_calls_allowed":True}},
        browser_health={"status":"PASS_CDP_REACHABLE","checked_at_utc": recent},
        browser_collection={"status":"PASS_CAPTURED","generated_at_utc":recent},
        workflow_runs={"workflow_runs":[{"id":44,"created_at":recent,
                                         "status":"completed","conclusion":"success"}]},
        checked_at=NOW)
    assert r["status"] == "READINESS_INFRASTRUCTURE_ONLY_EXACT_QUOTES_UNCERTIFIED"
    assert r["failures"] == []
    assert r["browser_health_fresh_15m"] is True
    assert r["browser_collection_fresh_15m"] is True
    assert r["signal_emission_authorized"] is False
    assert r["model_probability_modified"] is False


def test_stale_browser_health_fails_even_if_pass_label_is_still_present():
    old = (NOW - timedelta(hours=2)).isoformat()
    r = build(quota=quota_blocked(),
              browser_health={"status":"PASS_CDP_REACHABLE","checked_at_utc":old},
              browser_collection={"status":"PASS_CAPTURED","generated_at_utc":old},
              workflow_runs={}, checked_at=NOW)
    assert not r["browser_health_fresh_15m"]
    assert not r["browser_collection_fresh_15m"]
    assert r["status"] == "NO_GO_REAL_QUOTE_TRANSPORT_NOT_CERTIFIED"
