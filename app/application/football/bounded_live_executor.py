from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


R8_1_LEDGER_USER_VERSION = 81

R8_1_ALLOWED_MODALITIES = (
    "fixture_status",
    "fixture_statistics",
    "fixture_events",
)

R8_1_RUN_STATUS = "PLANNED_OFFLINE_ONLY"

R8_1_APPROVED_DESIGN_MANIFEST_SHA256 = (
    "02cd645bf0eccdac6ea27151ae63bbaf350a197adecc1d443359a19bb83c97fa"
)
R8_1_APPROVED_INDEPENDENT_AUDIT_SHA256 = (
    "8bcad0d5064b2a52fc9580a139f285a7b2f4b9a7acc14bd078501024d94b34b6"
)

R8_1_STOP_CONDITIONS = (
    "CAPTURE_ROUND_LIMIT_REACHED",
    "TOTAL_PROVIDER_CALL_BUDGET_REACHED",
    "MAX_RUNTIME_REACHED",
    "HUMAN_AUTHORIZATION_MISSING_OR_EXPIRED",
    "RIGHTS_SCOPE_NOT_APPROVED",
    "PROCESS_SCOPE_GUARD_NOT_HELD",
    "PROVIDER_KEY_CHANGED",
    "SUBJECT_KEY_CHANGED",
    "CLOCK_REGRESSION",
    "DURABLE_EVIDENCE_INTEGRITY_FAILURE",
    "SEQUENCE_ALLOCATOR_INTEGRITY_FAILURE",
    "UNEXPECTED_PROVIDER_RESPONSE_CONTRACT",
    "PROVIDER_CIRCUIT_OR_QUOTA_BLOCK",
    "FIXTURE_TERMINAL_STATUS_WHEN_CONFIGURED",
    "MANUAL_STOP_REQUEST",
)

R8_1_ROUND_STATE_MACHINE = (
    "PLANNED",
    "AUTHORIZED",
    "ATTEMPT_INTENT_RECORDED",
    "CAPTURED_OR_FAILED",
    "NORMALIZED",
    "DURABLY_RECORDED",
    "ADMISSION_EVALUATED",
    "ROUND_CLOSED",
)


def _canonical(value: Any) -> str:
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
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def _positive_int(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name.upper()}_MUST_BE_POSITIVE_INTEGER")
    return value


def _nonempty(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name.upper()}_REQUIRED")
    return value.strip()


def _sha256_hex(value: str, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name.upper()}_SHA256_REQUIRED")
    normalized = value.strip().lower()
    if (
        len(normalized) != 64
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise ValueError(f"{name.upper()}_SHA256_REQUIRED")
    return normalized


def _payload_bool(
    payload: Mapping[str, Any],
    name: str,
) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"RUN_MANIFEST_{name.upper()}_BOOLEAN_REQUIRED")
    return value


def _payload_positive_int(
    payload: Mapping[str, Any],
    name: str,
) -> int:
    value = payload.get(name)
    return _positive_int(value, name=f"run_manifest_{name}")


def _payload_string_tuple(
    payload: Mapping[str, Any],
    name: str,
) -> tuple[str, ...]:
    value = payload.get(name)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) for item in value)
    ):
        raise ValueError(
            f"RUN_MANIFEST_{name.upper()}_STRING_LIST_REQUIRED"
        )
    return tuple(value)


