from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)


UTC = timezone.utc

_ALLOWED_ENTITY_TYPES = {
    "football": {
        "team",
        "player",
        "competition",
        "season",
        "match",
    },
    "tennis": {
        "player",
        "competition",
        "season",
        "match",
    },
}

_ALLOWED_RESOLUTION_METHODS = {
    "provider_stable_id",
    "official_crosswalk",
    "manual_verified",
    "contractual_crosswalk",
}

_FORBIDDEN_NAME_METHODS = {
    "name",
    "exact_name",
    "normalized_name",
    "fuzzy_name",
}


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


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _validate_sport(value: object) -> str:
    if (
        not isinstance(value, str)
        or value not in _ALLOWED_ENTITY_TYPES
    ):
        raise ValueError("INVALID_SPORT")
    return value


def _validate_entity_type(
    *,
    sport: str,
    entity_type: object,
) -> str:
    if (
        not isinstance(entity_type, str)
        or entity_type not in _ALLOWED_ENTITY_TYPES[sport]
    ):
        raise ValueError("INVALID_ENTITY_TYPE_FOR_SPORT")
    return entity_type


def _require_nonempty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_{name}")
    return value.strip()


def _aware_utc(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"INVALID_{name}")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"INVALID_{name}")

    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class ProviderIdentityMapping:
    mapping_id: str
    sport: str
    entity_type: str
    provider_key: str
    provider_entity_id: str
    canonical_id: str
    resolution_method: str
    observed_at: datetime
    available_at: datetime
    mapping_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-identity-mapping/1",
            "mapping_id": self.mapping_id,
            "sport": self.sport,
            "entity_type": self.entity_type,
            "provider_key": self.provider_key,
            "provider_entity_id": self.provider_entity_id,
            "canonical_id": self.canonical_id,
            "resolution_method": self.resolution_method,
            "observed_at": _iso(self.observed_at),
            "available_at": _iso(self.available_at),
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "mapping_fingerprint": self.mapping_fingerprint,
        }


