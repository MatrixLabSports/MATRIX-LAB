from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.application.football.live_snapshot import (
    FootballLivePressureFeatures,
    FootballLiveSnapshot,
)


def _canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class FootballLiveEvidence:
    evidence_id: str
    fixture_id: int
    captured_at: str
    snapshot: Mapping[str, Any]
    pressure_features: Mapping[str, Any]
    automatic_wagering: bool = False

    def payload(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "fixture_id": self.fixture_id,
            "captured_at": self.captured_at,
            "snapshot": dict(self.snapshot),
            "pressure_features": dict(
                self.pressure_features
            ),
            "automatic_wagering": False,
        }


class SQLiteFootballLiveEvidenceStore:
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
                CREATE TABLE IF NOT EXISTS
                football_live_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    fixture_id INTEGER NOT NULL,
                    captured_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )

    def record(
        self,
        *,
        snapshot: FootballLiveSnapshot,
        pressure_features: FootballLivePressureFeatures,
    ) -> FootballLiveEvidence:
        core = {
            "fixture_id": snapshot.fixture_id,
            "captured_at": (
                snapshot.captured_at.isoformat()
            ),
            "snapshot": snapshot.payload(),
            "pressure_features": (
                pressure_features.payload()
            ),
            "automatic_wagering": False,
        }
        evidence_id = _sha(
            {
                "schema": (
                    "matrix.football-private-live-evidence/1"
                ),
                "core": core,
            }
        )
        evidence = FootballLiveEvidence(
            evidence_id=evidence_id,
            **core,
        )
        payload_json = _canonical_json(
            evidence.payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM football_live_evidence
                WHERE evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO football_live_evidence
                    (
                        evidence_id,
                        fixture_id,
                        captured_at,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        evidence.fixture_id,
                        evidence.captured_at,
                        payload_json,
                        payload_sha,
                    ),
                )
            elif existing != (
                payload_json,
                payload_sha,
            ):
                raise ValueError(
                    "LIVE_EVIDENCE_ID_COLLISION"
                )

        stored = self.get_verified(
            evidence_id
        )
        if stored != evidence:
            raise ValueError(
                "LIVE_EVIDENCE_DURABLE_RECORD_MISMATCH"
            )
        return evidence

    def get_verified(
        self,
        evidence_id: str,
    ) -> FootballLiveEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM football_live_evidence
                WHERE evidence_id = ?
                """,
                (evidence_id,),
            ).fetchone()

        if row is None:
            return None

        payload_json, stored_sha = row
        actual_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()
        if actual_sha != stored_sha:
            raise ValueError(
                "LIVE_EVIDENCE_STORAGE_INTEGRITY_FAILURE"
            )

        payload = json.loads(payload_json)
        rebuilt = FootballLiveEvidence(
            evidence_id=str(
                payload["evidence_id"]
            ),
            fixture_id=int(
                payload["fixture_id"]
            ),
            captured_at=str(
                payload["captured_at"]
            ),
            snapshot=dict(
                payload["snapshot"]
            ),
            pressure_features=dict(
                payload["pressure_features"]
            ),
            automatic_wagering=bool(
                payload["automatic_wagering"]
            ),
        )
        if (
            rebuilt.evidence_id
            != evidence_id
            or rebuilt.automatic_wagering is not False
            or _sha(
                {
                    "schema": (
                        "matrix.football-private-live-evidence/1"
                    ),
                    "core": {
                        "fixture_id": rebuilt.fixture_id,
                        "captured_at": rebuilt.captured_at,
                        "snapshot": rebuilt.snapshot,
                        "pressure_features": (
                            rebuilt.pressure_features
                        ),
                        "automatic_wagering": False,
                    },
                }
            )
            != evidence_id
        ):
            raise ValueError(
                "LIVE_EVIDENCE_REDERIVATION_FAILURE"
            )
        return rebuilt

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            ids = [
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT evidence_id
                    FROM football_live_evidence
                    ORDER BY evidence_id
                    """
                ).fetchall()
            ]
        try:
            return all(
                self.get_verified(value)
                is not None
                for value in ids
            )
        except Exception:
            return False