@dataclass(frozen=True)
class BoundedFootballLiveExecutorConfig:
    provider_key: str
    subject_key: str
    modalities: tuple[str, ...]
    max_capture_rounds: int
    max_total_provider_calls: int
    max_runtime_ms: int
    max_attempts_per_slot: int = 1
    capture_interval_ms: int | None = None
    odds_enabled: bool = False
    single_process_only: bool = True
    cross_process_execution_allowed: bool = False
    automatic_retry: bool = False
    automatic_provider_switch: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False
    production_admissible: bool = False

    def __post_init__(self) -> None:
        provider_key = _nonempty(self.provider_key, name="provider_key")
        subject_key = _nonempty(self.subject_key, name="subject_key")
        object.__setattr__(self, "provider_key", provider_key)
        object.__setattr__(self, "subject_key", subject_key)

        if not subject_key.startswith("fixture:"):
            raise ValueError("FOOTBALL_FIXTURE_SUBJECT_KEY_REQUIRED")

        if (
            not isinstance(self.modalities, tuple)
            or not self.modalities
            or any(not isinstance(item, str) for item in self.modalities)
        ):
            raise ValueError("EXPLICIT_NONEMPTY_MODALITY_TUPLE_REQUIRED")

        if len(set(self.modalities)) != len(self.modalities):
            raise ValueError("DUPLICATE_MODALITY_FORBIDDEN")

        for modality in self.modalities:
            if modality == "odds":
                raise ValueError("ODDS_NOT_AUTHORIZED_IN_R8_1")
            if modality not in R8_1_ALLOWED_MODALITIES:
                raise ValueError("UNSUPPORTED_R8_1_FOOTBALL_MODALITY")

        _positive_int(
            self.max_capture_rounds,
            name="max_capture_rounds",
        )
        _positive_int(
            self.max_total_provider_calls,
            name="max_total_provider_calls",
        )
        _positive_int(
            self.max_runtime_ms,
            name="max_runtime_ms",
        )

        if self.max_attempts_per_slot != 1:
            raise ValueError("R8_1_AUTOMATIC_RETRY_FORBIDDEN")

        if self.capture_interval_ms is not None:
            raise ValueError(
                "CAPTURE_INTERVAL_REQUIRES_EMPIRICAL_CALIBRATION"
            )

        if self.odds_enabled is not False:
            raise ValueError("ODDS_NOT_AUTHORIZED_IN_R8_1")
        if self.single_process_only is not True:
            raise ValueError("R8_1_SINGLE_PROCESS_SCOPE_REQUIRED")
        if self.cross_process_execution_allowed is not False:
            raise ValueError("R8_1_CROSS_PROCESS_EXECUTION_FORBIDDEN")
        if self.automatic_retry is not False:
            raise ValueError("R8_1_AUTOMATIC_RETRY_FORBIDDEN")
        if self.automatic_provider_switch is not False:
            raise ValueError("AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN")
        if self.automatic_model_promotion is not False:
            raise ValueError("AUTOMATIC_MODEL_PROMOTION_FORBIDDEN")
        if self.automatic_wagering is not False:
            raise ValueError("AUTOMATIC_WAGERING_FORBIDDEN")
        if self.production_admissible is not False:
            raise ValueError("PRODUCTION_ADMISSION_FORBIDDEN")

        if self.planned_provider_calls > self.max_total_provider_calls:
            raise ValueError("PLANNED_PROVIDER_CALLS_EXCEED_BUDGET")

    @property
    def planned_provider_calls(self) -> int:
        return (
            self.max_capture_rounds
            * len(self.modalities)
            * self.max_attempts_per_slot
        )

    def payload(self) -> Mapping[str, Any]:
        payload = asdict(self)
        payload["schema"] = (
            "matrix.c2-r8-1-bounded-football-live-executor-config/1"
        )
        payload["sport"] = "football"
        payload["modalities"] = list(self.modalities)
        payload["planned_provider_calls"] = self.planned_provider_calls
        payload["thresholds_empirically_calibrated"] = False
        payload["rights_scope_approved"] = False
        payload["human_authorization_granted"] = False
        payload["execution_authorized"] = False
        return payload

    @property
    def config_fingerprint(self) -> str:
        return _sha(self.payload())


@dataclass(frozen=True)
class FootballBoundedCaptureSlot:
    round_index: int
    modality: str
    attempt_index: int = 1

    def __post_init__(self) -> None:
        _positive_int(self.round_index, name="round_index")
        if self.modality not in R8_1_ALLOWED_MODALITIES:
            raise ValueError("UNSUPPORTED_R8_1_FOOTBALL_MODALITY")
        if self.attempt_index != 1:
            raise ValueError("R8_1_AUTOMATIC_RETRY_FORBIDDEN")


