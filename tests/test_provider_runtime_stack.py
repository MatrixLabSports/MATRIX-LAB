from datetime import datetime, timedelta, timezone

import pytest

from app.application.tennis.acquisition_worker import (
    execute_tennis_acquisition_queue,
)
from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.acquisition_worker import WorkerLimits
from app.core.provider_circuit_breaker import (
    ProviderCircuitOpen,
    ProviderCircuitPolicy,
    SQLiteProviderCircuitStore,
)
from app.core.provider_quota import (
    ProviderQuotaPolicy,
    SQLiteProviderQuotaStore,
)
from app.core.provider_request_budget import (
    ExecutionRequestBudget,
    ProviderRequestBudgetExceeded,
)
from app.core.provider_retry import (
    ProviderRetryPolicy,
    RetryableProviderError,
)
from app.core.provider_runtime_stack import (
    build_provider_runtime_stack,
)


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


def queue_item(char="1", cost=1):
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


def policies(
    *,
    quota=20,
    threshold=20,
    cooldown=60,
    attempts=3,
):
    return (
        {
            "P1": ProviderQuotaPolicy(
                provider_key="P1",
                window_seconds=3600,
                max_request_units=quota,
            )
        },
        {
            "P1": ProviderCircuitPolicy(
                provider_key="P1",
                failure_threshold=threshold,
                cooldown_seconds=cooldown,
            )
        },
        {
            "P1": ProviderRetryPolicy(
                provider_key="P1",
                max_attempts=attempts,
                base_delay_seconds=0.0,
                max_delay_seconds=0.0,
                jitter_ratio=0.0,
            )
        },
    )


def stack(
    tmp_path,
    underlying,
    *,
    budget=10,
    quota=20,
    threshold=20,
    cooldown=60,
    attempts=3,
    clock=None,
):
    path = tmp_path / "runtime.db"
    quota_store = SQLiteProviderQuotaStore(path)
    circuit_store = SQLiteProviderCircuitStore(path)
    q, c, r = policies(
        quota=quota,
        threshold=threshold,
        cooldown=cooldown,
        attempts=attempts,
    )
    active_clock = clock or Clock(NOW)

    runtime = build_provider_runtime_stack(
        fetcher=underlying,
        quota_store=quota_store,
        circuit_store=circuit_store,
        quota_policies=q,
        circuit_policies=c,
        retry_policies=r,
        max_request_units=budget,
        clock=active_clock,
        sleeper=lambda _: None,
    )

    return runtime, quota_store, circuit_store, q["P1"], c["P1"]


def test_success_after_retry_reports_actual_attempt_units(tmp_path):
    underlying = SequenceFetcher([
        RetryableProviderError("temporary"),
        {"value": 42},
    ])
    runtime, _, _, _, _ = stack(
        tmp_path,
        underlying,
        budget=5,
        attempts=3,
    )
    persistence = SQLiteAcquisitionStore(tmp_path / "runtime.db")

    result = execute_tennis_acquisition_queue(
        queue_manifest={
            "sport": "tennis",
            "queue": [queue_item()],
        },
        fetcher=runtime.fetcher,
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=5),
        request_budget=runtime.request_budget,
    )

    assert result.processed == 1
    assert result.failed == 0
    assert result.requests_used == 2
    assert runtime.request_budget.used_units == 2
    assert underlying.calls == 2


def test_failed_attempt_is_counted_even_without_success(tmp_path):
    underlying = SequenceFetcher([
        RetryableProviderError("down"),
    ])
    runtime, _, _, _, _ = stack(
        tmp_path,
        underlying,
        budget=5,
        attempts=1,
    )
    persistence = SQLiteAcquisitionStore(tmp_path / "runtime.db")

    result = execute_tennis_acquisition_queue(
        queue_manifest={
            "sport": "tennis",
            "queue": [queue_item()],
        },
        fetcher=runtime.fetcher,
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=5),
        request_budget=runtime.request_budget,
    )

    assert result.processed == 0
    assert result.failed == 1
    assert result.requests_used == 1
    assert underlying.calls == 1


def test_budget_prevents_retry_from_overshooting_worker_limit(tmp_path):
    underlying = SequenceFetcher([
        RetryableProviderError("a"),
        RetryableProviderError("b"),
        {"ok": True},
    ])
    runtime, quota_store, _, quota_policy, _ = stack(
        tmp_path,
        underlying,
        budget=2,
        attempts=3,
    )

    with pytest.raises(ProviderRequestBudgetExceeded):
        runtime.fetcher.fetch(queue_item())

    assert underlying.calls == 2
    assert runtime.request_budget.used_units == 2
    assert quota_store.usage(
        policy=quota_policy,
        now=NOW,
    ) == 2


