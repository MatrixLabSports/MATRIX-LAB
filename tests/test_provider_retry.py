from datetime import datetime, timezone

import pytest

from app.application.tennis.acquisition_worker import (
    execute_tennis_acquisition_queue,
)
from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.acquisition_worker import WorkerLimits
from app.core.provider_circuit_breaker import (
    ProviderCircuitDecision,
    ProviderCircuitOpen,
)
from app.core.provider_quota import (
    ProviderQuotaDecision,
    ProviderQuotaExceeded,
    ProviderQuotaPolicy,
    QuotaGuardedFetcher,
    SQLiteProviderQuotaStore,
)
from app.core.provider_retry import (
    BoundedRetryFetcher,
    NonRetryableProviderError,
    ProviderRetryExhausted,
    ProviderRetryPolicy,
    RetryableProviderError,
    retry_delay_seconds,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def policy(
    provider="P1",
    attempts=3,
    base=1.0,
    maximum=8.0,
    jitter=0.0,
):
    return ProviderRetryPolicy(
        provider_key=provider,
        max_attempts=attempts,
        base_delay_seconds=base,
        max_delay_seconds=maximum,
        jitter_ratio=jitter,
    )


def item(char="1", provider="P1", cost=1):
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


def test_retry_delay_is_exponential_and_capped():
    p = policy(base=1.0, maximum=4.0, jitter=0.0)

    assert retry_delay_seconds(
        policy=p,
        queue_item_fingerprint="1" * 64,
        retry_number=1,
    ) == 1.0
    assert retry_delay_seconds(
        policy=p,
        queue_item_fingerprint="1" * 64,
        retry_number=2,
    ) == 2.0
    assert retry_delay_seconds(
        policy=p,
        queue_item_fingerprint="1" * 64,
        retry_number=3,
    ) == 4.0
    assert retry_delay_seconds(
        policy=p,
        queue_item_fingerprint="1" * 64,
        retry_number=4,
    ) == 4.0


def test_jitter_is_deterministic_for_same_queue_item():
    p = policy(jitter=0.25)

    a = retry_delay_seconds(
        policy=p,
        queue_item_fingerprint="a" * 64,
        retry_number=2,
    )
    b = retry_delay_seconds(
        policy=p,
        queue_item_fingerprint="a" * 64,
        retry_number=2,
    )

    assert a == b
    assert 0 <= a <= p.max_delay_seconds


def test_transient_failures_retry_until_success():
    underlying = SequenceFetcher([
        RetryableProviderError("temporary"),
        TimeoutError("timeout"),
        {"ok": True},
    ])
    sleeps = []

    guarded = BoundedRetryFetcher(
        fetcher=underlying,
        policies={"P1": policy(attempts=3)},
        sleeper=sleeps.append,
    )

    assert guarded.fetch(item()) == {"ok": True}
    assert underlying.calls == 3
    assert len(sleeps) == 2


def test_retry_exhaustion_is_bounded():
    underlying = SequenceFetcher([
        RetryableProviderError("a"),
        RetryableProviderError("b"),
        RetryableProviderError("c"),
    ])

    guarded = BoundedRetryFetcher(
        fetcher=underlying,
        policies={"P1": policy(attempts=3)},
        sleeper=lambda _: None,
    )

    with pytest.raises(ProviderRetryExhausted) as captured:
        guarded.fetch(item())

    assert captured.value.attempts == 3
    assert underlying.calls == 3


def test_non_retryable_error_fails_immediately():
    underlying = SequenceFetcher([
        NonRetryableProviderError("bad request"),
    ])
    sleeps = []

    guarded = BoundedRetryFetcher(
        fetcher=underlying,
        policies={"P1": policy()},
        sleeper=sleeps.append,
    )

    with pytest.raises(NonRetryableProviderError):
        guarded.fetch(item())

    assert underlying.calls == 1
    assert sleeps == []


def test_quota_exceeded_is_never_retried():
    decision = ProviderQuotaDecision(
        allowed=False,
        provider_key="P1",
        request_units=1,
        used_before=1,
        used_after=1,
        remaining_units=0,
        window_start_epoch=0,
        window_end_epoch=60,
        retry_after_seconds=60,
        reason_code="PROVIDER_QUOTA_EXCEEDED",
    )
    underlying = SequenceFetcher([
        ProviderQuotaExceeded(decision),
    ])

    guarded = BoundedRetryFetcher(
        fetcher=underlying,
        policies={"P1": policy()},
        sleeper=lambda _: pytest.fail("must not sleep"),
    )

    with pytest.raises(ProviderQuotaExceeded):
        guarded.fetch(item())

    assert underlying.calls == 1


def test_open_circuit_is_never_retried():
    decision = ProviderCircuitDecision(
        allowed=False,
        provider_key="P1",
        state="OPEN",
        failure_count=2,
        retry_after_seconds=60,
        reason_code="PROVIDER_CIRCUIT_OPEN",
    )
    underlying = SequenceFetcher([
        ProviderCircuitOpen(decision),
    ])

    guarded = BoundedRetryFetcher(
        fetcher=underlying,
        policies={"P1": policy()},
        sleeper=lambda _: pytest.fail("must not sleep"),
    )

    with pytest.raises(ProviderCircuitOpen):
        guarded.fetch(item())

    assert underlying.calls == 1


def test_missing_retry_policy_fails_closed():
    guarded = BoundedRetryFetcher(
        fetcher=SequenceFetcher([{"ok": True}]),
        policies={},
        sleeper=lambda _: None,
    )

    with pytest.raises(
        ValueError,
        match="MISSING_PROVIDER_RETRY_POLICY",
    ):
        guarded.fetch(item())


def test_each_retry_attempt_consumes_durable_quota(tmp_path):
    path = tmp_path / "runtime.db"
    quota_store = SQLiteProviderQuotaStore(path)
    underlying = SequenceFetcher([
        RetryableProviderError("a"),
        RetryableProviderError("b"),
        {"ok": True},
    ])

    quota_guard = QuotaGuardedFetcher(
        fetcher=underlying,
        quota_store=quota_store,
        policies={
            "P1": ProviderQuotaPolicy(
                provider_key="P1",
                window_seconds=60,
                max_request_units=3,
            )
        },
        clock=lambda: NOW,
    )

    retry_guard = BoundedRetryFetcher(
        fetcher=quota_guard,
        policies={"P1": policy(attempts=3, base=0.0, maximum=0.0)},
        sleeper=lambda _: None,
    )

    assert retry_guard.fetch(item()) == {"ok": True}
    assert underlying.calls == 3
    assert quota_store.usage(
        policy=ProviderQuotaPolicy(
            provider_key="P1",
            window_seconds=60,
            max_request_units=3,
        ),
        now=NOW,
    ) == 3


def test_worker_persists_success_after_bounded_retries(tmp_path):
    path = tmp_path / "runtime.db"
    persistence = SQLiteAcquisitionStore(path)

    underlying = SequenceFetcher([
        RetryableProviderError("temporary"),
        {"payload": 42},
    ])

    retry_guard = BoundedRetryFetcher(
        fetcher=underlying,
        policies={
            "P1": policy(
                attempts=2,
                base=0.0,
                maximum=0.0,
            )
        },
        sleeper=lambda _: None,
    )

    result = execute_tennis_acquisition_queue(
        queue_manifest={
            "sport": "tennis",
            "queue": [item(char="b")],
        },
        fetcher=retry_guard,
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert result.processed == 1
    assert result.failed == 0
    assert underlying.calls == 2
    assert persistence.audit_integrity().ok is True


def test_retry_policy_keeps_safety_flags_false():
    payload = policy().payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
