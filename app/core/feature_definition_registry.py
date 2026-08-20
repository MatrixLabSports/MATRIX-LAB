from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence


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

_ALLOWED_VALUE_TYPES = {
    "float",
    "int",
    "bool",
    "string",
    "category",
}

_FEATURE_NAME = re.compile(
    r"^[a-z][a-z0-9_.-]{2,127}$"
)
_VERSION = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
)


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


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    sport: str
    entity_type: str
    feature_name: str
    feature_version: str
    value_type: str
    nullable: bool
    source_schema_names: tuple[str, ...]
    definition_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.feature-definition/1",
            "feature_id": self.feature_id,
            "sport": self.sport,
            "entity_type": self.entity_type,
            "feature_name": self.feature_name,
            "feature_version": self.feature_version,
            "value_type": self.value_type,
            "nullable": self.nullable,
            "source_schema_names": list(
                self.source_schema_names
            ),
            "definition_fingerprint": (
                self.definition_fingerprint
            ),
            "point_in_time_required": True,
            "missing_is_zero": False,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class FeatureDefinitionIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteFeatureDefinitionRegistry:
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
                CREATE TABLE IF NOT EXISTS feature_definitions (
                    feature_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    feature_name TEXT NOT NULL,
                    feature_version TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    nullable INTEGER NOT NULL,
                    definition_fingerprint TEXT NOT NULL UNIQUE,
                    source_schema_names_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    UNIQUE (
                        sport,
                        entity_type,
                        feature_name,
                        feature_version
                    ),
                    CHECK (sport IN ('football', 'tennis')),
                    CHECK (nullable IN (0, 1))
                )
                """
            )

    @staticmethod
    def build_definition(
        *,
        sport: str,
        entity_type: str,
        feature_name: str,
        feature_version: str,
        value_type: str,
        nullable: bool,
        source_schema_names: Sequence[str],
    ) -> FeatureDefinition:
        sport = _validate_sport(sport)
        entity_type = _validate_entity_type(
            sport=sport,
            entity_type=entity_type,
        )

        if (
            not isinstance(feature_name, str)
            or not _FEATURE_NAME.fullmatch(feature_name)
        ):
            raise ValueError("INVALID_FEATURE_NAME")

        if (
            not isinstance(feature_version, str)
            or not _VERSION.fullmatch(feature_version)
        ):
            raise ValueError("INVALID_FEATURE_VERSION")

        if value_type not in _ALLOWED_VALUE_TYPES:
            raise ValueError("INVALID_FEATURE_VALUE_TYPE")

        if not isinstance(nullable, bool):
            raise ValueError("INVALID_NULLABLE")

        if (
            isinstance(source_schema_names, (str, bytes))
            or not isinstance(source_schema_names, Sequence)
        ):
            raise ValueError("INVALID_SOURCE_SCHEMAS")

        normalized = tuple(
            sorted(
                {
                    value.strip()
                    for value in source_schema_names
                    if isinstance(value, str)
                    and value.strip()
                }
            )
        )

        if not normalized:
            raise ValueError("EMPTY_SOURCE_SCHEMAS")

        base = {
            "schema": "matrix.feature-definition/1",
            "sport": sport,
            "entity_type": entity_type,
            "feature_name": feature_name,
            "feature_version": feature_version,
            "value_type": value_type,
            "nullable": nullable,
            "source_schema_names": list(normalized),
            "point_in_time_required": True,
            "missing_is_zero": False,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }

        definition_fingerprint = _sha(base)
        feature_id = (
            f"{sport}:{entity_type}:{feature_name}:"
            f"{feature_version}:"
            f"{definition_fingerprint[:16]}"
        )

        return FeatureDefinition(
            feature_id=feature_id,
            sport=sport,
            entity_type=entity_type,
            feature_name=feature_name,
            feature_version=feature_version,
            value_type=value_type,
            nullable=nullable,
            source_schema_names=normalized,
            definition_fingerprint=definition_fingerprint,
        )

    def register(
        self,
        definition: FeatureDefinition,
    ) -> FeatureDefinition:
        expected = self.build_definition(
            sport=definition.sport,
            entity_type=definition.entity_type,
            feature_name=definition.feature_name,
            feature_version=definition.feature_version,
            value_type=definition.value_type,
            nullable=definition.nullable,
            source_schema_names=(
                definition.source_schema_names
            ),
        )

        if expected != definition:
            raise ValueError(
                "FEATURE_DEFINITION_DERIVATION_MISMATCH"
            )

        payload_json = _canonical_json(
            definition.payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()
        source_json = _canonical_json(
            list(definition.source_schema_names)
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT
                    feature_id,
                    definition_fingerprint,
                    payload_sha256
                FROM feature_definitions
                WHERE
                    sport = ?
                    AND entity_type = ?
                    AND feature_name = ?
                    AND feature_version = ?
                """,
                (
                    definition.sport,
                    definition.entity_type,
                    definition.feature_name,
                    definition.feature_version,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == definition.feature_id
                    and str(existing[1])
                    == definition.definition_fingerprint
                    and str(existing[2]) == payload_sha
                ):
                    return definition

                raise ValueError(
                    "FEATURE_DEFINITION_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO feature_definitions (
                        feature_id,
                        sport,
                        entity_type,
                        feature_name,
                        feature_version,
                        value_type,
                        nullable,
                        definition_fingerprint,
                        source_schema_names_json,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        definition.feature_id,
                        definition.sport,
                        definition.entity_type,
                        definition.feature_name,
                        definition.feature_version,
                        definition.value_type,
                        int(definition.nullable),
                        definition.definition_fingerprint,
                        source_json,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "FEATURE_DEFINITION_APPEND_ONLY_VIOLATION"
                ) from error

        return definition

    def get_by_feature_id(
        self,
        feature_id: str,
    ) -> Mapping[str, Any] | None:
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError("INVALID_FEATURE_ID")

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM feature_definitions
                WHERE feature_id = ?
                """,
                (feature_id,),
            ).fetchone()

        return None if row is None else json.loads(row[0])

    def audit_integrity(
        self,
    ) -> FeatureDefinitionIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    feature_id,
                    payload_json,
                    payload_sha256
                FROM feature_definitions
                ORDER BY created_at, feature_id
                """
            ).fetchall()

        for feature_id, payload_json, stored_sha in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(f"INVALID_JSON:{feature_id}")
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:{feature_id}"
                )

            if payload.get("point_in_time_required") is not True:
                errors.append(
                    f"POINT_IN_TIME_DISABLED:{feature_id}"
                )

            if payload.get("missing_is_zero") is not False:
                errors.append(
                    f"MISSING_ZERO_ENABLED:{feature_id}"
                )

            if payload.get("name_join_used") is not False:
                errors.append(
                    f"NAME_JOIN_USED:{feature_id}"
                )

            if (
                payload.get("automatic_model_promotion")
                is not False
            ):
                errors.append(
                    f"AUTO_MODEL_PROMOTION_ENABLED:{feature_id}"
                )

        return FeatureDefinitionIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