def test_open_circuit_refusal_releases_execution_budget(tmp_path):
    clock = Clock(NOW)
    underlying = SequenceFetcher([{"ok": True}])
    runtime, quota_store, circuit_store, quota_policy, circuit_policy = stack(
        tmp_path,
        underlying,
        budget=3,
        threshold=1,
        clock=clock,
    )

    circuit_store.record_failure(
        policy=circuit_policy,
        now=NOW,
    )

    with pytest.raises(ProviderCircuitOpen):
        runtime.fetcher.fetch(queue_item())

    assert runtime.request_budget.used_units == 0
    assert quota_store.usage(policy=quota_policy, now=NOW) == 0
    assert underlying.calls == 0


def test_quota_refusal_releases_execution_budget(tmp_path):
    underlying = SequenceFetcher([
        {"ok": True},
        {"should_not": "run"},
    ])
    runtime, quota_store, _, quota_policy, _ = stack(
        tmp_path,
        underlying,
        budget=3,
        quota=1,
        attempts=1,
    )

    assert runtime.fetcher.fetch(queue_item(char="2")) == {"ok": True}

    with pytest.raises(Exception) as captured:
        runtime.fetcher.fetch(queue_item(char="3"))

    assert "PROVIDER_QUOTA_EXCEEDED" in str(captured.value)
    assert runtime.request_budget.used_units == 1
    assert quota_store.usage(policy=quota_policy, now=NOW) == 1
    assert underlying.calls == 1


def test_half_open_quota_refusal_does_not_false_close_circuit(tmp_path):
    clock = Clock(NOW)
    underlying = SequenceFetcher([{"should_not": "run"}])
    runtime, quota_store, circuit_store, quota_policy, circuit_policy = stack(
        tmp_path,
        underlying,
        budget=3,
        quota=1,
        threshold=1,
        cooldown=60,
        attempts=1,
        clock=clock,
    )

    quota_store.reserve(
        policy=quota_policy,
        request_units=1,
        now=NOW,
    )
    circuit_store.record_failure(
        policy=circuit_policy,
        now=NOW,
    )

    clock.value = NOW + timedelta(seconds=60)

    with pytest.raises(Exception) as captured:
        runtime.fetcher.fetch(queue_item(char="4"))

    assert "PROVIDER_QUOTA_EXCEEDED" in str(captured.value)

    snapshot = circuit_store.snapshot("P1")
    assert snapshot["state"] == "HALF_OPEN"
    assert snapshot["probe_in_flight"] is False
    assert runtime.request_budget.used_units == 0
    assert underlying.calls == 0


def test_released_half_open_probe_can_be_claimed_again(tmp_path):
    clock = Clock(NOW)
    circuit_store = SQLiteProviderCircuitStore(tmp_path / "runtime.db")
    p = ProviderCircuitPolicy(
        provider_key="P1",
        failure_threshold=1,
        cooldown_seconds=60,
    )

    circuit_store.record_failure(policy=p, now=NOW)
    clock.value = NOW + timedelta(seconds=60)

    first = circuit_store.before_request(policy=p, now=clock())
    assert first.allowed is True

    circuit_store.release_neutral_probe(policy=p)

    second = circuit_store.before_request(policy=p, now=clock())
    assert second.allowed is True
    assert second.state == "HALF_OPEN"


def test_worker_rejects_mismatched_budget_limit(tmp_path):
    persistence = SQLiteAcquisitionStore(tmp_path / "runtime.db")

    with pytest.raises(
        ValueError,
        match="REQUEST_BUDGET_LIMIT_MISMATCH",
    ):
        execute_tennis_acquisition_queue(
            queue_manifest={"sport": "tennis", "queue": []},
            fetcher=SequenceFetcher([]),
            raw_ledger=persistence,
            checkpoints=persistence,
            limits=WorkerLimits(max_items=10, max_requests=5),
            request_budget=ExecutionRequestBudget(6),
        )


def test_runtime_stack_rejects_mismatched_provider_policy_sets(tmp_path):
    q, c, _ = policies()

    with pytest.raises(
        ValueError,
        match="PROVIDER_POLICY_SET_MISMATCH",
    ):
        build_provider_runtime_stack(
            fetcher=SequenceFetcher([{"ok": True}]),
            quota_store=SQLiteProviderQuotaStore(tmp_path / "runtime.db"),
            circuit_store=SQLiteProviderCircuitStore(tmp_path / "runtime.db"),
            quota_policies=q,
            circuit_policies=c,
            retry_policies={},
            max_request_units=5,
            clock=lambda: NOW,
            sleeper=lambda _: None,
        )


def test_request_budget_safety_flags_remain_false():
    budget = ExecutionRequestBudget(2)
    payload = budget.reserve(1).payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
