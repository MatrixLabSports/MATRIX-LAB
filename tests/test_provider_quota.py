from datetime import datetime, timedelta, timezone

import pytest

from app.application.tennis.acquisition_worker import (
    execute_tennis_acquisition_queue,
)
from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.acquisition_worker import WorkerLimits
from app.core.provider_quota import (
    ProviderQuotaExceeded,
    ProviderQuotaPolicy,
    QuotaGuardedFetcher,
    SQLiteProviderQuotaStore,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


class FakeFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, queue_item):
        self.calls += 1
        return {"ok": True, "subject": queue_item["subject_key"]}


def policy(provider="P1", limit=3, window=60):
    return ProviderQuotaPolicy(
        provider_key=provider,
        window_seconds=window,
        max_request_units=limit,
    )


def queue_item(subject="PLAYER:1", char="1", cost=1, provider="P1"):
    return {
        "sport": "tennis",
        "subject_key": subject,
        "provider_key": provider,
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": char * 64,
        "estimated_request_cost": cost,
        "source_fingerprint": "a" * 64,
    }


def test_quota_allows_within_limit(tmp_path):
    store = SQLiteProviderQuotaStore(tmp_path / "runtime.db")
    p = policy(limit=3)

    first = store.reserve(policy=p, request_units=1, now=NOW)
    second = store.reserve(policy=p, request_units=2, now=NOW)

    assert first.allowed is True
    assert second.allowed is True
    assert second.used_after == 3
    assert second.remaining_units == 0


def test_quota_blocks_without_mutating_usage(tmp_path):
    store = SQLiteProviderQuotaStore(tmp_path / "runtime.db")
    p = policy(limit=2)

    store.reserve(policy=p, request_units=2, now=NOW)
    blocked = store.reserve(policy=p, request_units=1, now=NOW)

    assert blocked.allowed is False
    assert blocked.reason_code == "PROVIDER_QUOTA_EXCEEDED"
    assert store.usage(policy=p, now=NOW) == 2


def test_next_window_resets_effective_usage(tmp_path):
    store = SQLiteProviderQuotaStore(tmp_path / "runtime.db")
    p = policy(limit=1, window=60)

    store.reserve(policy=p, request_units=1, now=NOW)
    later = NOW + timedelta(seconds=60)
    decision = store.reserve(policy=p, request_units=1, now=later)

    assert decision.allowed is True
    assert decision.used_before == 0


def test_usage_persists_after_reopen(tmp_path):
    path = tmp_path / "runtime.db"
    p = policy(limit=5)

    first = SQLiteProviderQuotaStore(path)
    first.reserve(policy=p, request_units=3, now=NOW)

    reopened = SQLiteProviderQuotaStore(path)

    assert reopened.usage(policy=p, now=NOW) == 3


def test_providers_are_isolated(tmp_path):
    store = SQLiteProviderQuotaStore(tmp_path / "runtime.db")
    p1 = policy(provider="P1", limit=1)
    p2 = policy(provider="P2", limit=1)

    assert store.reserve(policy=p1, request_units=1, now=NOW).allowed
    assert store.reserve(policy=p2, request_units=1, now=NOW).allowed


def test_naive_time_is_rejected(tmp_path):
    store = SQLiteProviderQuotaStore(tmp_path / "runtime.db")

    with pytest.raises(ValueError, match="TIMEZONE_UNVERIFIED"):
        store.reserve(
            policy=policy(),
            request_units=1,
            now=NOW.replace(tzinfo=None),
        )


def test_guarded_fetcher_fails_closed_without_policy(tmp_path):
    underlying = FakeFetcher()
    guarded = QuotaGuardedFetcher(
        fetcher=underlying,
        quota_store=SQLiteProviderQuotaStore(tmp_path / "runtime.db"),
        policies={},
        clock=lambda: NOW,
    )

    with pytest.raises(
        ValueError,
        match="MISSING_PROVIDER_QUOTA_POLICY",
    ):
        guarded.fetch(queue_item())

    assert underlying.calls == 0


def test_guarded_fetcher_does_not_call_provider_when_blocked(tmp_path):
    underlying = FakeFetcher()
    store = SQLiteProviderQuotaStore(tmp_path / "runtime.db")
    guarded = QuotaGuardedFetcher(
        fetcher=underlying,
        quota_store=store,
        policies={"P1": policy(limit=1)},
        clock=lambda: NOW,
    )

    guarded.fetch(queue_item(char="1"))

    with pytest.raises(ProviderQuotaExceeded):
        guarded.fetch(queue_item(subject="PLAYER:2", char="2"))

    assert underlying.calls == 1


def test_worker_integration_respects_durable_provider_quota(tmp_path):
    path = tmp_path / "runtime.db"
    persistence = SQLiteAcquisitionStore(path)
    quota_store = SQLiteProviderQuotaStore(path)
    underlying = FakeFetcher()

    guarded = QuotaGuardedFetcher(
        fetcher=underlying,
        quota_store=quota_store,
        policies={"P1": policy(limit=1)},
        clock=lambda: NOW,
    )

    result = execute_tennis_acquisition_queue(
        queue_manifest={
            "sport": "tennis",
            "queue": [
                queue_item(subject="A", char="3"),
                queue_item(subject="B", char="4"),
            ],
        },
        fetcher=guarded,
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=10),
    )

    assert result.processed == 1
    assert result.failed == 1
    assert underlying.calls == 1
    assert persistence.audit_integrity().ok is True


def test_quota_decision_keeps_safety_flags_false(tmp_path):
    store = SQLiteProviderQuotaStore(tmp_path / "runtime.db")
    decision = store.reserve(
        policy=policy(limit=2),
        request_units=1,
        now=NOW,
    )

    payload = decision.payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
