from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from app.core.provider_request_budget import ExecutionRequestBudget
from app.core.runtime_audit_ledger import SQLiteRuntimeAuditLedger


def _aware_utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("TIMEZONE_UNVERIFIED")
    return value.astimezone(timezone.utc)


def _validate_hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")

    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error

    return value.lower()


class ProviderCallAuditFetcher:
    def __init__(
        self,
        *,
        fetcher,
        audit_ledger: SQLiteRuntimeAuditLedger,
        run_id: str,
        clock: Callable[[], datetime],
        request_budget: ExecutionRequestBudget | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.audit_ledger = audit_ledger
        self.run_id = _validate_hex64("RUN_ID", run_id)
        self.clock = clock
        self.request_budget = request_budget

    def _budget_used(self) -> int | None:
        if self.request_budget is None:
            return None
        return self.request_budget.used_units

    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(queue_item, Mapping):
            raise ValueError("INVALID_QUEUE_ITEM")

        provider_key = queue_item.get("provider_key")
        if not isinstance(provider_key, str) or not provider_key:
            raise ValueError("MISSING_PROVIDER_KEY")

        queue_fingerprint = _validate_hex64(
            "QUEUE_ITEM_FINGERPRINT",
            queue_item.get("queue_item_fingerprint"),
        )

        request_cost = queue_item.get("estimated_request_cost")
        if (
            isinstance(request_cost, bool)
            or not isinstance(request_cost, int)
            or request_cost <= 0
        ):
            raise ValueError("INVALID_REQUEST_COST")

        budget_before = self._budget_used()

        self.audit_ledger.append_event(
            run_id=self.run_id,
            event_type="PROVIDER_CALL_STARTED",
            event_payload={
                "provider_key": provider_key,
                "queue_item_fingerprint": queue_fingerprint,
                "estimated_request_cost": request_cost,
                "request_budget_used_before": budget_before,
            },
            created_at=_aware_utc(self.clock()),
        )

        try:
            payload = self.fetcher.fetch(queue_item)

            if not isinstance(payload, Mapping):
                raise ValueError("PROVIDER_PAYLOAD_NOT_MAPPING")

        except Exception as error:
            budget_after = self._budget_used()
            consumed = (
                None
                if budget_before is None or budget_after is None
                else budget_after - budget_before
            )

            self.audit_ledger.append_event(
                run_id=self.run_id,
                event_type="PROVIDER_CALL_FAILED",
                event_payload={
                    "provider_key": provider_key,
                    "queue_item_fingerprint": queue_fingerprint,
                    "error_type": type(error).__name__,
                    "reason_code": str(error),
                    "request_budget_used_after": budget_after,
                    "consumed_request_units": consumed,
                },
                created_at=_aware_utc(self.clock()),
            )
            raise

        budget_after = self._budget_used()
        consumed = (
            None
            if budget_before is None or budget_after is None
            else budget_after - budget_before
        )

        self.audit_ledger.append_event(
            run_id=self.run_id,
            event_type="PROVIDER_CALL_COMPLETED",
            event_payload={
                "provider_key": provider_key,
                "queue_item_fingerprint": queue_fingerprint,
                "request_budget_used_after": budget_after,
                "consumed_request_units": consumed,
            },
            created_at=_aware_utc(self.clock()),
        )

        return payload