def build_bounded_capture_plan(
    config: BoundedFootballLiveExecutorConfig,
) -> tuple[FootballBoundedCaptureSlot, ...]:
    slots = tuple(
        FootballBoundedCaptureSlot(
            round_index=round_index,
            modality=modality,
        )
        for round_index in range(1, config.max_capture_rounds + 1)
        for modality in config.modalities
    )

    if len(slots) != config.planned_provider_calls:
        raise ValueError("BOUNDED_CAPTURE_PLAN_CARDINALITY_MISMATCH")
    if len(slots) > config.max_total_provider_calls:
        raise ValueError("PLANNED_PROVIDER_CALLS_EXCEED_BUDGET")

    return slots


def _derive_bounded_run_id(
    *,
    config_fingerprint: str,
    created_at: datetime,
    run_nonce_sha256: str,
    design_manifest_sha256: str,
    independent_audit_sha256: str,
) -> str:
    return _sha(
        {
            "schema": "matrix.c2-r8-1-bounded-run-id/1",
            "config_fingerprint": config_fingerprint,
            "created_at": created_at.isoformat(),
            "run_nonce_sha256": run_nonce_sha256,
            "design_manifest_sha256": design_manifest_sha256,
            "independent_audit_sha256": independent_audit_sha256,
        }
    )


