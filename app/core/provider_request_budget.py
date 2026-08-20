from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Mapping, Protocol

from app.core.provider_circuit_breaker import ProviderCircuitOpen
from app.core.provider_quota import ProviderQuotaExceeded


class ProviderFetcher(Protocol):
    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class ProviderRequestBudgetDecision:
    allowed: bool
    requested_units: int
    used_before: int
    used_after: int
    remaining_units: int
    max_units: int
    reason_code: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-request-budget-decision/1",
            "allowed": self.allowed,
            "requested_units": self.requested_units,
            "used_before": self.used_before,
            "used_after": self.used_after,
            "remaining_units": self.remaining_units,
            "max_units": self.max_units,
            "reason_code": self.reason_code,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


class ProviderRequestBudgetExceeded(RuntimeError):
    def __init__(self, decision: ProviderRequestBudgetDecision) -> None:
        self.decision = decision
        super().__init__(
            "PROVIDER_REQUEST_BUDGET_EXCEEDED:"
            f"requested={decision.requested_units}:"
            f"remaining={decision.remaining_units}"
        )


class ExecutionRequestBudget:
    def __init__(self, max_units: int) -> None:
        if (
            isinstance(max_units, bool)
            or not isinstance(max_units, int)
            or max_units < 0
        ):
            raise ValueError("INVALID_MAX_REQUEST_UNITS")

        self.max_units = max_units
        self._used_units = 0
        self._lock = threading.Lock()

    @property
    def used_units(self) -> int:
        with self._lock:
            return self._used_units

    @property
    def remaining_units(self) -> int:
        with self._lock:
            return self.max_units - self._used_units

    def reserve(self, units: int) -> ProviderRequestBudgetDecision:
        if (
            isinstance(units, bool)
            or not isinstance(units, int)
            or units <= 0
        ):
            raise ValueError("INVALID_REQUEST_UNITS")

        with self._lock:
            used_before = self._used_units
            proposed = used_before + units

            if proposed > self.max_units:
                decision = ProviderRequestBudgetDecision(
                    allowed=False,
                    requested_units=units,
                    used_before=used_before,
                    used_after=used_before,
                    remaining_units=self.max_units - used_before,
                    max_units=self.max_units,
                    reason_code="PROVIDER_REQUEST_BUDGET_EXCEEDED",
                )
                raise ProviderRequestBudgetExceeded(decision)

            self._used_units = proposed

            return ProviderRequestBudgetDecision(
                allowed=True,
                requested_units=units,
                used_before=used_before,
                used_after=proposed,
                remaining_units=self.max_units - proposed,
                max_units=self.max_units,
                reason_code="PASS",
            )

    def release_neutral(self, units: int) -> None:
        if (
            isinstance(units, bool)
            or not isinstance(units, int)
            or units <= 0
        ):
            raise ValueError("INVALID_REQUEST_UNITS")

        with self._lock:
            if units > self._used_units:
                raise ValueError("REQUEST_BUDGET_RELEASE_UNDERFLOW")
            self._used_units -= units


_NEUTRAL_VALUE_ERRORS = {
    "MISSING_PROVIDER_KEY",
    "MISSING_PROVIDER_CIRCUIT_POLICY",
    "PROVIDER_CIRCUIT_POLICY_MISMATCH",
    "MISSING_PROVIDER_QUOTA_POLICY",
    "PROVIDER_QUOTA_POLICY_MISMATCH",
    "OPEN_CIRCUIT_WITHOUT_TIMESTAMP",
    "INVALID_CIRCUIT_STATE",
    "TIMEZONE_UNVERIFIED",
}


class BudgetGuardedFetcher:
    def __init__(
        self,
        *,
        fetcher: ProviderFetcher,
        budget: ExecutionRequestBudget,
    ) -> None:
        self.fetcher = fetcher
        self.budget = budget

    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        request_units = queue_item.get("estimated_request_cost")
        if (
            isinstance(request_units, bool)
            or not isinstance(request_units, int)
            or request_units <= 0
        ):
            raise ValueError("INVALID_REQUEST_UNITS")

        self.budget.reserve(request_units)

        try:
            return self.fetcher.fetch(queue_item)
        except (ProviderCircuitOpen, ProviderQuotaExceeded):
            self.budget.release_neutral(request_units)
            raise
        except ValueError as error:
            if str(error) in _NEUTRAL_VALUE_ERRORS:
                self.budget.release_neutral(request_units)
            raise
