from datetime import datetime, timezone

from app.application.football.provider_health_snapshot import (
    build_football_provider_health_snapshot,
)
from app.application.tennis.audited_acquisition_execution import (
    execute_audited_tennis_acquisition_queue,
)
from app.application.tennis.provider_health_snapshot import (
    build_tennis_provider_health_snapshot,
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

    return result, audit


def test_successful_provider_snapshot_is_valid(tmp_path):
    result, audit = execute_run(
        tmp_path,
        [{"value": 1}],
    )

    snapshot = build_tennis_provider_health_snapshot(
        provider_key="P1",
        run_ids=[result.run_id],
        audit_ledger=audit,
    )

    assert snapshot.snapshot_status == "VALID"
    assert snapshot.calls_started == 1
    assert snapshot.calls_completed == 1
    assert snapshot.calls_failed == 0
    assert snapshot.success_rate == 1.0
    assert snapshot.failure_rate == 0.0
    assert snapshot.consumed_request_units == 1


def test_retry_is_counted_as_one_logical_call_but_two_units(tmp_path):
    result, audit = execute_run(
        tmp_path,
        [
            RetryableProviderError("temporary"),
            {"value": 2},
        ],
        attempts=2,
        char="2",
    )

    snapshot = build_tennis_provider_health_snapshot(
        provider_key="P1",
        run_ids=[result.run_id],
        audit_ledger=audit,
    )

    assert snapshot.calls_started == 1
    assert snapshot.calls_completed == 1
    assert snapshot.calls_failed == 0
    assert snapshot.consumed_request_units == 2


def test_provider_failure_is_visible_in_snapshot(tmp_path):
    result, audit = execute_run(
        tmp_path,
        [RetryableProviderError("down")],
        attempts=1,
        char="3",
    )

    snapshot = build_tennis_provider_health_snapshot(
        provider_key="P1",
        run_ids=[result.run_id],
        audit_ledger=audit,
    )

    assert snapshot.snapshot_status == "VALID"
    assert snapshot.calls_failed == 1
    assert snapshot.failure_rate == 1.0
    assert snapshot.success_rate == 0.0
    assert snapshot.consumed_request_units == 1


def test_cross_sport_run_is_degraded(tmp_path):
    result, audit = execute_run(
        tmp_path,
        [{"value": 4}],
        char="4",
    )

    snapshot = build_football_provider_health_snapshot(
        provider_key="P1",
        run_ids=[result.run_id],
        audit_ledger=audit,
    )

    assert snapshot.snapshot_status == "DEGRADED"
    assert any(
        reason.startswith("SPORT_BOUNDARY_VIOLATION:")
        for reason in snapshot.reason_codes
    )


def test_no_observations_is_degraded(tmp_path):
    result, audit = execute_run(
        tmp_path,
        [{"value": 5}],
        char="5",
    )

    snapshot = build_tennis_provider_health_snapshot(
        provider_key="OTHER",
        run_ids=[result.run_id],
        audit_ledger=audit,
    )

    assert snapshot.snapshot_status == "DEGRADED"
    assert "NO_PROVIDER_OBSERVATIONS" in snapshot.reason_codes
    assert snapshot.success_rate is None
    assert snapshot.failure_rate is None


def test_duplicate_run_ids_are_rejected(tmp_path):
    result, audit = execute_run(
        tmp_path,
        [{"value": 6}],
        char="6",
    )

    import pytest

    with pytest.raises(ValueError, match="DUPLICATE_RUN_ID"):
        build_tennis_provider_health_snapshot(
            provider_key="P1",
            run_ids=[result.run_id, result.run_id],
            audit_ledger=audit,
        )


def test_snapshot_fingerprint_is_deterministic(tmp_path):
    result, audit = execute_run(
        tmp_path,
        [{"value": 7}],
        char="7",
    )

    first = build_tennis_provider_health_snapshot(
        provider_key="P1",
        run_ids=[result.run_id],
        audit_ledger=audit,
    )
    second = build_tennis_provider_health_snapshot(
        provider_key="P1",
        run_ids=[result.run_id],
        audit_ledger=audit,
    )

    assert first.snapshot_fingerprint == second.snapshot_fingerprint
    assert len(first.snapshot_fingerprint) == 64


def test_snapshot_payload_keeps_safety_flags_false(tmp_path):
    result, audit = execute_run(
        tmp_path,
        [{"value": 8}],
        char="8",
    )

    payload = build_tennis_provider_health_snapshot(
        provider_key="P1",
        run_ids=[result.run_id],
        audit_ledger=audit,
    ).payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
