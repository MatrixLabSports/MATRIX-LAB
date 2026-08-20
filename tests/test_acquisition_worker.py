import pytest

from app.application.football.acquisition_worker import (
    execute_football_acquisition_queue,
)
from app.application.tennis.acquisition_worker import (
    execute_tennis_acquisition_queue,
)
from app.core.acquisition_worker import (
    InMemoryCheckpointStore,
    InMemoryRawAppendOnlyLedger,
    WorkerLimits,
)


def item(
    sport: str,
    subject: str,
    fingerprint_char: str,
    *,
    cost: int = 1,
):
    return {
        "sport": sport,
        "subject_key": subject,
        "provider_key": "P1",
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": fingerprint_char * 64,
        "estimated_request_cost": cost,
        "source_fingerprint": "a" * 64,
    }


class FakeFetcher:
    def __init__(self):
        self.calls = []

    def fetch(self, queue_item):
        self.calls.append(queue_item["queue_item_fingerprint"])
        return {"rows": [queue_item["subject_key"]]}


class BrokenFetcher:
    def fetch(self, queue_item):
        raise RuntimeError("provider down")


def manifest(sport, items):
    return {"sport": sport, "queue": items}


def test_worker_processes_and_appends_raw_evidence():
    fetcher = FakeFetcher()
    raw = InMemoryRawAppendOnlyLedger()
    checkpoints = InMemoryCheckpointStore()

    result = execute_tennis_acquisition_queue(
        queue_manifest=manifest(
            "tennis",
            [item("tennis", "PLAYER:1", "1")],
        ),
        fetcher=fetcher,
        raw_ledger=raw,
        checkpoints=checkpoints,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert result.processed == 1
    assert result.failed == 0
    assert len(raw.records) == 1
    assert len(checkpoints.completed) == 1


def test_worker_is_idempotent_with_checkpoint():
    fetcher = FakeFetcher()
    raw = InMemoryRawAppendOnlyLedger()
    checkpoints = InMemoryCheckpointStore()
    queue = manifest(
        "football",
        [item("football", "TEAM:1", "2")],
    )

    first = execute_football_acquisition_queue(
        queue_manifest=queue,
        fetcher=fetcher,
        raw_ledger=raw,
        checkpoints=checkpoints,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )
    second = execute_football_acquisition_queue(
        queue_manifest=queue,
        fetcher=fetcher,
        raw_ledger=raw,
        checkpoints=checkpoints,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert first.processed == 1
    assert second.processed == 0
    assert second.skipped_completed == 1
    assert len(fetcher.calls) == 1


def test_raw_ledger_is_append_only():
    raw = InMemoryRawAppendOnlyLedger()
    raw.append("e1", {"x": 1})

    with pytest.raises(ValueError, match="RAW_APPEND_ONLY_VIOLATION"):
        raw.append("e1", {"x": 2})


def test_request_limit_stops_before_overrun():
    fetcher = FakeFetcher()
    raw = InMemoryRawAppendOnlyLedger()
    checkpoints = InMemoryCheckpointStore()

    result = execute_tennis_acquisition_queue(
        queue_manifest=manifest(
            "tennis",
            [
                item("tennis", "A", "3", cost=2),
                item("tennis", "B", "4", cost=2),
            ],
        ),
        fetcher=fetcher,
        raw_ledger=raw,
        checkpoints=checkpoints,
        limits=WorkerLimits(max_items=10, max_requests=2),
    )

    assert result.processed == 1
    assert result.requests_used == 2
    assert len(fetcher.calls) == 1
    assert (
        result.failures[-1][1]
        == "WORKER_REQUEST_LIMIT_REACHED"
    )


def test_max_items_bounds_execution():
    fetcher = FakeFetcher()
    raw = InMemoryRawAppendOnlyLedger()
    checkpoints = InMemoryCheckpointStore()

    result = execute_football_acquisition_queue(
        queue_manifest=manifest(
            "football",
            [
                item("football", "A", "5"),
                item("football", "B", "6"),
            ],
        ),
        fetcher=fetcher,
        raw_ledger=raw,
        checkpoints=checkpoints,
        limits=WorkerLimits(max_items=1, max_requests=10),
    )

    assert result.processed == 1
    assert len(fetcher.calls) == 1


def test_provider_failure_is_recorded_without_checkpoint():
    raw = InMemoryRawAppendOnlyLedger()
    checkpoints = InMemoryCheckpointStore()

    result = execute_tennis_acquisition_queue(
        queue_manifest=manifest(
            "tennis",
            [item("tennis", "FAIL", "7")],
        ),
        fetcher=BrokenFetcher(),
        raw_ledger=raw,
        checkpoints=checkpoints,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert result.processed == 0
    assert result.failed == 1
    assert checkpoints.completed == {}
    assert raw.records == {}


def test_cross_sport_item_is_blocked():
    fetcher = FakeFetcher()

    result = execute_football_acquisition_queue(
        queue_manifest=manifest(
            "football",
            [item("tennis", "PLAYER:X", "8")],
        ),
        fetcher=fetcher,
        raw_ledger=InMemoryRawAppendOnlyLedger(),
        checkpoints=InMemoryCheckpointStore(),
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert result.failed == 1
    assert result.failures[0][1] == "CROSS_SPORT_QUEUE_ITEM"
    assert fetcher.calls == []


def test_adapter_rejects_wrong_manifest_sport():
    with pytest.raises(ValueError, match="SPORT_BOUNDARY_VIOLATION"):
        execute_tennis_acquisition_queue(
            queue_manifest=manifest("football", []),
            fetcher=FakeFetcher(),
            raw_ledger=InMemoryRawAppendOnlyLedger(),
            checkpoints=InMemoryCheckpointStore(),
            limits=WorkerLimits(max_items=10, max_requests=10),
        )


def test_invalid_zero_request_cost_is_rejected():
    bad = item("tennis", "BAD", "9", cost=0)

    result = execute_tennis_acquisition_queue(
        queue_manifest=manifest("tennis", [bad]),
        fetcher=FakeFetcher(),
        raw_ledger=InMemoryRawAppendOnlyLedger(),
        checkpoints=InMemoryCheckpointStore(),
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert result.failed == 1
    assert result.failures[0][1] == "INVALID_REQUEST_COST"


def test_safety_flags_remain_false():
    result = execute_football_acquisition_queue(
        queue_manifest=manifest("football", []),
        fetcher=FakeFetcher(),
        raw_ledger=InMemoryRawAppendOnlyLedger(),
        checkpoints=InMemoryCheckpointStore(),
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    payload = result.payload()
    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False

def test_in_memory_worker_recovers_raw_without_refetch():
    fetcher = FakeFetcher()
    raw = InMemoryRawAppendOnlyLedger()
    checkpoints = InMemoryCheckpointStore()
    queue = manifest(
        "tennis",
        [item("tennis", "RECOVER", "a")],
    )

    first = execute_tennis_acquisition_queue(
        queue_manifest=queue,
        fetcher=fetcher,
        raw_ledger=raw,
        checkpoints=checkpoints,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    evidence_id = first.evidence_ids[0]
    checkpoints.completed.clear()

    second = execute_tennis_acquisition_queue(
        queue_manifest=queue,
        fetcher=fetcher,
        raw_ledger=raw,
        checkpoints=checkpoints,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert second.processed == 0
    assert second.recovered_without_fetch == 1
    assert second.requests_used == 0
    assert second.evidence_ids == (evidence_id,)
    assert len(fetcher.calls) == 1
