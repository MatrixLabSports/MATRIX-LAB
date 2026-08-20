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


def _aware(
    value: datetime,
) -> datetime:
    if (
        not isinstance(
            value,
            datetime,
        )
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            "INVALID_AS_OF"
        )
    return value.astimezone(
        UTC
    )


def _decision_fingerprint(
    *,
    status: str,
    executable: bool,
    downstream_quarantine_required: bool,
    run_id: str,
    sport: str,
    provider_key: str,
    mode: str,
    queue_fingerprint: str,
    permit_id: str,
    rights_manifest_fingerprint: str,
    scheduling_evidence_fingerprint: str,
    bootstrap_policy_fingerprint: str | None,
    requested_data_scope: Sequence[str],
    requested_purpose: str,
    requested_jurisdiction: str,
    max_items: int,
    max_requests: int,
    provider_health_status: str,
    reason_codes: Sequence[str],
) -> str:
    return _sha(
        {
            "schema": (
                "matrix.provider-preflight-decision/2"
            ),
            "status": status,
            "executable": executable,
            "downstream_quarantine_required": (
                downstream_quarantine_required
            ),
            "run_id": run_id,
            "sport": sport,
            "provider_key": provider_key,
            "mode": mode,
            "queue_fingerprint": (
                queue_fingerprint
            ),
            "permit_id": permit_id,
            "rights_manifest_fingerprint": (
                rights_manifest_fingerprint
            ),
            "scheduling_evidence_fingerprint": (
                scheduling_evidence_fingerprint
            ),
            "bootstrap_policy_fingerprint": (
                bootstrap_policy_fingerprint
            ),
            "requested_data_scope": sorted(
                requested_data_scope
            ),
            "requested_purpose": (
                requested_purpose
            ),
            "requested_jurisdiction": (
                requested_jurisdiction
            ),
            "max_items": max_items,
            "max_requests": max_requests,
            "provider_health_status": (
                provider_health_status
            ),
            "reason_codes": sorted(
                reason_codes
            ),
            "authoritative_for_future_provider_calls": True,
            "automatic_provider_switch": False,
            "automatic_health_promotion": False,
            "automatic_wagering": False,
        }
    )


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
    rights_manifest_fingerprint: str
    scheduling_evidence_fingerprint: str
    bootstrap_policy_fingerprint: str | None
    requested_data_scope: tuple[str, ...]
    requested_purpose: str
    requested_jurisdiction: str
    max_items: int
    max_requests: int
    provider_health_status: str
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
    scheduling_evidence_fingerprint: str,
    requested_data_scope: Sequence[str],
    requested_purpose: str,
    requested_jurisdiction: str,
    max_items: int,
    max_requests: int,
    rights_registry,
    provider_health_status: str,
    bootstrap_policy_fingerprint: str | None,
    bootstrap_policy_registry,
    permit_store,
    as_of: datetime,
) -> ProviderPreflightDecision:
    as_of = _aware(
        as_of
    )

    reasons: list[str] = []
    quarantine = (
        mode
        == "BOOTSTRAP_PROBE"
    )

    requested_scope = tuple(
        sorted(
            set(
                requested_data_scope
            )
        )
    )

    try:
        rights_registry.authorize_use(
            manifest_fingerprint=(
                rights_manifest_fingerprint
            ),
            sport=sport,
            provider_key=provider_key,
            requested_data_scope=(
                requested_scope
            ),
            requested_purpose=(
                requested_purpose
            ),
            requested_jurisdiction=(
                requested_jurisdiction
            ),
            as_of=as_of,
        )
    except ValueError as error:
        reasons.append(
            f"RIGHTS:{error}"
        )

    policy = None

    if mode == "PRODUCTION":
        quarantine = False

        if (
            provider_health_status
            != "ELIGIBLE"
        ):
            reasons.append(
                "PRODUCTION_PROVIDER_NOT_ELIGIBLE"
            )

        if (
            bootstrap_policy_fingerprint
            is not None
        ):
            reasons.append(
                "BOOTSTRAP_POLICY_PRESENT_IN_PRODUCTION"
            )

    elif mode == "BOOTSTRAP_PROBE":
        if (
            bootstrap_policy_fingerprint
            is None
        ):
            reasons.append(
                "BOOTSTRAP_POLICY_REQUIRED"
            )
        else:
            try:
                policy = (
                    bootstrap_policy_registry
                    .get_by_fingerprint(
                        bootstrap_policy_fingerprint
                    )
                )
            except ValueError as error:
                reasons.append(
                    f"BOOTSTRAP_POLICY_INTEGRITY:{error}"
                )

            if policy is None:
                reasons.append(
                    "UNREGISTERED_BOOTSTRAP_POLICY"
                )
            else:
                if (
                    policy["sport"]
                    != sport
                ):
                    reasons.append(
                        "BOOTSTRAP_POLICY_SPORT_MISMATCH"
                    )

                if (
                    policy[
                        "provider_key"
                    ]
                    != provider_key
                ):
                    reasons.append(
                        "BOOTSTRAP_POLICY_PROVIDER_MISMATCH"
                    )

                if (
                    policy[
                        "downstream_quarantine_required"
                    ]
                    is not True
                ):
                    reasons.append(
                        "BOOTSTRAP_QUARANTINE_REQUIRED"
                    )

                if (
                    max_items
                    > policy[
                        "max_items"
                    ]
                ):
                    reasons.append(
                        "BOOTSTRAP_ITEMS_EXCEED_POLICY"
                    )

                if (
                    max_requests
                    > policy[
                        "max_requests"
                    ]
                ):
                    reasons.append(
                        "BOOTSTRAP_REQUESTS_EXCEED_POLICY"
                    )

        if (
            provider_health_status
            not in {
                "REVIEW_REQUIRED",
                "ELIGIBLE",
            }
        ):
            reasons.append(
                "BOOTSTRAP_PROVIDER_STATUS_NOT_ALLOWED"
            )

    else:
        reasons.append(
            "INVALID_PROVIDER_MODE"
        )

    reasons = sorted(
        set(reasons)
    )

    if reasons:
        status = "QUARANTINE"
        executable = False

    else:
        try:
            permit_store.consume(
                permit_id=permit_id,
                run_id=run_id,
                sport=sport,
                provider_key=(
                    provider_key
                ),
                mode=mode,
                queue_fingerprint=(
                    queue_fingerprint
                ),
                scheduling_evidence_fingerprint=(
                    scheduling_evidence_fingerprint
                ),
                rights_manifest_fingerprint=(
                    rights_manifest_fingerprint
                ),
                bootstrap_policy_fingerprint=(
                    bootstrap_policy_fingerprint
                ),
                max_items=max_items,
                max_requests=(
                    max_requests
                ),
            )
        except ValueError as error:
            reasons.append(
                f"PERMIT:{error}"
            )
            status = (
                "QUARANTINE"
            )
            executable = False
        else:
            status = "EXECUTE"
            executable = True

    reasons = sorted(
        set(reasons)
    )

    decision_fp = _decision_fingerprint(
        status=status,
        executable=executable,
        downstream_quarantine_required=(
            quarantine
        ),
        run_id=run_id,
        sport=sport,
        provider_key=provider_key,
        mode=mode,
        queue_fingerprint=(
            queue_fingerprint
        ),
        permit_id=permit_id,
        rights_manifest_fingerprint=(
            rights_manifest_fingerprint
        ),
        scheduling_evidence_fingerprint=(
            scheduling_evidence_fingerprint
        ),
        bootstrap_policy_fingerprint=(
            bootstrap_policy_fingerprint
        ),
        requested_data_scope=(
            requested_scope
        ),
        requested_purpose=(
            requested_purpose
        ),
        requested_jurisdiction=(
            requested_jurisdiction
        ),
        max_items=max_items,
        max_requests=max_requests,
        provider_health_status=(
            provider_health_status
        ),
        reason_codes=reasons,
    )

    return ProviderPreflightDecision(
        status=status,
        executable=executable,
        downstream_quarantine_required=(
            quarantine
        ),
        run_id=run_id,
        sport=sport,
        provider_key=provider_key,
        mode=mode,
        queue_fingerprint=(
            queue_fingerprint
        ),
        permit_id=permit_id,
        rights_manifest_fingerprint=(
            rights_manifest_fingerprint
        ),
        scheduling_evidence_fingerprint=(
            scheduling_evidence_fingerprint
        ),
        bootstrap_policy_fingerprint=(
            bootstrap_policy_fingerprint
        ),
        requested_data_scope=(
            requested_scope
        ),
        requested_purpose=(
            requested_purpose
        ),
        requested_jurisdiction=(
            requested_jurisdiction
        ),
        max_items=max_items,
        max_requests=max_requests,
        provider_health_status=(
            provider_health_status
        ),
        reason_codes=tuple(
            reasons
        ),
        decision_fingerprint=(
            decision_fp
        ),
    )


