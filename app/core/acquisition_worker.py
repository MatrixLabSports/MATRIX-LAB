from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Protocol, Sequence


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


class ProviderFetcher(Protocol):
    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class RawAppendOnlyLedger(Protocol):
    def contains(self, evidence_id: str) -> bool:
        ...

    def append(self, evidence_id: str, payload: Mapping[str, Any]) -> None:
        ...

    def find_evidence_for_queue_item(
        self,
        queue_item_fingerprint: str,
    ) -> str | None:
        ...


class CheckpointStore(Protocol):
    def is_completed(self, queue_item_fingerprint: str) -> bool:
        ...

    def mark_completed(
        self,
        queue_item_fingerprint: str,
        evidence_id: str,
    ) -> None:
        ...


@dataclass
class InMemoryRawAppendOnlyLedger:
    records: dict[str, Mapping[str, Any]]

    def __init__(self) -> None:
        self.records = {}

    def contains(self, evidence_id: str) -> bool:
        return evidence_id in self.records

    def append(self, evidence_id: str, payload: Mapping[str, Any]) -> None:
        if evidence_id in self.records:
            raise ValueError("RAW_APPEND_ONLY_VIOLATION")

        queue_fingerprint = payload.get("queue_item_fingerprint")
        existing = self.find_evidence_for_queue_item(
            str(queue_fingerprint)
        )
        if existing is not None:
            raise ValueError("RAW_QUEUE_ITEM_ALREADY_PERSISTED")

        self.records[evidence_id] = dict(payload)

    def find_evidence_for_queue_item(
        self,
        queue_item_fingerprint: str,
    ) -> str | None:
        matches = [
            evidence_id
            for evidence_id, payload in self.records.items()
            if payload.get("queue_item_fingerprint")
            == queue_item_fingerprint
        ]

        if len(matches) > 1:
            raise ValueError("RAW_QUEUE_ITEM_COLLISION")

        return matches[0] if matches else None


@dataclass
class InMemoryCheckpointStore:
    completed: dict[str, str]

    def __init__(self) -> None:
        self.completed = {}

    def is_completed(self, queue_item_fingerprint: str) -> bool:
        return queue_item_fingerprint in self.completed

    def mark_completed(
        self,
        queue_item_fingerprint: str,
        evidence_id: str,
    ) -> None:
        existing = self.completed.get(queue_item_fingerprint)
        if existing is not None and existing != evidence_id:
            raise ValueError("CHECKPOINT_MUTATION_VIOLATION")
        self.completed[queue_item_fingerprint] = evidence_id


@dataclass(frozen=True)
class WorkerLimits:
    max_items: int
    max_requests: int

    def __post_init__(self) -> None:
        for name, value in (
            ("MAX_ITEMS", self.max_items),
            ("MAX_REQUESTS", self.max_requests),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"INVALID_{name}")


