from datetime import datetime, timedelta, timezone

import pytest

from app.core.provider_circuit_breaker import (
    CircuitBreakerFetcher,
    ProviderCircuitOpen,
    ProviderCircuitPolicy,
    SQLiteProviderCircuitStore,
)
from app.core.provider_quota import (
    ProviderQuotaPolicy,
    QuotaGuardedFetcher,
    SQLiteProviderQuotaStore,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class SuccessfulFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, queue_item):
        self.calls += 1
        return {"ok": True}


class FailingFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, queue_item):
        self.calls += 1
        raise RuntimeError("provider down")


class SequenceFetcher:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def fetch(self, queue_item):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def policy(provider="P1", threshold=2, cooldown=60):
    return ProviderCircuitPolicy(
        provider_key=provider,
        failure_threshold=threshold,
        cooldown_seconds=cooldown,
    )


def item(provider="P1", char="1", cost=1):
    return {
        "sport": "tennis",
        "subject_key": "PLAYER:1",
        "provider_key": provider,
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": char * 64,
        "estimated_request_cost": cost,
        "source_fingerprint": "a" * 64,
    }


def test_closed_circuit_allows_request(tmp_path):
    store = SQLiteProviderCircuitStore(tmp_path / "runtime.db")

    decision = store.before_request(
        policy=policy(),
        now=NOW,
    )

    assert decision.allowed is True
    assert decision.state == "CLOSED"


def test_failures_open_circuit_at_threshold(tmp_path):
    store = SQLiteProviderCircuitStore(tmp_path / "runtime.db")
    p = policy(threshold=2)

    store.record_failure(policy=p, now=NOW)
    assert store.snapshot("P1")["state"] == "CLOSED"

    store.record_failure(policy=p, now=NOW)
    snapshot = store.snapshot("P1")

    assert snapshot["state"] == "OPEN"
    assert snapshot["failure_count"] == 2


def test_open_circuit_blocks_without_calling_provider(tmp_path):
    clock = Clock(NOW)
    store = SQLiteProviderCircuitStore(tmp_path / "runtime.db")
    underlying = FailingFetcher()
    guarded = CircuitBreakerFetcher(
        fetcher=underlying,
        circuit_store=store,
        policies={"P1": policy(threshold=1)},
        clock=clock,
    )

    with pytest.raises(RuntimeError):
        guarded.fetch(item(char="1"))

    with pytest.raises(ProviderCircuitOpen):
        guarded.fetch(item(char="2"))

    assert underlying.calls == 1


def test_cooldown_allows_single_half_open_probe(tmp_path):
    clock = Clock(NOW)
    store = SQLiteProviderCircuitStore(tmp_path / "runtime.db")
    p = policy(threshold=1, cooldown=60)

    store.record_failure(policy=p, now=NOW)
    clock.value = NOW + timedelta(seconds=60)

    first = store.before_request(policy=p, now=clock())
    second = store.before_request(policy=p, now=clock())

    assert first.allowed is True
    assert first.state == "HALF_OPEN"
    assert second.allowed is False
    assert second.reason_code == "HALF_OPEN_PROBE_IN_FLIGHT"


def test_successful_half_open_probe_closes_circuit(tmp_path):
    clock = Clock(NOW)
    store = SQLiteProviderCircuitStore(tmp_path / "runtime.db")
    p = policy(threshold=1, cooldown=60)
    underlying = SuccessfulFetcher()
    guarded = CircuitBreakerFetcher(
        fetcher=underlying,
        circuit_store=store,
        policies={"P1": p},
        clock=clock,
    )

    store.record_failure(policy=p, now=NOW)
    clock.value = NOW + timedelta(seconds=60)

    assert guarded.fetch(item()) == {"ok": True}
    assert store.snapshot("P1")["state"] == "CLOSED"
    assert store.snapshot("P1")["failure_count"] == 0


def test_failed_half_open_probe_reopens_circuit(tmp_path):
    clock = Clock(NOW)
    store = SQLiteProviderCircuitStore(tmp_path / "runtime.db")
    p = policy(threshold=1, cooldown=60)
    underlying = FailingFetcher()
    guarded = CircuitBreakerFetcher(
        fetcher=underlying,
        circuit_store=store,
        policies={"P1": p},
        clock=clock,
    )

    store.record_failure(policy=p, now=NOW)
    clock.value = NOW + timedelta(seconds=60)

    with pytest.raises(RuntimeError):
        guarded.fetch(item())

    snapshot = store.snapshot("P1")
    assert snapshot["state"] == "OPEN"
    assert snapshot["opened_at_epoch"] == int(clock().timestamp())


def test_circuit_state_persists_after_reopen(tmp_path):
    path = tmp_path / "runtime.db"
    p = policy(threshold=1)

    first = SQLiteProviderCircuitStore(path)
    first.record_failure(policy=p, now=NOW)

    reopened = SQLiteProviderCircuitStore(path)

    assert reopened.snapshot("P1")["state"] == "OPEN"


def test_providers_have_independent_circuits(tmp_path):
    store = SQLiteProviderCircuitStore(tmp_path / "runtime.db")
    p1 = policy(provider="P1", threshold=1)
    p2 = policy(provider="P2", threshold=1)

    store.record_failure(policy=p1, now=NOW)

    assert store.snapshot("P1")["state"] == "OPEN"
    assert store.before_request(policy=p2, now=NOW).allowed is True


def test_missing_policy_fails_closed(tmp_path):
    guarded = CircuitBreakerFetcher(
        fetcher=SuccessfulFetcher(),
        circuit_store=SQLiteProviderCircuitStore(tmp_path / "runtime.db"),
        policies={},
        clock=lambda: NOW,
    )

    with pytest.raises(
        ValueError,
        match="MISSING_PROVIDER_CIRCUIT_POLICY",
    ):
        guarded.fetch(item())


def test_quota_block_does_not_count_as_provider_failure(tmp_path):
    path = tmp_path / "runtime.db"
    clock = Clock(NOW)

    underlying = SuccessfulFetcher()
    quota_store = SQLiteProviderQuotaStore(path)
    quota_guard = QuotaGuardedFetcher(
        fetcher=underlying,
        quota_store=quota_store,
        policies={
            "P1": ProviderQuotaPolicy(
                provider_key="P1",
                window_seconds=60,
                max_request_units=1,
            )
        },
        clock=clock,
    )

    circuit_store = SQLiteProviderCircuitStore(path)
    circuit_guard = CircuitBreakerFetcher(
        fetcher=quota_guard,
        circuit_store=circuit_store,
        policies={"P1": policy(threshold=1)},
        clock=clock,
    )

    circuit_guard.fetch(item(char="3"))

    with pytest.raises(Exception) as captured:
        circuit_guard.fetch(item(char="4"))

    assert "PROVIDER_QUOTA_EXCEEDED" in str(captured.value)
    assert circuit_store.snapshot("P1")["failure_count"] == 0
    assert circuit_store.snapshot("P1")["state"] == "CLOSED"
    assert underlying.calls == 1


def test_circuit_decision_keeps_safety_flags_false(tmp_path):
    store = SQLiteProviderCircuitStore(tmp_path / "runtime.db")

    payload = store.before_request(
        policy=policy(),
        now=NOW,
    ).payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
