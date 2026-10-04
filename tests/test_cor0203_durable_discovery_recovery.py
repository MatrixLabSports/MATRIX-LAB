from pathlib import Path

from app.application.tennis.acquisition_worker import execute_tennis_acquisition_queue
from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.acquisition_worker import WorkerLimits
from tools.cor0203_durable_discovery import (
    MAX_REQUESTS_PER_BUCKET,
    ApiTennisDiscoveryFetcher,
    build_hourly_discovery_queue,
)


class FakeApiTennisClient:
    def __init__(self):
        self.request_count = 0

    def fixtures(self, start, stop):
        self.request_count += 1
        return {"success": 1, "result": []}

    def standings(self):
        self.request_count += 1
        return {"success": 1, "result": []}

    def draw(self, tournament_key, tournament_season):
        self.request_count += 1
        return {"success": 1, "result": {}}


def test_same_hour_second_run_uses_checkpoint_without_refetch(tmp_path):
    as_of = "2026-09-26T22:30:00+00:00"
    queue = build_hourly_discovery_queue(as_of_utc=as_of, days=2)
    store = SQLiteAcquisitionStore(tmp_path / "acquisition.sqlite3")
    client = FakeApiTennisClient()
    fetcher = ApiTennisDiscoveryFetcher(
        client=client,
        start=__import__("datetime").date(2026, 9, 26),
        stop=__import__("datetime").date(2026, 9, 27),
        as_of_utc=as_of,
    )

    first = execute_tennis_acquisition_queue(
        queue_manifest=queue,
        fetcher=fetcher,
        raw_ledger=store,
        checkpoints=store,
        limits=WorkerLimits(max_items=1, max_requests=MAX_REQUESTS_PER_BUCKET),
    )
    calls_after_first = client.request_count

    second = execute_tennis_acquisition_queue(
        queue_manifest=queue,
        fetcher=fetcher,
        raw_ledger=store,
        checkpoints=store,
        limits=WorkerLimits(max_items=1, max_requests=MAX_REQUESTS_PER_BUCKET),
    )

    assert first.processed == 1
    assert first.failed == 0
    assert calls_after_first == 2
    assert second.processed == 0
    assert second.skipped_completed == 1
    assert client.request_count == calls_after_first
    integrity = store.audit_integrity()
    assert integrity.ok is True
    assert integrity.raw_records == 1
    assert integrity.checkpoints == 1