@dataclass(frozen=True)
class ProviderIdentityMappingIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteProviderIdentityMappingLedger:
    def __init__(
        self,
        path: str | Path,
        *,
        identity_registry: SQLiteCanonicalIdentityRegistry,
    ) -> None:
        self.path = Path(path)
        self.identity_registry = identity_registry
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
                CREATE TABLE IF NOT EXISTS provider_identity_mappings (
                    mapping_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    provider_entity_id TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    resolution_method TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    mapping_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )

    def build_mapping(
        self,
        *,
        sport: str,
        entity_type: str,
        provider_key: str,
        provider_entity_id: str,
        canonical_id: str,
        resolution_method: str,
        observed_at: datetime,
        available_at: datetime,
    ) -> ProviderIdentityMapping:
        sport = _validate_sport(sport)
        entity_type = _validate_entity_type(
            sport=sport,
            entity_type=entity_type,
        )
        provider_key = _require_nonempty(
            "PROVIDER_KEY",
            provider_key,
        )
        provider_entity_id = _require_nonempty(
            "PROVIDER_ENTITY_ID",
            provider_entity_id,
        )
        canonical_id = _require_nonempty(
            "CANONICAL_ID",
            canonical_id,
        )

        if resolution_method in _FORBIDDEN_NAME_METHODS:
            raise ValueError(
                "NAME_BASED_IDENTITY_RESOLUTION_FORBIDDEN"
            )

        if resolution_method not in _ALLOWED_RESOLUTION_METHODS:
            raise ValueError("INVALID_RESOLUTION_METHOD")

        observed_at = _aware_utc(
            "OBSERVED_AT",
            observed_at,
        )
        available_at = _aware_utc(
            "AVAILABLE_AT",
            available_at,
        )

        if available_at < observed_at:
            raise ValueError(
                "AVAILABLE_AT_BEFORE_OBSERVED_AT"
            )

        canonical = self.identity_registry.get_by_canonical_id(
            canonical_id
        )
        if canonical is None:
            raise ValueError("CANONICAL_ENTITY_NOT_FOUND")

        if canonical.get("sport") != sport:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")

        if canonical.get("entity_type") != entity_type:
            raise ValueError("ENTITY_TYPE_MISMATCH")

        base = {
            "schema": "matrix.provider-identity-mapping/1",
            "sport": sport,
            "entity_type": entity_type,
            "provider_key": provider_key,
            "provider_entity_id": provider_entity_id,
            "canonical_id": canonical_id,
            "resolution_method": resolution_method,
            "observed_at": _iso(observed_at),
            "available_at": _iso(available_at),
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }

        mapping_fingerprint = _sha(base)
        mapping_id = _sha(
            {
                "schema": (
                    "matrix.provider-identity-mapping-id/1"
                ),
                "mapping_fingerprint": mapping_fingerprint,
            }
        )

        return ProviderIdentityMapping(
            mapping_id=mapping_id,
            sport=sport,
            entity_type=entity_type,
            provider_key=provider_key,
            provider_entity_id=provider_entity_id,
            canonical_id=canonical_id,
            resolution_method=resolution_method,
            observed_at=observed_at,
            available_at=available_at,
            mapping_fingerprint=mapping_fingerprint,
        )

    def append(
        self,
        mapping: ProviderIdentityMapping,
    ) -> ProviderIdentityMapping:
        expected = self.build_mapping(
            sport=mapping.sport,
            entity_type=mapping.entity_type,
            provider_key=mapping.provider_key,
            provider_entity_id=mapping.provider_entity_id,
            canonical_id=mapping.canonical_id,
            resolution_method=mapping.resolution_method,
            observed_at=mapping.observed_at,
            available_at=mapping.available_at,
        )

        if expected != mapping:
            raise ValueError(
                "PROVIDER_MAPPING_DERIVATION_MISMATCH"
            )

        payload_json = _canonical_json(mapping.payload())
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT payload_sha256
                FROM provider_identity_mappings
                WHERE mapping_fingerprint = ?
                """,
                (mapping.mapping_fingerprint,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if str(existing[0]) == payload_sha:
                    return mapping

                raise ValueError(
                    "PROVIDER_MAPPING_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO provider_identity_mappings (
                        mapping_id,
                        sport,
                        entity_type,
                        provider_key,
                        provider_entity_id,
                        canonical_id,
                        resolution_method,
                        observed_at,
                        available_at,
                        mapping_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mapping.mapping_id,
                        mapping.sport,
                        mapping.entity_type,
                        mapping.provider_key,
                        mapping.provider_entity_id,
                        mapping.canonical_id,
                        mapping.resolution_method,
                        _iso(mapping.observed_at),
                        _iso(mapping.available_at),
                        mapping.mapping_fingerprint,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "PROVIDER_MAPPING_APPEND_ONLY_VIOLATION"
                ) from error

        return mapping

    def resolve_as_of(
        self,
        *,
        sport: str,
        entity_type: str,
        provider_key: str,
        provider_entity_id: str,
        as_of: datetime,
    ) -> Mapping[str, Any] | None:
        sport = _validate_sport(sport)
        entity_type = _validate_entity_type(
            sport=sport,
            entity_type=entity_type,
        )
        provider_key = _require_nonempty(
            "PROVIDER_KEY",
            provider_key,
        )
        provider_entity_id = _require_nonempty(
            "PROVIDER_ENTITY_ID",
            provider_entity_id,
        )
        as_of = _aware_utc("AS_OF", as_of)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json, available_at
                FROM provider_identity_mappings
                WHERE
                    sport = ?
                    AND entity_type = ?
                    AND provider_key = ?
                    AND provider_entity_id = ?
                    AND available_at <= ?
                ORDER BY available_at DESC, mapping_id ASC
                """,
                (
                    sport,
                    entity_type,
                    provider_key,
                    provider_entity_id,
                    _iso(as_of),
                ),
            ).fetchall()

        if not rows:
            return None

        latest_available_at = rows[0][1]
        latest_payloads = [
            json.loads(payload_json)
            for payload_json, available_at in rows
            if available_at == latest_available_at
        ]

        canonical_ids = {
            payload["canonical_id"]
            for payload in latest_payloads
        }

        if len(canonical_ids) != 1:
            raise ValueError(
                "AMBIGUOUS_PROVIDER_MAPPING_AS_OF"
            )

        return latest_payloads[0]

    def audit_integrity(
        self,
    ) -> ProviderIdentityMappingIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    mapping_id,
                    sport,
                    entity_type,
                    provider_key,
                    provider_entity_id,
                    canonical_id,
                    resolution_method,
                    observed_at,
                    available_at,
                    mapping_fingerprint,
                    payload_json,
                    payload_sha256
                FROM provider_identity_mappings
                ORDER BY created_at, mapping_id
                """
            ).fetchall()

        for row in rows:
            (
                mapping_id,
                sport,
                entity_type,
                provider_key,
                provider_entity_id,
                canonical_id,
                resolution_method,
                observed_at,
                available_at,
                mapping_fingerprint,
                payload_json,
                stored_sha,
            ) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(f"INVALID_JSON:{mapping_id}")
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:{mapping_id}"
                )

            try:
                expected = self.build_mapping(
                    sport=sport,
                    entity_type=entity_type,
                    provider_key=provider_key,
                    provider_entity_id=provider_entity_id,
                    canonical_id=canonical_id,
                    resolution_method=resolution_method,
                    observed_at=datetime.fromisoformat(
                        observed_at.replace("Z", "+00:00")
                    ),
                    available_at=datetime.fromisoformat(
                        available_at.replace("Z", "+00:00")
                    ),
                )
            except (ValueError, TypeError):
                errors.append(
                    f"INVALID_MAPPING_FIELDS:{mapping_id}"
                )
                continue

            if expected.mapping_id != mapping_id:
                errors.append(
                    f"MAPPING_ID_MISMATCH:{mapping_id}"
                )

            if (
                expected.mapping_fingerprint
                != mapping_fingerprint
            ):
                errors.append(
                    f"MAPPING_FINGERPRINT_MISMATCH:{mapping_id}"
                )

            if (
                payload.get("mapping_fingerprint")
                != mapping_fingerprint
            ):
                errors.append(
                    f"PAYLOAD_FINGERPRINT_MISMATCH:{mapping_id}"
                )

            if payload.get("name_join_used") is not False:
                errors.append(
                    f"NAME_JOIN_USED:{mapping_id}"
                )

            if (
                payload.get("resolution_method")
                in _FORBIDDEN_NAME_METHODS
            ):
                errors.append(
                    f"NAME_METHOD_PERSISTED:{mapping_id}"
                )

            if payload.get("automatic_provider_switch") is not False:
                errors.append(
                    f"AUTO_SWITCH_ENABLED:{mapping_id}"
                )

            if payload.get("automatic_wagering") is not False:
                errors.append(
                    f"AUTO_WAGERING_ENABLED:{mapping_id}"
                )

        return ProviderIdentityMappingIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
