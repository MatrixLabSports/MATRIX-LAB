from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


UTC = timezone.utc
_ALLOWED_TYPES = {
    "string",
    "integer",
    "float",
    "number",
    "boolean",
    "object",
    "array",
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


def _aware(name: str, value: object) -> datetime:
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


def _nonempty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_{name}")
    return value.strip()


@dataclass(frozen=True)
class RawSchemaField:
    name: str
    value_type: str
    required: bool
    nullable: bool

    def payload(self) -> Mapping[str, Any]:
        return {
            "name": self.name,
            "value_type": self.value_type,
            "required": self.required,
            "nullable": self.nullable,
        }


@dataclass(frozen=True)
class RawSchemaContract:
    schema_id: str
    sport: str
    entity_type: str
    schema_name: str
    schema_version: str
    available_at: datetime
    fields: tuple[RawSchemaField, ...]
    allow_additional_fields: bool
    schema_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.raw-schema-contract/1",
            "schema_id": self.schema_id,
            "sport": self.sport,
            "entity_type": self.entity_type,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "available_at": _iso(self.available_at),
            "fields": [
                field.payload()
                for field in self.fields
            ],
            "allow_additional_fields": (
                self.allow_additional_fields
            ),
            "schema_fingerprint": (
                self.schema_fingerprint
            ),
            "missing_is_zero": False,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class RawSchemaIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteRawSchemaRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
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
                CREATE TABLE IF NOT EXISTS raw_schema_contracts (
                    schema_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    schema_name TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    schema_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    UNIQUE (
                        sport,
                        entity_type,
                        schema_name,
                        schema_version
                    ),
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )

    @staticmethod
    def build_contract(
        *,
        sport: str,
        entity_type: str,
        schema_name: str,
        schema_version: str,
        available_at: datetime,
        fields: Sequence[RawSchemaField],
        allow_additional_fields: bool = False,
    ) -> RawSchemaContract:
        if sport not in {"football", "tennis"}:
            raise ValueError("INVALID_SPORT")

        entity_type = _nonempty(
            "ENTITY_TYPE",
            entity_type,
        )
        schema_name = _nonempty(
            "SCHEMA_NAME",
            schema_name,
        )
        schema_version = _nonempty(
            "SCHEMA_VERSION",
            schema_version,
        )
        available_at = _aware(
            "AVAILABLE_AT",
            available_at,
        )

        if not isinstance(
            allow_additional_fields,
            bool,
        ):
            raise ValueError(
                "INVALID_ADDITIONAL_FIELDS_POLICY"
            )

        if (
            isinstance(fields, (str, bytes))
            or not isinstance(fields, Sequence)
            or not fields
        ):
            raise ValueError(
                "EMPTY_SCHEMA_FIELDS"
            )

        normalized: list[RawSchemaField] = []
        names: set[str] = set()

        for field in fields:
            if not isinstance(
                field,
                RawSchemaField,
            ):
                raise ValueError(
                    "INVALID_SCHEMA_FIELD"
                )

            name = _nonempty(
                "FIELD_NAME",
                field.name,
            )

            if name in names:
                raise ValueError(
                    "DUPLICATE_SCHEMA_FIELD"
                )
            names.add(name)

            if field.value_type not in _ALLOWED_TYPES:
                raise ValueError(
                    "INVALID_SCHEMA_FIELD_TYPE"
                )

            if not isinstance(
                field.required,
                bool,
            ):
                raise ValueError(
                    "INVALID_REQUIRED_FLAG"
                )

            if not isinstance(
                field.nullable,
                bool,
            ):
                raise ValueError(
                    "INVALID_NULLABLE_FLAG"
                )

            normalized.append(
                RawSchemaField(
                    name=name,
                    value_type=field.value_type,
                    required=field.required,
                    nullable=field.nullable,
                )
            )

        normalized = sorted(
            normalized,
            key=lambda item: item.name,
        )

        base = {
            "schema": "matrix.raw-schema-contract/1",
            "sport": sport,
            "entity_type": entity_type,
            "schema_name": schema_name,
            "schema_version": schema_version,
            "available_at": _iso(available_at),
            "fields": [
                field.payload()
                for field in normalized
            ],
            "allow_additional_fields": (
                allow_additional_fields
            ),
            "missing_is_zero": False,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }

        schema_fingerprint = _sha(base)
        schema_id = _sha(
            {
                "schema": (
                    "matrix.raw-schema-contract-id/1"
                ),
                "sport": sport,
                "entity_type": entity_type,
                "schema_name": schema_name,
                "schema_version": schema_version,
                "schema_fingerprint": (
                    schema_fingerprint
                ),
            }
        )

        return RawSchemaContract(
            schema_id=schema_id,
            sport=sport,
            entity_type=entity_type,
            schema_name=schema_name,
            schema_version=schema_version,
            available_at=available_at,
            fields=tuple(normalized),
            allow_additional_fields=(
                allow_additional_fields
            ),
            schema_fingerprint=(
                schema_fingerprint
            ),
        )

    def register(
        self,
        contract: RawSchemaContract,
    ) -> RawSchemaContract:
        expected = self.build_contract(
            sport=contract.sport,
            entity_type=contract.entity_type,
            schema_name=contract.schema_name,
            schema_version=contract.schema_version,
            available_at=contract.available_at,
            fields=contract.fields,
            allow_additional_fields=(
                contract.allow_additional_fields
            ),
        )

        if expected != contract:
            raise ValueError(
                "RAW_SCHEMA_DERIVATION_MISMATCH"
            )

        payload_json = _canonical_json(
            contract.payload()
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
                    schema_id,
                    schema_fingerprint,
                    payload_sha256
                FROM raw_schema_contracts
                WHERE
                    sport = ?
                    AND entity_type = ?
                    AND schema_name = ?
                    AND schema_version = ?
                """,
                (
                    contract.sport,
                    contract.entity_type,
                    contract.schema_name,
                    contract.schema_version,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0])
                    == contract.schema_id
                    and str(existing[1])
                    == contract.schema_fingerprint
                    and str(existing[2])
                    == payload_sha
                ):
                    return contract

                raise ValueError(
                    "RAW_SCHEMA_VERSION_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO raw_schema_contracts (
                        schema_id,
                        sport,
                        entity_type,
                        schema_name,
                        schema_version,
                        available_at,
                        schema_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contract.schema_id,
                        contract.sport,
                        contract.entity_type,
                        contract.schema_name,
                        contract.schema_version,
                        _iso(contract.available_at),
                        contract.schema_fingerprint,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "RAW_SCHEMA_APPEND_ONLY_VIOLATION"
                ) from error

        return contract

    def get_exact(
        self,
        *,
        sport: str,
        entity_type: str,
        schema_name: str,
        schema_version: str,
    ) -> Mapping[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM raw_schema_contracts
                WHERE
                    sport = ?
                    AND entity_type = ?
                    AND schema_name = ?
                    AND schema_version = ?
                """,
                (
                    sport,
                    entity_type,
                    schema_name,
                    schema_version,
                ),
            ).fetchone()

        return (
            None
            if row is None
            else json.loads(row[0])
        )

    def audit_integrity(
        self,
    ) -> RawSchemaIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    schema_id,
                    sport,
                    entity_type,
                    schema_name,
                    schema_version,
                    available_at,
                    schema_fingerprint,
                    payload_json,
                    payload_sha256
                FROM raw_schema_contracts
                ORDER BY created_at, schema_id
                """
            ).fetchall()

        for row in rows:
            (
                schema_id,
                sport,
                entity_type,
                schema_name,
                schema_version,
                available_at,
                schema_fingerprint,
                payload_json,
                stored_sha,
            ) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{schema_id}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(
                    payload
                ).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:"
                    f"{schema_id}"
                )

            for key, expected in {
                "schema_id": schema_id,
                "sport": sport,
                "entity_type": entity_type,
                "schema_name": schema_name,
                "schema_version": schema_version,
                "available_at": available_at,
                "schema_fingerprint": (
                    schema_fingerprint
                ),
                "missing_is_zero": False,
                "name_join_used": False,
                "automatic_model_promotion": False,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{schema_id}"
                    )

        return RawSchemaIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
