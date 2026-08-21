from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.secret_reference import (
    SecretReference,
    build_secret_reference,
    resolve_secret_runtime,
)


_ALLOWED_TYPES = {
    "READINESS",
    "REQUEST",
}

_SHADOW_ATTESTATION_PROVIDER_KEY = (
    "matrix_shadow_rehearsal"
)
_SHADOW_ATTESTATION_ENVIRONMENT_VARIABLE = (
    "MATRIX_SHADOW_REHEARSAL_ATTESTATION_KEY"
)
_MINIMUM_ATTESTATION_KEY_BYTES = 32


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
        _json(value).encode(
            "utf-8"
        )
    ).hexdigest()


def _aware(value: datetime) -> datetime:
    if (
        value.tzinfo is None
        or value.utcoffset()
        is None
    ):
        raise ValueError(
            "TIMEZONE_UNVERIFIED"
        )

    return value.astimezone(
        timezone.utc
    )


def _hex64(
    name: str,
    value: object,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or len(
            value
        )
        != 64
    ):
        raise ValueError(
            f"INVALID_{name}"
        )

    try:
        int(
            value,
            16,
        )
    except ValueError as error:
        raise ValueError(
            f"INVALID_{name}"
        ) from error

    return value.lower()


def _store_identity(
    path: Path,
) -> str:
    return _sha(
        {
            "schema": (
                "matrix.provider-shadow-rehearsal-store-identity/1"
            ),
            "path": str(
                path.resolve()
            ),
        }
    )


def build_provider_shadow_attestation_key_reference() -> SecretReference:
    """Return the one canonical, durable reference for SHADOW attestation.

    The raw key is resolved only at runtime and is never persisted in the
    rehearsal evidence database. The fixed reference prevents callers from
    supplying an arbitrary signing root to certification.
    """
    return build_secret_reference(
        provider_key=(
            _SHADOW_ATTESTATION_PROVIDER_KEY
        ),
        environment_variable=(
            _SHADOW_ATTESTATION_ENVIRONMENT_VARIABLE
        ),
        secret_type="TOKEN",
    )


def _resolve_attestation_key() -> tuple[
    SecretReference,
    bytes,
]:
    reference = (
        build_provider_shadow_attestation_key_reference()
    )
    value = resolve_secret_runtime(
        reference
    )
    key = value.encode(
        "utf-8"
    )

    if len(key) < _MINIMUM_ATTESTATION_KEY_BYTES:
        raise ValueError(
            "SHADOW_ATTESTATION_KEY_TOO_SHORT"
        )

    return reference, key


def _authority_id(
    *,
    provider_key: str,
    store_identity: str,
    attestation_key_reference_fingerprint: str,
) -> str:
    return _sha(
        {
            "schema": (
                "matrix.provider-shadow-rehearsal-authority-id/3"
            ),
            "provider_key": provider_key,
            "store_identity": store_identity,
            "attestation_key_reference_fingerprint": (
                attestation_key_reference_fingerprint
            ),
            "raw_attestation_key_persisted": False,
        }
    )


def _unsigned_base(
    *,
    provider_key: str,
    evidence_type: str,
    parent_readiness_evidence_id: str | None,
    payload_fingerprint: str,
    created_at: datetime,
    authority_id: str,
    store_identity: str,
    attestation_key_reference_fingerprint: str,
) -> Mapping[str, Any]:
    return {
        "schema": (
            "matrix.provider-shadow-rehearsal-evidence-unsigned/3"
        ),
        "provider_key": provider_key,
        "evidence_type": evidence_type,
        "parent_readiness_evidence_id": (
            parent_readiness_evidence_id
        ),
        "payload_fingerprint": (
            payload_fingerprint
        ),
        "created_at": (
            created_at.isoformat()
        ),
        "authority_id": authority_id,
        "store_identity": (
            store_identity
        ),
        "attestation_key_reference_fingerprint": (
            attestation_key_reference_fingerprint
        ),
        "raw_attestation_key_persisted": False,
        "real_provider_execution_authorized": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }


