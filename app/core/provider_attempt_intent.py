from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


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
class ProviderAttemptIntentEvidence:
    intent_id: str
    run_id: str
    provider_key: str
    queue_item_fingerprint: str
    permit_id: str
    endpoint_manifest_id: str
    security_evidence_id: str
    request_contract_id: str
    request_contract_fingerprint: str
    request_path: str
    request_parameter_names: tuple[str, ...]
    request_parameter_values_fingerprint: str
    secret_reference_fingerprint: str
    created_at: datetime

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-attempt-intent/1",
            "intent_id": self.intent_id,
            "run_id": self.run_id,
            "provider_key": self.provider_key,
            "queue_item_fingerprint": self.queue_item_fingerprint,
            "permit_id": self.permit_id,
            "endpoint_manifest_id": self.endpoint_manifest_id,
            "security_evidence_id": self.security_evidence_id,
            "request_contract_id": self.request_contract_id,
            "request_contract_fingerprint": (
                self.request_contract_fingerprint
            ),
            "request_path": self.request_path,
            "request_parameter_names": list(
                self.request_parameter_names
            ),
            "request_parameter_values_fingerprint": (
                self.request_parameter_values_fingerprint
            ),
            "secret_reference_fingerprint": (
                self.secret_reference_fingerprint
            ),
            "created_at": self.created_at.isoformat(),
            "network_call_started": False,
            "secret_value_persisted": False,
            "query_values_persisted": False,
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def build_provider_attempt_intent_evidence(
    *,
    run_id: str,
    provider_key: str,
    queue_item_fingerprint: str,
    permit_id: str,
    endpoint_manifest_id: str,
    security_evidence_id: str,
    request_contract_id: str,
    request_contract_fingerprint: str,
    request_path: str,
    request_parameter_names: tuple[str, ...],
    request_parameter_values_fingerprint: str,
    secret_reference_fingerprint: str,
    created_at: datetime,
) -> ProviderAttemptIntentEvidence:
    if not provider_key:
        raise ValueError("INVALID_PROVIDER_KEY")
    if (
        not request_path.startswith("/")
        or "?" in request_path
        or "#" in request_path
    ):
        raise ValueError("INVALID_REQUEST_PATH")

    names = tuple(
        sorted(
            str(name)
            for name
            in request_parameter_names
        )
    )

    if len(set(names)) != len(names):
        raise ValueError(
            "DUPLICATE_REQUEST_PARAMETER_NAME"
        )

    created_at = _aware(created_at)

    values = {
        "run_id": _hex64(
            "RUN_ID",
            run_id,
        ),
        "queue_item_fingerprint": _hex64(
            "QUEUE_ITEM_FINGERPRINT",
            queue_item_fingerprint,
        ),
        "permit_id": _hex64(
            "PERMIT_ID",
            permit_id,
        ),
        "endpoint_manifest_id": _hex64(
            "ENDPOINT_MANIFEST_ID",
            endpoint_manifest_id,
        ),
        "security_evidence_id": _hex64(
            "SECURITY_EVIDENCE_ID",
            security_evidence_id,
        ),
        "request_contract_id": _hex64(
            "REQUEST_CONTRACT_ID",
            request_contract_id,
        ),
        "request_contract_fingerprint": _hex64(
            "REQUEST_CONTRACT_FINGERPRINT",
            request_contract_fingerprint,
        ),
        "request_parameter_values_fingerprint": _hex64(
            "REQUEST_PARAMETER_VALUES_FINGERPRINT",
            request_parameter_values_fingerprint,
        ),
        "secret_reference_fingerprint": _hex64(
            "SECRET_REFERENCE_FINGERPRINT",
            secret_reference_fingerprint,
        ),
    }

    base = {
        "schema": "matrix.provider-attempt-intent-id/1",
        "run_id": values["run_id"],
        "provider_key": provider_key,
        "queue_item_fingerprint": (
            values["queue_item_fingerprint"]
        ),
        "permit_id": values["permit_id"],
        "endpoint_manifest_id": (
            values["endpoint_manifest_id"]
        ),
        "security_evidence_id": (
            values["security_evidence_id"]
        ),
        "request_contract_id": (
            values["request_contract_id"]
        ),
        "request_contract_fingerprint": (
            values["request_contract_fingerprint"]
        ),
        "request_path": request_path,
        "request_parameter_names": list(names),
        "request_parameter_values_fingerprint": (
            values[
                "request_parameter_values_fingerprint"
            ]
        ),
        "secret_reference_fingerprint": (
            values["secret_reference_fingerprint"]
        ),
        "created_at": created_at.isoformat(),
        "network_call_started": False,
        "secret_value_persisted": False,
        "query_values_persisted": False,
        "real_provider_execution_authorized": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return ProviderAttemptIntentEvidence(
        intent_id=_sha(base),
        run_id=values["run_id"],
        provider_key=provider_key,
        queue_item_fingerprint=(
            values["queue_item_fingerprint"]
        ),
        permit_id=values["permit_id"],
        endpoint_manifest_id=(
            values["endpoint_manifest_id"]
        ),
        security_evidence_id=(
            values["security_evidence_id"]
        ),
        request_contract_id=(
            values["request_contract_id"]
        ),
        request_contract_fingerprint=(
            values["request_contract_fingerprint"]
        ),
        request_path=request_path,
        request_parameter_names=names,
        request_parameter_values_fingerprint=(
            values[
                "request_parameter_values_fingerprint"
            ]
        ),
        secret_reference_fingerprint=(
            values["secret_reference_fingerprint"]
        ),
        created_at=created_at,
    )


class SQLiteProviderAttemptIntentStore:
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
                CREATE TABLE IF NOT EXISTS provider_attempt_intent (
                    intent_id TEXT PRIMARY KEY,
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
        evidence: ProviderAttemptIntentEvidence,
    ) -> ProviderAttemptIntentEvidence:
        rebuilt = build_provider_attempt_intent_evidence(
            run_id=evidence.run_id,
            provider_key=evidence.provider_key,
            queue_item_fingerprint=(
                evidence.queue_item_fingerprint
            ),
            permit_id=evidence.permit_id,
            endpoint_manifest_id=(
                evidence.endpoint_manifest_id
            ),
            security_evidence_id=(
                evidence.security_evidence_id
            ),
            request_contract_id=(
                evidence.request_contract_id
            ),
            request_contract_fingerprint=(
                evidence.request_contract_fingerprint
            ),
            request_path=evidence.request_path,
            request_parameter_names=(
                evidence.request_parameter_names
            ),
            request_parameter_values_fingerprint=(
                evidence.request_parameter_values_fingerprint
            ),
            secret_reference_fingerprint=(
                evidence.secret_reference_fingerprint
            ),
            created_at=evidence.created_at,
        )

        if rebuilt != evidence:
            raise ValueError(
                "ATTEMPT_INTENT_DERIVATION_MISMATCH"
            )

        existing = self.get_by_permit(
            evidence.permit_id
        )

        if existing is not None:
            if existing != evidence:
                raise ValueError(
                    "ATTEMPT_INTENT_PERMIT_REUSE_VIOLATION"
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
                INSERT INTO provider_attempt_intent (
                    intent_id,
                    permit_id,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    evidence.intent_id,
                    evidence.permit_id,
                    payload_json,
                    payload_sha,
                ),
            )

        return evidence

    def get_by_permit(
        self,
        permit_id: str,
    ) -> ProviderAttemptIntentEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    intent_id,
                    payload_json,
                    payload_sha256
                FROM provider_attempt_intent
                WHERE permit_id = ?
                """,
                (
                    permit_id,
                ),
            ).fetchone()

        if row is None:
            return None

        intent_id, payload_json, payload_sha = row

        if (
            sha256(
                payload_json.encode("utf-8")
            ).hexdigest()
            != payload_sha
        ):
            raise ValueError(
                "ATTEMPT_INTENT_INTEGRITY_FAILURE"
            )

        payload = json.loads(
            payload_json
        )

        rebuilt = build_provider_attempt_intent_evidence(
            run_id=payload["run_id"],
            provider_key=payload["provider_key"],
            queue_item_fingerprint=(
                payload["queue_item_fingerprint"]
            ),
            permit_id=payload["permit_id"],
            endpoint_manifest_id=(
                payload["endpoint_manifest_id"]
            ),
            security_evidence_id=(
                payload["security_evidence_id"]
            ),
            request_contract_id=(
                payload["request_contract_id"]
            ),
            request_contract_fingerprint=(
                payload[
                    "request_contract_fingerprint"
                ]
            ),
            request_path=payload["request_path"],
            request_parameter_names=tuple(
                payload["request_parameter_names"]
            ),
            request_parameter_values_fingerprint=(
                payload[
                    "request_parameter_values_fingerprint"
                ]
            ),
            secret_reference_fingerprint=(
                payload[
                    "secret_reference_fingerprint"
                ]
            ),
            created_at=datetime.fromisoformat(
                payload["created_at"]
            ),
        )

        if (
            rebuilt.intent_id != intent_id
            or rebuilt.payload() != payload
        ):
            raise ValueError(
                "ATTEMPT_INTENT_REDERIVATION_FAILURE"
            )

        return rebuilt

    def list_verified_for_run(
        self,
        run_id: str,
    ) -> tuple[
        ProviderAttemptIntentEvidence,
        ...,
    ]:
        run_id = _hex64(
            "RUN_ID",
            run_id,
        )

        with self._connect() as connection:
            permit_ids = [
                str(row[0])
                for row
                in connection.execute(
                    """
                    SELECT permit_id
                    FROM provider_attempt_intent
                    ORDER BY permit_id
                    """
                ).fetchall()
            ]

        records = []

        for permit_id in permit_ids:
            evidence = self.get_by_permit(
                permit_id
            )
            if (
                evidence is not None
                and evidence.run_id == run_id
            ):
                records.append(
                    evidence
                )

        return tuple(
            records
        )

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            permit_ids = [
                str(row[0])
                for row
                in connection.execute(
                    """
                    SELECT permit_id
                    FROM provider_attempt_intent
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