@dataclass(frozen=True)
class BoundedFootballLiveRunManifest:
    run_id: str
    created_at: datetime
    run_nonce_sha256: str
    config_fingerprint: str
    design_manifest_sha256: str
    independent_audit_sha256: str
    provider_key: str
    subject_key: str
    modalities: tuple[str, ...]
    max_capture_rounds: int
    max_total_provider_calls: int
    max_runtime_ms: int
    planned_provider_calls: int
    status: str = R8_1_RUN_STATUS
    human_authorization_granted: bool = False
    rights_scope_approved: bool = False
    execution_authorized: bool = False
    repeated_provider_execution_authorized: bool = False
    single_process_only: bool = True
    cross_process_execution_allowed: bool = False
    crash_recovery_required: bool = True
    idempotent_resume_required: bool = True
    production_admissible: bool = False
    automatic_provider_switch: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False
    manifest_fingerprint: str = ""

    def __post_init__(self) -> None:
        normalized_run_id = _sha256_hex(self.run_id, name="run_id")
        object.__setattr__(self, "run_id", normalized_run_id)
        object.__setattr__(
            self,
            "created_at",
            _aware_utc(self.created_at, name="created_at"),
        )
        normalized_nonce = _sha256_hex(
            self.run_nonce_sha256,
            name="run_nonce",
        )
        object.__setattr__(
            self,
            "run_nonce_sha256",
            normalized_nonce,
        )
        normalized_config = _sha256_hex(
            self.config_fingerprint,
            name="config_fingerprint",
        )
        object.__setattr__(
            self,
            "config_fingerprint",
            normalized_config,
        )
        normalized_design = _sha256_hex(
            self.design_manifest_sha256,
            name="design_manifest",
        )
        normalized_audit = _sha256_hex(
            self.independent_audit_sha256,
            name="independent_audit",
        )
        object.__setattr__(
            self,
            "design_manifest_sha256",
            normalized_design,
        )
        object.__setattr__(
            self,
            "independent_audit_sha256",
            normalized_audit,
        )

        if (
            normalized_design
            != R8_1_APPROVED_DESIGN_MANIFEST_SHA256
        ):
            raise ValueError(
                "RUN_MANIFEST_DESIGN_AUTHORITY_SHA_MISMATCH"
            )
        if (
            normalized_audit
            != R8_1_APPROVED_INDEPENDENT_AUDIT_SHA256
        ):
            raise ValueError(
                "RUN_MANIFEST_INDEPENDENT_AUDIT_AUTHORITY_SHA_MISMATCH"
            )
        _nonempty(self.provider_key, name="provider_key")
        _nonempty(self.subject_key, name="subject_key")

        if self.status != R8_1_RUN_STATUS:
            raise ValueError("R8_1_RUN_STATUS_MUST_REMAIN_PLANNED")
        if self.human_authorization_granted is not False:
            raise ValueError("R8_1_HUMAN_AUTHORIZATION_MUST_REMAIN_FALSE")
        if self.rights_scope_approved is not False:
            raise ValueError("R8_1_RIGHTS_SCOPE_MUST_REMAIN_FALSE")
        if self.execution_authorized is not False:
            raise ValueError("R8_1_EXECUTION_MUST_REMAIN_UNAUTHORIZED")
        if self.repeated_provider_execution_authorized is not False:
            raise ValueError(
                "R8_1_REPEATED_PROVIDER_EXECUTION_MUST_REMAIN_UNAUTHORIZED"
            )
        if self.single_process_only is not True:
            raise ValueError("R8_1_SINGLE_PROCESS_SCOPE_REQUIRED")
        if self.cross_process_execution_allowed is not False:
            raise ValueError("R8_1_CROSS_PROCESS_EXECUTION_FORBIDDEN")
        if self.crash_recovery_required is not True:
            raise ValueError("R8_1_CRASH_RECOVERY_REQUIRED")
        if self.idempotent_resume_required is not True:
            raise ValueError("R8_1_IDEMPOTENT_RESUME_REQUIRED")
        if self.production_admissible is not False:
            raise ValueError("PRODUCTION_ADMISSION_FORBIDDEN")
        if self.automatic_provider_switch is not False:
            raise ValueError("AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN")
        if self.automatic_model_promotion is not False:
            raise ValueError("AUTOMATIC_MODEL_PROMOTION_FORBIDDEN")
        if self.automatic_wagering is not False:
            raise ValueError("AUTOMATIC_WAGERING_FORBIDDEN")

        # Re-derive the complete R8.1 executor configuration contract from
        # durable manifest fields.  Direct manifest construction must not be
        # able to bypass the config allowlist, football fixture binding,
        # finite call budget, or single-process/no-production safeguards.
        rederived_config = BoundedFootballLiveExecutorConfig(
            provider_key=self.provider_key,
            subject_key=self.subject_key,
            modalities=self.modalities,
            max_capture_rounds=self.max_capture_rounds,
            max_total_provider_calls=self.max_total_provider_calls,
            max_runtime_ms=self.max_runtime_ms,
            max_attempts_per_slot=1,
            capture_interval_ms=None,
            odds_enabled=False,
            single_process_only=self.single_process_only,
            cross_process_execution_allowed=(
                self.cross_process_execution_allowed
            ),
            automatic_retry=False,
            automatic_provider_switch=self.automatic_provider_switch,
            automatic_model_promotion=self.automatic_model_promotion,
            automatic_wagering=self.automatic_wagering,
            production_admissible=self.production_admissible,
        )

        if (
            self.planned_provider_calls
            != rederived_config.planned_provider_calls
        ):
            raise ValueError(
                "RUN_MANIFEST_PLANNED_PROVIDER_CALLS_MISMATCH"
            )

        if (
            self.config_fingerprint
            != rederived_config.config_fingerprint
        ):
            raise ValueError(
                "RUN_MANIFEST_CONFIG_CONTRACT_FINGERPRINT_MISMATCH"
            )

        expected_run_id = _derive_bounded_run_id(
            config_fingerprint=self.config_fingerprint,
            created_at=self.created_at,
            run_nonce_sha256=self.run_nonce_sha256,
            design_manifest_sha256=self.design_manifest_sha256,
            independent_audit_sha256=self.independent_audit_sha256,
        )
        if self.run_id != expected_run_id:
            raise ValueError("RUN_MANIFEST_RUN_ID_PROVENANCE_MISMATCH")

        expected = _sha(self._fingerprint_payload())
        if self.manifest_fingerprint:
            if self.manifest_fingerprint != expected:
                raise ValueError("RUN_MANIFEST_FINGERPRINT_MISMATCH")
        else:
            object.__setattr__(
                self,
                "manifest_fingerprint",
                expected,
            )

    def _fingerprint_payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.c2-r8-1-bounded-football-live-run-manifest/1",
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "run_nonce_sha256": self.run_nonce_sha256,
            "config_fingerprint": self.config_fingerprint,
            "design_manifest_sha256": self.design_manifest_sha256,
            "independent_audit_sha256": self.independent_audit_sha256,
            "provider_key": self.provider_key,
            "subject_key": self.subject_key,
            "modalities": list(self.modalities),
            "max_capture_rounds": self.max_capture_rounds,
            "max_total_provider_calls": self.max_total_provider_calls,
            "max_runtime_ms": self.max_runtime_ms,
            "planned_provider_calls": self.planned_provider_calls,
            "status": self.status,
            "human_authorization_granted": self.human_authorization_granted,
            "rights_scope_approved": self.rights_scope_approved,
            "execution_authorized": self.execution_authorized,
            "repeated_provider_execution_authorized": (
                self.repeated_provider_execution_authorized
            ),
            "single_process_only": self.single_process_only,
            "cross_process_execution_allowed": (
                self.cross_process_execution_allowed
            ),
            "crash_recovery_required": self.crash_recovery_required,
            "idempotent_resume_required": self.idempotent_resume_required,
            "production_admissible": self.production_admissible,
            "automatic_provider_switch": self.automatic_provider_switch,
            "automatic_model_promotion": self.automatic_model_promotion,
            "automatic_wagering": self.automatic_wagering,
            "stop_conditions": list(R8_1_STOP_CONDITIONS),
            "round_state_machine": list(R8_1_ROUND_STATE_MACHINE),
        }

    def payload(self) -> Mapping[str, Any]:
        payload = dict(self._fingerprint_payload())
        payload["manifest_fingerprint"] = self.manifest_fingerprint
        return payload


