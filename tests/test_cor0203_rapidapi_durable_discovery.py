from datetime import date

import pytest

import tools.cor0203_rapidapi_durable_discovery as durable
from tools.cor0203_rapidapi_durable_discovery import (
    MAX_REQUESTS_PER_BUCKET,
    RapidApiTennisDiscoveryFetcher,
    build_hourly_discovery_queue,
)
from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisDiscoveryError


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


def test_fetcher_retains_safe_provider_failure_for_durable_diagnosis(monkeypatch):
    class FakeClient:
        request_count = 3

    def fail_discovery(**kwargs):
        raise RapidApiTennisDiscoveryError("SAFE_PROVIDER_FAILURE")

    monkeypatch.setattr(durable, "fetch_discovery", fail_discovery)
    fetcher = RapidApiTennisDiscoveryFetcher(
        client=FakeClient(),
        start=date(2026, 9, 28),
        stop=date(2026, 9, 29),
        as_of_utc="2026-09-28T02:27:00+00:00",
    )

    with pytest.raises(RapidApiTennisDiscoveryError, match="SAFE_PROVIDER_FAILURE"):
        fetcher.fetch({
            "provider_key": "rapidapi_tennis",
            "queue_item_fingerprint": "a" * 64,
        })

    assert fetcher.last_error == "SAFE_PROVIDER_FAILURE"
    assert fetcher.client.request_count == 3
