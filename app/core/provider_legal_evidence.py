from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


_ALLOWED_KINDS = {
    "PROVIDER_TERMS",
    "RIGHTS_HOLDER_LICENSE",
    "HUMAN_APPROVAL",
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
class ProviderLegalEvidence:
    evidence_id: str
    evidence_kind: str
    source_reference: str
    content_fingerprint: str
    captured_at: datetime
    verified_by: str
    verification_reference: str
    verification_status: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-legal-evidence/1",
            "evidence_id": self.evidence_id,
            "evidence_kind": self.evidence_kind,
            "source_reference": self.source_reference,
            "content_fingerprint": self.content_fingerprint,
            "captured_at": self.captured_at.isoformat(),
            "verified_by": self.verified_by,
            "verification_reference": self.verification_reference,
            "verification_status": self.verification_status,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "real_provider_execution_authorized": False,
        }


def build_provider_legal_evidence(
    *,
    evidence_kind: str,
    source_reference: str,
    content_fingerprint: str,
    captured_at: datetime,
    verified_by: str,
    verification_reference: str,
    verification_status: str = "HUMAN_VERIFIED",
) -> ProviderLegalEvidence:
    if evidence_kind not in _ALLOWED_KINDS:
        raise ValueError("INVALID_LEGAL_EVIDENCE_KIND")
    if not source_reference:
        raise ValueError("LEGAL_EVIDENCE_SOURCE_REQUIRED")
    if not verified_by:
        raise ValueError("LEGAL_EVIDENCE_VERIFIER_REQUIRED")
    if verification_status != "HUMAN_VERIFIED":
        raise ValueError("LEGAL_EVIDENCE_NOT_HUMAN_VERIFIED")

    content_fingerprint = _hex64(
        "LEGAL_CONTENT_FINGERPRINT",
        content_fingerprint,
    )
    verification_reference = _hex64(
        "LEGAL_VERIFICATION_REFERENCE",
        verification_reference,
    )
    captured_at = _aware(captured_at)

    base = {
        "schema": "matrix.provider-legal-evidence-id/1",
        "evidence_kind": evidence_kind,
        "source_reference": source_reference,
        "content_fingerprint": content_fingerprint,
        "captured_at": captured_at.isoformat(),
        "verified_by": verified_by,
        "verification_reference": verification_reference,
        "verification_status": verification_status,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
        "real_provider_execution_authorized": False,
    }

    return ProviderLegalEvidence(
        evidence_id=_sha(base),
        evidence_kind=evidence_kind,
        source_reference=source_reference,
        content_fingerprint=content_fingerprint,
        captured_at=captured_at,
        verified_by=verified_by,
        verification_reference=verification_reference,
        verification_status=verification_status,
    )


class SQLiteProviderLegalEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_legal_evidence (
                    evidence_id TEXT PRIMARY KEY,
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
        evidence: ProviderLegalEvidence,
    ) -> ProviderLegalEvidence:
        rebuilt = build_provider_legal_evidence(
            evidence_kind=evidence.evidence_kind,
            source_reference=evidence.source_reference,
            content_fingerprint=evidence.content_fingerprint,
            captured_at=evidence.captured_at,
            verified_by=evidence.verified_by,
            verification_reference=evidence.verification_reference,
            verification_status=evidence.verification_status,
        )
        if rebuilt != evidence:
            raise ValueError(
                "LEGAL_EVIDENCE_DERIVATION_MISMATCH"
            )

        payload_json = _json(
            evidence.payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO provider_legal_evidence (
                    evidence_id,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?)
                """,
                (
                    evidence.evidence_id,
                    payload_json,
                    payload_sha,
                ),
            )
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM provider_legal_evidence
                WHERE evidence_id = ?
                """,
                (
                    evidence.evidence_id,
                ),
            ).fetchone()

        if row != (
            payload_json,
            payload_sha,
        ):
            raise ValueError(
                "LEGAL_EVIDENCE_MUTATION_VIOLATION"
            )
        return evidence

    def get_verified(
        self,
        evidence_id: str,
    ) -> ProviderLegalEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM provider_legal_evidence
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
                payload_json.encode("utf-8")
            ).hexdigest()
            != payload_sha
        ):
            raise ValueError(
                "LEGAL_EVIDENCE_INTEGRITY_FAILURE"
            )

        payload = json.loads(
            payload_json
        )

        rebuilt = build_provider_legal_evidence(
            evidence_kind=payload["evidence_kind"],
            source_reference=payload["source_reference"],
            content_fingerprint=payload["content_fingerprint"],
            captured_at=datetime.fromisoformat(
                payload["captured_at"]
            ),
            verified_by=payload["verified_by"],
            verification_reference=payload["verification_reference"],
            verification_status=payload["verification_status"],
        )

        if (
            rebuilt.evidence_id != evidence_id
            or rebuilt.payload() != payload
        ):
            raise ValueError(
                "LEGAL_EVIDENCE_REDERIVATION_FAILURE"
            )

        return rebuilt

    def find_verified(
        self,
        *,
        evidence_kind: str,
        content_fingerprint: str,
    ) -> ProviderLegalEvidence | None:
        content_fingerprint = _hex64(
            "LEGAL_CONTENT_FINGERPRINT",
            content_fingerprint,
        )

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT evidence_id
                FROM provider_legal_evidence
                ORDER BY evidence_id
                """
            ).fetchall()

        matches: list[
            ProviderLegalEvidence
        ] = []

        for row in rows:
            evidence = self.get_verified(
                str(
                    row[0]
                )
            )
            if (
                evidence is not None
                and evidence.evidence_kind
                == evidence_kind
                and evidence.content_fingerprint
                == content_fingerprint
                and evidence.verification_status
                == "HUMAN_VERIFIED"
            ):
                matches.append(
                    evidence
                )

        if len(matches) > 1:
            raise ValueError(
                "LEGAL_EVIDENCE_AMBIGUOUS"
            )

        return (
            matches[0]
            if matches
            else None
        )

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            evidence_ids = [
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT evidence_id
                    FROM provider_legal_evidence
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