@dataclass(frozen=True)
class AcquisitionWorkerResult:
    processed: int
    skipped_completed: int
    recovered_without_fetch: int
    failed: int
    requests_used: int
    evidence_ids: tuple[str, ...]
    failures: tuple[tuple[str, str], ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.acquisition-worker-result/2",
            "processed": self.processed,
            "skipped_completed": self.skipped_completed,
            "recovered_without_fetch": self.recovered_without_fetch,
            "failed": self.failed,
            "requests_used": self.requests_used,
            "evidence_ids": list(self.evidence_ids),
            "failures": [list(item) for item in self.failures],
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def _validate_queue_item(item: Mapping[str, Any]) -> None:
    required = (
        "sport",
        "subject_key",
        "provider_key",
        "competition_key",
        "season_key",
        "queue_item_fingerprint",
        "estimated_request_cost",
        "source_fingerprint",
    )

    for key in required:
        if key not in item:
            raise ValueError(f"MISSING_QUEUE_FIELD:{key}")

    fingerprint = item["queue_item_fingerprint"]
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise ValueError("INVALID_QUEUE_ITEM_FINGERPRINT")

    request_cost = item["estimated_request_cost"]
    if (
        isinstance(request_cost, bool)
        or not isinstance(request_cost, int)
        or request_cost <= 0
    ):
        raise ValueError("INVALID_REQUEST_COST")


def _build_raw_envelope(
    *,
    queue_item: Mapping[str, Any],
    raw_payload: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    payload = {
        "schema": "matrix.raw-provider-evidence/1",
        "sport": queue_item["sport"],
        "subject_key": queue_item["subject_key"],
        "provider_key": queue_item["provider_key"],
        "competition_key": queue_item["competition_key"],
        "season_key": queue_item["season_key"],
        "queue_item_fingerprint": queue_item["queue_item_fingerprint"],
        "source_fingerprint": queue_item["source_fingerprint"],
        "raw_payload": dict(raw_payload),
    }
    evidence_id = _sha256(payload)
    return evidence_id, payload


def execute_acquisition_queue(
    *,
    queue_manifest: Mapping[str, Any],
    fetcher: ProviderFetcher,
    raw_ledger: RawAppendOnlyLedger,
    checkpoints: CheckpointStore,
    limits: WorkerLimits,
) -> AcquisitionWorkerResult:
    queue = queue_manifest.get("queue")
    if not isinstance(queue, Sequence) or isinstance(queue, (str, bytes)):
        raise ValueError("INVALID_QUEUE_MANIFEST")

    manifest_sport = queue_manifest.get("sport")
    if manifest_sport not in {"football", "tennis"}:
        raise ValueError("INVALID_QUEUE_SPORT")

    processed = 0
    skipped_completed = 0
    recovered_without_fetch = 0
    failed = 0
    requests_used = 0
    evidence_ids: list[str] = []
    failures: list[tuple[str, str]] = []

    for item in queue:
        if processed + failed >= limits.max_items:
            break

        if not isinstance(item, Mapping):
            failed += 1
            failures.append(("<invalid>", "INVALID_QUEUE_ITEM"))
            continue

        try:
            _validate_queue_item(item)
        except ValueError as error:
            failed += 1
            failures.append((
                str(item.get("queue_item_fingerprint", "<invalid>")),
                str(error),
            ))
            continue

        queue_fingerprint = str(item["queue_item_fingerprint"])

        if item["sport"] != manifest_sport:
            failed += 1
            failures.append((queue_fingerprint, "CROSS_SPORT_QUEUE_ITEM"))
            continue

        if checkpoints.is_completed(queue_fingerprint):
            skipped_completed += 1
            continue

        try:
            persisted_evidence = raw_ledger.find_evidence_for_queue_item(
                queue_fingerprint
            )
        except Exception as error:
            failed += 1
            failures.append((queue_fingerprint, type(error).__name__))
            continue

        if persisted_evidence is not None:
            try:
                checkpoints.mark_completed(
                    queue_fingerprint,
                    persisted_evidence,
                )
            except Exception as error:
                failed += 1
                failures.append((queue_fingerprint, type(error).__name__))
                continue

            skipped_completed += 1
            recovered_without_fetch += 1
            evidence_ids.append(persisted_evidence)
            continue

        request_cost = int(item["estimated_request_cost"])
        if requests_used + request_cost > limits.max_requests:
            failures.append((
                queue_fingerprint,
                "WORKER_REQUEST_LIMIT_REACHED",
            ))
            break

        try:
            raw_payload = fetcher.fetch(item)
            requests_used += request_cost

            if not isinstance(raw_payload, Mapping):
                raise ValueError("PROVIDER_PAYLOAD_NOT_MAPPING")

            evidence_id, envelope = _build_raw_envelope(
                queue_item=item,
                raw_payload=raw_payload,
            )

            if raw_ledger.contains(evidence_id):
                checkpoints.mark_completed(
                    queue_fingerprint,
                    evidence_id,
                )
                skipped_completed += 1
                recovered_without_fetch += 1
                evidence_ids.append(evidence_id)
                continue

            raw_ledger.append(evidence_id, envelope)
            checkpoints.mark_completed(queue_fingerprint, evidence_id)

            processed += 1
            evidence_ids.append(evidence_id)

        except Exception as error:
            failed += 1
            failures.append((queue_fingerprint, type(error).__name__))

    return AcquisitionWorkerResult(
        processed=processed,
        skipped_completed=skipped_completed,
        recovered_without_fetch=recovered_without_fetch,
        failed=failed,
        requests_used=requests_used,
        evidence_ids=tuple(evidence_ids),
        failures=tuple(failures),
    )
