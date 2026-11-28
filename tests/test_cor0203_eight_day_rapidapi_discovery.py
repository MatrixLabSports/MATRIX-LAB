from tools.cor0203_eight_day_rapidapi_discovery import merge


def _payload(ids):
    return {
        "schema":"TEST",
        "provider":"rapidapi_tennis",
        "status":"DISCOVERY_COMPLETED",
        "eligible_candidates":[
            {"event_id":x,"canonical_source_event_id":x}
            for x in ids
        ],
        "provider_rejected":[],
        "network_calls":2,
        "request_count":2,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def test_rapidapi_eight_day_merge_deduplicates_without_second_paid_source():
    out=merge(_payload(["a","b"]),_payload(["b","c"]),as_of_utc="2026-10-15T05:00:00+00:00")
    assert [x["event_id"] for x in out["eligible_candidates"]] == ["a","b","c"]
    assert out["eligible_input_events"] == 3
    assert out["eight_day_horizon"]["logical_days"] == 8
    assert out["eight_day_horizon"]["duplicate_source_event_count"] == 1
    assert out["api_tennis_status"] == "RETIRED_COST_UTILITY_DECISION"
    assert out["automatic_wagering"] is False
    assert out["real_money"] == "BLOCKED"
