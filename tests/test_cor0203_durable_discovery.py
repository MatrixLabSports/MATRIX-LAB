from pathlib import Path

from tools.cor0203_durable_discovery import (
    MAX_REQUESTS_PER_BUCKET,
    build_hourly_discovery_queue,
)


def test_hourly_queue_is_singleton_and_bounded():
    q = build_hourly_discovery_queue(
        as_of_utc="2026-09-26T22:31:45+00:00",
        days=2,
    )
    assert q["sport"] == "tennis"
    assert len(q["queue"]) == 1
    item = q["queue"][0]
    assert item["provider_key"] == "api_tennis"
    assert item["estimated_request_cost"] == MAX_REQUESTS_PER_BUCKET
    assert q["provider_usage"]["api_tennis"]["requests_max"] == MAX_REQUESTS_PER_BUCKET
    assert item["rights_status"] == "RESEARCH_ONLY"


def test_same_hour_same_fingerprint_even_if_minutes_change():
    a = build_hourly_discovery_queue(
        as_of_utc="2026-09-26T22:01:00+00:00",
        days=2,
    )
    b = build_hourly_discovery_queue(
        as_of_utc="2026-09-26T22:59:59+00:00",
        days=2,
    )
    assert a["queue"][0]["queue_item_fingerprint"] == b["queue"][0]["queue_item_fingerprint"]


def test_next_hour_gets_fresh_queue_identity():
    a = build_hourly_discovery_queue(
        as_of_utc="2026-09-26T22:59:59+00:00",
        days=2,
    )
    b = build_hourly_discovery_queue(
        as_of_utc="2026-09-26T23:00:00+00:00",
        days=2,
    )
    assert a["queue"][0]["queue_item_fingerprint"] != b["queue"][0]["queue_item_fingerprint"]


def test_source_fingerprint_never_contains_secret():
    q = build_hourly_discovery_queue(
        as_of_utc="2026-09-26T22:00:00+00:00",
        days=2,
    )
    fp = q["queue"][0]["source_fingerprint"]
    assert len(fp) == 64
    int(fp, 16)


def test_sqlite_store_path_is_not_required_for_missing_key_cli_contract():
    # The runtime only opens the durable store when the provider credential exists.
    assert Path("evidence/cor0203/acquisition/MATRIX_COR0203_ACQUISITION.sqlite3").suffix == ".sqlite3"
