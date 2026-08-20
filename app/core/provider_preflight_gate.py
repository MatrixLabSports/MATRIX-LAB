from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
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


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("INVALID_AS_OF")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("INVALID_AS_OF")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ProviderPreflightDecision:
    status: str
    executable: bool
    downstream_quarantine_required: bool
    run_id: str
    sport: str
    provider_key: str
    mode: str
    queue_fingerprint: str
    permit_id: str
    reason_codes: tuple[str, ...]
    decision_fingerprint: str


def authorize_and_consume_provider_preflight(
    *,
    run_id: str,
    sport: str,
    provider_key: str,
    mode: str,
    queue_fingerprint: str,
    permit_id: str,
    rights_manifest_fingerprint: str,
    rights_registry,
    provider_health_status: str,
    bootstrap_policy: object | None,
    permit_store,
    as_of: datetime,
) -> ProviderPreflightDecision:
    as_of = _aware(as_of)
    reasons: list[str] = []
    quarantine = mode == "BOOTSTRAP_PROBE"

    try:
        rights = rights_registry.get_by_fingerprint(
            rights_manifest_fingerprint
        )
    except ValueError as error:
        rights = None
        reasons.append(f"RIGHTS_INTEGRITY:{error}")

    if rights is None:
        reasons.append("MISSING_PROVIDER_USE_RIGHTS")
    else:
        if rights["sport"] != sport:
            reasons.append("RIGHTS_SPORT_MISMATCH")
        if rights["provider_key"] != provider_key:
            reasons.append("RIGHTS_PROVIDER_MISMATCH")
        if rights["status"] != "APPROVED":
            reasons.append("RIGHTS_NOT_APPROVED")

        effective = datetime.fromisoformat(
            rights["effective_at"].replace("Z", "+00:00")
        ).astimezone(UTC)
        if effective > as_of:
            reasons.append("RIGHTS_NOT_YET_EFFECTIVE")

        if rights["expires_at"] is not None:
            expiry = datetime.fromisoformat(
                rights["expires_at"].replace("Z", "+00:00")
            ).astimezone(UTC)
            if expiry <= as_of:
                reasons.append("RIGHTS_EXPIRED")

    if mode == "PRODUCTION":
        quarantine = False
        if provider_health_status != "ELIGIBLE":
            reasons.append("PRODUCTION_PROVIDER_NOT_ELIGIBLE")
        if bootstrap_policy is not None:
            reasons.append("BOOTSTRAP_POLICY_PRESENT_IN_PRODUCTION")

    elif mode == "BOOTSTRAP_PROBE":
        if bootstrap_policy is None:
            reasons.append("BOOTSTRAP_POLICY_REQUIRED")
        else:
            if bootstrap_policy.sport != sport:
                reasons.append("BOOTSTRAP_POLICY_SPORT_MISMATCH")
            if bootstrap_policy.provider_key != provider_key:
                reasons.append("BOOTSTRAP_POLICY_PROVIDER_MISMATCH")
            if bootstrap_policy.downstream_quarantine_required is not True:
                reasons.append("BOOTSTRAP_QUARANTINE_REQUIRED")
        if provider_health_status not in {"REVIEW_REQUIRED", "ELIGIBLE"}:
            reasons.append("BOOTSTRAP_PROVIDER_STATUS_NOT_ALLOWED")
    else:
        reasons.append("INVALID_PROVIDER_MODE")

    reasons = sorted(set(reasons))

    if reasons:
        status = "QUARANTINE"
        executable = False
    else:
        try:
            permit_store.consume(
                permit_id=permit_id,
                run_id=run_id,
                sport=sport,
                provider_key=provider_key,
                mode=mode,
                queue_fingerprint=queue_fingerprint,
            )
        except ValueError as error:
            reasons.append(f"PERMIT:{error}")
            status = "QUARANTINE"
            executable = False
        else:
            status = "EXECUTE"
            executable = True

    reasons = sorted(set(reasons))
    base = {
        "schema": "matrix.provider-preflight-decision/1",
        "status": status,
        "executable": executable,
        "downstream_quarantine_required": quarantine,
        "run_id": run_id,
        "sport": sport,
        "provider_key": provider_key,
        "mode": mode,
        "queue_fingerprint": queue_fingerprint,
        "permit_id": permit_id,
        "reason_codes": reasons,
        "authoritative_for_future_provider_calls": True,
        "automatic_provider_switch": False,
        "automatic_health_promotion": False,
        "automatic_wagering": False,
    }

    return ProviderPreflightDecision(
        status=status,
        executable=executable,
        downstream_quarantine_required=quarantine,
        run_id=run_id,
        sport=sport,
        provider_key=provider_key,
        mode=mode,
        queue_fingerprint=queue_fingerprint,
        permit_id=permit_id,
        reason_codes=tuple(reasons),
        decision_fingerprint=_sha(base),
    )


class SQLiteProviderPreflightEvidenceStore:
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
                CREATE TABLE IF NOT EXISTS provider_preflight_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    sport TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    decision_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )

    def record(
        self,
        decision: ProviderPreflightDecision,
    ) -> str:
        evidence_id = _sha(
            {
                "schema": "matrix.provider-preflight-evidence-id/1",
                "decision_fingerprint": decision.decision_fingerprint,
            }
        )
        payload = {
            "schema": "matrix.provider-preflight-evidence/1",
            "evidence_id": evidence_id,
            "status": decision.status,
            "executable": decision.executable,
            "downstream_quarantine_required": (
                decision.downstream_quarantine_required
            ),
            "run_id": decision.run_id,
            "sport": decision.sport,
            "provider_key": decision.provider_key,
            "mode": decision.mode,
            "queue_fingerprint": decision.queue_fingerprint,
            "permit_id": decision.permit_id,
            "reason_codes": list(decision.reason_codes),
            "decision_fingerprint": decision.decision_fingerprint,
            "authoritative_for_future_provider_calls": True,
            "automatic_provider_switch": False,
            "automatic_health_promotion": False,
            "automatic_wagering": False,
        }
        payload_json = _canonical_json(payload)
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT evidence_id, payload_sha256
                FROM provider_preflight_evidence
                WHERE run_id = ?
                """,
                (decision.run_id,),
            ).fetchone()
            if existing is not None:
                connection.execute("ROLLBACK")
                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1]) == payload_sha
                ):
                    return evidence_id
                raise ValueError("PROVIDER_PREFLIGHT_RUN_MUTATION_VIOLATION")

            connection.execute(
                """
                INSERT INTO provider_preflight_evidence (
                    evidence_id,
                    run_id,
                    sport,
                    provider_key,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    decision.run_id,
                    decision.sport,
                    decision.provider_key,
                    decision.decision_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")

        return evidence_id
