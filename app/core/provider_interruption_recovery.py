from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


_ALLOWED_REASONS = {
    "PROCESS_INTERRUPTED",
    "HOST_SHUTDOWN",
    "CRASH_RECOVERY",
    "UNKNOWN_TERMINATION",
}


def _json(value: Any) -> str:
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


def _sha(value: Any) -> str:
    return sha256(
        _json(value).encode("utf-8")
    ).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TIMEZONE_UNVERIFIED")
    return value.astimezone(timezone.utc)


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class ProviderInterruptionEvidence:
    recovery_id: str
    run_id: str
    provider_key: str
    queue_item_fingerprint: str
    permit_id: str
    pre_network_binding_intent_id: str
    endpoint_manifest_id: str
    request_contract_id: str
    request_contract_fingerprint: str
    reason_code: str
    status: str
    safe_to_retry: bool
    request_units_refunded: bool
    created_at: datetime

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-interruption-evidence/2"
            ),
            "recovery_id": self.recovery_id,
            "run_id": self.run_id,
            "provider_key": self.provider_key,
            "queue_item_fingerprint": (
                self.queue_item_fingerprint
            ),
            "permit_id": self.permit_id,
            "pre_network_binding_intent_id": (
                self.pre_network_binding_intent_id
            ),
            "endpoint_manifest_id": (
                self.endpoint_manifest_id
            ),
            "request_contract_id": (
                self.request_contract_id
            ),
            "request_contract_fingerprint": (
                self.request_contract_fingerprint
            ),
            "reason_code": self.reason_code,
            "status": self.status,
            "safe_to_retry": False,
            "request_units_refunded": False,
            "permit_reused": False,
            "terminal_network_binding_evidence_id": None,
            "created_at": (
                self.created_at.isoformat()
            ),
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class ProviderRecoveredAttemptState:
    permit_id: str
    state: str
    safe_to_retry: bool
    recovery_id: str | None
    errors: tuple[str, ...]


def build_provider_interruption_evidence(
    *,
    run_id: str,
    provider_key: str,
    queue_item_fingerprint: str,
    permit_id: str,
    pre_network_binding_intent_id: str,
    endpoint_manifest_id: str,
    request_contract_id: str,
    request_contract_fingerprint: str,
    reason_code: str,
    created_at: datetime,
) -> ProviderInterruptionEvidence:
    if not provider_key:
        raise ValueError("INVALID_PROVIDER_KEY")
    if reason_code not in _ALLOWED_REASONS:
        raise ValueError(
            "INVALID_INTERRUPTION_REASON"
        )

    run_id = _hex64(
        "RUN_ID",
        run_id,
    )
    queue_item_fingerprint = _hex64(
        "QUEUE_ITEM_FINGERPRINT",
        queue_item_fingerprint,
    )
    permit_id = _hex64(
        "PERMIT_ID",
        permit_id,
    )
    pre_network_binding_intent_id = _hex64(
        "ATTEMPT_INTENT_ID",
        pre_network_binding_intent_id,
    )
    endpoint_manifest_id = _hex64(
        "ENDPOINT_MANIFEST_ID",
        endpoint_manifest_id,
    )
    request_contract_id = _hex64(
        "REQUEST_CONTRACT_ID",
        request_contract_id,
    )
    request_contract_fingerprint = _hex64(
        "REQUEST_CONTRACT_FINGERPRINT",
        request_contract_fingerprint,
    )
    created_at = _aware(
        created_at
    )

    base = {
        "schema": (
            "matrix.provider-interruption-evidence-id/2"
        ),
        "run_id": run_id,
        "provider_key": provider_key,
        "queue_item_fingerprint": (
            queue_item_fingerprint
        ),
        "permit_id": permit_id,
        "pre_network_binding_intent_id": (
            pre_network_binding_intent_id
        ),
        "endpoint_manifest_id": (
            endpoint_manifest_id
        ),
        "request_contract_id": (
            request_contract_id
        ),
        "request_contract_fingerprint": (
            request_contract_fingerprint
        ),
        "reason_code": reason_code,
        "status": (
            "INTERRUPTED_UNKNOWN_OUTCOME"
        ),
        "safe_to_retry": False,
        "request_units_refunded": False,
        "permit_reused": False,
        "terminal_network_binding_evidence_id": None,
        "created_at": (
            created_at.isoformat()
        ),
        "real_provider_execution_authorized": False,
    }

    return ProviderInterruptionEvidence(
        recovery_id=_sha(base),
        run_id=run_id,
        provider_key=provider_key,
        queue_item_fingerprint=(
            queue_item_fingerprint
        ),
        permit_id=permit_id,
        pre_network_binding_intent_id=(
            pre_network_binding_intent_id
        ),
        endpoint_manifest_id=(
            endpoint_manifest_id
        ),
        request_contract_id=(
            request_contract_id
        ),
        request_contract_fingerprint=(
            request_contract_fingerprint
        ),
        reason_code=reason_code,
        status=(
            "INTERRUPTED_UNKNOWN_OUTCOME"
        ),
        safe_to_retry=False,
        request_units_refunded=False,
        created_at=created_at,
    )


