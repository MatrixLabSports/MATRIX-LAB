from datetime import datetime, timezone

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


UTC = timezone.utc
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


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


def item(char="1", cost=1):
    return {
        "sport": "tennis",
        "subject_key": "PLAYER:1",
        "provider_key": "P1",
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": char * 64,
        "estimated_request_cost": cost,
        "source_fingerprint": "a" * 64,
    }


def policy_fp(audit):
    return audit.policy_fingerprint(
        quota_policies={"P1": {"limit": 10}},
        circuit_policies={"P1": {"threshold": 5}},
        retry_policies={"P1": {"attempts": 3}},
        worker_limits={"max_items": 10, "max_requests": 5},
    )


def runtime(tmp_path, underlying, *, quota=10, attempts=3):
    path = tmp_path / "runtime.db"
    clock = Clock(NOW)

    stack = build_provider_runtime_stack(
        fetcher=underlying,
        quota_store=SQLiteProviderQuotaStore(path),
        circuit_store=SQLiteProviderCircuitStore(path),
        quota_policies={
            "P1": ProviderQuotaPolicy(
                provider_key="P1",
                window_seconds=60,
                max_request_units=quota,
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
        clock=clock,
        sleeper=lambda _: None,
    )
    return stack, clock


def provider_events(audit, run_id):
    return [
        event
        for event in audit.list_events(run_id)
        if event["event_type"].startswith("PROVIDER_CALL_")
    ]


def execute(tmp_path, underlying, *, char="1", quota=10, attempts=1):
    path = tmp_path / "runtime.db"
    audit = SQLiteRuntimeAuditLedger(path)
    persistence = SQLiteAcquisitionStore(path)
    stack, clock = runtime(
        tmp_path,
        underlying,
        quota=quota,
        attempts=attempts,
    )

    result = execute_audited_tennis_acquisition_queue(
        queue_manifest={"sport": "tennis", "queue": [item(char=char)]},
        policy_fingerprint=policy_fp(audit),
        audit_ledger=audit,
        fetcher=stack.fetcher,
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=5),
        clock=clock,
        request_budget=stack.request_budget,
    )

    return result, audit, persistence, stack


def test_successful_provider_call_is_audited(tmp_path):
    result, audit, _, _ = execute(
        tmp_path,
        SequenceFetcher([{"value": 1}]),
    )

    events = provider_events(audit, result.run_id)

    assert [event["event_type"] for event in events] == [
        "PROVIDER_CALL_STARTED",
        "PROVIDER_CALL_COMPLETED",
    ]
    assert events[-1]["event_payload"]["consumed_request_units"] == 1
    assert audit.audit_integrity().ok is True


def test_retry_consumption_is_observed_from_attempt_budget(tmp_path):
    underlying = SequenceFetcher([
        RetryableProviderError("temporary"),
        {"value": 2},
    ])

    result, audit, _, _ = execute(
        tmp_path,
        underlying,
        char="2",
        attempts=2,
    )

    events = provider_events(audit, result.run_id)

    assert underlying.calls == 2
    assert events[-1]["event_type"] == "PROVIDER_CALL_COMPLETED"
    assert events[-1]["event_payload"]["consumed_request_units"] == 2
    assert result.worker_result.requests_used == 2


def test_failed_provider_call_is_audited(tmp_path):
    underlying = SequenceFetcher([
        RetryableProviderError("down"),
    ])

    result, audit, _, _ = execute(
        tmp_path,
        underlying,
        char="3",
        attempts=1,
    )

    events = provider_events(audit, result.run_id)

    assert result.worker_result.failed == 1
    assert events[-1]["event_type"] == "PROVIDER_CALL_FAILED"
    assert events[-1]["event_payload"]["consumed_request_units"] == 1
    assert audit.audit_integrity().ok is True


def test_quota_refusal_records_zero_consumption(tmp_path):
    path = tmp_path / "runtime.db"
    audit = SQLiteRuntimeAuditLedger(path)
    persistence = SQLiteAcquisitionStore(path)
    underlying = SequenceFetcher([
        {"value": 1},
        {"must_not": "run"},
    ])
    stack, clock = runtime(
        tmp_path,
        underlying,
        quota=1,
        attempts=1,
    )

    result = execute_audited_tennis_acquisition_queue(
        queue_manifest={
            "sport": "tennis",
            "queue": [
                item(char="4"),
                item(char="5"),
            ],
        },
        policy_fingerprint=policy_fp(audit),
        audit_ledger=audit,
        fetcher=stack.fetcher,
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=5),
        clock=clock,
        request_budget=stack.request_budget,
    )

    failed = [
        event
        for event in provider_events(audit, result.run_id)
        if event["event_type"] == "PROVIDER_CALL_FAILED"
    ]

    assert underlying.calls == 1
    assert result.worker_result.processed == 1
    assert result.worker_result.failed == 1
    assert failed[-1]["event_payload"]["consumed_request_units"] == 0


def test_raw_provider_payload_is_not_copied_into_audit_event(tmp_path):
    secret = "RAW_PAYLOAD_SHOULD_STAY_IN_RAW_LEDGER"

    result, audit, persistence, _ = execute(
        tmp_path,
        SequenceFetcher([{"private_raw": secret}]),
        char="6",
    )

    serialized_events = str(audit.list_events(result.run_id))

    assert secret not in serialized_events
    assert persistence.audit_integrity().ok is True


def test_non_mapping_payload_is_audited_as_failure(tmp_path):
    result, audit, _, _ = execute(
        tmp_path,
        SequenceFetcher([["not", "a", "mapping"]]),
        char="7",
    )

    events = provider_events(audit, result.run_id)

    assert result.worker_result.failed == 1
    assert events[-1]["event_type"] == "PROVIDER_CALL_FAILED"
    assert (
        events[-1]["event_payload"]["reason_code"]
        == "PROVIDER_PAYLOAD_NOT_MAPPING"
    )


def test_provider_call_audit_preserves_hash_chain(tmp_path):
    _, audit, _, _ = execute(
        tmp_path,
        SequenceFetcher([{"value": 7}]),
        char="8",
    )

    report = audit.audit_integrity()

    assert report.ok is True
    assert report.errors == ()
