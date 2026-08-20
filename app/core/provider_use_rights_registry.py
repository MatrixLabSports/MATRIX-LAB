from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


UTC = timezone.utc


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _aware(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"INVALID_{name}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"INVALID_{name}")
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _nonempty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_{name}")
    return value.strip()


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class ProviderUseRightsManifest:
    manifest_id: str
    sport: str
    provider_key: str
    data_scope: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    jurisdiction_scope: tuple[str, ...]
    effective_at: datetime
    expires_at: datetime | None
    terms_reference_sha256: str
    manual_approval_id: str
    status: str
    manifest_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-use-rights-manifest/1",
            "manifest_id": self.manifest_id,
            "sport": self.sport,
            "provider_key": self.provider_key,
            "data_scope": list(self.data_scope),
            "allowed_purposes": list(self.allowed_purposes),
            "jurisdiction_scope": list(self.jurisdiction_scope),
            "effective_at": _iso(self.effective_at),
            "expires_at": (
                None if self.expires_at is None else _iso(self.expires_at)
            ),
            "terms_reference_sha256": self.terms_reference_sha256,
            "manual_approval_id": self.manual_approval_id,
            "status": self.status,
            "automatic_rights_approval": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "manifest_fingerprint": self.manifest_fingerprint,
        }


@dataclass(frozen=True)
class ProviderUseRightsIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteProviderUseRightsRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_use_rights (
                    manifest_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    effective_at TEXT NOT NULL,
                    expires_at TEXT,
                    manifest_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    CHECK (sport IN ('football', 'tennis')),
                    CHECK (status IN ('APPROVED', 'REJECTED'))
                )
                """
            )

    @staticmethod
    def build_manifest(
        *,
        sport: str,
        provider_key: str,
        data_scope: Sequence[str],
        allowed_purposes: Sequence[str],
        jurisdiction_scope: Sequence[str],
        effective_at: datetime,
        expires_at: datetime | None,
        terms_reference_sha256: str,
        manual_approval_id: str,
        status: str,
    ) -> ProviderUseRightsManifest:
        if sport not in {"football", "tennis"}:
            raise ValueError("INVALID_SPORT")
        provider_key = _nonempty("PROVIDER_KEY", provider_key)
        manual_approval_id = _nonempty(
            "MANUAL_APPROVAL_ID",
            manual_approval_id,
        )
        effective_at = _aware("EFFECTIVE_AT", effective_at)
        if expires_at is not None:
            expires_at = _aware("EXPIRES_AT", expires_at)
            if expires_at <= effective_at:
                raise ValueError("INVALID_RIGHTS_EXPIRY")
        terms_reference_sha256 = _hex64(
            "TERMS_REFERENCE_SHA256",
            terms_reference_sha256,
        )
        if status not in {"APPROVED", "REJECTED"}:
            raise ValueError("INVALID_RIGHTS_STATUS")

        def normalize(name: str, values: Sequence[str]) -> tuple[str, ...]:
            if (
                isinstance(values, (str, bytes))
                or not isinstance(values, Sequence)
                or not values
            ):
                raise ValueError(f"EMPTY_{name}")
            result = tuple(
                sorted(
                    {
                        _nonempty(name, item)
                        for item in values
                    }
                )
            )
            if len(result) != len(values):
                raise ValueError(f"DUPLICATE_{name}")
            return result

        data = normalize("DATA_SCOPE", data_scope)
        purposes = normalize("ALLOWED_PURPOSES", allowed_purposes)
        jurisdictions = normalize(
            "JURISDICTION_SCOPE",
            jurisdiction_scope,
        )

        base = {
            "schema": "matrix.provider-use-rights-manifest/1",
            "sport": sport,
            "provider_key": provider_key,
            "data_scope": list(data),
            "allowed_purposes": list(purposes),
            "jurisdiction_scope": list(jurisdictions),
            "effective_at": _iso(effective_at),
            "expires_at": (
                None if expires_at is None else _iso(expires_at)
            ),
            "terms_reference_sha256": terms_reference_sha256,
            "manual_approval_id": manual_approval_id,
            "status": status,
            "automatic_rights_approval": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }
        manifest_fingerprint = _sha(base)
        manifest_id = _sha(
            {
                "schema": "matrix.provider-use-rights-manifest-id/1",
                "manifest_fingerprint": manifest_fingerprint,
            }
        )
        return ProviderUseRightsManifest(
            manifest_id=manifest_id,
            sport=sport,
            provider_key=provider_key,
            data_scope=data,
            allowed_purposes=purposes,
            jurisdiction_scope=jurisdictions,
            effective_at=effective_at,
            expires_at=expires_at,
            terms_reference_sha256=terms_reference_sha256,
            manual_approval_id=manual_approval_id,
            status=status,
            manifest_fingerprint=manifest_fingerprint,
        )

    def register(
        self,
        manifest: ProviderUseRightsManifest,
    ) -> ProviderUseRightsManifest:
        expected = self.build_manifest(
            sport=manifest.sport,
            provider_key=manifest.provider_key,
            data_scope=manifest.data_scope,
            allowed_purposes=manifest.allowed_purposes,
            jurisdiction_scope=manifest.jurisdiction_scope,
            effective_at=manifest.effective_at,
            expires_at=manifest.expires_at,
            terms_reference_sha256=manifest.terms_reference_sha256,
            manual_approval_id=manifest.manual_approval_id,
            status=manifest.status,
        )
        if expected != manifest:
            raise ValueError("PROVIDER_RIGHTS_DERIVATION_MISMATCH")

        payload_json = _canonical_json(manifest.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT manifest_id, payload_sha256
                FROM provider_use_rights
                WHERE manifest_fingerprint = ?
                """,
                (manifest.manifest_fingerprint,),
            ).fetchone()
            if existing is not None:
                connection.execute("ROLLBACK")
                if (
                    str(existing[0]) == manifest.manifest_id
                    and str(existing[1]) == payload_sha
                ):
                    return manifest
                raise ValueError("PROVIDER_RIGHTS_MUTATION_VIOLATION")

            connection.execute(
                """
                INSERT INTO provider_use_rights (
                    manifest_id,
                    sport,
                    provider_key,
                    status,
                    effective_at,
                    expires_at,
                    manifest_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.manifest_id,
                    manifest.sport,
                    manifest.provider_key,
                    manifest.status,
                    _iso(manifest.effective_at),
                    (
                        None
                        if manifest.expires_at is None
                        else _iso(manifest.expires_at)
                    ),
                    manifest.manifest_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")

        return manifest

    def get_by_fingerprint(
        self,
        fingerprint: str,
    ) -> Mapping[str, Any] | None:
        fingerprint = _hex64("MANIFEST_FINGERPRINT", fingerprint)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM provider_use_rights
                WHERE manifest_fingerprint = ?
                """,
                (fingerprint,),
            ).fetchone()

        if row is None:
            return None

        payload = json.loads(row[0])
        actual_sha = sha256(
            _canonical_json(payload).encode("utf-8")
        ).hexdigest()
        if actual_sha != row[1]:
            raise ValueError("PROVIDER_RIGHTS_INTEGRITY_VIOLATION")
        return payload

    def audit_integrity(self) -> ProviderUseRightsIntegrityReport:
        errors: list[str] = []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT manifest_fingerprint
                FROM provider_use_rights
                ORDER BY manifest_id
                """
            ).fetchall()
        for (fingerprint,) in rows:
            try:
                payload = self.get_by_fingerprint(fingerprint)
                if payload["manifest_fingerprint"] != fingerprint:
                    errors.append(
                        f"MANIFEST_FINGERPRINT_MISMATCH:{fingerprint}"
                    )
            except Exception as error:
                errors.append(f"{type(error).__name__}:{fingerprint}")
        return ProviderUseRightsIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
