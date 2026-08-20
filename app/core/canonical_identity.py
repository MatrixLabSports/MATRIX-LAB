from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping


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

_CANONICAL_KEY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$"
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


def _sha256(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _validate_sport(sport: object) -> str:
    if not isinstance(sport, str) or sport not in _ALLOWED_ENTITY_TYPES:
        raise ValueError("INVALID_SPORT")
    return sport


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


def _validate_canonical_key(value: object) -> str:
    if (
        not isinstance(value, str)
        or not _CANONICAL_KEY_PATTERN.fullmatch(value)
    ):
        raise ValueError("INVALID_CANONICAL_KEY")
    return value


def _validate_display_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("INVALID_DISPLAY_NAME")
    return value.strip()


def make_canonical_id(
    *,
    sport: str,
    entity_type: str,
    canonical_key: str,
) -> str:
    sport = _validate_sport(sport)
    entity_type = _validate_entity_type(
        sport=sport,
        entity_type=entity_type,
    )
    canonical_key = _validate_canonical_key(canonical_key)

    digest = _sha256(
        {
            "schema": "matrix.canonical-identity/1",
            "sport": sport,
            "entity_type": entity_type,
            "canonical_key": canonical_key,
        }
    )

    return f"{sport}:{entity_type}:{digest}"


@dataclass(frozen=True)
class CanonicalEntity:
    canonical_id: str
    sport: str
    entity_type: str
    canonical_key: str
    display_name: str
    identity_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.canonical-entity/1",
            "canonical_id": self.canonical_id,
            "sport": self.sport,
            "entity_type": self.entity_type,
            "canonical_key": self.canonical_key,
            "display_name": self.display_name,
            "identity_fingerprint": self.identity_fingerprint,
            "name_join_allowed": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class CanonicalIdentityIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteCanonicalIdentityRegistry:
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
                CREATE TABLE IF NOT EXISTS canonical_entities (
                    canonical_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    canonical_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    identity_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    UNIQUE (sport, entity_type, canonical_key),
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )

    @staticmethod
    def build_entity(
        *,
        sport: str,
        entity_type: str,
        canonical_key: str,
        display_name: str,
    ) -> CanonicalEntity:
        sport = _validate_sport(sport)
        entity_type = _validate_entity_type(
            sport=sport,
            entity_type=entity_type,
        )
        canonical_key = _validate_canonical_key(canonical_key)
        display_name = _validate_display_name(display_name)

        canonical_id = make_canonical_id(
            sport=sport,
            entity_type=entity_type,
            canonical_key=canonical_key,
        )

        fingerprint_base = {
            "schema": "matrix.canonical-entity/1",
            "canonical_id": canonical_id,
            "sport": sport,
            "entity_type": entity_type,
            "canonical_key": canonical_key,
            "display_name": display_name,
            "name_join_allowed": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }

        return CanonicalEntity(
            canonical_id=canonical_id,
            sport=sport,
            entity_type=entity_type,
            canonical_key=canonical_key,
            display_name=display_name,
            identity_fingerprint=_sha256(fingerprint_base),
        )

    def register(
        self,
        entity: CanonicalEntity,
    ) -> CanonicalEntity:
        expected = self.build_entity(
            sport=entity.sport,
            entity_type=entity.entity_type,
            canonical_key=entity.canonical_key,
            display_name=entity.display_name,
        )

        if expected != entity:
            raise ValueError("CANONICAL_ENTITY_DERIVATION_MISMATCH")

        payload = dict(entity.payload())
        payload_json = _canonical_json(payload)
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT
                    canonical_id,
                    identity_fingerprint,
                    payload_sha256
                FROM canonical_entities
                WHERE
                    sport = ?
                    AND entity_type = ?
                    AND canonical_key = ?
                """,
                (
                    entity.sport,
                    entity.entity_type,
                    entity.canonical_key,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == entity.canonical_id
                    and str(existing[1])
                    == entity.identity_fingerprint
                    and str(existing[2]) == payload_sha
                ):
                    return entity

                raise ValueError(
                    "CANONICAL_IDENTITY_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO canonical_entities (
                        canonical_id,
                        sport,
                        entity_type,
                        canonical_key,
                        display_name,
                        identity_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity.canonical_id,
                        entity.sport,
                        entity.entity_type,
                        entity.canonical_key,
                        entity.display_name,
                        entity.identity_fingerprint,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "CANONICAL_IDENTITY_APPEND_ONLY_VIOLATION"
                ) from error

        return entity

    def get_by_canonical_id(
        self,
        canonical_id: str,
    ) -> Mapping[str, Any] | None:
        if not isinstance(canonical_id, str) or not canonical_id:
            raise ValueError("INVALID_CANONICAL_ID")

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM canonical_entities
                WHERE canonical_id = ?
                """,
                (canonical_id,),
            ).fetchone()

        if row is None:
            return None

        return json.loads(row[0])

    def get_by_key(
        self,
        *,
        sport: str,
        entity_type: str,
        canonical_key: str,
    ) -> Mapping[str, Any] | None:
        sport = _validate_sport(sport)
        entity_type = _validate_entity_type(
            sport=sport,
            entity_type=entity_type,
        )
        canonical_key = _validate_canonical_key(canonical_key)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM canonical_entities
                WHERE
                    sport = ?
                    AND entity_type = ?
                    AND canonical_key = ?
                """,
                (sport, entity_type, canonical_key),
            ).fetchone()

        if row is None:
            return None

        return json.loads(row[0])

    def audit_integrity(
        self,
    ) -> CanonicalIdentityIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    canonical_id,
                    sport,
                    entity_type,
                    canonical_key,
                    display_name,
                    identity_fingerprint,
                    payload_json,
                    payload_sha256
                FROM canonical_entities
                ORDER BY sport, entity_type, canonical_key
                """
            ).fetchall()

        for (
            canonical_id,
            sport,
            entity_type,
            canonical_key,
            display_name,
            identity_fingerprint,
            payload_json,
            payload_sha256,
        ) in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{canonical_id}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()

            if actual_sha != payload_sha256:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:{canonical_id}"
                )

            try:
                expected = self.build_entity(
                    sport=sport,
                    entity_type=entity_type,
                    canonical_key=canonical_key,
                    display_name=display_name,
                )
            except ValueError:
                errors.append(
                    f"INVALID_IDENTITY_FIELDS:{canonical_id}"
                )
                continue

            expected_fields = {
                "canonical_id": canonical_id,
                "sport": sport,
                "entity_type": entity_type,
                "canonical_key": canonical_key,
                "display_name": display_name,
                "identity_fingerprint": identity_fingerprint,
                "name_join_allowed": False,
                "automatic_model_promotion": False,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }

            for key, expected_value in expected_fields.items():
                if payload.get(key) != expected_value:
                    errors.append(
                        f"{key.upper()}_MISMATCH:{canonical_id}"
                    )

            if expected.canonical_id != canonical_id:
                errors.append(
                    f"CANONICAL_ID_MISMATCH:{canonical_id}"
                )

            if (
                expected.identity_fingerprint
                != identity_fingerprint
            ):
                errors.append(
                    f"IDENTITY_FINGERPRINT_MISMATCH:{canonical_id}"
                )

        return CanonicalIdentityIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