def build_bounded_run_manifest(
    config: BoundedFootballLiveExecutorConfig,
    *,
    created_at: datetime,
    run_nonce_sha256: str,
) -> BoundedFootballLiveRunManifest:
    created = _aware_utc(created_at, name="created_at")
    nonce = _sha256_hex(run_nonce_sha256, name="run_nonce")
    design_sha = R8_1_APPROVED_DESIGN_MANIFEST_SHA256
    audit_sha = R8_1_APPROVED_INDEPENDENT_AUDIT_SHA256

    run_id = _derive_bounded_run_id(
        config_fingerprint=config.config_fingerprint,
        created_at=created,
        run_nonce_sha256=nonce,
        design_manifest_sha256=design_sha,
        independent_audit_sha256=audit_sha,
    )

    return BoundedFootballLiveRunManifest(
        run_id=run_id,
        created_at=created,
        run_nonce_sha256=nonce,
        config_fingerprint=config.config_fingerprint,
        design_manifest_sha256=design_sha,
        independent_audit_sha256=audit_sha,
        provider_key=config.provider_key,
        subject_key=config.subject_key,
        modalities=config.modalities,
        max_capture_rounds=config.max_capture_rounds,
        max_total_provider_calls=config.max_total_provider_calls,
        max_runtime_ms=config.max_runtime_ms,
        planned_provider_calls=config.planned_provider_calls,
    )


@dataclass(frozen=True)
class BoundedRunManifestWriteResult:
    run_id: str
    manifest_fingerprint: str
    idempotent: bool
    execution_authorized: bool = False
    production_admissible: bool = False


