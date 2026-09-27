from tools.cor0203_rapidapi_durable_discovery import (
    MAX_REQUESTS_PER_BUCKET,
    build_hourly_discovery_queue,
)


def test_rapidapi_hourly_queue_is_singleton_bounded_and_provider_specific():
    q = build_hourly_discovery_queue(
        as_of_utc="2026-09-27T00:31:45+00:00",
        days=2,
    )
    assert q["sport"] == "tennis"
    assert len(q["queue"]) == 1
    item = q["queue"][0]
    assert item["provider_key"] == "rapidapi_tennis"
    assert item["estimated_request_cost"] == MAX_REQUESTS_PER_BUCKET
    assert (
        q["provider_usage"]["rapidapi_tennis"]["requests_max"]
        == MAX_REQUESTS_PER_BUCKET
    )
    assert item["rights_status"] == "RESEARCH_ONLY"


def test_rapidapi_same_hour_is_idempotent_but_next_hour_is_fresh():
    a = build_hourly_discovery_queue(
        as_of_utc="2026-09-27T00:01:00+00:00",
        days=2,
    )
    b = build_hourly_discovery_queue(
        as_of_utc="2026-09-27T00:59:59+00:00",
        days=2,
    )
    c = build_hourly_discovery_queue(
        as_of_utc="2026-09-27T01:00:00+00:00",
        days=2,
    )
    assert (
        a["queue"][0]["queue_item_fingerprint"]
        == b["queue"][0]["queue_item_fingerprint"]
    )
    assert (
        a["queue"][0]["queue_item_fingerprint"]
        != c["queue"][0]["queue_item_fingerprint"]
    )
