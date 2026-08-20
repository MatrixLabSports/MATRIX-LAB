from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Mapping


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


def _aware_utc(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"INVALID_{name}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"INVALID_{name}")
    return value.astimezone(UTC)


def _parse_utc(name: str, value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"INVALID_{name}")
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return _aware_utc(name, parsed)


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
class OpponentQualityObservation:
    observation_id: str
    sport: str
    opponent_canonical_id: str
    quality_key: str
    quality_value: float
    observed_at: datetime
    available_at: datetime
    source_record_fingerprint: str
    quality_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.opponent-quality-observation/1",
            "observation_id": self.observation_id,
            "sport": self.sport,
            "opponent_canonical_id": self.opponent_canonical_id,
            "quality_key": self.quality_key,
            "quality_value": self.quality_value,
            "observed_at": _iso(self.observed_at),
            "available_at": _iso(self.available_at),
            "source_record_fingerprint": self.source_record_fingerprint,
            "quality_fingerprint": self.quality_fingerprint,
            "point_in_time_enforced": True,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class OpponentQualityIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteOpponentQualityLedger:
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
                CREATE TABLE IF NOT EXISTS opponent_quality_observations (
                    observation_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    opponent_canonical_id TEXT NOT NULL,
                    quality_key TEXT NOT NULL,
                    quality_value REAL NOT NULL,
                    observed_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    source_record_fingerprint TEXT NOT NULL,
                    quality_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_opponent_quality_as_of
                ON opponent_quality_observations (
                    sport,
                    opponent_canonical_id,
                    quality_key,
                    available_at
                )
                """
            )

    @staticmethod
    def build_observation(
        *,
        sport: str,
        opponent_canonical_id: str,
        quality_key: str,
        quality_value: float,
        observed_at: datetime,
        available_at: datetime,
        source_record_fingerprint: str,
    ) -> OpponentQualityObservation:
        if sport not in {"football", "tennis"}:
            raise ValueError("INVALID_SPORT")

        opponent_canonical_id = _nonempty(
            "OPPONENT_CANONICAL_ID",
            opponent_canonical_id,
        )
        quality_key = _nonempty("QUALITY_KEY", quality_key)

        if isinstance(quality_value, bool) or not isinstance(
            quality_value, (int, float)
        ):
            raise ValueError("INVALID_QUALITY_VALUE")

        quality_value = float(quality_value)
        if not math.isfinite(quality_value):
            raise ValueError("NONFINITE_QUALITY_VALUE")

        observed_at = _aware_utc("OBSERVED_AT", observed_at)
        available_at = _aware_utc("AVAILABLE_AT", available_at)

        if available_at < observed_at:
            raise ValueError("AVAILABLE_AT_BEFORE_OBSERVED_AT")

        source_record_fingerprint = _hex64(
            "SOURCE_RECORD_FINGERPRINT",
            source_record_fingerprint,
        )

        base = {
            "schema": "matrix.opponent-quality-observation/1",
            "sport": sport,
            "opponent_canonical_id": opponent_canonical_id,
            "quality_key": quality_key,
            "quality_value": quality_value,
            "observed_at": _iso(observed_at),
            "available_at": _iso(available_at),
            "source_record_fingerprint": source_record_fingerprint,
            "point_in_time_enforced": True,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }
        quality_fingerprint = _sha(base)
        observation_id = _sha(
            {
                "schema": "matrix.opponent-quality-observation-id/1",
                "quality_fingerprint": quality_fingerprint,
            }
        )

        return OpponentQualityObservation(
            observation_id=observation_id,
            sport=sport,
            opponent_canonical_id=opponent_canonical_id,
            quality_key=quality_key,
            quality_value=quality_value,
            observed_at=observed_at,
            available_at=available_at,
            source_record_fingerprint=source_record_fingerprint,
            quality_fingerprint=quality_fingerprint,
        )

    def append(
        self,
        observation: OpponentQualityObservation,
    ) -> OpponentQualityObservation:
        expected = self.build_observation(
            sport=observation.sport,
            opponent_canonical_id=observation.opponent_canonical_id,
            quality_key=observation.quality_key,
            quality_value=observation.quality_value,
            observed_at=observation.observed_at,
            available_at=observation.available_at,
            source_record_fingerprint=observation.source_record_fingerprint,
        )
        if expected != observation:
            raise ValueError("OPPONENT_QUALITY_DERIVATION_MISMATCH")

        payload_json = _canonical_json(observation.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT observation_id, payload_sha256
                FROM opponent_quality_observations
                WHERE quality_fingerprint = ?
                """,
                (observation.quality_fingerprint,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")
                if (
                    str(existing[0]) == observation.observation_id
                    and str(existing[1]) == payload_sha
                ):
                    return observation
                raise ValueError("OPPONENT_QUALITY_MUTATION_VIOLATION")

            try:
                connection.execute(
                    """
                    INSERT INTO opponent_quality_observations (
                        observation_id,
                        sport,
                        opponent_canonical_id,
                        quality_key,
                        quality_value,
                        observed_at,
                        available_at,
                        source_record_fingerprint,
                        quality_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation.observation_id,
                        observation.sport,
                        observation.opponent_canonical_id,
                        observation.quality_key,
                        observation.quality_value,
                        _iso(observation.observed_at),
                        _iso(observation.available_at),
                        observation.source_record_fingerprint,
                        observation.quality_fingerprint,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError("OPPONENT_QUALITY_APPEND_ONLY_VIOLATION") from error

        return observation

    def resolve_as_of(
        self,
        *,
        sport: str,
        opponent_canonical_id: str,
        quality_key: str,
        as_of: datetime,
    ) -> Mapping[str, Any] | None:
        if sport not in {"football", "tennis"}:
            raise ValueError("INVALID_SPORT")
        as_of = _aware_utc("AS_OF", as_of)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json, available_at
                FROM opponent_quality_observations
                WHERE
                    sport = ?
                    AND opponent_canonical_id = ?
                    AND quality_key = ?
                    AND available_at <= ?
                ORDER BY available_at DESC, quality_fingerprint ASC
                """,
                (
                    sport,
                    opponent_canonical_id,
                    quality_key,
                    _iso(as_of),
                ),
            ).fetchall()

        if not rows:
            return None

        latest_available_at = rows[0][1]
        latest = [
            json.loads(payload_json)
            for payload_json, available_at in rows
            if available_at == latest_available_at
        ]

        fingerprints = {
            item["quality_fingerprint"]
            for item in latest
        }
        if len(fingerprints) > 1:
            raise ValueError("AMBIGUOUS_OPPONENT_QUALITY_AS_OF")

        return latest[0]

    def audit_integrity(self) -> OpponentQualityIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    observation_id,
                    sport,
                    opponent_canonical_id,
                    quality_key,
                    quality_value,
                    observed_at,
                    available_at,
                    source_record_fingerprint,
                    quality_fingerprint,
                    payload_json,
                    payload_sha256
                FROM opponent_quality_observations
                ORDER BY created_at, observation_id
                """
            ).fetchall()

        for row in rows:
            (
                observation_id,
                sport,
                opponent_canonical_id,
                quality_key,
                quality_value,
                observed_at,
                available_at,
                source_record_fingerprint,
                quality_fingerprint,
                payload_json,
                stored_sha,
            ) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(f"INVALID_JSON:{observation_id}")
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()
            if actual_sha != stored_sha:
                errors.append(f"PAYLOAD_HASH_MISMATCH:{observation_id}")

            try:
                expected = self.build_observation(
                    sport=sport,
                    opponent_canonical_id=opponent_canonical_id,
                    quality_key=quality_key,
                    quality_value=quality_value,
                    observed_at=_parse_utc("OBSERVED_AT", observed_at),
                    available_at=_parse_utc("AVAILABLE_AT", available_at),
                    source_record_fingerprint=source_record_fingerprint,
                )
            except (ValueError, TypeError):
                errors.append(f"INVALID_FIELDS:{observation_id}")
                continue

            if expected.observation_id != observation_id:
                errors.append(f"OBSERVATION_ID_MISMATCH:{observation_id}")
            if expected.quality_fingerprint != quality_fingerprint:
                errors.append(f"QUALITY_FINGERPRINT_MISMATCH:{observation_id}")
            if expected.payload() != payload:
                errors.append(f"PAYLOAD_DERIVATION_MISMATCH:{observation_id}")

        return OpponentQualityIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