@dataclass(frozen=True)
class ProviderPreflightIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteProviderPreflightEvidenceStore:
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
                CREATE TABLE IF NOT EXISTS provider_preflight_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    sport TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    decision_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    CHECK (
                        sport IN (
                            'football',
                            'tennis'
                        )
                    )
                )
                """
            )

    @staticmethod
    def _evidence_id(
        decision_fingerprint: str,
    ) -> str:
        return _sha(
            {
                "schema": (
                    "matrix.provider-preflight-evidence-id/2"
                ),
                "decision_fingerprint": (
                    decision_fingerprint
                ),
            }
        )

    def record(
        self,
        decision: ProviderPreflightDecision,
    ) -> str:
        expected_fp = _decision_fingerprint(
            status=decision.status,
            executable=(
                decision.executable
            ),
            downstream_quarantine_required=(
                decision
                .downstream_quarantine_required
            ),
            run_id=decision.run_id,
            sport=decision.sport,
            provider_key=(
                decision.provider_key
            ),
            mode=decision.mode,
            queue_fingerprint=(
                decision
                .queue_fingerprint
            ),
            permit_id=(
                decision.permit_id
            ),
            rights_manifest_fingerprint=(
                decision
                .rights_manifest_fingerprint
            ),
            scheduling_evidence_fingerprint=(
                decision
                .scheduling_evidence_fingerprint
            ),
            bootstrap_policy_fingerprint=(
                decision
                .bootstrap_policy_fingerprint
            ),
            requested_data_scope=(
                decision
                .requested_data_scope
            ),
            requested_purpose=(
                decision
                .requested_purpose
            ),
            requested_jurisdiction=(
                decision
                .requested_jurisdiction
            ),
            max_items=(
                decision.max_items
            ),
            max_requests=(
                decision.max_requests
            ),
            provider_health_status=(
                decision
                .provider_health_status
            ),
            reason_codes=(
                decision.reason_codes
            ),
        )

        if (
            expected_fp
            != decision
            .decision_fingerprint
        ):
            raise ValueError(
                "PROVIDER_PREFLIGHT_DECISION_DERIVATION_MISMATCH"
            )

        if (
            decision.executable
            != (
                decision.status
                == "EXECUTE"
            )
        ):
            raise ValueError(
                "PROVIDER_PREFLIGHT_STATUS_MISMATCH"
            )

        evidence_id = (
            self._evidence_id(
                decision
                .decision_fingerprint
            )
        )

        payload = {
            "schema": (
                "matrix.provider-preflight-evidence/2"
            ),
            "evidence_id": (
                evidence_id
            ),
            "status": (
                decision.status
            ),
            "executable": (
                decision.executable
            ),
            "downstream_quarantine_required": (
                decision
                .downstream_quarantine_required
            ),
            "run_id": decision.run_id,
            "sport": decision.sport,
            "provider_key": (
                decision.provider_key
            ),
            "mode": decision.mode,
            "queue_fingerprint": (
                decision
                .queue_fingerprint
            ),
            "permit_id": (
                decision.permit_id
            ),
            "rights_manifest_fingerprint": (
                decision
                .rights_manifest_fingerprint
            ),
            "scheduling_evidence_fingerprint": (
                decision
                .scheduling_evidence_fingerprint
            ),
            "bootstrap_policy_fingerprint": (
                decision
                .bootstrap_policy_fingerprint
            ),
            "requested_data_scope": list(
                decision
                .requested_data_scope
            ),
            "requested_purpose": (
                decision
                .requested_purpose
            ),
            "requested_jurisdiction": (
                decision
                .requested_jurisdiction
            ),
            "max_items": (
                decision.max_items
            ),
            "max_requests": (
                decision.max_requests
            ),
            "provider_health_status": (
                decision
                .provider_health_status
            ),
            "reason_codes": list(
                decision.reason_codes
            ),
            "decision_fingerprint": (
                decision
                .decision_fingerprint
            ),
            "authoritative_for_future_provider_calls": True,
            "automatic_provider_switch": False,
            "automatic_health_promotion": False,
            "automatic_wagering": False,
        }

        payload_json = (
            _canonical_json(
                payload
            )
        )
        payload_sha = sha256(
            payload_json.encode(
                "utf-8"
            )
        ).hexdigest()

        with self._connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            existing = connection.execute(
                """
                SELECT
                    evidence_id,
                    payload_sha256
                FROM provider_preflight_evidence
                WHERE run_id = ?
                """,
                (
                    decision.run_id,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    "ROLLBACK"
                )

                if (
                    str(existing[0])
                    == evidence_id
                    and str(existing[1])
                    == payload_sha
                ):
                    return evidence_id

                raise ValueError(
                    "PROVIDER_PREFLIGHT_RUN_MUTATION_VIOLATION"
                )

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
                    decision
                    .decision_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute(
                "COMMIT"
            )

        return evidence_id

    def audit_integrity(
        self,
    ) -> ProviderPreflightIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    run_id,
                    sport,
                    provider_key,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                FROM provider_preflight_evidence
                ORDER BY evidence_id
                """
            ).fetchall()

        for (
            evidence_id,
            run_id,
            sport,
            provider_key,
            decision_fp,
            payload_json,
            stored_sha,
        ) in rows:
            try:
                payload = json.loads(
                    payload_json
                )
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:"
                    f"{decision_fp}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(
                    payload
                ).encode("utf-8")
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    "PAYLOAD_HASH_MISMATCH:"
                    f"{decision_fp}"
                )

            expected_fp = (
                _decision_fingerprint(
                    status=payload.get(
                        "status"
                    ),
                    executable=payload.get(
                        "executable"
                    ),
                    downstream_quarantine_required=payload.get(
                        "downstream_quarantine_required"
                    ),
                    run_id=payload.get(
                        "run_id"
                    ),
                    sport=payload.get(
                        "sport"
                    ),
                    provider_key=payload.get(
                        "provider_key"
                    ),
                    mode=payload.get(
                        "mode"
                    ),
                    queue_fingerprint=payload.get(
                        "queue_fingerprint"
                    ),
                    permit_id=payload.get(
                        "permit_id"
                    ),
                    rights_manifest_fingerprint=payload.get(
                        "rights_manifest_fingerprint"
                    ),
                    scheduling_evidence_fingerprint=payload.get(
                        "scheduling_evidence_fingerprint"
                    ),
                    bootstrap_policy_fingerprint=payload.get(
                        "bootstrap_policy_fingerprint"
                    ),
                    requested_data_scope=payload.get(
                        "requested_data_scope",
                        [],
                    ),
                    requested_purpose=payload.get(
                        "requested_purpose"
                    ),
                    requested_jurisdiction=payload.get(
                        "requested_jurisdiction"
                    ),
                    max_items=payload.get(
                        "max_items"
                    ),
                    max_requests=payload.get(
                        "max_requests"
                    ),
                    provider_health_status=payload.get(
                        "provider_health_status"
                    ),
                    reason_codes=payload.get(
                        "reason_codes",
                        [],
                    ),
                )
            )

            if (
                expected_fp
                != decision_fp
            ):
                errors.append(
                    "DECISION_FINGERPRINT_MISMATCH:"
                    f"{decision_fp}"
                )

            expected_evidence_id = (
                self._evidence_id(
                    decision_fp
                )
            )

            if (
                expected_evidence_id
                != evidence_id
            ):
                errors.append(
                    "EVIDENCE_ID_MISMATCH:"
                    f"{decision_fp}"
                )

            for key, expected in {
                "evidence_id": (
                    evidence_id
                ),
                "run_id": run_id,
                "sport": sport,
                "provider_key": (
                    provider_key
                ),
                "decision_fingerprint": (
                    decision_fp
                ),
                "authoritative_for_future_provider_calls": True,
                "automatic_provider_switch": False,
                "automatic_health_promotion": False,
                "automatic_wagering": False,
            }.items():
                if (
                    payload.get(key)
                    != expected
                ):
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{decision_fp}"
                    )

        return ProviderPreflightIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
