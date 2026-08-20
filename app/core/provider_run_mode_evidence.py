from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"


def _sha(value: Any) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("NAIVE_DATETIME")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ProviderRunModeEvidence:
    evidence_id: str
    run_id: str
    sport: str
    provider_key: str
    mode: str
    preflight_decision_fingerprint: str
    first_authorized_at: datetime

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-run-mode-evidence/1",
            "evidence_id": self.evidence_id,
            "run_id": self.run_id,
            "sport": self.sport,
            "provider_key": self.provider_key,
            "mode": self.mode,
            "preflight_decision_fingerprint": self.preflight_decision_fingerprint,
            "first_authorized_at": self.first_authorized_at.isoformat(),
            "production_admissible": self.mode == "PRODUCTION",
            "retroactive_mode_change_allowed": False,
        }


class SQLiteProviderRunModeEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_run_mode_evidence (
                    run_id TEXT PRIMARY KEY,
                    evidence_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @staticmethod
    def _build(*, run_id: str, sport: str, provider_key: str, mode: str, preflight_decision_fingerprint: str, first_authorized_at: datetime) -> ProviderRunModeEvidence:
        first_authorized_at = _aware(first_authorized_at)
        if mode not in {"PRODUCTION", "BOOTSTRAP_PROBE"}:
            raise ValueError("INVALID_PROVIDER_MODE")
        base = {
            "schema": "matrix.provider-run-mode-evidence-id/1",
            "run_id": run_id,
            "sport": sport,
            "provider_key": provider_key,
            "mode": mode,
            "preflight_decision_fingerprint": preflight_decision_fingerprint,
            "first_authorized_at": first_authorized_at.isoformat(),
            "production_admissible": mode == "PRODUCTION",
            "retroactive_mode_change_allowed": False,
        }
        return ProviderRunModeEvidence(
            evidence_id=_sha(base),
            run_id=run_id,
            sport=sport,
            provider_key=provider_key,
            mode=mode,
            preflight_decision_fingerprint=preflight_decision_fingerprint,
            first_authorized_at=first_authorized_at,
        )

    def record(self, *, run_id: str, sport: str, provider_key: str, mode: str, preflight_decision_fingerprint: str, authorized_at: datetime) -> ProviderRunModeEvidence:
        existing = self.get_verified(run_id)
        if existing is not None:
            if (
                existing.sport != sport
                or existing.provider_key != provider_key
                or existing.mode != mode
                or existing.preflight_decision_fingerprint != preflight_decision_fingerprint
            ):
                raise ValueError("RUN_MODE_MUTATION_VIOLATION")
            return existing

        evidence = self._build(
            run_id=run_id,
            sport=sport,
            provider_key=provider_key,
            mode=mode,
            preflight_decision_fingerprint=preflight_decision_fingerprint,
            first_authorized_at=authorized_at,
        )
        payload_json = _json(evidence.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM provider_run_mode_evidence WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is not None:
                connection.execute("ROLLBACK")
                return self.record(
                    run_id=run_id,
                    sport=sport,
                    provider_key=provider_key,
                    mode=mode,
                    preflight_decision_fingerprint=preflight_decision_fingerprint,
                    authorized_at=authorized_at,
                )
            connection.execute(
                "INSERT INTO provider_run_mode_evidence (run_id, evidence_id, payload_json, payload_sha256) VALUES (?, ?, ?, ?)",
                (run_id, evidence.evidence_id, payload_json, payload_sha),
            )
            connection.execute("COMMIT")
        return evidence

    def get_verified(self, run_id: str) -> ProviderRunModeEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT evidence_id, payload_json, payload_sha256 FROM provider_run_mode_evidence WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None

        evidence_id, payload_json, payload_sha = row
        if sha256(payload_json.encode("utf-8")).hexdigest() != payload_sha:
            raise ValueError("RUN_MODE_EVIDENCE_INTEGRITY_FAILURE")
        payload = json.loads(payload_json)
        rebuilt = self._build(
            run_id=str(payload["run_id"]),
            sport=str(payload["sport"]),
            provider_key=str(payload["provider_key"]),
            mode=str(payload["mode"]),
            preflight_decision_fingerprint=str(payload["preflight_decision_fingerprint"]),
            first_authorized_at=datetime.fromisoformat(payload["first_authorized_at"]),
        )
        if rebuilt.evidence_id != evidence_id or payload.get("evidence_id") != evidence_id:
            raise ValueError("RUN_MODE_EVIDENCE_REDERIVATION_FAILURE")
        return rebuilt

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            run_ids = [str(row[0]) for row in connection.execute("SELECT run_id FROM provider_run_mode_evidence ORDER BY run_id").fetchall()]
        try:
            return all(self.get_verified(run_id) is not None for run_id in run_ids)
        except ValueError:
            return False
