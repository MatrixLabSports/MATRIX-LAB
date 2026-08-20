from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from app.core.runtime_audit_ledger import SQLiteRuntimeAuditLedger


_ALLOWED_SPORTS = {"football", "tennis"}


def _canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")

    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error

    return value.lower()


@dataclass(frozen=True)
class ProviderHealthSnapshot:
    provider_key: str
    sport: str
    run_ids: tuple[str, ...]
    calls_started: int
    calls_completed: int
    calls_failed: int
    zero_consumption_refusals: int
    consumed_request_units: int | None
    success_rate: float | None
    failure_rate: float | None
    snapshot_status: str
    reason_codes: tuple[str, ...]
    snapshot_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-health-snapshot/1",
            "provider_key": self.provider_key,
            "sport": self.sport,
            "run_ids": list(self.run_ids),
            "calls_started": self.calls_started,
            "calls_completed": self.calls_completed,
            "calls_failed": self.calls_failed,
            "zero_consumption_refusals": self.zero_consumption_refusals,
            "consumed_request_units": self.consumed_request_units,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "snapshot_status": self.snapshot_status,
            "reason_codes": list(self.reason_codes),
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def build_provider_health_snapshot(
    *,
    provider_key: str,
    sport: str,
    run_ids: Sequence[str],
    audit_ledger: SQLiteRuntimeAuditLedger,
) -> ProviderHealthSnapshot:
    if not isinstance(provider_key, str) or not provider_key.strip():
        raise ValueError("INVALID_PROVIDER_KEY")

    if sport not in _ALLOWED_SPORTS:
        raise ValueError("INVALID_SPORT")

    if not isinstance(run_ids, Sequence) or isinstance(
        run_ids,
        (str, bytes),
    ):
        raise ValueError("INVALID_RUN_IDS")

    normalized_run_ids = tuple(
        _validate_hex64("RUN_ID", run_id)
        for run_id in run_ids
    )

    if len(normalized_run_ids) != len(set(normalized_run_ids)):
        raise ValueError("DUPLICATE_RUN_ID")

    reasons: list[str] = []
    calls_started = 0
    calls_completed = 0
    calls_failed = 0
    zero_consumption_refusals = 0
    consumed_values: list[int] = []
    consumption_unknown = False

    integrity = audit_ledger.audit_integrity()
    if not integrity.ok:
        reasons.append("AUDIT_LEDGER_INTEGRITY_FAILED")

    for run_id in normalized_run_ids:
        events = tuple(audit_ledger.list_events(run_id))
        if not events:
            reasons.append(f"RUN_NOT_FOUND:{run_id}")
            continue

        start_events = [
            event
            for event in events
            if event.get("event_type") == "RUN_STARTED"
        ]

        if len(start_events) != 1:
            reasons.append(f"RUN_START_EVENT_COUNT:{run_id}")
            continue

        start_payload = start_events[0].get("event_payload")
        if not isinstance(start_payload, Mapping):
            reasons.append(f"INVALID_RUN_START_PAYLOAD:{run_id}")
            continue

        if start_payload.get("sport") != sport:
            reasons.append(f"SPORT_BOUNDARY_VIOLATION:{run_id}")
            continue

        provider_started = [
            event
            for event in events
            if event.get("event_type") == "PROVIDER_CALL_STARTED"
            and isinstance(event.get("event_payload"), Mapping)
            and event["event_payload"].get("provider_key") == provider_key
        ]

        provider_terminal = [
            event
            for event in events
            if event.get("event_type")
            in {"PROVIDER_CALL_COMPLETED", "PROVIDER_CALL_FAILED"}
            and isinstance(event.get("event_payload"), Mapping)
            and event["event_payload"].get("provider_key") == provider_key
        ]

        calls_started += len(provider_started)

        for event in provider_terminal:
            if event.get("event_type") == "PROVIDER_CALL_COMPLETED":
                calls_completed += 1
            else:
                calls_failed += 1

            payload = event["event_payload"]
            consumed = payload.get("consumed_request_units")

            if consumed is None:
                consumption_unknown = True
                continue

            if (
                isinstance(consumed, bool)
                or not isinstance(consumed, int)
                or consumed < 0
            ):
                reasons.append(
                    f"INVALID_PROVIDER_CONSUMPTION:{run_id}"
                )
                consumption_unknown = True
                continue

            consumed_values.append(consumed)

            if (
                event.get("event_type") == "PROVIDER_CALL_FAILED"
                and consumed == 0
            ):
                zero_consumption_refusals += 1

        if len(provider_started) != len(provider_terminal):
            reasons.append(
                f"PROVIDER_CALL_LIFECYCLE_MISMATCH:{run_id}"
            )

    terminal_calls = calls_completed + calls_failed

    if calls_started != terminal_calls:
        reasons.append("AGGREGATE_CALL_LIFECYCLE_MISMATCH")

    if terminal_calls == 0:
        success_rate = None
        failure_rate = None
        reasons.append("NO_PROVIDER_OBSERVATIONS")
    else:
        success_rate = calls_completed / terminal_calls
        failure_rate = calls_failed / terminal_calls

    consumed_request_units = (
        None if consumption_unknown else sum(consumed_values)
    )

    snapshot_status = "VALID" if not reasons else "DEGRADED"
    reason_codes = tuple(dict.fromkeys(reasons))

    base = {
        "schema": "matrix.provider-health-snapshot/1",
        "provider_key": provider_key,
        "sport": sport,
        "run_ids": list(normalized_run_ids),
        "calls_started": calls_started,
        "calls_completed": calls_completed,
        "calls_failed": calls_failed,
        "zero_consumption_refusals": zero_consumption_refusals,
        "consumed_request_units": consumed_request_units,
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "snapshot_status": snapshot_status,
        "reason_codes": list(reason_codes),
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return ProviderHealthSnapshot(
        provider_key=provider_key,
        sport=sport,
        run_ids=normalized_run_ids,
        calls_started=calls_started,
        calls_completed=calls_completed,
        calls_failed=calls_failed,
        zero_consumption_refusals=zero_consumption_refusals,
        consumed_request_units=consumed_request_units,
        success_rate=success_rate,
        failure_rate=failure_rate,
        snapshot_status=snapshot_status,
        reason_codes=reason_codes,
        snapshot_fingerprint=_sha256(base),
    )
