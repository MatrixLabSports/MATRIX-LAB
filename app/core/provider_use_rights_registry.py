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
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _aware(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"INVALID_{name}")
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"INVALID_{name}")
    return value.astimezone(UTC)


def _parse_utc(
    name: str,
    value: object,
) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"INVALID_{name}")
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(
            f"INVALID_{name}"
        ) from error
    return _aware(name, parsed)


def _iso(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _nonempty(
    name: str,
    value: object,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError(f"INVALID_{name}")
    return value.strip()


def _hex64(
    name: str,
    value: object,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
    ):
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(
            f"INVALID_{name}"
        ) from error
    return value.lower()


def _normalize_scope(
    name: str,
    values: Sequence[str],
) -> tuple[str, ...]:
    if (
        isinstance(values, (str, bytes))
        or not isinstance(values, Sequence)
        or not values
    ):
        raise ValueError(f"EMPTY_{name}")

    normalized = tuple(
        sorted(
            {
                _nonempty(name, item)
                for item in values
            }
        )
    )

    if len(normalized) != len(values):
        raise ValueError(
            f"DUPLICATE_{name}"
        )

    return normalized


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

    def payload(
        self,
    ) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-use-rights-manifest/1"
            ),
            "manifest_id": self.manifest_id,
            "sport": self.sport,
            "provider_key": self.provider_key,
            "data_scope": list(
                self.data_scope
            ),
            "allowed_purposes": list(
                self.allowed_purposes
            ),
            "jurisdiction_scope": list(
                self.jurisdiction_scope
            ),
            "effective_at": _iso(
                self.effective_at
            ),
            "expires_at": (
                None
                if self.expires_at is None
                else _iso(self.expires_at)
            ),
            "terms_reference_sha256": (
                self.terms_reference_sha256
            ),
            "manual_approval_id": (
                self.manual_approval_id
            ),
            "status": self.status,
            "automatic_rights_approval": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "manifest_fingerprint": (
                self.manifest_fingerprint
            ),
        }