def _evidence_id(
    *,
    unsigned_base: Mapping[str, Any],
    issuer_attestation: str,
) -> str:
    return _sha(
        {
            "schema": (
                "matrix.provider-shadow-rehearsal-evidence-id/3"
            ),
            "unsigned_base": dict(
                unsigned_base
            ),
            "issuer_attestation": (
                issuer_attestation
            ),
        }
    )


@dataclass(frozen=True)
class ProviderShadowRehearsalEvidence:
    evidence_id: str
    provider_key: str
    evidence_type: str
    parent_readiness_evidence_id: str | None
    payload_fingerprint: str
    payload: Mapping[str, Any]
    created_at: datetime
    authority_id: str
    store_identity: str
    attestation_key_reference_fingerprint: str
    issuer_attestation: str

    def canonical_payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-shadow-rehearsal-evidence/3"
            ),
            "evidence_id": (
                self.evidence_id
            ),
            "provider_key": (
                self.provider_key
            ),
            "evidence_type": (
                self.evidence_type
            ),
            "parent_readiness_evidence_id": (
                self.parent_readiness_evidence_id
            ),
            "payload_fingerprint": (
                self.payload_fingerprint
            ),
            "payload": dict(
                self.payload
            ),
            "created_at": (
                self.created_at.isoformat()
            ),
            "authority_id": (
                self.authority_id
            ),
            "store_identity": (
                self.store_identity
            ),
            "attestation_key_reference_fingerprint": (
                self.attestation_key_reference_fingerprint
            ),
            "issuer_attestation": (
                self.issuer_attestation
            ),
            "raw_attestation_key_persisted": False,
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def _build_attested_provider_shadow_rehearsal_evidence(
    *,
    provider_key: str,
    store_identity: str,
    evidence_type: str,
    payload: Mapping[str, Any],
    created_at: datetime,
    parent_readiness_evidence_id: str | None = None,
) -> ProviderShadowRehearsalEvidence:
    """Internal issuer used only by the governed SHADOW runtime.

    The signing root is fixed outside caller-controlled arguments. CI forbids
    application imports of this issuer outside the official SHADOW runtime.
    """
    if (
        not isinstance(
            provider_key,
            str,
        )
        or not provider_key
    ):
        raise ValueError(
            "INVALID_PROVIDER_KEY"
        )

    if evidence_type not in _ALLOWED_TYPES:
        raise ValueError(
            "INVALID_SHADOW_EVIDENCE_TYPE"
        )

    if not isinstance(
        payload,
        Mapping,
    ):
        raise ValueError(
            "INVALID_SHADOW_EVIDENCE_PAYLOAD"
        )

    store_identity = _hex64(
        "STORE_IDENTITY",
        store_identity,
    )
    created_at = _aware(
        created_at
    )
    payload_dict = dict(
        payload
    )
    payload_fingerprint = _sha(
        payload_dict
    )

    if (
        evidence_type == "READINESS"
        and parent_readiness_evidence_id
        is not None
    ):
        raise ValueError(
            "READINESS_EVIDENCE_CANNOT_HAVE_PARENT"
        )

    if evidence_type == "REQUEST":
        parent_readiness_evidence_id = (
            _hex64(
                "PARENT_READINESS_EVIDENCE_ID",
                parent_readiness_evidence_id,
            )
        )

    reference, signing_key = (
        _resolve_attestation_key()
    )
    reference_fingerprint = (
        reference.reference_fingerprint
    )
    authority_id = _authority_id(
        provider_key=provider_key,
        store_identity=store_identity,
        attestation_key_reference_fingerprint=(
            reference_fingerprint
        ),
    )

    unsigned = _unsigned_base(
        provider_key=provider_key,
        evidence_type=evidence_type,
        parent_readiness_evidence_id=(
            parent_readiness_evidence_id
        ),
        payload_fingerprint=(
            payload_fingerprint
        ),
        created_at=created_at,
        authority_id=authority_id,
        store_identity=store_identity,
        attestation_key_reference_fingerprint=(
            reference_fingerprint
        ),
    )

    issuer_attestation = hmac.new(
        signing_key,
        _json(
            {
                "unsigned_base": dict(
                    unsigned
                ),
                "payload": payload_dict,
            }
        ).encode(
            "utf-8"
        ),
        sha256,
    ).hexdigest()

    evidence_id = _evidence_id(
        unsigned_base=unsigned,
        issuer_attestation=(
            issuer_attestation
        ),
    )

    return ProviderShadowRehearsalEvidence(
        evidence_id=evidence_id,
        provider_key=provider_key,
        evidence_type=evidence_type,
        parent_readiness_evidence_id=(
            parent_readiness_evidence_id
        ),
        payload_fingerprint=(
            payload_fingerprint
        ),
        payload=payload_dict,
        created_at=created_at,
        authority_id=authority_id,
        store_identity=store_identity,
        attestation_key_reference_fingerprint=(
            reference_fingerprint
        ),
        issuer_attestation=(
            issuer_attestation
        ),
    )


