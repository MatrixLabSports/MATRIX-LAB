from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from app.core.runtime_audit_ledger import SQLiteRuntimeAuditLedger
from app.core.runtime_reconciliation import RuntimeReconciliationReport


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


def _nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"INVALID_{name}")
    return value


@dataclass(frozen=True)
class RuntimeAdmissionDecision:
    run_id: str
    sport: str
    admission_status: str
    downstream_eligible: bool
    processed: int | None
    skipped_completed: int | None
    recovered_without_fetch: int | None
    failed: int | None
    reconciliation_fingerprint: str
    reason_codes: tuple[str, ...]
    decision_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.reconciled-runtime-admission/1",
            "run_id": self.run_id,
            "sport": self.sport,
            "admission_status": self.admission_status,
            "downstream_eligible": self.downstream_eligible,
            "processed": self.processed,
            "skipped_completed": self.skipped_completed,
            "recovered_without_fetch": self.recovered_without_fetch,
            "failed": self.failed,
            "reconciliation_fingerprint": self.reconciliation_fingerprint,
            "reason_codes": list(self.reason_codes),
            "decision_fingerprint": self.decision_fingerprint,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def evaluate_reconciled_runtime_admission(
    *,
    report: RuntimeReconciliationReport,
    audit_ledger: SQLiteRuntimeAuditLedger,
    expected_sport: str | None = None,
) -> RuntimeAdmissionDecision:
    reasons: list[str] = []

    if expected_sport is not None and expected_sport not in _ALLOWED_SPORTS:
        raise ValueError("INVALID_EXPECTED_SPORT")

    events = tuple(audit_ledger.list_events(report.run_id))
    if not events:
        raise ValueError("RUNTIME_AUDIT_RUN_NOT_FOUND")

    start_events = [
        event for event in events if event.get("event_type") == "RUN_STARTED"
    ]
    result_events = [
        event
        for event in events
        if event.get("event_type") == "ACQUISITION_EXECUTION_RESULT"
    ]

    sport = "unknown"

    if len(start_events) != 1:
        reasons.append("RUN_START_EVENT_COUNT")
    else:
        payload = start_events[0].get("event_payload")
        if not isinstance(payload, Mapping):
            reasons.append("INVALID_RUN_START_PAYLOAD")
        else:
            raw_sport = payload.get("sport")
            if raw_sport not in _ALLOWED_SPORTS:
                reasons.append("INVALID_RUN_SPORT")
            else:
                sport = str(raw_sport)

    if expected_sport is not None and sport != expected_sport:
        reasons.append("SPORT_BOUNDARY_VIOLATION")

    if not report.ok:
        reasons.append("RECONCILIATION_FAILED")

    if report.status != "COMPLETED":
        reasons.append("RUN_NOT_COMPLETED")

    if report.provider_consumed_units is None:
        reasons.append("UNKNOWN_PROVIDER_CONSUMPTION")

    processed: int | None = None
    skipped_completed: int | None = None
    recovered_without_fetch: int | None = None
    failed: int | None = None

    if len(result_events) != 1:
        reasons.append("WORKER_RESULT_EVENT_COUNT")
    else:
        worker_payload = result_events[0].get("event_payload")

        if not isinstance(worker_payload, Mapping):
            reasons.append("INVALID_WORKER_RESULT_PAYLOAD")
        else:
            try:
                processed = _nonnegative_int(
                    "PROCESSED",
                    worker_payload.get("processed"),
                )
                skipped_completed = _nonnegative_int(
                    "SKIPPED_COMPLETED",
                    worker_payload.get("skipped_completed"),
                )
                recovered_without_fetch = _nonnegative_int(
                    "RECOVERED_WITHOUT_FETCH",
                    worker_payload.get("recovered_without_fetch"),
                )
                failed = _nonnegative_int(
                    "FAILED",
                    worker_payload.get("failed"),
                )
            except ValueError:
                reasons.append("INVALID_WORKER_COUNTERS")

    if failed is not None and failed > 0:
        reasons.append("WORKER_FAILURES_PRESENT")

    if (
        processed is not None
        and processed > 0
        and len(report.evidence_ids) < processed
    ):
        reasons.append("PROCESSED_WITHOUT_RECONCILED_EVIDENCE")

    if (
        report.requests_used is not None
        and report.provider_consumed_units is not None
        and report.requests_used != report.provider_consumed_units
    ):
        reasons.append("REQUEST_CONSUMPTION_MISMATCH")

    reason_codes = tuple(dict.fromkeys(reasons))
    admission_status = "ADMIT" if not reason_codes else "QUARANTINE"
    downstream_eligible = admission_status == "ADMIT"

    decision_base = {
        "schema": "matrix.reconciled-runtime-admission/1",
        "run_id": report.run_id,
        "sport": sport,
        "admission_status": admission_status,
        "downstream_eligible": downstream_eligible,
        "processed": processed,
        "skipped_completed": skipped_completed,
        "recovered_without_fetch": recovered_without_fetch,
        "failed": failed,
        "reconciliation_fingerprint": report.report_fingerprint,
        "reason_codes": list(reason_codes),
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return RuntimeAdmissionDecision(
        run_id=report.run_id,
        sport=sport,
        admission_status=admission_status,
        downstream_eligible=downstream_eligible,
        processed=processed,
        skipped_completed=skipped_completed,
        recovered_without_fetch=recovered_without_fetch,
        failed=failed,
        reconciliation_fingerprint=report.report_fingerprint,
        reason_codes=reason_codes,
        decision_fingerprint=_sha256(decision_base),
    )
