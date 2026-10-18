from tools.cor0203_eight_day_dual_discovery import merge_discovery_payloads
from tools.cor0203_milestone_status import build_status


def _payload(provider, ids):
    return {
        "schema":"TEST",
        "provider":provider,
        "status":"DISCOVERY_COMPLETED",
        "eligible_candidates":[
            {"event_id":x,"canonical_source_event_id":x,"players":[{"name":"A"},{"name":"B"}]}
            for x in ids
        ],
        "provider_rejected":[],
        "network_calls":3,
        "request_count":3,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def test_eight_day_merge_deduplicates_source_events():
    out=merge_discovery_payloads(
        _payload("rapidapi_tennis",["a","b"]),
        _payload("rapidapi_tennis",["b","c"]),
        provider="rapidapi_tennis",
        as_of_utc="2026-10-03T23:00:00+00:00",
    )
    assert [x["event_id"] for x in out["eligible_candidates"]]==["a","b","c"]
    assert out["eligible_input_events"]==3
    assert out["eight_day_horizon"]["logical_days"]==8
    assert out["eight_day_horizon"]["provider_call_max_days"]==4
    assert out["eight_day_horizon"]["duplicate_source_event_count"]==1
    assert out["network_calls"]==6
    assert out["real_money"]=="BLOCKED"


def test_milestones_do_not_open_metrics():
    p=build_status({"result":"PASS","unique_calibration_observations":93})
    assert p["milestones"]["100"]["status"]=="PENDING"
    assert p["milestones"]["100"]["remaining"]==7
    assert p["milestones"]["150"]["remaining"]==57
    assert p["milestones"]["200"]["remaining"]==107
    assert p["metrics_opened"] is False
    assert p["metrics_policy"]=="SEALED_UNTIL_600"
    assert p["real_money"]=="BLOCKED"


def test_window_closes_only_at_200_without_metrics():
    p=build_status({"result":"PASS","unique_calibration_observations":200})
    assert p["window1_physical_status"]=="CLOSED_AT_200"
    assert all(x["status"]=="REACHED" for x in p["milestones"].values())
    assert all(x["metrics_open_allowed"] is False for x in p["milestones"].values())
    assert p["metrics_opened"] is False