class SQLiteProviderInterruptionRecoveryStore:
    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_interruption_recovery (
                    recovery_id TEXT PRIMARY KEY,
                    permit_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )

    def _connect(self):
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute(
            "PRAGMA journal_mode = WAL"
        )
        connection.execute(
            "PRAGMA synchronous = FULL"
        )
        return connection

    def record(
        self,
        evidence: ProviderInterruptionEvidence,
    ) -> ProviderInterruptionEvidence:
        rebuilt = (
            build_provider_interruption_evidence(
                run_id=evidence.run_id,
                provider_key=evidence.provider_key,
                queue_item_fingerprint=(
                    evidence.queue_item_fingerprint
                ),
                permit_id=evidence.permit_id,
                pre_network_binding_intent_id=(
                    evidence.pre_network_binding_intent_id
                ),
                endpoint_manifest_id=(
                    evidence.endpoint_manifest_id
                ),
                request_contract_id=(
                    evidence.request_contract_id
                ),
                request_contract_fingerprint=(
                    evidence.request_contract_fingerprint
                ),
                reason_code=evidence.reason_code,
                created_at=evidence.created_at,
            )
        )

        if rebuilt != evidence:
            raise ValueError(
                "INTERRUPTION_EVIDENCE_DERIVATION_MISMATCH"
            )

        existing = self.get_by_permit(
            evidence.permit_id
        )

        if existing is not None:
            if existing != evidence:
                raise ValueError(
                    "INTERRUPTION_RECOVERY_MUTATION_VIOLATION"
                )
            return existing

        payload_json = _json(
            evidence.payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO provider_interruption_recovery (
                    recovery_id,
                    permit_id,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    evidence.recovery_id,
                    evidence.permit_id,
                    payload_json,
                    payload_sha,
                ),
            )

        return evidence

    def get_by_permit(
        self,
        permit_id: str,
    ) -> ProviderInterruptionEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    recovery_id,
                    payload_json,
                    payload_sha256
                FROM provider_interruption_recovery
                WHERE permit_id = ?
                """,
                (
                    permit_id,
                ),
            ).fetchone()

        if row is None:
            return None

        recovery_id, payload_json, payload_sha = row

        if (
            sha256(
                payload_json.encode("utf-8")
            ).hexdigest()
            != payload_sha
        ):
            raise ValueError(
                "INTERRUPTION_RECOVERY_INTEGRITY_FAILURE"
            )

        payload = json.loads(
            payload_json
        )

        rebuilt = (
            build_provider_interruption_evidence(
                run_id=payload["run_id"],
                provider_key=(
                    payload["provider_key"]
                ),
                queue_item_fingerprint=(
                    payload[
                        "queue_item_fingerprint"
                    ]
                ),
                permit_id=payload["permit_id"],
                pre_network_binding_intent_id=(
                    payload[
                        "pre_network_binding_intent_id"
                    ]
                ),
                endpoint_manifest_id=(
                    payload[
                        "endpoint_manifest_id"
                    ]
                ),
                request_contract_id=(
                    payload[
                        "request_contract_id"
                    ]
                ),
                request_contract_fingerprint=(
                    payload[
                        "request_contract_fingerprint"
                    ]
                ),
                reason_code=(
                    payload["reason_code"]
                ),
                created_at=(
                    datetime.fromisoformat(
                        payload["created_at"]
                    )
                ),
            )
        )

        if (
            rebuilt.recovery_id
            != recovery_id
            or rebuilt.payload()
            != payload
        ):
            raise ValueError(
                "INTERRUPTION_RECOVERY_REDERIVATION_FAILURE"
            )

        return rebuilt

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            permit_ids = [
                str(row[0])
                for row
                in connection.execute(
                    """
                    SELECT permit_id
                    FROM provider_interruption_recovery
                    ORDER BY permit_id
                    """
                ).fetchall()
            ]

        try:
            return all(
                self.get_by_permit(
                    permit_id
                )
                is not None
                for permit_id
                in permit_ids
            )
        except ValueError:
            return False


def _events_for_permit(
    *,
    permit_id: str,
    network_call_evidence_store,
):
    return tuple(
        network_call_evidence_store.list_verified_events_for_permit(
            permit_id
        )
    )


def _classify_events(
    events,
) -> tuple[
    list[
        Mapping[str, Any]
    ],
    list[
        Mapping[str, Any]
    ],
]:
    started = [
        event
        for event
        in events
        if event.get(
            "event_type"
        )
        == "NETWORK_CALL_STARTED"
    ]

    terminal = [
        event
        for event
        in events
        if event.get(
            "event_type"
        )
        in {
            "NETWORK_CALL_COMPLETED",
            "NETWORK_CALL_FAILED",
        }
    ]

    return started, terminal


def recover_started_only_network_attempt(
    *,
    run_id: str,
    provider_key: str,
    permit_id: str,
    reason_code: str,
    now: datetime,
    attempt_intent_store,
    network_permit_store,
    network_call_evidence_store,
    recovery_store: SQLiteProviderInterruptionRecoveryStore,
    contract_endpoint_binding_store,
) -> ProviderInterruptionEvidence:
    intent = (
        attempt_intent_store.get_by_permit(
            permit_id
        )
    )

    if intent is None:
        raise ValueError(
            "INTERRUPTION_ATTEMPT_INTENT_NOT_FOUND"
        )

    if intent.run_id != run_id:
        raise ValueError(
            "INTERRUPTION_RUN_MISMATCH"
        )

    if intent.provider_key != provider_key:
        raise ValueError(
            "INTERRUPTION_PROVIDER_MISMATCH"
        )

    permit = network_permit_store.get_verified(
        permit_id
    )

    if permit is None:
        raise ValueError(
            "INTERRUPTION_PERMIT_NOT_FOUND"
        )

    if (
        permit.get(
            "run_id"
        )
        != intent.run_id
        or permit.get(
            "provider_key"
        )
        != intent.provider_key
        or permit.get(
            "endpoint_manifest_id"
        )
        != intent.endpoint_manifest_id
    ):
        raise ValueError(
            "INTERRUPTION_PERMIT_INTENT_MISMATCH"
        )

    if permit.get(
        "consumed_at"
    ) is None:
        raise ValueError(
            "INTERRUPTION_REQUIRES_CONSUMED_PERMIT"
        )

    contract_endpoint_binding_store.authorize(
        request_contract_id=(
            intent.request_contract_id
        ),
        endpoint_manifest_id=(
            intent.endpoint_manifest_id
        ),
        path=intent.request_path,
        now=now,
    )

    events = _events_for_permit(
        permit_id=permit_id,
        network_call_evidence_store=(
            network_call_evidence_store
        ),
    )

    started, terminal = _classify_events(
        events
    )

    if len(started) != 1:
        raise ValueError(
            "INTERRUPTION_STARTED_EVENT_COUNT"
        )

    if terminal:
        raise ValueError(
            "INTERRUPTION_TERMINAL_EVENT_ALREADY_EXISTS"
        )

    existing = recovery_store.get_by_permit(
        permit_id
    )

    if existing is not None:
        if (
            existing.run_id != intent.run_id
            or existing.provider_key
            != intent.provider_key
            or existing.queue_item_fingerprint
            != intent.queue_item_fingerprint
            or existing.pre_network_binding_intent_id
            != intent.intent_id
            or existing.request_contract_id
            != intent.request_contract_id
            or existing.reason_code != reason_code
        ):
            raise ValueError(
                "INTERRUPTION_RECOVERY_ALREADY_RECORDED"
            )

        return existing

    evidence = (
        build_provider_interruption_evidence(
            run_id=intent.run_id,
            provider_key=(
                intent.provider_key
            ),
            queue_item_fingerprint=(
                intent.queue_item_fingerprint
            ),
            permit_id=intent.permit_id,
            pre_network_binding_intent_id=(
                intent.intent_id
            ),
            endpoint_manifest_id=(
                intent.endpoint_manifest_id
            ),
            request_contract_id=(
                intent.request_contract_id
            ),
            request_contract_fingerprint=(
                intent.request_contract_fingerprint
            ),
            reason_code=reason_code,
            created_at=now,
        )
    )

    return recovery_store.record(
        evidence
    )


def reconcile_network_attempt_with_recovery(
    *,
    permit_id: str,
    attempt_intent_store,
    network_call_evidence_store,
    recovery_store: SQLiteProviderInterruptionRecoveryStore,
) -> ProviderRecoveredAttemptState:
    intent = (
        attempt_intent_store.get_by_permit(
            permit_id
        )
    )

    if intent is None:
        return ProviderRecoveredAttemptState(
            permit_id=permit_id,
            state="INVALID",
            safe_to_retry=False,
            recovery_id=None,
            errors=(
                "RECOVERY_ATTEMPT_INTENT_REQUIRED",
            ),
        )

    events = _events_for_permit(
        permit_id=permit_id,
        network_call_evidence_store=(
            network_call_evidence_store
        ),
    )

    started, terminal = _classify_events(
        events
    )

    recovery = recovery_store.get_by_permit(
        permit_id
    )

    errors: list[str] = []

    if len(started) != 1:
        errors.append(
            "RECOVERY_STARTED_EVENT_COUNT"
        )

    if len(terminal) > 1:
        errors.append(
            "RECOVERY_TERMINAL_EVENT_COUNT"
        )

    if terminal and recovery is not None:
        errors.append(
            "RECOVERY_CONFLICT_WITH_TERMINAL_EVENT"
        )

    if (
        recovery is not None
        and recovery.pre_network_binding_intent_id
        != intent.intent_id
    ):
        errors.append(
            "RECOVERY_ATTEMPT_INTENT_MISMATCH"
        )

    if errors:
        return ProviderRecoveredAttemptState(
            permit_id=permit_id,
            state="INVALID",
            safe_to_retry=False,
            recovery_id=(
                recovery.recovery_id
                if recovery
                else None
            ),
            errors=tuple(
                errors
            ),
        )

    if len(terminal) == 1:
        state = (
            "COMPLETED"
            if terminal[0].get(
                "event_type"
            )
            == "NETWORK_CALL_COMPLETED"
            else "FAILED"
        )

        return ProviderRecoveredAttemptState(
            permit_id=permit_id,
            state=state,
            safe_to_retry=False,
            recovery_id=None,
            errors=(),
        )

    if recovery is not None:
        return ProviderRecoveredAttemptState(
            permit_id=permit_id,
            state=(
                "INTERRUPTED_UNKNOWN_OUTCOME"
            ),
            safe_to_retry=False,
            recovery_id=(
                recovery.recovery_id
            ),
            errors=(),
        )

    return ProviderRecoveredAttemptState(
        permit_id=permit_id,
        state="STARTED_WITHOUT_TERMINAL",
        safe_to_retry=False,
        recovery_id=None,
        errors=(
            "RECOVERY_EVIDENCE_REQUIRED",
        ),
    )


def scan_started_only_network_attempts(
    *,
    run_id: str,
    attempt_intent_store,
    network_call_evidence_store,
    recovery_store: SQLiteProviderInterruptionRecoveryStore,
) -> tuple[
    ProviderRecoveredAttemptState,
    ...,
]:
    intents = (
        attempt_intent_store.list_verified_for_run(
            run_id
        )
    )

    return tuple(
        reconcile_network_attempt_with_recovery(
            permit_id=(
                intent.permit_id
            ),
            attempt_intent_store=(
                attempt_intent_store
            ),
            network_call_evidence_store=(
                network_call_evidence_store
            ),
            recovery_store=(
                recovery_store
            ),
        )
        for intent
        in intents
    )


def recover_all_started_only_network_attempts(
    *,
    run_id: str,
    provider_key: str,
    reason_code: str,
    now: datetime,
    attempt_intent_store,
    network_permit_store,
    network_call_evidence_store,
    recovery_store: SQLiteProviderInterruptionRecoveryStore,
    contract_endpoint_binding_store,
) -> tuple[
    ProviderInterruptionEvidence,
    ...,
]:
    recovered = []

    for intent in (
        attempt_intent_store.list_verified_for_run(
            run_id
        )
    ):
        state = (
            reconcile_network_attempt_with_recovery(
                permit_id=(
                    intent.permit_id
                ),
                attempt_intent_store=(
                    attempt_intent_store
                ),
                network_call_evidence_store=(
                    network_call_evidence_store
                ),
                recovery_store=(
                    recovery_store
                ),
            )
        )

        if (
            state.state
            == "STARTED_WITHOUT_TERMINAL"
        ):
            recovered.append(
                recover_started_only_network_attempt(
                    run_id=run_id,
                    provider_key=(
                        provider_key
                    ),
                    permit_id=(
                        intent.permit_id
                    ),
                    reason_code=(
                        reason_code
                    ),
                    now=now,
                    attempt_intent_store=(
                        attempt_intent_store
                    ),
                    network_permit_store=(
                        network_permit_store
                    ),
                    network_call_evidence_store=(
                        network_call_evidence_store
                    ),
                    recovery_store=(
                        recovery_store
                    ),
                    contract_endpoint_binding_store=(
                        contract_endpoint_binding_store
                    ),
                )
            )

    return tuple(
        recovered
    )