@dataclass(frozen=True)
class ProviderUseRightsIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteProviderUseRightsRegistry:
    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._initialize()

    def _connect(
        self,
    ) -> sqlite3.Connection:
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
                    CHECK (
                        sport IN (
                            'football',
                            'tennis'
                        )
                    ),
                    CHECK (
                        status IN (
                            'APPROVED',
                            'REJECTED'
                        )
                    )
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
        if sport not in {
            "football",
            "tennis",
        }:
            raise ValueError("INVALID_SPORT")

        provider_key = _nonempty(
            "PROVIDER_KEY",
            provider_key,
        )
        manual_approval_id = _nonempty(
            "MANUAL_APPROVAL_ID",
            manual_approval_id,
        )
        effective_at = _aware(
            "EFFECTIVE_AT",
            effective_at,
        )

        if expires_at is not None:
            expires_at = _aware(
                "EXPIRES_AT",
                expires_at,
            )
            if expires_at <= effective_at:
                raise ValueError(
                    "INVALID_RIGHTS_EXPIRY"
                )

        terms_reference_sha256 = _hex64(
            "TERMS_REFERENCE_SHA256",
            terms_reference_sha256,
        )

        if status not in {
            "APPROVED",
            "REJECTED",
        }:
            raise ValueError(
                "INVALID_RIGHTS_STATUS"
            )

        data = _normalize_scope(
            "DATA_SCOPE",
            data_scope,
        )
        purposes = _normalize_scope(
            "ALLOWED_PURPOSES",
            allowed_purposes,
        )
        jurisdictions = _normalize_scope(
            "JURISDICTION_SCOPE",
            jurisdiction_scope,
        )

        base = {
            "schema": (
                "matrix.provider-use-rights-manifest/1"
            ),
            "sport": sport,
            "provider_key": provider_key,
            "data_scope": list(data),
            "allowed_purposes": list(
                purposes
            ),
            "jurisdiction_scope": list(
                jurisdictions
            ),
            "effective_at": _iso(
                effective_at
            ),
            "expires_at": (
                None
                if expires_at is None
                else _iso(expires_at)
            ),
            "terms_reference_sha256": (
                terms_reference_sha256
            ),
            "manual_approval_id": (
                manual_approval_id
            ),
            "status": status,
            "automatic_rights_approval": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }

        manifest_fingerprint = _sha(
            base
        )
        manifest_id = _sha(
            {
                "schema": (
                    "matrix.provider-use-rights-manifest-id/1"
                ),
                "manifest_fingerprint": (
                    manifest_fingerprint
                ),
            }
        )

        return ProviderUseRightsManifest(
            manifest_id=manifest_id,
            sport=sport,
            provider_key=provider_key,
            data_scope=data,
            allowed_purposes=purposes,
            jurisdiction_scope=(
                jurisdictions
            ),
            effective_at=effective_at,
            expires_at=expires_at,
            terms_reference_sha256=(
                terms_reference_sha256
            ),
            manual_approval_id=(
                manual_approval_id
            ),
            status=status,
            manifest_fingerprint=(
                manifest_fingerprint
            ),
        )

    @classmethod
    def _rederive(
        cls,
        payload: Mapping[str, Any],
    ) -> ProviderUseRightsManifest:
        return cls.build_manifest(
            sport=payload["sport"],
            provider_key=(
                payload["provider_key"]
            ),
            data_scope=payload["data_scope"],
            allowed_purposes=(
                payload["allowed_purposes"]
            ),
            jurisdiction_scope=(
                payload[
                    "jurisdiction_scope"
                ]
            ),
            effective_at=_parse_utc(
                "EFFECTIVE_AT",
                payload["effective_at"],
            ),
            expires_at=(
                None
                if payload["expires_at"]
                is None
                else _parse_utc(
                    "EXPIRES_AT",
                    payload["expires_at"],
                )
            ),
            terms_reference_sha256=(
                payload[
                    "terms_reference_sha256"
                ]
            ),
            manual_approval_id=(
                payload[
                    "manual_approval_id"
                ]
            ),
            status=payload["status"],
        )

    def register(
        self,
        manifest: ProviderUseRightsManifest,
    ) -> ProviderUseRightsManifest:
        expected = self.build_manifest(
            sport=manifest.sport,
            provider_key=(
                manifest.provider_key
            ),
            data_scope=(
                manifest.data_scope
            ),
            allowed_purposes=(
                manifest.allowed_purposes
            ),
            jurisdiction_scope=(
                manifest.jurisdiction_scope
            ),
            effective_at=(
                manifest.effective_at
            ),
            expires_at=manifest.expires_at,
            terms_reference_sha256=(
                manifest
                .terms_reference_sha256
            ),
            manual_approval_id=(
                manifest.manual_approval_id
            ),
            status=manifest.status,
        )

        if expected != manifest:
            raise ValueError(
                "PROVIDER_RIGHTS_DERIVATION_MISMATCH"
            )

        payload_json = _canonical_json(
            manifest.payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            existing = connection.execute(
                """
                SELECT
                    manifest_id,
                    payload_sha256
                FROM provider_use_rights
                WHERE manifest_fingerprint = ?
                """,
                (
                    manifest
                    .manifest_fingerprint,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    "ROLLBACK"
                )

                if (
                    str(existing[0])
                    == manifest.manifest_id
                    and str(existing[1])
                    == payload_sha
                ):
                    return manifest

                raise ValueError(
                    "PROVIDER_RIGHTS_MUTATION_VIOLATION"
                )

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
                    _iso(
                        manifest.effective_at
                    ),
                    (
                        None
                        if manifest.expires_at
                        is None
                        else _iso(
                            manifest.expires_at
                        )
                    ),
                    manifest
                    .manifest_fingerprint,
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
        fingerprint = _hex64(
            "MANIFEST_FINGERPRINT",
            fingerprint,
        )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    manifest_id,
                    sport,
                    provider_key,
                    status,
                    effective_at,
                    expires_at,
                    manifest_fingerprint,
                    payload_json,
                    payload_sha256
                FROM provider_use_rights
                WHERE manifest_fingerprint = ?
                """,
                (fingerprint,),
            ).fetchone()

        if row is None:
            return None

        (
            manifest_id,
            sport,
            provider_key,
            status,
            effective_at,
            expires_at,
            stored_fp,
            payload_json,
            stored_sha,
        ) = row

        payload = json.loads(
            payload_json
        )
        actual_sha = sha256(
            _canonical_json(
                payload
            ).encode("utf-8")
        ).hexdigest()

        if actual_sha != stored_sha:
            raise ValueError(
                "PROVIDER_RIGHTS_PAYLOAD_HASH_MISMATCH"
            )

        expected = self._rederive(
            payload
        )

        if (
            expected.manifest_id
            != manifest_id
            or expected
            .manifest_fingerprint
            != stored_fp
            or expected.payload()
            != payload
        ):
            raise ValueError(
                "PROVIDER_RIGHTS_REDERIVATION_MISMATCH"
            )

        db_pairs = {
            "sport": sport,
            "provider_key": provider_key,
            "status": status,
            "effective_at": effective_at,
            "expires_at": expires_at,
            "manifest_fingerprint": (
                stored_fp
            ),
        }

        for key, value in db_pairs.items():
            if payload.get(key) != value:
                raise ValueError(
                    "PROVIDER_RIGHTS_DB_PAYLOAD_MISMATCH"
                )

        return payload

    def authorize_use(
        self,
        *,
        manifest_fingerprint: str,
        sport: str,
        provider_key: str,
        requested_data_scope: Sequence[str],
        requested_purpose: str,
        requested_jurisdiction: str,
        as_of: datetime,
    ) -> Mapping[str, Any]:
        payload = self.get_by_fingerprint(
            manifest_fingerprint
        )

        if payload is None:
            raise ValueError(
                "MISSING_PROVIDER_USE_RIGHTS"
            )

        as_of = _aware(
            "AS_OF",
            as_of,
        )

        if payload["sport"] != sport:
            raise ValueError(
                "RIGHTS_SPORT_MISMATCH"
            )

        if (
            payload["provider_key"]
            != provider_key
        ):
            raise ValueError(
                "RIGHTS_PROVIDER_MISMATCH"
            )

        if (
            payload["status"]
            != "APPROVED"
        ):
            raise ValueError(
                "RIGHTS_NOT_APPROVED"
            )

        effective = _parse_utc(
            "EFFECTIVE_AT",
            payload["effective_at"],
        )

        if effective > as_of:
            raise ValueError(
                "RIGHTS_NOT_YET_EFFECTIVE"
            )

        if payload["expires_at"] is not None:
            expiry = _parse_utc(
                "EXPIRES_AT",
                payload["expires_at"],
            )
            if expiry <= as_of:
                raise ValueError(
                    "RIGHTS_EXPIRED"
                )

        requested_scope = _normalize_scope(
            "REQUESTED_DATA_SCOPE",
            requested_data_scope,
        )

        if not set(
            requested_scope
        ).issubset(
            set(payload["data_scope"])
        ):
            raise ValueError(
                "RIGHTS_DATA_SCOPE_NOT_ALLOWED"
            )

        requested_purpose = _nonempty(
            "REQUESTED_PURPOSE",
            requested_purpose,
        )
        if (
            requested_purpose
            not in payload[
                "allowed_purposes"
            ]
        ):
            raise ValueError(
                "RIGHTS_PURPOSE_NOT_ALLOWED"
            )

        requested_jurisdiction = (
            _nonempty(
                "REQUESTED_JURISDICTION",
                requested_jurisdiction,
            )
        )

        if (
            requested_jurisdiction
            not in payload[
                "jurisdiction_scope"
            ]
        ):
            raise ValueError(
                "RIGHTS_JURISDICTION_NOT_ALLOWED"
            )

        return payload

    def audit_integrity(
        self,
    ) -> ProviderUseRightsIntegrityReport:
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
                self.get_by_fingerprint(
                    fingerprint
                )
            except Exception as error:
                errors.append(
                    f"{type(error).__name__}:"
                    f"{fingerprint}"
                )

        return ProviderUseRightsIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