def _manifest_from_payload(
    payload: Mapping[str, Any],
) -> BoundedFootballLiveRunManifest:
    if payload.get("schema") != (
        "matrix.c2-r8-1-bounded-football-live-run-manifest/1"
    ):
        raise ValueError("RUN_MANIFEST_SCHEMA_MISMATCH")

    return BoundedFootballLiveRunManifest(
        run_id=_sha256_hex(str(payload["run_id"]), name="run_id"),
        created_at=datetime.fromisoformat(str(payload["created_at"])),
        run_nonce_sha256=_sha256_hex(
            str(payload["run_nonce_sha256"]),
            name="run_nonce",
        ),
        config_fingerprint=_sha256_hex(
            str(payload["config_fingerprint"]),
            name="config_fingerprint",
        ),
        design_manifest_sha256=_sha256_hex(
            str(payload["design_manifest_sha256"]),
            name="design_manifest",
        ),
        independent_audit_sha256=_sha256_hex(
            str(payload["independent_audit_sha256"]),
            name="independent_audit",
        ),
        provider_key=_nonempty(
            payload["provider_key"],
            name="provider_key",
        ),
        subject_key=_nonempty(
            payload["subject_key"],
            name="subject_key",
        ),
        modalities=_payload_string_tuple(payload, "modalities"),
        max_capture_rounds=_payload_positive_int(
            payload,
            "max_capture_rounds",
        ),
        max_total_provider_calls=_payload_positive_int(
            payload,
            "max_total_provider_calls",
        ),
        max_runtime_ms=_payload_positive_int(
            payload,
            "max_runtime_ms",
        ),
        planned_provider_calls=_payload_positive_int(
            payload,
            "planned_provider_calls",
        ),
        status=_nonempty(payload["status"], name="status"),
        human_authorization_granted=_payload_bool(
            payload,
            "human_authorization_granted",
        ),
        rights_scope_approved=_payload_bool(
            payload,
            "rights_scope_approved",
        ),
        execution_authorized=_payload_bool(
            payload,
            "execution_authorized",
        ),
        repeated_provider_execution_authorized=_payload_bool(
            payload,
            "repeated_provider_execution_authorized",
        ),
        single_process_only=_payload_bool(
            payload,
            "single_process_only",
        ),
        cross_process_execution_allowed=_payload_bool(
            payload,
            "cross_process_execution_allowed",
        ),
        crash_recovery_required=_payload_bool(
            payload,
            "crash_recovery_required",
        ),
        idempotent_resume_required=_payload_bool(
            payload,
            "idempotent_resume_required",
        ),
        production_admissible=_payload_bool(
            payload,
            "production_admissible",
        ),
        automatic_provider_switch=_payload_bool(
            payload,
            "automatic_provider_switch",
        ),
        automatic_model_promotion=_payload_bool(
            payload,
            "automatic_model_promotion",
        ),
        automatic_wagering=_payload_bool(
            payload,
            "automatic_wagering",
        ),
        manifest_fingerprint=_sha256_hex(
            str(payload["manifest_fingerprint"]),
            name="manifest_fingerprint",
        ),
    )


