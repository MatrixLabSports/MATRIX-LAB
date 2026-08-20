from hashlib import sha256
import json
import sqlite3

import pytest

from app.application.tennis.acquisition_worker import (
    execute_tennis_acquisition_queue,
)
from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.acquisition_worker import WorkerLimits


def canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def evidence(queue_fingerprint="1" * 64, raw_value=1):
    payload = {
        "schema": "matrix.raw-provider-evidence/1",
        "sport": "tennis",
        "subject_key": "PLAYER:1",
        "provider_key": "P1",
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": queue_fingerprint,
        "source_fingerprint": "a" * 64,
        "raw_payload": {"value": raw_value},
    }
    evidence_id = sha256(
        canonical(payload).encode("utf-8")
    ).hexdigest()
    return evidence_id, payload


def queue_item(fingerprint="1" * 64):
    return {
        "sport": "tennis",
        "subject_key": "PLAYER:1",
        "provider_key": "P1",
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": fingerprint,
        "estimated_request_cost": 1,
        "source_fingerprint": "a" * 64,
    }


class FakeFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, queue_item):
        self.calls += 1
        return {"value": 1}


def test_sqlite_store_persists_raw_and_checkpoint(tmp_path):
    path = tmp_path / "runtime.db"
    store = SQLiteAcquisitionStore(path)
    evidence_id, payload = evidence()

    store.append(evidence_id, payload)
    store.mark_completed("1" * 64, evidence_id)

    reopened = SQLiteAcquisitionStore(path)

    assert reopened.contains(evidence_id) is True
    assert reopened.is_completed("1" * 64) is True
    assert reopened.get_raw(evidence_id) == payload


def test_raw_evidence_is_append_only(tmp_path):
    store = SQLiteAcquisitionStore(tmp_path / "runtime.db")
    evidence_id, payload = evidence()

    store.append(evidence_id, payload)

    with pytest.raises(
        ValueError,
        match="RAW_APPEND_ONLY_VIOLATION",
    ):
        store.append(evidence_id, payload)


def test_one_queue_item_cannot_map_to_two_raw_records(tmp_path):
    store = SQLiteAcquisitionStore(tmp_path / "runtime.db")
    evidence_id, payload = evidence(raw_value=1)
    store.append(evidence_id, payload)

    second_id, second_payload = evidence(raw_value=2)

    with pytest.raises(
        ValueError,
        match="RAW_APPEND_ONLY_VIOLATION",
    ):
        store.append(second_id, second_payload)


def test_checkpoint_requires_existing_raw(tmp_path):
    store = SQLiteAcquisitionStore(tmp_path / "runtime.db")

    with pytest.raises(
        ValueError,
        match="CHECKPOINT_WITHOUT_RAW_EVIDENCE",
    ):
        store.mark_completed("1" * 64, "f" * 64)


def test_checkpoint_is_idempotent_but_immutable(tmp_path):
    store = SQLiteAcquisitionStore(tmp_path / "runtime.db")
    evidence_id, payload = evidence()
    store.append(evidence_id, payload)

    store.mark_completed("1" * 64, evidence_id)
    store.mark_completed("1" * 64, evidence_id)

    other_id, other_payload = evidence(
        queue_fingerprint="2" * 64,
        raw_value=2,
    )
    store.append(other_id, other_payload)

    with pytest.raises(
        ValueError,
        match="CHECKPOINT_QUEUE_ITEM_MISMATCH",
    ):
        store.mark_completed("1" * 64, other_id)


def test_evidence_id_must_match_payload(tmp_path):
    store = SQLiteAcquisitionStore(tmp_path / "runtime.db")
    _, payload = evidence()

    with pytest.raises(
        ValueError,
        match="EVIDENCE_ID_PAYLOAD_MISMATCH",
    ):
        store.append("f" * 64, payload)


def test_integrity_audit_passes_on_valid_store(tmp_path):
    store = SQLiteAcquisitionStore(tmp_path / "runtime.db")
    evidence_id, payload = evidence()

    store.append(evidence_id, payload)
    store.mark_completed("1" * 64, evidence_id)

    report = store.audit_integrity()

    assert report.ok is True
    assert report.raw_records == 1
    assert report.checkpoints == 1
    assert report.errors == ()


def test_integrity_audit_detects_direct_database_tampering(tmp_path):
    path = tmp_path / "runtime.db"
    store = SQLiteAcquisitionStore(path)
    evidence_id, payload = evidence()
    store.append(evidence_id, payload)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE raw_evidence
            SET payload_json = ?
            WHERE evidence_id = ?
            """,
            ('{"tampered":true}\n', evidence_id),
        )
        connection.commit()

    report = store.audit_integrity()

    assert report.ok is False
    assert any(
        error.startswith("PAYLOAD_HASH_MISMATCH:")
        for error in report.errors
    )


def test_worker_uses_durable_store_end_to_end(tmp_path):
    store = SQLiteAcquisitionStore(tmp_path / "runtime.db")
    fetcher = FakeFetcher()

    result = execute_tennis_acquisition_queue(
        queue_manifest={
            "sport": "tennis",
            "queue": [queue_item()],
        },
        fetcher=fetcher,
        raw_ledger=store,
        checkpoints=store,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert result.processed == 1
    assert result.requests_used == 1
    assert fetcher.calls == 1

    reopened = SQLiteAcquisitionStore(tmp_path / "runtime.db")
    assert reopened.is_completed("1" * 64) is True
    assert reopened.audit_integrity().ok is True


def test_worker_recovers_raw_without_refetch_after_crash(tmp_path):
    store = SQLiteAcquisitionStore(tmp_path / "runtime.db")
    evidence_id, payload = evidence()

    # Simulates crash after RAW append but before checkpoint.
    store.append(evidence_id, payload)

    fetcher = FakeFetcher()

    result = execute_tennis_acquisition_queue(
        queue_manifest={
            "sport": "tennis",
            "queue": [queue_item()],
        },
        fetcher=fetcher,
        raw_ledger=store,
        checkpoints=store,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert result.processed == 0
    assert result.skipped_completed == 1
    assert result.recovered_without_fetch == 1
    assert result.requests_used == 0
    assert fetcher.calls == 0
    assert store.is_completed("1" * 64) is True
