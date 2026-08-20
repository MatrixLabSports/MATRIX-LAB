from datetime import datetime, timezone
import sqlite3

from app.application.tennis.audited_acquisition_execution import (
    execute_audited_tennis_acquisition_queue,
)
from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.acquisition_worker import WorkerLimits
from app.core.provider_circuit_breaker import (
    ProviderCircuitPolicy,
    SQLiteProviderCircuitStore,
)
from app.core.provider_quota import (
    ProviderQuotaPolicy,
    SQLiteProviderQuotaStore,
)
from app.core.provider_retry import (
    ProviderRetryPolicy,
    RetryableProviderError,
)
from app.core.provider_runtime_stack import build_provider_runtime_stack
from app.core.runtime_audit_ledger import SQLiteRuntimeAuditLedger
from app.core.runtime_reconciliation import reconcile_runtime_run


UTC = timezone.utc
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


class SequenceFetcher:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def fetch(self, queue_item):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def item(char="1"):
    return {
        "sport": "tennis",
        "subject_key": "PLAYER:1",
        "provider_key": "P1",
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": char * 64,
        "estimated_request_cost": 1,
        "source_fingerprint": "a" * 64,
    }


def execute_run(tmp_path, outcomes, *, attempts=1, char="1"):
    path = tmp_path / "runtime.db"
    audit = SQLiteRuntimeAuditLedger(path)
    persistence = SQLiteAcquisitionStore(path)

    runtime = build_provider_runtime_stack(
        fetcher=SequenceFetcher(outcomes),
        quota_store=SQLiteProviderQuotaStore(path),
        circuit_store=SQLiteProviderCircuitStore(path),
        quota_policies={
            "P1": ProviderQuotaPolicy(
                provider_key="P1",
                window_seconds=60,
                max_request_units=10,
            )
        },
        circuit_policies={
            "P1": ProviderCircuitPolicy(
                provider_key="P1",
                failure_threshold=10,
                cooldown_seconds=60,
            )
        },
        retry_policies={
            "P1": ProviderRetryPolicy(
                provider_key="P1",
                max_attempts=attempts,
                base_delay_seconds=0.0,
                max_delay_seconds=0.0,
                jitter_ratio=0.0,
            )
        },
        max_request_units=5,
        clock=lambda: NOW,
        sleeper=lambda _: None,
    )

    policy = audit.policy_fingerprint(
        quota_policies={"P1": {"limit": 10}},
        circuit_policies={"P1": {"threshold": 10}},
        retry_policies={"P1": {"attempts": attempts}},
        worker_limits={"max_items": 10, "max_requests": 5},
    )

    result = execute_audited_tennis_acquisition_queue(
        queue_manifest={"sport": "tennis", "queue": [item(char)]},
        policy_fingerprint=policy,
        audit_ledger=audit,
        fetcher=runtime.fetcher,
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=5),
        clock=lambda: NOW,
        request_budget=runtime.request_budget,
    )

    return result, audit, persistence


def test_successful_run_reconciles_across_ledgers(tmp_path):
    result, audit, persistence = execute_run(
        tmp_path,
        [{"value": 1}],
    )

    report = reconcile_runtime_run(
        run_id=result.run_id,
        audit_ledger=audit,
        acquisition_store=persistence,
    )

    assert report.ok is True
    assert report.status == "COMPLETED"
    assert report.requests_used == 1
    assert report.provider_consumed_units == 1
    assert len(report.evidence_ids) == 1
    assert report.errors == ()


def test_retry_consumption_reconciles_exactly(tmp_path):
    result, audit, persistence = execute_run(
        tmp_path,
        [
            RetryableProviderError("temporary"),
            {"value": 2},
        ],
        attempts=2,
        char="2",
    )

    report = reconcile_runtime_run(
        run_id=result.run_id,
        audit_ledger=audit,
        acquisition_store=persistence,
    )

    assert report.ok is True
    assert report.requests_used == 2
    assert report.provider_consumed_units == 2


def test_worker_level_failure_reconciles_as_completed_run(tmp_path):
    result, audit, persistence = execute_run(
        tmp_path,
        [RetryableProviderError("down")],
        attempts=1,
        char="3",
    )

    report = reconcile_runtime_run(
        run_id=result.run_id,
        audit_ledger=audit,
        acquisition_store=persistence,
    )

    assert result.worker_result.failed == 1
    assert report.status == "COMPLETED"
    assert report.requests_used == 1
    assert report.provider_consumed_units == 1
    assert report.ok is True


def test_missing_raw_evidence_is_detected(tmp_path):
    result, audit, persistence = execute_run(
        tmp_path,
        [{"value": 4}],
        char="4",
    )

    evidence_id = result.worker_result.evidence_ids[0]

    with sqlite3.connect(persistence.path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "DELETE FROM acquisition_checkpoints WHERE evidence_id = ?",
            (evidence_id,),
        )
        connection.execute(
            "DELETE FROM raw_evidence WHERE evidence_id = ?",
            (evidence_id,),
        )
        connection.commit()

    report = reconcile_runtime_run(
        run_id=result.run_id,
        audit_ledger=audit,
        acquisition_store=persistence,
    )

    assert report.ok is False
    assert any(
        error.startswith("MISSING_RAW_EVIDENCE:")
        for error in report.errors
    )


def test_audit_tampering_causes_reconciliation_failure(tmp_path):
    result, audit, persistence = execute_run(
        tmp_path,
        [{"value": 5}],
        char="5",
    )

    with sqlite3.connect(audit.path) as connection:
        connection.execute(
            """
            UPDATE runtime_audit_events
            SET event_json = ?
            WHERE run_id = ? AND sequence_no = 1
            """,
            ('{"tampered":true}\n', result.run_id),
        )
        connection.commit()

    report = reconcile_runtime_run(
        run_id=result.run_id,
        audit_ledger=audit,
        acquisition_store=persistence,
    )

    assert report.ok is False
    assert "AUDIT_LEDGER_INTEGRITY_FAILED" in report.errors


def test_report_fingerprint_is_deterministic(tmp_path):
    result, audit, persistence = execute_run(
        tmp_path,
        [{"value": 6}],
        char="6",
    )

    first = reconcile_runtime_run(
        run_id=result.run_id,
        audit_ledger=audit,
        acquisition_store=persistence,
    )
    second = reconcile_runtime_run(
        run_id=result.run_id,
        audit_ledger=audit,
        acquisition_store=persistence,
    )

    assert first.report_fingerprint == second.report_fingerprint
    assert len(first.report_fingerprint) == 64


def test_reconciliation_report_keeps_safety_flags_false(tmp_path):
    result, audit, persistence = execute_run(
        tmp_path,
        [{"value": 7}],
        char="7",
    )

    payload = reconcile_runtime_run(
        run_id=result.run_id,
        audit_ledger=audit,
        acquisition_store=persistence,
    ).payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