def verify_provider_shadow_rehearsal_attestation(
    evidence: ProviderShadowRehearsalEvidence,
) -> bool:
    if type(evidence) is not ProviderShadowRehearsalEvidence:
        return False

    try:
        reference, signing_key = (
            _resolve_attestation_key()
        )

        if (
            evidence.attestation_key_reference_fingerprint
            != reference.reference_fingerprint
        ):
            return False

        payload_fingerprint = _sha(
            dict(
                evidence.payload
            )
        )
        created_at = _aware(
            evidence.created_at
        )
        authority_id = _authority_id(
            provider_key=(
                evidence.provider_key
            ),
            store_identity=(
                evidence.store_identity
            ),
            attestation_key_reference_fingerprint=(
                reference.reference_fingerprint
            ),
        )

        if authority_id != evidence.authority_id:
            return False

        unsigned = _unsigned_base(
            provider_key=(
                evidence.provider_key
            ),
            evidence_type=(
                evidence.evidence_type
            ),
            parent_readiness_evidence_id=(
                evidence.parent_readiness_evidence_id
            ),
            payload_fingerprint=(
                payload_fingerprint
            ),
            created_at=created_at,
            authority_id=authority_id,
            store_identity=(
                evidence.store_identity
            ),
            attestation_key_reference_fingerprint=(
                reference.reference_fingerprint
            ),
        )
    except Exception:
        return False

    expected_attestation = hmac.new(
        signing_key,
        _json(
            {
                "unsigned_base": dict(
                    unsigned
                ),
                "payload": dict(
                    evidence.payload
                ),
            }
        ).encode(
            "utf-8"
        ),
        sha256,
    ).hexdigest()

    expected_id = _evidence_id(
        unsigned_base=unsigned,
        issuer_attestation=(
            expected_attestation
        ),
    )

    return (
        evidence.payload_fingerprint
        == payload_fingerprint
        and hmac.compare_digest(
            evidence.issuer_attestation,
            expected_attestation,
        )
        and evidence.evidence_id
        == expected_id
    )


