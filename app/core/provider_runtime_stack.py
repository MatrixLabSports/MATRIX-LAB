from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from app.core.provider_circuit_breaker import (
    CircuitBreakerFetcher,
    ProviderCircuitPolicy,
    SQLiteProviderCircuitStore,
)
from app.core.provider_quota import (
    ProviderQuotaPolicy,
    QuotaGuardedFetcher,
    SQLiteProviderQuotaStore,
)
from app.core.provider_request_budget import (
    BudgetGuardedFetcher,
    ExecutionRequestBudget,
)
from app.core.provider_retry import (
    BoundedRetryFetcher,
    ProviderRetryPolicy,
)


@dataclass(frozen=True)
class ProviderRuntimeStack:
    fetcher: Any
    request_budget: ExecutionRequestBudget


def build_provider_runtime_stack(
    *,
    fetcher,
    quota_store: SQLiteProviderQuotaStore,
    circuit_store: SQLiteProviderCircuitStore,
    quota_policies: Mapping[str, ProviderQuotaPolicy],
    circuit_policies: Mapping[str, ProviderCircuitPolicy],
    retry_policies: Mapping[str, ProviderRetryPolicy],
    max_request_units: int,
    clock: Callable[[], datetime],
    sleeper: Callable[[float], None],
) -> ProviderRuntimeStack:
    providers = set(quota_policies)

    if providers != set(circuit_policies):
        raise ValueError("PROVIDER_POLICY_SET_MISMATCH")

    if providers != set(retry_policies):
        raise ValueError("PROVIDER_POLICY_SET_MISMATCH")

    for provider_key in providers:
        if quota_policies[provider_key].provider_key != provider_key:
            raise ValueError("PROVIDER_QUOTA_POLICY_MISMATCH")
        if circuit_policies[provider_key].provider_key != provider_key:
            raise ValueError("PROVIDER_CIRCUIT_POLICY_MISMATCH")
        if retry_policies[provider_key].provider_key != provider_key:
            raise ValueError("PROVIDER_RETRY_POLICY_MISMATCH")

    request_budget = ExecutionRequestBudget(max_request_units)

    quota_guard = QuotaGuardedFetcher(
        fetcher=fetcher,
        quota_store=quota_store,
        policies=quota_policies,
        clock=clock,
    )

    circuit_guard = CircuitBreakerFetcher(
        fetcher=quota_guard,
        circuit_store=circuit_store,
        policies=circuit_policies,
        clock=clock,
    )

    budget_guard = BudgetGuardedFetcher(
        fetcher=circuit_guard,
        budget=request_budget,
    )

    retry_guard = BoundedRetryFetcher(
        fetcher=budget_guard,
        policies=retry_policies,
        sleeper=sleeper,
    )

    return ProviderRuntimeStack(
        fetcher=retry_guard,
        request_budget=request_budget,
    )
