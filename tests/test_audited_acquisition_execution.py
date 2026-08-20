from datetime import datetime, timedelta, timezone

import pytest

from app.application.football.audited_acquisition_execution import (
    execute_audited_football_acquisition_queue,
)
from app.application.tennis.audited_acquisition_execution import (
    execute_audited_tennis_acquisition_queue,
)
from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.acquisition_worker import WorkerLimits
from app.core.audited_acquisition_execution import (
    queue_manifest_fingerprint,
)
from app.core.runtime_audit_ledger import SQLiteRuntimeAuditLedger


UTC = timezone.utc
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        current = self.value
        self.value = self.value + timedelta(milliseconds=1)
        return current


class FakeFetcher:
    def __init__(self, payload=None):
        self.calls = 0
        self.payload = payload or {"value": 1}

    def fetch(self, queue_item):
        self.calls += 1
        return dict(self.payload)


class BrokenFetcher:
    def fetch(self, queue_item):
        raise RuntimeError("provider down")


def queue_item(sport="tennis", char="1"):
    return {
        "sport": sport,
        "subject_key": "SUBJECT:1",
        "provider_key": "P1",
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": char * 64,
        "estimated_request_cost": 1,
        "source_fingerprint": "a" * 64,
    }


def manifest(sport="tennis", char="1"):
    return {
        "sport": sport,
        "queue": [queue_item(sport=sport, char=char)],
    }


def policy_fingerprint(ledger):
    return ledger.policy_fingerprint(
        quota_policies={"P1": {"limit": 10}},
        circuit_policies={"P1": {"threshold": 3}},
        retry_policies={"P1": {"attempts": 2}},
        worker_limits={"max_items": 10, "max_requests": 10},
    )


def test_queue_manifest_fingerprint_is_deterministic():
    first = queue_manifest_fingerprint(manifest("tennis", "1"))
    second = queue_manifest_fingerprint(manifest("tennis", "1"))

    assert first == second
    assert len(first) == 64


def test_queue_manifest_fingerprint_changes_with_content():
    first = queue_manifest_fingerprint(manifest("tennis", "1"))
    second = queue_manifest_fingerprint(manifest("tennis", "2"))

    assert first != second


def test_successful_execution_closes_audit_run(tmp_path):
    path = tmp_path / "runtime.db"
    audit = SQLiteRuntimeAuditLedger(path)
    persistence = SQLiteAcquisitionStore(path)
    clock = Clock(NOW)

    result = execute_audited_tennis_acquisition_queue(
        queue_manifest=manifest("tennis"),
        policy_fingerprint=policy_fingerprint(audit),
        audit_ledger=audit,
        fetcher=FakeFetcher(),
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=10),
        clock=clock,
    )

    events = audit.list_events(result.run_id)

    assert result.worker_result.processed == 1
    assert [event["event_type"] for event in events] == [
        "RUN_STARTED",
        "ACQUISITION_EXECUTION_STARTED",
        "ACQUISITION_EXECUTION_RESULT",
        "RUN_FINISHED",
    ]
    assert audit.audit_integrity().ok is True


def test_failed_execution_is_closed_as_failed(tmp_path):
    path = tmp_path / "runtime.db"
    audit = SQLiteRuntimeAuditLedger(path)
    persistence = SQLiteAcquisitionStore(path)
    clock = Clock(NOW)

    # Force an unhandled pre-worker error after RUN_STARTED by creating
    # a budget/limit mismatch.
    from app.core.provider_request_budget import ExecutionRequestBudget

    with pytest.raises(
        ValueError,
        match="REQUEST_BUDGET_LIMIT_MISMATCH",
    ):
        execute_audited_tennis_acquisition_queue(
            queue_manifest=manifest("tennis"),
            policy_fingerprint=policy_fingerprint(audit),
            audit_ledger=audit,
            fetcher=BrokenFetcher(),
            raw_ledger=persistence,
            checkpoints=persistence,
            limits=WorkerLimits(max_items=10, max_requests=10),
            clock=clock,
            request_budget=ExecutionRequestBudget(9),
        )

    report = audit.audit_integrity()
    assert report.ok is True

    with audit._connect() as connection:
        status = connection.execute(
            "SELECT status FROM runtime_audit_runs"
        ).fetchone()[0]

    assert status == "FAILED"


def test_worker_level_provider_failure_is_a_completed_execution(tmp_path):
    path = tmp_path / "runtime.db"
    audit = SQLiteRuntimeAuditLedger(path)
    persistence = SQLiteAcquisitionStore(path)

    result = execute_audited_tennis_acquisition_queue(
        queue_manifest=manifest("tennis"),
        policy_fingerprint=policy_fingerprint(audit),
        audit_ledger=audit,
        fetcher=BrokenFetcher(),
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=10),
        clock=Clock(NOW),
    )

    assert result.worker_result.failed == 1

    with audit._connect() as connection:
        status = connection.execute(
            "SELECT status FROM runtime_audit_runs"
        ).fetchone()[0]

    assert status == "COMPLETED"
    assert audit.audit_integrity().ok is True


def test_tennis_adapter_rejects_football_manifest(tmp_path):
    path = tmp_path / "runtime.db"

    with pytest.raises(ValueError, match="SPORT_BOUNDARY_VIOLATION"):
        execute_audited_tennis_acquisition_queue(
            queue_manifest=manifest("football"),
            policy_fingerprint="a" * 64,
            audit_ledger=SQLiteRuntimeAuditLedger(path),
            fetcher=FakeFetcher(),
            raw_ledger=SQLiteAcquisitionStore(path),
            checkpoints=SQLiteAcquisitionStore(path),
            limits=WorkerLimits(max_items=10, max_requests=10),
            clock=Clock(NOW),
        )


def test_football_adapter_rejects_tennis_manifest(tmp_path):
    path = tmp_path / "runtime.db"

    with pytest.raises(ValueError, match="SPORT_BOUNDARY_VIOLATION"):
        execute_audited_football_acquisition_queue(
            queue_manifest=manifest("tennis"),
            policy_fingerprint="a" * 64,
            audit_ledger=SQLiteRuntimeAuditLedger(path),
            fetcher=FakeFetcher(),
            raw_ledger=SQLiteAcquisitionStore(path),
            checkpoints=SQLiteAcquisitionStore(path),
            limits=WorkerLimits(max_items=10, max_requests=10),
            clock=Clock(NOW),
        )


def test_result_keeps_safety_flags_false(tmp_path):
    path = tmp_path / "runtime.db"
    audit = SQLiteRuntimeAuditLedger(path)
    persistence = SQLiteAcquisitionStore(path)

    result = execute_audited_tennis_acquisition_queue(
        queue_manifest={"sport": "tennis", "queue": []},
        policy_fingerprint=policy_fingerprint(audit),
        audit_ledger=audit,
        fetcher=FakeFetcher(),
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=10),
        clock=Clock(NOW),
    )

    payload = result.payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
