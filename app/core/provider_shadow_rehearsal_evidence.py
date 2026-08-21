from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


_ALLOWED_TYPES = {
    "READINESS",
    "REQUEST",
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


@dataclass(frozen=True)
class ProviderShadowRehearsalEvidence:
    evidence_id: str
    provider_key: str
    evidence_type: str
    parent_readiness_evidence_id: str | None
    payload_fingerprint: str
    payload: Mapping[str, Any]
    created_at: datetime

    def canonical_payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-shadow-rehearsal-evidence/1"
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
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def build_provider_shadow_rehearsal_evidence(
    *,
    provider_key: str,
    evidence_type: str,
    payload: Mapping[str, Any],
    created_at: datetime,
    parent_readiness_evidence_id: str | None = None,
) -> ProviderShadowRehearsalEvidence:
    if not isinstance(
        provider_key,
        str,
    ) or not provider_key:
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
        evidence_type
        == "READINESS"
        and parent_readiness_evidence_id
        is not None
    ):
        raise ValueError(
            "READINESS_EVIDENCE_CANNOT_HAVE_PARENT"
        )

    if (
        evidence_type
        == "REQUEST"
        and (
            not isinstance(
                parent_readiness_evidence_id,
                str,
            )
            or len(
                parent_readiness_evidence_id
            )
            != 64
        )
    ):
        raise ValueError(
            "REQUEST_READINESS_EVIDENCE_ID_REQUIRED"
        )

    base = {
        "schema": (
            "matrix.provider-shadow-rehearsal-evidence-id/1"
        ),
        "provider_key": (
            provider_key
        ),
        "evidence_type": (
            evidence_type
        ),
        "parent_readiness_evidence_id": (
            parent_readiness_evidence_id
        ),
        "payload_fingerprint": (
            payload_fingerprint
        ),
        "created_at": (
            created_at.isoformat()
        ),
        "real_provider_execution_authorized": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return ProviderShadowRehearsalEvidence(
        evidence_id=_sha(
            base
        ),
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

    def record(
        self,
        evidence: ProviderShadowRehearsalEvidence,
    ) -> ProviderShadowRehearsalEvidence:
        rebuilt = (
            build_provider_shadow_rehearsal_evidence(
                provider_key=(
                    evidence.provider_key
                ),
                evidence_type=(
                    evidence.evidence_type
                ),
                payload=(
                    evidence.payload
                ),
                created_at=(
                    evidence.created_at
                ),
                parent_readiness_evidence_id=(
                    evidence.parent_readiness_evidence_id
                ),
            )
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
                SELECT
                    payload_json,
                    payload_sha256
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

            if (
                evidence.evidence_type
                == "REQUEST"
            ):
                parent = connection.execute(
                    """
                    SELECT evidence_type
                    FROM provider_shadow_rehearsal_evidence
                    WHERE evidence_id = ?
                    """,
                    (
                        evidence.parent_readiness_evidence_id,
                    ),
                ).fetchone()

                if (
                    parent is None
                    or str(
                        parent[0]
                    )
                    != "READINESS"
                ):
                    connection.execute(
                        "ROLLBACK"
                    )
                    raise ValueError(
                        "SHADOW_REQUEST_PARENT_READINESS_REQUIRED"
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
                SELECT
                    payload_json,
                    payload_sha256
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

        rebuilt = (
            build_provider_shadow_rehearsal_evidence(
                provider_key=(
                    payload[
                        "provider_key"
                    ]
                ),
                evidence_type=(
                    payload[
                        "evidence_type"
                    ]
                ),
                payload=(
                    payload[
                        "payload"
                    ]
                ),
                created_at=(
                    datetime.fromisoformat(
                        payload[
                            "created_at"
                        ]
                    )
                ),
                parent_readiness_evidence_id=(
                    payload[
                        "parent_readiness_evidence_id"
                    ]
                ),
            )
        )

        if (
            rebuilt.evidence_id
            != evidence_id
            or rebuilt.canonical_payload()
            != payload
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
                WHERE
                    evidence_type = 'REQUEST'
                    AND parent_readiness_evidence_id = ?
                ORDER BY evidence_id
                """,
                (
                    readiness_evidence_id,
                ),
            ).fetchall()

        return tuple(
            evidence
            for row
            in rows
            for evidence
            in (
                self.get_verified(
                    str(
                        row[0]
                    )
                ),
            )
            if evidence
            is not None
        )

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            evidence_ids = [
                str(
                    row[0]
                )
                for row
                in connection.execute(
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
                for evidence_id
                in evidence_ids
            )
        except ValueError:
            return False
