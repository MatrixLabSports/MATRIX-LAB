from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Callable, Mapping

from app.core.acquisition_worker import (
    AcquisitionWorkerResult,
    CheckpointStore,
    ProviderFetcher,
    RawAppendOnlyLedger,
    WorkerLimits,
    execute_acquisition_queue,
)
from app.core.provider_request_budget import ExecutionRequestBudget
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


def _aware_utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("TIMEZONE_UNVERIFIED")
    return value.astimezone(timezone.utc)


def queue_manifest_fingerprint(
    queue_manifest: Mapping[str, Any],
) -> str:
    if not isinstance(queue_manifest, Mapping):
        raise ValueError("INVALID_QUEUE_MANIFEST")

    sport = queue_manifest.get("sport")
    if sport not in {"football", "tennis"}:
        raise ValueError("INVALID_QUEUE_SPORT")

    queue = queue_manifest.get("queue")
    if not isinstance(queue, list):
        raise ValueError("INVALID_QUEUE_MANIFEST")

    payload = {
        "schema": "matrix.acquisition-queue-fingerprint/1",
        "sport": sport,
        "queue": queue,
    }
    return _sha256(payload)


@dataclass(frozen=True)
class AuditedAcquisitionExecutionResult:
    run_id: str
    queue_fingerprint: str
    policy_fingerprint: str
    worker_result: AcquisitionWorkerResult

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.audited-acquisition-execution-result/1",
            "run_id": self.run_id,
            "queue_fingerprint": self.queue_fingerprint,
            "policy_fingerprint": self.policy_fingerprint,
            "worker_result": dict(self.worker_result.payload()),
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def execute_audited_acquisition_queue(
    *,
    queue_manifest: Mapping[str, Any],
    policy_fingerprint: str,
    audit_ledger: SQLiteRuntimeAuditLedger,
    fetcher: ProviderFetcher,
    raw_ledger: RawAppendOnlyLedger,
    checkpoints: CheckpointStore,
    limits: WorkerLimits,
    clock: Callable[[], datetime],
    request_budget: ExecutionRequestBudget | None = None,
) -> AuditedAcquisitionExecutionResult:
    started_at = _aware_utc(clock())
    queue_fingerprint = queue_manifest_fingerprint(queue_manifest)

    run = audit_ledger.start_run(
        sport=str(queue_manifest["sport"]),
        queue_fingerprint=queue_fingerprint,
        policy_fingerprint=policy_fingerprint,
        started_at=started_at,
    )

    audit_ledger.append_event(
        run_id=run.run_id,
        event_type="ACQUISITION_EXECUTION_STARTED",
        event_payload={
            "max_items": limits.max_items,
            "max_requests": limits.max_requests,
            "request_budget_enabled": request_budget is not None,
        },
        created_at=_aware_utc(clock()),
    )

    try:
        worker_result = execute_acquisition_queue(
            queue_manifest=queue_manifest,
            fetcher=fetcher,
            raw_ledger=raw_ledger,
            checkpoints=checkpoints,
            limits=limits,
            request_budget=request_budget,
        )
    except Exception as error:
        failure_payload = {
            "error_type": type(error).__name__,
            "reason_code": str(error),
        }

        audit_ledger.append_event(
            run_id=run.run_id,
            event_type="ACQUISITION_EXECUTION_FAILED",
            event_payload=failure_payload,
            created_at=_aware_utc(clock()),
        )

        audit_ledger.finish_run(
            run_id=run.run_id,
            status="FAILED",
            result_payload=failure_payload,
            finished_at=_aware_utc(clock()),
        )
        raise

    worker_payload = dict(worker_result.payload())

    audit_ledger.append_event(
        run_id=run.run_id,
        event_type="ACQUISITION_EXECUTION_RESULT",
        event_payload=worker_payload,
        created_at=_aware_utc(clock()),
    )

    audit_ledger.finish_run(
        run_id=run.run_id,
        status="COMPLETED",
        result_payload=worker_payload,
        finished_at=_aware_utc(clock()),
    )

    return AuditedAcquisitionExecutionResult(
        run_id=run.run_id,
        queue_fingerprint=queue_fingerprint,
        policy_fingerprint=policy_fingerprint,
        worker_result=worker_result,
    )