class SQLiteBoundedFootballLiveRunManifestStore:
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
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _anchor_payload(
        *,
        total_run_count: int,
        membership_sha256: str,
    ) -> Mapping[str, Any]:
        return {
            "schema": "matrix.c2-r8-1-bounded-run-manifest-anchor/1",
            "total_run_count": total_run_count,
            "membership_sha256": membership_sha256,
        }

    @staticmethod
    def _membership(
        connection: sqlite3.Connection,
    ) -> tuple[int, str]:
        rows = connection.execute(
            """
            SELECT run_id, manifest_sha256
            FROM football_bounded_run_manifest
            ORDER BY run_id
            """
        ).fetchall()
        payload = [
            {
                "run_id": str(run_id),
                "manifest_sha256": str(manifest_sha256),
            }
            for run_id, manifest_sha256 in rows
        ]
        return len(rows), _sha(payload)

    def _rewrite_anchor(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        total, membership_sha = self._membership(connection)
        anchor_payload = self._anchor_payload(
            total_run_count=total,
            membership_sha256=membership_sha,
        )
        anchor_sha = _sha(anchor_payload)
        connection.execute(
            """
            INSERT INTO football_bounded_run_manifest_anchor (
                singleton_id,
                total_run_count,
                membership_sha256,
                anchor_sha256
            )
            VALUES (1, ?, ?, ?)
            ON CONFLICT(singleton_id) DO UPDATE SET
                total_run_count = excluded.total_run_count,
                membership_sha256 = excluded.membership_sha256,
                anchor_sha256 = excluded.anchor_sha256
            """,
            (total, membership_sha, anchor_sha),
        )

    def _assert_integrity(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        version = int(
            connection.execute("PRAGMA user_version").fetchone()[0]
        )
        if version != R8_1_LEDGER_USER_VERSION:
            raise ValueError("R8_1_RUN_MANIFEST_SCHEMA_VERSION_MISMATCH")

        rows = connection.execute(
            """
            SELECT
                run_id,
                config_fingerprint,
                manifest_json,
                manifest_sha256,
                created_at
            FROM football_bounded_run_manifest
            ORDER BY run_id
            """
        ).fetchall()

        for (
            run_id,
            config_fingerprint,
            manifest_json,
            manifest_sha,
            created_at,
        ) in rows:
            try:
                payload = json.loads(str(manifest_json))
            except json.JSONDecodeError as error:
                raise ValueError(
                    "RUN_MANIFEST_JSON_INVALID"
                ) from error

            if not isinstance(payload, dict):
                raise ValueError("RUN_MANIFEST_JSON_OBJECT_REQUIRED")

            if _sha(payload) != str(manifest_sha):
                raise ValueError("RUN_MANIFEST_PAYLOAD_SHA_MISMATCH")

            manifest = _manifest_from_payload(payload)
            if payload != manifest.payload():
                raise ValueError(
                    "RUN_MANIFEST_SEMANTIC_REDERIVATION_MISMATCH"
                )
            if manifest.run_id != str(run_id):
                raise ValueError("RUN_MANIFEST_RUN_ID_MISMATCH")
            if (
                manifest.config_fingerprint
                != str(config_fingerprint)
            ):
                raise ValueError(
                    "RUN_MANIFEST_CONFIG_FINGERPRINT_ROW_MISMATCH"
                )
            if manifest.created_at.isoformat() != str(created_at):
                raise ValueError(
                    "RUN_MANIFEST_CREATED_AT_ROW_MISMATCH"
                )

        anchor = connection.execute(
            """
            SELECT total_run_count, membership_sha256, anchor_sha256
            FROM football_bounded_run_manifest_anchor
            WHERE singleton_id = 1
            """
        ).fetchone()
        if anchor is None:
            raise ValueError("RUN_MANIFEST_ANCHOR_REQUIRED")

        total, membership_sha = self._membership(connection)
        expected_payload = self._anchor_payload(
            total_run_count=total,
            membership_sha256=membership_sha,
        )
        expected_anchor_sha = _sha(expected_payload)

        if int(anchor[0]) != total:
            raise ValueError("RUN_MANIFEST_ANCHOR_COUNT_MISMATCH")
        if str(anchor[1]) != membership_sha:
            raise ValueError("RUN_MANIFEST_ANCHOR_MEMBERSHIP_MISMATCH")
        if str(anchor[2]) != expected_anchor_sha:
            raise ValueError("RUN_MANIFEST_ANCHOR_SHA_MISMATCH")

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = int(
                    connection.execute(
                        "PRAGMA user_version"
                    ).fetchone()[0]
                )
                if version not in (0, R8_1_LEDGER_USER_VERSION):
                    raise ValueError(
                        "R8_1_RUN_MANIFEST_SCHEMA_VERSION_MISMATCH"
                    )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS
                    football_bounded_run_manifest (
                        run_id TEXT PRIMARY KEY,
                        config_fingerprint TEXT NOT NULL,
                        manifest_json TEXT NOT NULL,
                        manifest_sha256 TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS
                    football_bounded_run_manifest_anchor (
                        singleton_id INTEGER PRIMARY KEY
                            CHECK (singleton_id = 1),
                        total_run_count INTEGER NOT NULL,
                        membership_sha256 TEXT NOT NULL,
                        anchor_sha256 TEXT NOT NULL
                    )
                    """
                )

                anchor = connection.execute(
                    """
                    SELECT 1
                    FROM football_bounded_run_manifest_anchor
                    WHERE singleton_id = 1
                    """
                ).fetchone()
                count = int(
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM football_bounded_run_manifest
                        """
                    ).fetchone()[0]
                )

                if anchor is None:
                    if count != 0:
                        raise ValueError("RUN_MANIFEST_ANCHOR_REQUIRED")
                    connection.execute(
                        f"PRAGMA user_version = {R8_1_LEDGER_USER_VERSION}"
                    )
                    self._rewrite_anchor(connection)
                else:
                    if version == 0:
                        raise ValueError(
                            "R8_1_RUN_MANIFEST_SCHEMA_VERSION_REQUIRED"
                        )
                    self._assert_integrity(connection)

                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def record(
        self,
        manifest: BoundedFootballLiveRunManifest,
    ) -> BoundedRunManifestWriteResult:
        payload = manifest.payload()
        manifest_json = _canonical(payload)
        manifest_sha = _sha(payload)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)

                row = connection.execute(
                    """
                    SELECT manifest_json, manifest_sha256
                    FROM football_bounded_run_manifest
                    WHERE run_id = ?
                    """,
                    (manifest.run_id,),
                ).fetchone()

                if row is not None:
                    if (
                        str(row[0]) != manifest_json
                        or str(row[1]) != manifest_sha
                    ):
                        raise ValueError(
                            "RUN_MANIFEST_ID_MUTATION_VIOLATION"
                        )
                    connection.execute("COMMIT")
                    return BoundedRunManifestWriteResult(
                        run_id=manifest.run_id,
                        manifest_fingerprint=(
                            manifest.manifest_fingerprint
                        ),
                        idempotent=True,
                    )

                connection.execute(
                    """
                    INSERT INTO football_bounded_run_manifest (
                        run_id,
                        config_fingerprint,
                        manifest_json,
                        manifest_sha256,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        manifest.run_id,
                        manifest.config_fingerprint,
                        manifest_json,
                        manifest_sha,
                        manifest.created_at.isoformat(),
                    ),
                )
                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        return BoundedRunManifestWriteResult(
            run_id=manifest.run_id,
            manifest_fingerprint=manifest.manifest_fingerprint,
            idempotent=False,
        )

    def get_verified(
        self,
        run_id: str,
    ) -> BoundedFootballLiveRunManifest | None:
        normalized = _sha256_hex(run_id, name="run_id")
        with self._connect() as connection:
            self._assert_integrity(connection)
            row = connection.execute(
                """
                SELECT manifest_json, manifest_sha256
                FROM football_bounded_run_manifest
                WHERE run_id = ?
                """,
                (normalized,),
            ).fetchone()
            if row is None:
                return None

            payload = json.loads(str(row[0]))
            if not isinstance(payload, dict):
                raise ValueError("RUN_MANIFEST_JSON_OBJECT_REQUIRED")
            if _sha(payload) != str(row[1]):
                raise ValueError("RUN_MANIFEST_PAYLOAD_SHA_MISMATCH")
            manifest = _manifest_from_payload(payload)
            if payload != manifest.payload():
                raise ValueError(
                    "RUN_MANIFEST_SEMANTIC_REDERIVATION_MISMATCH"
                )
            return manifest

    def audit_integrity(self) -> bool:
        try:
            with self._connect() as connection:
                self._assert_integrity(connection)
            return True
        except (ValueError, sqlite3.Error, KeyError, TypeError):
            return False
