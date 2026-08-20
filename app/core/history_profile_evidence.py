from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


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


@dataclass(frozen=True)
class HistoryProfileEvidence:
    evidence_id: str
    sport: str
    canonical_id: str
    profile_fingerprint: str


@dataclass(frozen=True)
class HistoryProfileIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteHistoryProfileEvidenceStore:
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
                CREATE TABLE IF NOT EXISTS history_profile_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    history_fingerprint TEXT NOT NULL,
                    profile_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )

    @staticmethod
    def _validate_profile(profile) -> Mapping[str, Any]:
        payload = dict(profile.payload())

        if payload.get("sport") not in {
            "football",
            "tennis",
        }:
            raise ValueError("INVALID_PROFILE_SPORT")

        if payload.get("sport") != profile.sport:
            raise ValueError("PROFILE_SPORT_MISMATCH")

        if (
            payload.get("canonical_id")
            != profile.canonical_id
        ):
            raise ValueError(
                "PROFILE_CANONICAL_ID_MISMATCH"
            )

        stored_fp = payload.get("profile_fingerprint")
        if stored_fp != profile.profile_fingerprint:
            raise ValueError(
                "PROFILE_FINGERPRINT_FIELD_MISMATCH"
            )

        base = dict(payload)
        base.pop("profile_fingerprint", None)

        expected_fp = _sha(base)
        if expected_fp != profile.profile_fingerprint:
            raise ValueError(
                "HISTORY_PROFILE_DERIVATION_MISMATCH"
            )

        if payload.get("point_in_time_enforced") is not True:
            raise ValueError("POINT_IN_TIME_NOT_ENFORCED")

        if payload.get("missing_is_zero") is not False:
            raise ValueError("MISSING_ZERO_ENABLED")

        if payload.get("name_join_used") is not False:
            raise ValueError("NAME_JOIN_USED")

        return payload

    def record_profile(
        self,
        profile,
    ) -> HistoryProfileEvidence:
        payload = self._validate_profile(profile)

        evidence_id = _sha(
            {
                "schema": "matrix.history-profile-evidence-id/1",
                "sport": profile.sport,
                "canonical_id": profile.canonical_id,
                "as_of": payload["as_of"],
                "history_fingerprint": (
                    payload["history_fingerprint"]
                ),
                "profile_fingerprint": (
                    profile.profile_fingerprint
                ),
            }
        )

        evidence_payload = dict(payload)
        evidence_payload["evidence_id"] = evidence_id
        evidence_payload["evidence_schema"] = (
            "matrix.history-profile-evidence/1"
        )

        payload_json = _canonical_json(evidence_payload)
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT evidence_id, payload_sha256
                FROM history_profile_evidence
                WHERE profile_fingerprint = ?
                """,
                (profile.profile_fingerprint,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1]) == payload_sha
                ):
                    return HistoryProfileEvidence(
                        evidence_id=evidence_id,
                        sport=profile.sport,
                        canonical_id=profile.canonical_id,
                        profile_fingerprint=(
                            profile.profile_fingerprint
                        ),
                    )

                raise ValueError(
                    "HISTORY_PROFILE_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO history_profile_evidence (
                        evidence_id,
                        sport,
                        canonical_id,
                        as_of,
                        history_fingerprint,
                        profile_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        profile.sport,
                        profile.canonical_id,
                        payload["as_of"],
                        payload["history_fingerprint"],
                        profile.profile_fingerprint,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "HISTORY_PROFILE_APPEND_ONLY_VIOLATION"
                ) from error

        return HistoryProfileEvidence(
            evidence_id=evidence_id,
            sport=profile.sport,
            canonical_id=profile.canonical_id,
            profile_fingerprint=profile.profile_fingerprint,
        )

    def get_by_profile_fingerprint(
        self,
        profile_fingerprint: str,
    ) -> Mapping[str, Any] | None:
        if (
            not isinstance(profile_fingerprint, str)
            or len(profile_fingerprint) != 64
        ):
            raise ValueError(
                "INVALID_PROFILE_FINGERPRINT"
            )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM history_profile_evidence
                WHERE profile_fingerprint = ?
                """,
                (profile_fingerprint,),
            ).fetchone()

        return None if row is None else json.loads(row[0])

    def audit_integrity(
        self,
    ) -> HistoryProfileIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    sport,
                    canonical_id,
                    as_of,
                    history_fingerprint,
                    profile_fingerprint,
                    payload_json,
                    payload_sha256
                FROM history_profile_evidence
                ORDER BY created_at, evidence_id
                """
            ).fetchall()

        for row in rows:
            (
                evidence_id,
                sport,
                canonical_id,
                as_of,
                history_fingerprint,
                profile_fingerprint,
                payload_json,
                stored_sha,
            ) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{profile_fingerprint}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:"
                    f"{profile_fingerprint}"
                )

            expected_pairs = {
                "evidence_id": evidence_id,
                "sport": sport,
                "canonical_id": canonical_id,
                "as_of": as_of,
                "history_fingerprint": (
                    history_fingerprint
                ),
                "profile_fingerprint": (
                    profile_fingerprint
                ),
                "point_in_time_enforced": True,
                "missing_is_zero": False,
                "name_join_used": False,
                "automatic_model_promotion": False,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }

            for key, expected in expected_pairs.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{profile_fingerprint}"
                    )

            expected_evidence_id = _sha(
                {
                    "schema": (
                        "matrix.history-profile-evidence-id/1"
                    ),
                    "sport": sport,
                    "canonical_id": canonical_id,
                    "as_of": as_of,
                    "history_fingerprint": (
                        history_fingerprint
                    ),
                    "profile_fingerprint": (
                        profile_fingerprint
                    ),
                }
            )

            if evidence_id != expected_evidence_id:
                errors.append(
                    f"EVIDENCE_ID_MISMATCH:"
                    f"{profile_fingerprint}"
                )

        return HistoryProfileIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
