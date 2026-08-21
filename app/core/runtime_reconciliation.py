from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.runtime_audit_ledger import SQLiteRuntimeAuditLedger


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
class RuntimeReconciliationReport:
    run_id: str
    ok: bool
    status: str
    requests_used: int | None
    provider_consumed_units: int | None
    evidence_ids: tuple[str, ...]
    errors: tuple[str, ...]
    report_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.runtime-reconciliation-report/1",
            "run_id": self.run_id,
            "ok": self.ok,
            "status": self.status,
            "requests_used": self.requests_used,
            "provider_consumed_units": self.provider_consumed_units,
            "evidence_ids": list(self.evidence_ids),
            "errors": list(self.errors),
            "report_fingerprint": self.report_fingerprint,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def _event_types(
    events: Sequence[Mapping[str, Any]],
) -> list[str]:
    return [str(event.get("event_type")) for event in events]


def reconcile_runtime_run(
    *,
    run_id: str,
    audit_ledger: SQLiteRuntimeAuditLedger,
    acquisition_store: SQLiteAcquisitionStore,
    network_binding_store=None,
    network_permit_store=None,
    network_call_evidence_store=None,
    request_contract_registry=None,
) -> RuntimeReconciliationReport:
    validated_run = _validate_hex64("RUN_ID", run_id)
    errors: list[str] = []

    audit_integrity = audit_ledger.audit_integrity()
    if not audit_integrity.ok:
        errors.append("AUDIT_LEDGER_INTEGRITY_FAILED")

    acquisition_integrity = acquisition_store.audit_integrity()
    if not acquisition_integrity.ok:
        errors.append("ACQUISITION_STORE_INTEGRITY_FAILED")

    events = tuple(audit_ledger.list_events(validated_run))
    if not events:
        raise ValueError("RUNTIME_AUDIT_RUN_NOT_FOUND")

    types = _event_types(events)

    if types[0] != "RUN_STARTED":
        errors.append("RUN_START_EVENT_MISSING")

    if types[-1] != "RUN_FINISHED":
        errors.append("RUN_FINISH_EVENT_MISSING")

    start_event = events[0]
    finish_event = events[-1]

    start_payload = start_event.get("event_payload")
    finish_payload = finish_event.get("event_payload")

    if not isinstance(start_payload, Mapping):
        errors.append("INVALID_RUN_START_PAYLOAD")
        start_payload = {}

    if not isinstance(finish_payload, Mapping):
        errors.append("INVALID_RUN_FINISH_PAYLOAD")
        finish_payload = {}

    sport = start_payload.get("sport")
    if sport not in {"football", "tennis"}:
        errors.append("INVALID_RUN_SPORT")

    status = str(finish_payload.get("status", "UNKNOWN"))
    if status not in {"COMPLETED", "FAILED"}:
        errors.append("INVALID_TERMINAL_STATUS")

    result_events = [
        event
        for event in events
        if event.get("event_type") == "ACQUISITION_EXECUTION_RESULT"
    ]
    failure_events = [
        event
        for event in events
        if event.get("event_type") == "ACQUISITION_EXECUTION_FAILED"
    ]

    requests_used: int | None = None
    evidence_ids: tuple[str, ...] = ()

    if status == "COMPLETED":
        if len(result_events) != 1:
            errors.append("COMPLETED_RESULT_EVENT_COUNT")
            worker_payload: Mapping[str, Any] = {}
        else:
            payload = result_events[0].get("event_payload")
            if not isinstance(payload, Mapping):
                errors.append("INVALID_WORKER_RESULT_PAYLOAD")
                worker_payload = {}
            else:
                worker_payload = payload

        if failure_events:
            errors.append("COMPLETED_WITH_FAILURE_EVENT")

        finished_result = finish_payload.get("result_payload")
        if worker_payload and finished_result != worker_payload:
            errors.append("TERMINAL_RESULT_MISMATCH")

        raw_requests = worker_payload.get("requests_used")
        if isinstance(raw_requests, bool) or not isinstance(raw_requests, int):
            errors.append("INVALID_REQUESTS_USED")
        else:
            requests_used = raw_requests

        raw_evidence_ids = worker_payload.get("evidence_ids")
        if not isinstance(raw_evidence_ids, list):
            errors.append("INVALID_EVIDENCE_IDS")
        else:
            valid_evidence: list[str] = []
            for evidence_id in raw_evidence_ids:
                try:
                    valid = _validate_hex64("EVIDENCE_ID", evidence_id)
                except ValueError:
                    errors.append("INVALID_EVIDENCE_ID")
                    continue

                raw = acquisition_store.get_raw(valid)
                if raw is None:
                    errors.append(f"MISSING_RAW_EVIDENCE:{valid}")
                    continue

                if raw.get("sport") != sport:
                    errors.append(f"RAW_SPORT_MISMATCH:{valid}")

                valid_evidence.append(valid)

            evidence_ids = tuple(valid_evidence)

    elif status == "FAILED":
        if result_events:
            errors.append("FAILED_WITH_RESULT_EVENT")

        if len(failure_events) != 1:
            errors.append("FAILED_EVENT_COUNT")

        if failure_events:
            failure_payload = failure_events[0].get("event_payload")
            finished_result = finish_payload.get("result_payload")

            if failure_payload != finished_result:
                errors.append("FAILED_TERMINAL_RESULT_MISMATCH")

    call_started = [
        event
        for event in events
        if event.get("event_type") == "PROVIDER_CALL_STARTED"
    ]
    call_terminal = [
        event
        for event in events
        if event.get("event_type")
        in {"PROVIDER_CALL_COMPLETED", "PROVIDER_CALL_FAILED"}
    ]

    if len(call_started) != len(call_terminal):
        errors.append("PROVIDER_CALL_LIFECYCLE_MISMATCH")

    for started, terminal in zip(call_started, call_terminal):
        started_payload = started.get("event_payload")
        terminal_payload = terminal.get("event_payload")

        if not isinstance(started_payload, Mapping) or not isinstance(
            terminal_payload,
            Mapping,
        ):
            errors.append("INVALID_PROVIDER_CALL_PAYLOAD")
            continue

        if (
            started_payload.get("provider_key")
            != terminal_payload.get("provider_key")
        ):
            errors.append("PROVIDER_CALL_PROVIDER_MISMATCH")

        if (
            started_payload.get("queue_item_fingerprint")
            != terminal_payload.get("queue_item_fingerprint")
        ):
            errors.append("PROVIDER_CALL_QUEUE_ITEM_MISMATCH")

    consumed_values: list[int] = []
    consumption_unknown = False

    for terminal in call_terminal:
        payload = terminal.get("event_payload")

        if not isinstance(payload, Mapping):
            consumption_unknown = True
            continue

        consumed = payload.get("consumed_request_units")

        if consumed is None:
            consumption_unknown = True
            continue

        if isinstance(consumed, bool) or not isinstance(consumed, int):
            errors.append("INVALID_PROVIDER_CONSUMPTION")
            consumption_unknown = True
            continue

        if consumed < 0:
            errors.append("NEGATIVE_PROVIDER_CONSUMPTION")
            consumption_unknown = True
            continue

        consumed_values.append(consumed)

    provider_consumed_units = (
        None if consumption_unknown else sum(consumed_values)
    )

    if (
        status == "COMPLETED"
        and requests_used is not None
        and provider_consumed_units is not None
        and requests_used != provider_consumed_units
    ):
        errors.append("REQUEST_CONSUMPTION_MISMATCH")

    network_components = (
        network_binding_store,
        network_permit_store,
        network_call_evidence_store,
        request_contract_registry,
    )

    if any(
        component is not None
        for component
        in network_components
    ):
        if not all(
            component is not None
            for component
            in network_components
        ):
            errors.append(
                "NETWORK_BINDING_COMPONENTS_PARTIAL"
            )
        else:
            from app.core.provider_network_binding import (
                reconcile_provider_network_bindings,
            )

            network_report = (
                reconcile_provider_network_bindings(
                    run_id=validated_run,
                    audit_ledger=audit_ledger,
                    binding_store=(
                        network_binding_store
                    ),
                    network_permit_store=(
                        network_permit_store
                    ),
                    network_call_evidence_store=(
                        network_call_evidence_store
                    ),
                    request_contract_registry=(
                        request_contract_registry
                    ),
                )
            )

            if not network_report.ok:
                errors.extend(
                    f"NETWORK:{reason}"
                    for reason
                    in network_report.errors
                )

    report_base = {
        "schema": "matrix.runtime-reconciliation-report/1",
        "run_id": validated_run,
        "ok": not errors,
        "status": status,
        "requests_used": requests_used,
        "provider_consumed_units": provider_consumed_units,
        "evidence_ids": list(evidence_ids),
        "errors": list(errors),
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }
    fingerprint = _sha256(report_base)

    return RuntimeReconciliationReport(
        run_id=validated_run,
        ok=not errors,
        status=status,
        requests_used=requests_used,
        provider_consumed_units=provider_consumed_units,
        evidence_ids=evidence_ids,
        errors=tuple(errors),
        report_fingerprint=fingerprint,
    )