class SQLiteProviderShadowRehearsalEvidenceStore:
    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(
            path
        )
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.store_identity = (
            _store_identity(
                self.path
            )
        )

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_shadow_rehearsal_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    provider_key TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    parent_readiness_evidence_id TEXT,
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

    @staticmethod
    def _rebuild_structural(
        payload: Mapping[str, Any],
    ) -> ProviderShadowRehearsalEvidence:
        if (
            payload.get(
                "schema"
            )
            != "matrix.provider-shadow-rehearsal-evidence/3"
        ):
            raise ValueError(
                "SHADOW_EVIDENCE_SCHEMA_MISMATCH"
            )

        provider_key = payload[
            "provider_key"
        ]
        evidence_type = payload[
            "evidence_type"
        ]
        parent = payload[
            "parent_readiness_evidence_id"
        ]
        payload_dict = dict(
            payload[
                "payload"
            ]
        )
        created_at = _aware(
            datetime.fromisoformat(
                payload[
                    "created_at"
                ]
            )
        )
        authority_id = _hex64(
            "AUTHORITY_ID",
            payload[
                "authority_id"
            ],
        )
        store_identity = _hex64(
            "STORE_IDENTITY",
            payload[
                "store_identity"
            ],
        )
        reference_fingerprint = _hex64(
            "ATTESTATION_KEY_REFERENCE_FINGERPRINT",
            payload[
                "attestation_key_reference_fingerprint"
            ],
        )
        issuer_attestation = _hex64(
            "ISSUER_ATTESTATION",
            payload[
                "issuer_attestation"
            ],
        )

        if (
            payload.get(
                "raw_attestation_key_persisted"
            )
            is not False
        ):
            raise ValueError(
                "RAW_SHADOW_ATTESTATION_KEY_PERSISTED"
            )

        if evidence_type not in _ALLOWED_TYPES:
            raise ValueError(
                "INVALID_SHADOW_EVIDENCE_TYPE"
            )

        if (
            evidence_type == "READINESS"
            and parent is not None
        ):
            raise ValueError(
                "READINESS_EVIDENCE_CANNOT_HAVE_PARENT"
            )

        if evidence_type == "REQUEST":
            parent = _hex64(
                "PARENT_READINESS_EVIDENCE_ID",
                parent,
            )

        payload_fingerprint = _sha(
            payload_dict
        )
        expected_authority_id = _authority_id(
            provider_key=provider_key,
            store_identity=store_identity,
            attestation_key_reference_fingerprint=(
                reference_fingerprint
            ),
        )

        if authority_id != expected_authority_id:
            raise ValueError(
                "SHADOW_EVIDENCE_AUTHORITY_ID_MISMATCH"
            )

        unsigned = _unsigned_base(
            provider_key=provider_key,
            evidence_type=evidence_type,
            parent_readiness_evidence_id=parent,
            payload_fingerprint=(
                payload_fingerprint
            ),
            created_at=created_at,
            authority_id=authority_id,
            store_identity=store_identity,
            attestation_key_reference_fingerprint=(
                reference_fingerprint
            ),
        )
        evidence_id = _evidence_id(
            unsigned_base=unsigned,
            issuer_attestation=(
                issuer_attestation
            ),
        )

        rebuilt = ProviderShadowRehearsalEvidence(
            evidence_id=evidence_id,
            provider_key=provider_key,
            evidence_type=evidence_type,
            parent_readiness_evidence_id=(
                parent
            ),
            payload_fingerprint=(
                payload_fingerprint
            ),
            payload=payload_dict,
            created_at=created_at,
            authority_id=authority_id,
            store_identity=store_identity,
            attestation_key_reference_fingerprint=(
                reference_fingerprint
            ),
            issuer_attestation=(
                issuer_attestation
            ),
        )

        if rebuilt.canonical_payload() != payload:
            raise ValueError(
                "SHADOW_EVIDENCE_REDERIVATION_FAILURE"
            )

        return rebuilt

    def record(
        self,
        evidence: ProviderShadowRehearsalEvidence,
    ) -> ProviderShadowRehearsalEvidence:
        if type(evidence) is not ProviderShadowRehearsalEvidence:
            raise ValueError(
                "INVALID_SHADOW_EVIDENCE"
            )

        if evidence.store_identity != self.store_identity:
            raise ValueError(
                "SHADOW_EVIDENCE_STORE_BINDING_MISMATCH"
            )

        if not verify_provider_shadow_rehearsal_attestation(
            evidence
        ):
            raise ValueError(
                "SHADOW_EVIDENCE_ATTESTATION_INVALID"
            )

        rebuilt = self._rebuild_structural(
            evidence.canonical_payload()
        )

        if rebuilt != evidence:
            raise ValueError(
                "SHADOW_EVIDENCE_DERIVATION_MISMATCH"
            )

        payload_json = _json(
            evidence.canonical_payload()
        )
        payload_sha = sha256(
            payload_json.encode(
                "utf-8"
            )
        ).hexdigest()

        with self._connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM provider_shadow_rehearsal_evidence
                WHERE evidence_id = ?
                """,
                (
                    evidence.evidence_id,
                ),
            ).fetchone()

            if row is not None:
                connection.execute(
                    "ROLLBACK"
                )

                if row == (
                    payload_json,
                    payload_sha,
                ):
                    return evidence

                raise ValueError(
                    "SHADOW_EVIDENCE_MUTATION_VIOLATION"
                )

            if evidence.evidence_type == "REQUEST":
                parent = connection.execute(
                    """
                    SELECT evidence_type, provider_key, payload_json
                    FROM provider_shadow_rehearsal_evidence
                    WHERE evidence_id = ?
                    """,
                    (
                        evidence.parent_readiness_evidence_id,
                    ),
                ).fetchone()

                if (
                    parent is None
                    or str(parent[0]) != "READINESS"
                    or str(parent[1]) != evidence.provider_key
                ):
                    connection.execute(
                        "ROLLBACK"
                    )
                    raise ValueError(
                        "SHADOW_REQUEST_PARENT_READINESS_REQUIRED"
                    )

                parent_payload = json.loads(
                    str(
                        parent[2]
                    )
                )

                if (
                    parent_payload.get(
                        "authority_id"
                    )
                    != evidence.authority_id
                    or parent_payload.get(
                        "store_identity"
                    )
                    != evidence.store_identity
                    or parent_payload.get(
                        "attestation_key_reference_fingerprint"
                    )
                    != evidence.attestation_key_reference_fingerprint
                ):
                    connection.execute(
                        "ROLLBACK"
                    )
                    raise ValueError(
                        "SHADOW_REQUEST_AUTHORITY_CHAIN_MISMATCH"
                    )

            connection.execute(
                """
                INSERT INTO provider_shadow_rehearsal_evidence (
                    evidence_id,
                    provider_key,
                    evidence_type,
                    parent_readiness_evidence_id,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.evidence_id,
                    evidence.provider_key,
                    evidence.evidence_type,
                    evidence.parent_readiness_evidence_id,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute(
                "COMMIT"
            )

        return evidence

    def get_verified(
        self,
        evidence_id: str,
    ) -> ProviderShadowRehearsalEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM provider_shadow_rehearsal_evidence
                WHERE evidence_id = ?
                """,
                (
                    evidence_id,
                ),
            ).fetchone()

        if row is None:
            return None

        payload_json, payload_sha = row

        if (
            sha256(
                payload_json.encode(
                    "utf-8"
                )
            ).hexdigest()
            != payload_sha
        ):
            raise ValueError(
                "SHADOW_EVIDENCE_INTEGRITY_FAILURE"
            )

        payload = json.loads(
            payload_json
        )
        rebuilt = self._rebuild_structural(
            payload
        )

        if (
            rebuilt.evidence_id != evidence_id
            or rebuilt.store_identity != self.store_identity
        ):
            raise ValueError(
                "SHADOW_EVIDENCE_REDERIVATION_FAILURE"
            )

        return rebuilt

    def list_verified_requests(
        self,
        readiness_evidence_id: str,
    ) -> tuple[
        ProviderShadowRehearsalEvidence,
        ...,
    ]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT evidence_id
                FROM provider_shadow_rehearsal_evidence
                WHERE evidence_type = 'REQUEST'
                  AND parent_readiness_evidence_id = ?
                ORDER BY evidence_id
                """,
                (
                    readiness_evidence_id,
                ),
            ).fetchall()

        return tuple(
            evidence
            for row in rows
            for evidence in (
                self.get_verified(
                    str(
                        row[0]
                    )
                ),
            )
            if evidence is not None
        )

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            evidence_ids = [
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT evidence_id
                    FROM provider_shadow_rehearsal_evidence
                    ORDER BY evidence_id
                    """
                ).fetchall()
            ]

        try:
            return all(
                self.get_verified(
                    evidence_id
                )
                is not None
                for evidence_id in evidence_ids
            )
        except (
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ):
            return False
