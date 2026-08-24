from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

from app.application.football.bounded_live_control import (
    BoundedExecutorProcessScopeGuard,
    ProcessScopeLease,
    RunControlSnapshot,
    SQLiteBoundedFootballLiveControlStore,
)
from app.application.football.bounded_live_executor import (
    BoundedFootballLiveExecutorConfig,
    BoundedFootballLiveRunManifest,
    build_bounded_capture_plan,
)
from app.application.football.repeatable_live_ingestion import (
    SEQUENCE_ACCEPTED,
    SEQUENCE_DUPLICATE_SOURCE,
    SQLiteFootballLiveObservationStore,
)
from app.core.live_temporal_observation import (
    LiveTemporalObservation,
    build_live_temporal_observation,
)


R8_3_FAKE_PROVIDER_KEY = "fake:football:deterministic"
R8_3_APPROVED_BASELINE_HEAD = (
    "1fbb9ba97a2ffeb33c158382d0bf0c0e877e340c"
)
R8_3_APPROVED_I20_REPORT_SHA256 = (
    "b6ad7c453440fd59b2b35c08706989e20995c9569be1652e6a7fe9422ba85dc4"
)
R8_3_APPROVED_DESIGN_MANIFEST_SHA256 = (
    "112b28a24d7e992576824959652a471a3e10ee7948d8dccee4d1703d2a010791"
)
R8_3_APPROVED_GAP_AUDIT_SHA256 = (
    "7101a406d895c715e25224cf2af11f7b9b47ca193b502c8da944ed4cee468e3d"
)

R8_3_CRASH_POINTS = (
    "AFTER_RUN_REGISTERED",
    "AFTER_RUN_IN_PROGRESS",
    "AFTER_SLOT_RESERVED_BEFORE_FAKE_CALL",
    "AFTER_FAKE_CALL_BEFORE_NORMALIZED_PERSIST",
    "AFTER_NORMALIZED_PERSIST_BEFORE_SLOT_COMMIT",
    "AFTER_SLOT_COMMIT_BEFORE_NEXT_SLOT",
    "BEFORE_RUN_COMPLETED",
)

R8_3_STOP_REASONS = (
    "CAPTURE_ROUND_LIMIT_REACHED",
    "TOTAL_FAKE_CALL_BUDGET_REACHED",
    "MAX_RUNTIME_REACHED",
    "PROCESS_SCOPE_GUARD_NOT_HELD",
    "PROVIDER_KEY_CHANGED",
    "SUBJECT_KEY_CHANGED",
    "CLOCK_REGRESSION",
    "DURABLE_EVIDENCE_INTEGRITY_FAILURE",
    "SEQUENCE_ALLOCATOR_INTEGRITY_FAILURE",
    "UNEXPECTED_FAKE_RESPONSE_CONTRACT",
    "SCRIPTED_FAKE_PROVIDER_FAILURE",
    "FIXTURE_TERMINAL_STATUS_WHEN_CONFIGURED",
    "MANUAL_STOP_REQUEST",
)

_JOURNAL_USER_VERSION = 3
_JOURNAL_STATES = {"INTENT", "SUCCEEDED", "FAILED"}

_JOURNAL_DDL = {
    "r8_3_fake_run_meta": """
        CREATE TABLE r8_3_fake_run_meta (
            run_id TEXT PRIMARY KEY,
            manifest_fingerprint TEXT NOT NULL,
            plan_fingerprint TEXT NOT NULL,
            provider_key TEXT NOT NULL,
            subject_key TEXT NOT NULL,
            modalities_json TEXT NOT NULL,
            max_capture_rounds INTEGER NOT NULL,
            max_total_fake_calls INTEGER NOT NULL,
            resume_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """,
    "r8_3_fake_call_attempt": """
        CREATE TABLE r8_3_fake_call_attempt (
            run_id TEXT NOT NULL,
            round_index INTEGER NOT NULL,
            modality TEXT NOT NULL,
            attempt_index INTEGER NOT NULL,
            sequence_number INTEGER NOT NULL,
            correlation_id TEXT NOT NULL,
            state TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            result_at TEXT,
            source_record_fingerprint TEXT,
            error_code TEXT,
            intent_binding_sha256 TEXT NOT NULL,
            result_binding_sha256 TEXT,
            PRIMARY KEY (
                run_id,
                round_index,
                modality,
                attempt_index
            ),
            FOREIGN KEY (run_id)
                REFERENCES r8_3_fake_run_meta(run_id)
        )
    """,
    "r8_3_fake_resume_event": """
        CREATE TABLE r8_3_fake_resume_event (
            run_id TEXT NOT NULL,
            resume_index INTEGER NOT NULL,
            resumed_at TEXT NOT NULL,
            control_state_before TEXT NOT NULL,
            control_state_version_before INTEGER NOT NULL,
            PRIMARY KEY (
                run_id,
                resume_index
            ),
            FOREIGN KEY (run_id)
                REFERENCES r8_3_fake_run_meta(run_id)
        )
    """,
    "r8_3_fake_stop_event": """
        CREATE TABLE r8_3_fake_stop_event (
            run_id TEXT NOT NULL,
            stop_index INTEGER NOT NULL,
            reason_code TEXT NOT NULL,
            stopped_at TEXT NOT NULL,
            PRIMARY KEY (
                run_id,
                stop_index
            ),
            FOREIGN KEY (run_id)
                REFERENCES r8_3_fake_run_meta(run_id)
        )
    """,
    "r8_3_fake_journal_anchor": """
        CREATE TABLE r8_3_fake_journal_anchor (
            singleton_id INTEGER PRIMARY KEY
                CHECK(singleton_id = 1),
            payload_sha256 TEXT NOT NULL
        )
    """,
}


def _normalize_sql(sql: str) -> str:
    return "".join(str(sql).split()).lower()


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


def _git_sha1(value: str, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name.upper()}_GIT_SHA1_REQUIRED")
    normalized = value.strip().lower()
    if (
        len(normalized) != 40
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise ValueError(f"{name.upper()}_GIT_SHA1_REQUIRED")
    return normalized


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def _nonempty(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name.upper()}_REQUIRED")
    return value.strip()


def _positive_int(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name.upper()}_MUST_BE_POSITIVE_INTEGER")
    return value


def _runtime_ms(now: datetime, anchor: datetime) -> int:
    delta = int(round((now - anchor).total_seconds() * 1000))
    if delta < 0:
        raise ValueError("R8_3_CLOCK_REGRESSION")
    return delta


def _round_correlation_id(run_id: str, round_index: int) -> str:
    return _sha(
        {
            "schema": "matrix.c2-r8-3-round-correlation/1",
            "run_id": run_id,
            "round_index": round_index,
        }
    )


def _attempt_intent_binding(
    *,
    run_id: str,
    round_index: int,
    modality: str,
    attempt_index: int,
    sequence_number: int,
    correlation_id: str,
    attempted_at: str,
) -> str:
    return _sha(
        {
            "schema": "matrix.c2-r8-3r2-fake-call-intent-binding/1",
            "run_id": run_id,
            "round_index": round_index,
            "modality": modality,
            "attempt_index": attempt_index,
            "sequence_number": sequence_number,
            "correlation_id": correlation_id,
            "attempted_at": attempted_at,
        }
    )


def _attempt_result_binding(
    *,
    intent_binding_sha256: str,
    state: str,
    result_at: str,
    source_record_fingerprint: str | None,
    error_code: str | None,
) -> str:
    return _sha(
        {
            "schema": "matrix.c2-r8-3r2-fake-call-result-binding/1",
            "intent_binding_sha256": intent_binding_sha256,
            "state": state,
            "result_at": result_at,
            "source_record_fingerprint": source_record_fingerprint,
            "error_code": error_code,
        }
    )


def _manifest_config(
    manifest: BoundedFootballLiveRunManifest,
) -> BoundedFootballLiveExecutorConfig:
    return BoundedFootballLiveExecutorConfig(
        provider_key=manifest.provider_key,
        subject_key=manifest.subject_key,
        modalities=manifest.modalities,
        max_capture_rounds=manifest.max_capture_rounds,
        max_total_provider_calls=manifest.max_total_provider_calls,
        max_runtime_ms=manifest.max_runtime_ms,
        max_attempts_per_slot=1,
        capture_interval_ms=None,
        odds_enabled=False,
        single_process_only=True,
        cross_process_execution_allowed=False,
        automatic_retry=False,
        automatic_provider_switch=False,
        automatic_model_promotion=False,
        automatic_wagering=False,
        production_admissible=False,
    )


@dataclass(frozen=True)
class R83OfflineFakeExecutionAuthorityPlan:
    baseline_head: str
    i20_report_sha256: str
    design_manifest_sha256: str
    gap_audit_sha256: str
    provider_key: str
    subject_key: str
    manifest_fingerprint: str
    fake_provider_only: bool = True
    network_access_allowed: bool = False
    secret_access_allowed: bool = False
    real_provider_execution_authorized: bool = False
    repeated_provider_execution_authorized: bool = False
    production_admissible: bool = False
    automatic_provider_switch: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False
    plan_fingerprint: str = ""

    def __post_init__(self) -> None:
        baseline = _git_sha1(self.baseline_head, name="baseline_head")
        i20 = _sha256_hex(self.i20_report_sha256, name="i20_report")
        design = _sha256_hex(
            self.design_manifest_sha256,
            name="design_manifest",
        )
        gap = _sha256_hex(self.gap_audit_sha256, name="gap_audit")
        manifest_fp = _sha256_hex(
            self.manifest_fingerprint,
            name="manifest_fingerprint",
        )
        provider = _nonempty(self.provider_key, name="provider_key")
        subject = _nonempty(self.subject_key, name="subject_key")

        object.__setattr__(self, "baseline_head", baseline)
        object.__setattr__(self, "i20_report_sha256", i20)
        object.__setattr__(self, "design_manifest_sha256", design)
        object.__setattr__(self, "gap_audit_sha256", gap)
        object.__setattr__(self, "manifest_fingerprint", manifest_fp)
        object.__setattr__(self, "provider_key", provider)
        object.__setattr__(self, "subject_key", subject)

        if baseline != R8_3_APPROVED_BASELINE_HEAD:
            raise ValueError("R8_3_BASELINE_AUTHORITY_MISMATCH")
        if i20 != R8_3_APPROVED_I20_REPORT_SHA256:
            raise ValueError("R8_3_I20_AUTHORITY_MISMATCH")
        if design != R8_3_APPROVED_DESIGN_MANIFEST_SHA256:
            raise ValueError("R8_3_DESIGN_AUTHORITY_MISMATCH")
        if gap != R8_3_APPROVED_GAP_AUDIT_SHA256:
            raise ValueError("R8_3_GAP_AUDIT_AUTHORITY_MISMATCH")
        if provider != R8_3_FAKE_PROVIDER_KEY:
            raise ValueError("R8_3_FAKE_PROVIDER_KEY_REQUIRED")
        if self.fake_provider_only is not True:
            raise ValueError("R8_3_FAKE_PROVIDER_ONLY_REQUIRED")
        if self.network_access_allowed is not False:
            raise ValueError("R8_3_NETWORK_ACCESS_FORBIDDEN")
        if self.secret_access_allowed is not False:
            raise ValueError("R8_3_SECRET_ACCESS_FORBIDDEN")
        if self.real_provider_execution_authorized is not False:
            raise ValueError("R8_3_REAL_PROVIDER_EXECUTION_FORBIDDEN")
        if self.repeated_provider_execution_authorized is not False:
            raise ValueError("R8_3_REPEATED_REAL_PROVIDER_EXECUTION_FORBIDDEN")
        if self.production_admissible is not False:
            raise ValueError("R8_3_PRODUCTION_ADMISSION_FORBIDDEN")
        if self.automatic_provider_switch is not False:
            raise ValueError("AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN")
        if self.automatic_model_promotion is not False:
            raise ValueError("AUTOMATIC_MODEL_PROMOTION_FORBIDDEN")
        if self.automatic_wagering is not False:
            raise ValueError("AUTOMATIC_WAGERING_FORBIDDEN")

        expected = _sha(self._fingerprint_payload())
        if self.plan_fingerprint:
            actual = _sha256_hex(
                self.plan_fingerprint,
                name="plan_fingerprint",
            )
            if actual != expected:
                raise ValueError("R8_3_AUTHORITY_PLAN_FINGERPRINT_MISMATCH")
            object.__setattr__(self, "plan_fingerprint", actual)
        else:
            object.__setattr__(self, "plan_fingerprint", expected)

    def _fingerprint_payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.c2-r8-3-offline-fake-execution-authority/1",
            "baseline_head": self.baseline_head,
            "i20_report_sha256": self.i20_report_sha256,
            "design_manifest_sha256": self.design_manifest_sha256,
            "gap_audit_sha256": self.gap_audit_sha256,
            "provider_key": self.provider_key,
            "subject_key": self.subject_key,
            "manifest_fingerprint": self.manifest_fingerprint,
            "fake_provider_only": True,
            "network_access_allowed": False,
            "secret_access_allowed": False,
            "real_provider_execution_authorized": False,
            "repeated_provider_execution_authorized": False,
            "production_admissible": False,
            "automatic_provider_switch": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
        }

    def validate_manifest(
        self,
        manifest: BoundedFootballLiveRunManifest,
    ) -> None:
        if manifest.provider_key != self.provider_key:
            raise ValueError("R8_3_PROVIDER_KEY_CHANGED")
        if manifest.subject_key != self.subject_key:
            raise ValueError("R8_3_SUBJECT_KEY_CHANGED")
        if manifest.manifest_fingerprint != self.manifest_fingerprint:
            raise ValueError("R8_3_MANIFEST_AUTHORITY_MISMATCH")


def build_r8_3_offline_fake_execution_authority(
    manifest: BoundedFootballLiveRunManifest,
) -> R83OfflineFakeExecutionAuthorityPlan:
    if manifest.provider_key != R8_3_FAKE_PROVIDER_KEY:
        raise ValueError("R8_3_FAKE_PROVIDER_KEY_REQUIRED")
    return R83OfflineFakeExecutionAuthorityPlan(
        baseline_head=R8_3_APPROVED_BASELINE_HEAD,
        i20_report_sha256=R8_3_APPROVED_I20_REPORT_SHA256,
        design_manifest_sha256=R8_3_APPROVED_DESIGN_MANIFEST_SHA256,
        gap_audit_sha256=R8_3_APPROVED_GAP_AUDIT_SHA256,
        provider_key=manifest.provider_key,
        subject_key=manifest.subject_key,
        manifest_fingerprint=manifest.manifest_fingerprint,
    )


@dataclass(frozen=True)
class FakeProviderCapture:
    run_id: str
    round_index: int
    modality: str
    sequence_number: int
    correlation_id: str
    observed_at: datetime
    request_started_at: datetime
    response_received_at: datetime
    ingested_at: datetime
    normalized_at: datetime
    feature_ready_at: datetime
    source_record_fingerprint: str
    normalized_payload: Mapping[str, Any]
    fixture_terminal: bool = False

    def __post_init__(self) -> None:
        _sha256_hex(self.run_id, name="run_id")
        _positive_int(self.round_index, name="round_index")
        _positive_int(self.sequence_number, name="sequence_number")
        _sha256_hex(self.correlation_id, name="correlation_id")
        _sha256_hex(
            self.source_record_fingerprint,
            name="source_record_fingerprint",
        )
        for name in (
            "observed_at",
            "request_started_at",
            "response_received_at",
            "ingested_at",
            "normalized_at",
            "feature_ready_at",
        ):
            object.__setattr__(
                self,
                name,
                _aware_utc(getattr(self, name), name=name),
            )

    def observation(
        self,
        *,
        provider_key: str,
        subject_key: str,
    ) -> LiveTemporalObservation:
        return build_live_temporal_observation(
            sport="football",
            provider_key=provider_key,
            subject_key=subject_key,
            modality=self.modality,
            correlation_id=self.correlation_id,
            sequence_id=self.sequence_number,
            observed_at=self.observed_at,
            request_started_at=self.request_started_at,
            response_received_at=self.response_received_at,
            ingested_at=self.ingested_at,
            normalized_at=self.normalized_at,
            feature_ready_at=self.feature_ready_at,
            inference_completed_at=None,
            signal_emitted_at=None,
            source_record_fingerprint=self.source_record_fingerprint,
        )



def _expected_fake_normalized_payload(
    *,
    run_id: str,
    subject_key: str,
    round_index: int,
    modality: str,
    sequence_number: int,
    terminal_status_rounds: frozenset[int] = frozenset(),
) -> Mapping[str, Any]:
    terminal = (
        modality == "fixture_status"
        and round_index in terminal_status_rounds
    )
    base: dict[str, Any] = {
        "schema": "matrix.c2-r8-3-deterministic-fake-football-record/1",
        "provider_key": R8_3_FAKE_PROVIDER_KEY,
        "run_id": run_id,
        "subject_key": subject_key,
        "round_index": round_index,
        "modality": modality,
        "sequence_number": sequence_number,
        "synthetic": True,
        "raw_retained": False,
    }
    if modality == "fixture_status":
        base["status"] = "FT" if terminal else "1H"
        base["elapsed"] = min(90, round_index * 5)
        base["fixture_terminal"] = terminal
    elif modality == "fixture_statistics":
        base["home_shots_on_target"] = round_index * 2
        base["away_shots_on_target"] = round_index
        base["home_corners"] = round_index
        base["away_corners"] = max(0, round_index - 1)
    elif modality == "fixture_events":
        base["event_count"] = round_index
        base["latest_event_type"] = "Card" if round_index % 2 else "Goal"
    else:
        raise ValueError("R8_3_UNEXPECTED_FAKE_RESPONSE_CONTRACT")
    return base


def _expected_fake_source_fingerprint(
    *,
    run_id: str,
    subject_key: str,
    round_index: int,
    modality: str,
    sequence_number: int,
) -> str:
    return _sha(
        _expected_fake_normalized_payload(
            run_id=run_id,
            subject_key=subject_key,
            round_index=round_index,
            modality=modality,
            sequence_number=sequence_number,
        )
    )


class ScriptedFakeProviderFailure(RuntimeError):
    pass


class R83InjectedCrash(RuntimeError):
    def __init__(self, point: str) -> None:
        super().__init__(f"R8_3_INJECTED_CRASH:{point}")
        self.point = point


class DeterministicFakeFootballLiveProvider:
    def __init__(
        self,
        *,
        failure_slots: frozenset[tuple[int, str]] = frozenset(),
        terminal_status_rounds: frozenset[int] = frozenset(),
    ) -> None:
        self.failure_slots = frozenset(failure_slots)
        self.terminal_status_rounds = frozenset(terminal_status_rounds)
        self.call_count = 0
        self.call_count_by_modality: dict[str, int] = {}
        self.calls: list[tuple[int, str, int]] = []

    def _normalized_payload(
        self,
        *,
        run_id: str,
        subject_key: str,
        round_index: int,
        modality: str,
        sequence_number: int,
    ) -> Mapping[str, Any]:
        return _expected_fake_normalized_payload(
            run_id=run_id,
            subject_key=subject_key,
            round_index=round_index,
            modality=modality,
            sequence_number=sequence_number,
            terminal_status_rounds=self.terminal_status_rounds,
        )

    def peek(
        self,
        *,
        run_id: str,
        subject_key: str,
        round_index: int,
        modality: str,
        sequence_number: int,
        reservation_created_at: datetime,
    ) -> FakeProviderCapture:
        reservation_time = _aware_utc(
            reservation_created_at,
            name="reservation_created_at",
        )
        correlation_id = _round_correlation_id(run_id, round_index)
        payload = self._normalized_payload(
            run_id=run_id,
            subject_key=subject_key,
            round_index=round_index,
            modality=modality,
            sequence_number=sequence_number,
        )
        source_fp = _sha(payload)
        observed = reservation_time
        request = reservation_time + timedelta(milliseconds=1)
        response = reservation_time + timedelta(milliseconds=2)
        ingested = reservation_time + timedelta(milliseconds=3)
        normalized = reservation_time + timedelta(milliseconds=4)
        ready = reservation_time + timedelta(milliseconds=5)
        return FakeProviderCapture(
            run_id=run_id,
            round_index=round_index,
            modality=modality,
            sequence_number=sequence_number,
            correlation_id=correlation_id,
            observed_at=observed,
            request_started_at=request,
            response_received_at=response,
            ingested_at=ingested,
            normalized_at=normalized,
            feature_ready_at=ready,
            source_record_fingerprint=source_fp,
            normalized_payload=payload,
            fixture_terminal=bool(payload.get("fixture_terminal", False)),
        )

    def capture(
        self,
        *,
        run_id: str,
        subject_key: str,
        round_index: int,
        modality: str,
        sequence_number: int,
        reservation_created_at: datetime,
    ) -> FakeProviderCapture:
        self.call_count += 1
        self.call_count_by_modality[modality] = (
            self.call_count_by_modality.get(modality, 0) + 1
        )
        self.calls.append((round_index, modality, sequence_number))
        if (round_index, modality) in self.failure_slots:
            raise ScriptedFakeProviderFailure(
                f"SCRIPTED_FAKE_PROVIDER_FAILURE:{round_index}:{modality}"
            )
        return self.peek(
            run_id=run_id,
            subject_key=subject_key,
            round_index=round_index,
            modality=modality,
            sequence_number=sequence_number,
            reservation_created_at=reservation_created_at,
        )


@dataclass(frozen=True)
class FakeCallAttempt:
    run_id: str
    round_index: int
    modality: str
    attempt_index: int
    sequence_number: int
    correlation_id: str
    state: str
    attempted_at: datetime
    result_at: datetime | None
    source_record_fingerprint: str | None
    error_code: str | None


class SQLiteR83FakeExecutorJournal:
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
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                user_version = int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                )
                if user_version not in {0, _JOURNAL_USER_VERSION}:
                    raise ValueError(
                        "R8_3R2_JOURNAL_SCHEMA_VERSION_MISMATCH"
                    )

                for ddl in _JOURNAL_DDL.values():
                    connection.execute(
                        ddl.replace(
                            "CREATE TABLE ",
                            "CREATE TABLE IF NOT EXISTS ",
                            1,
                        )
                    )

                connection.execute(
                    f"PRAGMA user_version = {_JOURNAL_USER_VERSION}"
                )

                row = connection.execute(
                    """
                    SELECT payload_sha256
                    FROM r8_3_fake_journal_anchor
                    WHERE singleton_id = 1
                    """
                ).fetchone()

                if row is None:
                    self._rewrite_anchor(connection)
                else:
                    self._assert_integrity(connection)

                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _anchor_payload(connection: sqlite3.Connection) -> Mapping[str, Any]:
        meta = connection.execute(
            """
            SELECT
                run_id,
                manifest_fingerprint,
                plan_fingerprint,
                provider_key,
                subject_key,
                modalities_json,
                max_capture_rounds,
                max_total_fake_calls,
                resume_count,
                created_at,
                updated_at
            FROM r8_3_fake_run_meta
            ORDER BY run_id
            """
        ).fetchall()

        attempts = connection.execute(
            """
            SELECT
                run_id,
                round_index,
                modality,
                attempt_index,
                sequence_number,
                correlation_id,
                state,
                attempted_at,
                result_at,
                source_record_fingerprint,
                error_code,
                intent_binding_sha256,
                result_binding_sha256
            FROM r8_3_fake_call_attempt
            ORDER BY run_id, round_index, modality, attempt_index
            """
        ).fetchall()

        resume_events = connection.execute(
            """
            SELECT
                run_id,
                resume_index,
                resumed_at,
                control_state_before,
                control_state_version_before
            FROM r8_3_fake_resume_event
            ORDER BY run_id, resume_index
            """
        ).fetchall()

        stop_events = connection.execute(
            """
            SELECT
                run_id,
                stop_index,
                reason_code,
                stopped_at
            FROM r8_3_fake_stop_event
            ORDER BY run_id, stop_index
            """
        ).fetchall()

        return {
            "schema": "matrix.c2-r8-3r3-fake-executor-journal-anchor/3",
            "run_meta": [list(row) for row in meta],
            "attempts": [list(row) for row in attempts],
            "resume_events": [list(row) for row in resume_events],
            "stop_events": [list(row) for row in stop_events],
        }

    def _rewrite_anchor(self, connection: sqlite3.Connection) -> None:
        digest = _sha(self._anchor_payload(connection))
        connection.execute(
            """
            INSERT INTO r8_3_fake_journal_anchor(singleton_id, payload_sha256)
            VALUES (1, ?)
            ON CONFLICT(singleton_id) DO UPDATE SET payload_sha256 = excluded.payload_sha256
            """,
            (digest,),
        )

    def _assert_integrity(self, connection: sqlite3.Connection) -> None:
        user_version = int(
            connection.execute("PRAGMA user_version").fetchone()[0]
        )
        if user_version != _JOURNAL_USER_VERSION:
            raise ValueError("R8_3R2_JOURNAL_SCHEMA_VERSION_MISMATCH")

        namespace = connection.execute(
            """
            SELECT type, name
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
        expected_namespace = [
            ("table", "r8_3_fake_call_attempt"),
            ("table", "r8_3_fake_journal_anchor"),
            ("table", "r8_3_fake_resume_event"),
            ("table", "r8_3_fake_run_meta"),
            ("table", "r8_3_fake_stop_event"),
        ]
        if [
            (str(row[0]), str(row[1]))
            for row in namespace
        ] != expected_namespace:
            raise ValueError("R8_3R2_JOURNAL_NAMESPACE_MISMATCH")

        for table, expected_ddl in _JOURNAL_DDL.items():
            row = connection.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None or row[0] is None:
                raise ValueError("R8_3R2_JOURNAL_DDL_MISSING")
            if _normalize_sql(str(row[0])) != _normalize_sql(expected_ddl):
                raise ValueError(
                    "R8_3R2_JOURNAL_DDL_SEMANTICS_MISMATCH"
                )

        stored = connection.execute(
            """
            SELECT payload_sha256
            FROM r8_3_fake_journal_anchor
            WHERE singleton_id = 1
            """
        ).fetchone()
        if stored is None:
            raise ValueError("R8_3R2_JOURNAL_ANCHOR_MISSING")
        expected = _sha(self._anchor_payload(connection))
        if str(stored[0]) != expected:
            raise ValueError("R8_3R2_JOURNAL_ANCHOR_MISMATCH")

        meta_rows = connection.execute(
            """
            SELECT
                run_id,
                manifest_fingerprint,
                plan_fingerprint,
                provider_key,
                subject_key,
                modalities_json,
                max_capture_rounds,
                max_total_fake_calls,
                resume_count,
                created_at,
                updated_at
            FROM r8_3_fake_run_meta
            ORDER BY run_id
            """
        ).fetchall()

        meta_by_run: dict[str, tuple[Any, ...]] = {}
        for row in meta_rows:
            run_id = _sha256_hex(str(row[0]), name="run_id")
            _sha256_hex(str(row[1]), name="manifest_fingerprint")
            _sha256_hex(str(row[2]), name="plan_fingerprint")

            if str(row[3]) != R8_3_FAKE_PROVIDER_KEY:
                raise ValueError("R8_3R2_JOURNAL_REAL_PROVIDER_FORBIDDEN")

            subject_key = str(row[4])
            if not subject_key.startswith("fixture:"):
                raise ValueError("R8_3R2_JOURNAL_SUBJECT_INVALID")
            fixture_id = subject_key.split(":", 1)[1]
            if (
                not fixture_id
                or fixture_id[0] == "0"
                or not fixture_id.isascii()
                or not fixture_id.isdecimal()
            ):
                raise ValueError("R8_3R2_JOURNAL_SUBJECT_INVALID")

            modalities_raw = str(row[5])
            try:
                modalities = tuple(json.loads(modalities_raw))
            except (json.JSONDecodeError, TypeError) as error:
                raise ValueError(
                    "R8_3R2_JOURNAL_MODALITIES_INVALID"
                ) from error

            expected_modalities_raw = json.dumps(
                list(modalities),
                separators=(",", ":"),
                ensure_ascii=False,
            )
            if modalities_raw != expected_modalities_raw:
                raise ValueError(
                    "R8_3R2_JOURNAL_MODALITIES_CANONICAL_BYTES_MISMATCH"
                )
            if (
                not modalities
                or len(set(modalities)) != len(modalities)
                or any(
                    item not in {
                        "fixture_status",
                        "fixture_statistics",
                        "fixture_events",
                    }
                    for item in modalities
                )
            ):
                raise ValueError("R8_3R2_JOURNAL_MODALITIES_INVALID")

            max_rounds = _positive_int(
                int(row[6]),
                name="max_capture_rounds",
            )
            max_calls = _positive_int(
                int(row[7]),
                name="max_total_fake_calls",
            )
            resume_count = int(row[8])
            if resume_count < 0:
                raise ValueError("R8_3R2_JOURNAL_RESUME_COUNT_INVALID")

            created_text = str(row[9])
            updated_text = str(row[10])
            created = _aware_utc(
                datetime.fromisoformat(created_text),
                name="created_at",
            )
            updated = _aware_utc(
                datetime.fromisoformat(updated_text),
                name="updated_at",
            )
            if (
                created.isoformat() != created_text
                or updated.isoformat() != updated_text
            ):
                raise ValueError(
                    "R8_3R2_JOURNAL_TIMESTAMP_CANONICAL_FORM_REQUIRED"
                )
            if updated < created:
                raise ValueError("R8_3R2_JOURNAL_RUN_TIME_REGRESSION")

            meta_by_run[run_id] = (
                subject_key,
                modalities,
                max_rounds,
                max_calls,
                resume_count,
                created,
                updated,
            )

        resume_rows = connection.execute(
            """
            SELECT
                run_id,
                resume_index,
                resumed_at,
                control_state_before,
                control_state_version_before
            FROM r8_3_fake_resume_event
            ORDER BY run_id, resume_index
            """
        ).fetchall()

        resume_indexes_by_run: dict[str, list[int]] = {}
        resume_times_by_run: dict[str, list[datetime]] = {}
        resume_control_versions_by_run: dict[str, list[int]] = {}

        for row in resume_rows:
            run_id = _sha256_hex(str(row[0]), name="run_id")
            if run_id not in meta_by_run:
                raise ValueError("R8_3R3_JOURNAL_RESUME_EVENT_ORPHAN_RUN")
            resume_index = _positive_int(
                int(row[1]),
                name="resume_index",
            )
            resumed_text = str(row[2])
            resumed_at = _aware_utc(
                datetime.fromisoformat(resumed_text),
                name="resumed_at",
            )
            if resumed_at.isoformat() != resumed_text:
                raise ValueError(
                    "R8_3R3_JOURNAL_TIMESTAMP_CANONICAL_FORM_REQUIRED"
                )
            created = meta_by_run[run_id][5]
            if resumed_at < created:
                raise ValueError(
                    "R8_3R3_JOURNAL_RESUME_TIME_PRECEDES_RUN"
                )

            control_state_before = str(row[3])
            control_version_before = _positive_int(
                int(row[4]),
                name="control_state_version_before",
            )
            if control_state_before not in {
                "IN_PROGRESS",
                "RECOVERY_REQUIRED",
            }:
                raise ValueError(
                    "R8_3R3_JOURNAL_RESUME_CONTROL_STATE_INVALID"
                )
            if (
                control_state_before == "IN_PROGRESS"
                and control_version_before % 2 != 1
            ):
                raise ValueError(
                    "R8_3R3_JOURNAL_RESUME_CONTROL_VERSION_INVALID"
                )
            if (
                control_state_before == "RECOVERY_REQUIRED"
                and control_version_before % 2 != 0
            ):
                raise ValueError(
                    "R8_3R3_JOURNAL_RESUME_CONTROL_VERSION_INVALID"
                )

            resume_indexes_by_run.setdefault(run_id, []).append(
                resume_index
            )
            resume_times_by_run.setdefault(run_id, []).append(
                resumed_at
            )
            resume_control_versions_by_run.setdefault(
                run_id,
                [],
            ).append(control_version_before)

        for run_id, meta in meta_by_run.items():
            resume_count = int(meta[4])
            created = meta[5]
            updated = meta[6]
            indexes = resume_indexes_by_run.get(run_id, [])
            times = resume_times_by_run.get(run_id, [])
            control_versions = resume_control_versions_by_run.get(
                run_id,
                [],
            )

            if indexes != list(range(1, len(indexes) + 1)):
                raise ValueError("R8_3R3_JOURNAL_RESUME_INDEX_GAP")
            if len(indexes) != resume_count:
                raise ValueError(
                    "R8_3R3_JOURNAL_RESUME_COUNT_NOT_EVENT_DERIVED"
                )
            if any(
                later < earlier
                for earlier, later in zip(times, times[1:])
            ):
                raise ValueError(
                    "R8_3R3_JOURNAL_RESUME_TIME_REGRESSION"
                )
            if any(
                later < earlier
                for earlier, later in zip(
                    control_versions,
                    control_versions[1:],
                )
            ):
                raise ValueError(
                    "R8_3R3_JOURNAL_RESUME_CONTROL_VERSION_REGRESSION"
                )

            expected_updated = times[-1] if times else created
            if updated != expected_updated:
                raise ValueError(
                    "R8_3R3_JOURNAL_RUN_UPDATED_AT_NOT_EVENT_DERIVED"
                )

        stop_rows = connection.execute(
            """
            SELECT
                run_id,
                stop_index,
                reason_code,
                stopped_at
            FROM r8_3_fake_stop_event
            ORDER BY run_id, stop_index
            """
        ).fetchall()

        stop_indexes_by_run: dict[str, list[int]] = {}
        stop_times_by_run: dict[str, list[datetime]] = {}
        stop_codes_by_run: dict[str, list[str]] = {}

        for row in stop_rows:
            run_id = _sha256_hex(str(row[0]), name="run_id")
            if run_id not in meta_by_run:
                raise ValueError("R8_3R3_JOURNAL_STOP_EVENT_ORPHAN_RUN")
            stop_index = _positive_int(
                int(row[1]),
                name="stop_index",
            )
            reason_code = str(row[2])
            if reason_code not in R8_3_STOP_REASONS:
                raise ValueError(
                    "R8_3R3_JOURNAL_STOP_REASON_INVALID"
                )
            stopped_text = str(row[3])
            stopped_at = _aware_utc(
                datetime.fromisoformat(stopped_text),
                name="stopped_at",
            )
            if stopped_at.isoformat() != stopped_text:
                raise ValueError(
                    "R8_3R3_JOURNAL_TIMESTAMP_CANONICAL_FORM_REQUIRED"
                )
            if stopped_at < meta_by_run[run_id][5]:
                raise ValueError(
                    "R8_3R3_JOURNAL_STOP_TIME_PRECEDES_RUN"
                )
            stop_indexes_by_run.setdefault(run_id, []).append(
                stop_index
            )
            stop_times_by_run.setdefault(run_id, []).append(
                stopped_at
            )
            stop_codes_by_run.setdefault(run_id, []).append(
                reason_code
            )

        for run_id in meta_by_run:
            indexes = stop_indexes_by_run.get(run_id, [])
            times = stop_times_by_run.get(run_id, [])
            codes = stop_codes_by_run.get(run_id, [])
            if indexes != list(range(1, len(indexes) + 1)):
                raise ValueError("R8_3R3_JOURNAL_STOP_INDEX_GAP")
            if len(codes) != len(set(codes)):
                raise ValueError(
                    "R8_3R3_JOURNAL_STOP_REASON_DUPLICATE"
                )
            if any(
                later < earlier
                for earlier, later in zip(times, times[1:])
            ):
                raise ValueError(
                    "R8_3R3_JOURNAL_STOP_TIME_REGRESSION"
                )

        attempt_rows = connection.execute(
            """
            SELECT
                run_id,
                round_index,
                modality,
                attempt_index,
                sequence_number,
                correlation_id,
                state,
                attempted_at,
                result_at,
                source_record_fingerprint,
                error_code,
                intent_binding_sha256,
                result_binding_sha256
            FROM r8_3_fake_call_attempt
            ORDER BY run_id, round_index, modality, attempt_index
            """
        ).fetchall()

        slot_attempt_indexes: dict[
            tuple[str, int, str],
            list[int],
        ] = {}
        slot_sequence: dict[tuple[str, int, str], int] = {}
        slot_correlation: dict[tuple[str, int, str], str] = {}
        attempt_counts_by_run: dict[str, int] = {}
        last_attempted_by_slot: dict[
            tuple[str, int, str],
            datetime,
        ] = {}

        for row in attempt_rows:
            run_id = _sha256_hex(str(row[0]), name="run_id")
            if run_id not in meta_by_run:
                raise ValueError("R8_3R2_JOURNAL_ATTEMPT_ORPHAN_RUN")

            round_index = _positive_int(
                int(row[1]),
                name="round_index",
            )
            modality = str(row[2])
            attempt_index = _positive_int(
                int(row[3]),
                name="attempt_index",
            )
            sequence_number = _positive_int(
                int(row[4]),
                name="sequence_number",
            )
            correlation_id = _sha256_hex(
                str(row[5]),
                name="correlation_id",
            )
            state = str(row[6])
            intent_binding = _sha256_hex(
                str(row[11]),
                name="intent_binding",
            )
            result_binding = (
                None
                if row[12] is None
                else _sha256_hex(
                    str(row[12]),
                    name="result_binding",
                )
            )

            attempted_text = str(row[7])
            attempted_at = _aware_utc(
                datetime.fromisoformat(attempted_text),
                name="attempted_at",
            )
            if attempted_at.isoformat() != attempted_text:
                raise ValueError(
                    "R8_3R2_JOURNAL_TIMESTAMP_CANONICAL_FORM_REQUIRED"
                )

            expected_intent_binding = _attempt_intent_binding(
                run_id=run_id,
                round_index=round_index,
                modality=modality,
                attempt_index=attempt_index,
                sequence_number=sequence_number,
                correlation_id=correlation_id,
                attempted_at=attempted_text,
            )
            if intent_binding != expected_intent_binding:
                raise ValueError(
                    "R8_3R2_JOURNAL_INTENT_BINDING_MISMATCH"
                )

            result_text = None if row[8] is None else str(row[8])
            result_at = (
                None
                if result_text is None
                else _aware_utc(
                    datetime.fromisoformat(result_text),
                    name="result_at",
                )
            )
            if (
                result_at is not None
                and result_at.isoformat() != result_text
            ):
                raise ValueError(
                    "R8_3R2_JOURNAL_TIMESTAMP_CANONICAL_FORM_REQUIRED"
                )

            source_fp = None if row[9] is None else str(row[9])
            error_code = None if row[10] is None else str(row[10])

            subject_key, modalities, max_rounds, max_calls, _, _, _ = (
                meta_by_run[run_id]
            )
            if round_index > max_rounds or modality not in modalities:
                raise ValueError("R8_3R2_JOURNAL_SLOT_OUTSIDE_PLAN")

            expected_correlation = _round_correlation_id(
                run_id,
                round_index,
            )
            if correlation_id != expected_correlation:
                raise ValueError(
                    "R8_3R2_JOURNAL_CORRELATION_PROVENANCE_MISMATCH"
                )

            slot_key = (run_id, round_index, modality)
            slot_attempt_indexes.setdefault(
                slot_key,
                [],
            ).append(attempt_index)

            if (
                slot_key in slot_sequence
                and slot_sequence[slot_key] != sequence_number
            ):
                raise ValueError(
                    "R8_3R2_JOURNAL_SLOT_SEQUENCE_MUTATION"
                )
            slot_sequence[slot_key] = sequence_number

            if (
                slot_key in slot_correlation
                and slot_correlation[slot_key] != correlation_id
            ):
                raise ValueError(
                    "R8_3R2_JOURNAL_SLOT_CORRELATION_MUTATION"
                )
            slot_correlation[slot_key] = correlation_id

            prior_attempted = last_attempted_by_slot.get(slot_key)
            if (
                prior_attempted is not None
                and attempted_at < prior_attempted
            ):
                raise ValueError(
                    "R8_3R2_JOURNAL_ATTEMPT_TIME_REGRESSION"
                )
            last_attempted_by_slot[slot_key] = attempted_at

            attempt_counts_by_run[run_id] = (
                attempt_counts_by_run.get(run_id, 0) + 1
            )
            if state not in _JOURNAL_STATES:
                raise ValueError(
                    "R8_3R2_JOURNAL_ATTEMPT_STATE_INVALID"
                )

            if state == "INTENT":
                if (
                    result_at is not None
                    or source_fp is not None
                    or error_code is not None
                    or result_binding is not None
                ):
                    raise ValueError(
                        "R8_3R2_JOURNAL_INTENT_RESULT_FIELDS_FORBIDDEN"
                    )

            elif state == "SUCCEEDED":
                if (
                    result_at is None
                    or source_fp is None
                    or error_code is not None
                    or result_binding is None
                ):
                    raise ValueError(
                        "R8_3R2_JOURNAL_SUCCESS_FIELDS_INVALID"
                    )
                source_fp = _sha256_hex(
                    source_fp,
                    name="source_record_fingerprint",
                )

            elif state == "FAILED":
                if (
                    result_at is None
                    or source_fp is not None
                    or not error_code
                    or result_binding is None
                ):
                    raise ValueError(
                        "R8_3R2_JOURNAL_FAILURE_FIELDS_INVALID"
                    )

            if result_at is not None and result_at < attempted_at:
                raise ValueError(
                    "R8_3R2_JOURNAL_RESULT_TIME_REGRESSION"
                )

            if state in {"SUCCEEDED", "FAILED"}:
                expected_result_binding = _attempt_result_binding(
                    intent_binding_sha256=intent_binding,
                    state=state,
                    result_at=result_text,
                    source_record_fingerprint=source_fp,
                    error_code=error_code,
                )
                if result_binding != expected_result_binding:
                    raise ValueError(
                        "R8_3R2_JOURNAL_RESULT_BINDING_MISMATCH"
                    )

        for slot_key, indexes in slot_attempt_indexes.items():
            if indexes != list(range(1, len(indexes) + 1)):
                raise ValueError(
                    "R8_3R2_JOURNAL_ATTEMPT_INDEX_GAP"
                )

        for run_id, count in attempt_counts_by_run.items():
            max_calls = int(meta_by_run[run_id][3])
            if count > max_calls:
                raise ValueError(
                    "R8_3R2_JOURNAL_FAKE_CALL_BUDGET_EXCEEDED"
                )

    def register_run(
        self,
        *,
        manifest: BoundedFootballLiveRunManifest,
        authority: R83OfflineFakeExecutionAuthorityPlan,
        registered_at: datetime,
    ) -> None:
        authority.validate_manifest(manifest)
        registered = _aware_utc(registered_at, name="registered_at")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                row = connection.execute(
                    """
                    SELECT
                        manifest_fingerprint,
                        plan_fingerprint,
                        provider_key,
                        subject_key,
                        modalities_json,
                        max_capture_rounds,
                        max_total_fake_calls
                    FROM r8_3_fake_run_meta
                    WHERE run_id = ?
                    """,
                    (manifest.run_id,),
                ).fetchone()
                modalities_json = json.dumps(
                    list(manifest.modalities),
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                expected = (
                    manifest.manifest_fingerprint,
                    authority.plan_fingerprint,
                    manifest.provider_key,
                    manifest.subject_key,
                    modalities_json,
                    manifest.max_capture_rounds,
                    manifest.max_total_provider_calls,
                )
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO r8_3_fake_run_meta (
                            run_id,
                            manifest_fingerprint,
                            plan_fingerprint,
                            provider_key,
                            subject_key,
                            modalities_json,
                            max_capture_rounds,
                            max_total_fake_calls,
                            resume_count,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                        """,
                        (
                            manifest.run_id,
                            *expected,
                            registered.isoformat(),
                            registered.isoformat(),
                        ),
                    )
                else:
                    actual = (
                        str(row[0]),
                        str(row[1]),
                        str(row[2]),
                        str(row[3]),
                        str(row[4]),
                        int(row[5]),
                        int(row[6]),
                    )
                    if actual != expected:
                        raise ValueError("R8_3_JOURNAL_RUN_IDENTITY_MISMATCH")
                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def increment_resume(
        self,
        run_id: str,
        *,
        changed_at: datetime,
        control_state_before: str,
        control_state_version_before: int,
    ) -> int:
        changed = _aware_utc(changed_at, name="changed_at")
        control_state = str(control_state_before)
        control_version = _positive_int(
            control_state_version_before,
            name="control_state_version_before",
        )
        if control_state not in {"IN_PROGRESS", "RECOVERY_REQUIRED"}:
            raise ValueError(
                "R8_3R3_RESUME_CONTROL_STATE_INVALID"
            )
        if control_state == "IN_PROGRESS" and control_version % 2 != 1:
            raise ValueError(
                "R8_3R3_RESUME_CONTROL_VERSION_INVALID"
            )
        if (
            control_state == "RECOVERY_REQUIRED"
            and control_version % 2 != 0
        ):
            raise ValueError(
                "R8_3R3_RESUME_CONTROL_VERSION_INVALID"
            )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                row = connection.execute(
                    """
                    SELECT
                        resume_count,
                        updated_at
                    FROM r8_3_fake_run_meta
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("R8_3R3_JOURNAL_RUN_NOT_FOUND")

                prior = _aware_utc(
                    datetime.fromisoformat(str(row[1])),
                    name="journal_updated_at",
                )
                if changed < prior:
                    raise ValueError(
                        "R8_3R3_JOURNAL_RUN_TIME_REGRESSION"
                    )

                value = int(row[0]) + 1
                connection.execute(
                    """
                    INSERT INTO r8_3_fake_resume_event (
                        run_id,
                        resume_index,
                        resumed_at,
                        control_state_before,
                        control_state_version_before
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        value,
                        changed.isoformat(),
                        control_state,
                        control_version,
                    ),
                )
                connection.execute(
                    """
                    UPDATE r8_3_fake_run_meta
                    SET resume_count = ?,
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (
                        value,
                        changed.isoformat(),
                        run_id,
                    ),
                )

                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return value

    def record_stop_reason(
        self,
        run_id: str,
        *,
        reason_code: str,
        stopped_at: datetime,
    ) -> None:
        code = str(reason_code)
        if code not in R8_3_STOP_REASONS:
            raise ValueError("R8_3R3_STOP_REASON_INVALID")
        stopped = _aware_utc(stopped_at, name="stopped_at")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                meta = connection.execute(
                    """
                    SELECT created_at
                    FROM r8_3_fake_run_meta
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                if meta is None:
                    raise ValueError("R8_3R3_JOURNAL_RUN_NOT_FOUND")

                existing = connection.execute(
                    """
                    SELECT stopped_at
                    FROM r8_3_fake_stop_event
                    WHERE run_id = ? AND reason_code = ?
                    """,
                    (run_id, code),
                ).fetchone()
                if existing is not None:
                    connection.execute("COMMIT")
                    return

                prior = connection.execute(
                    """
                    SELECT
                        COALESCE(MAX(stop_index), 0),
                        MAX(stopped_at)
                    FROM r8_3_fake_stop_event
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                stop_index = int(prior[0]) + 1
                if prior[1] is not None:
                    prior_time = _aware_utc(
                        datetime.fromisoformat(str(prior[1])),
                        name="prior_stopped_at",
                    )
                    if stopped < prior_time:
                        raise ValueError(
                            "R8_3R3_JOURNAL_STOP_TIME_REGRESSION"
                        )

                connection.execute(
                    """
                    INSERT INTO r8_3_fake_stop_event(
                        run_id,
                        stop_index,
                        reason_code,
                        stopped_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        stop_index,
                        code,
                        stopped.isoformat(),
                    ),
                )
                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def stop_reasons(self, run_id: str) -> tuple[str, ...]:
        with self._connect() as connection:
            self._assert_integrity(connection)
            rows = connection.execute(
                """
                SELECT reason_code
                FROM r8_3_fake_stop_event
                WHERE run_id = ?
                ORDER BY stop_index
                """,
                (run_id,),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def latest_attempt_for_slot(
        self,
        run_id: str,
        *,
        round_index: int,
        modality: str,
    ) -> FakeCallAttempt | None:
        with self._connect() as connection:
            self._assert_integrity(connection)
            row = connection.execute(
                """
                SELECT MAX(attempt_index)
                FROM r8_3_fake_call_attempt
                WHERE
                    run_id = ?
                    AND round_index = ?
                    AND modality = ?
                """,
                (run_id, round_index, modality),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return self.get_attempt(
            run_id,
            round_index=round_index,
            modality=modality,
            attempt_index=int(row[0]),
        )

    def begin_attempt(
        self,
        *,
        run_id: str,
        round_index: int,
        modality: str,
        sequence_number: int,
        correlation_id: str,
        attempted_at: datetime,
    ) -> FakeCallAttempt:
        round_number = _positive_int(round_index, name="round_index")
        sequence = _positive_int(sequence_number, name="sequence_number")
        correlation = _sha256_hex(correlation_id, name="correlation_id")
        attempted = _aware_utc(attempted_at, name="attempted_at")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                meta = connection.execute(
                    "SELECT max_total_fake_calls FROM r8_3_fake_run_meta WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if meta is None:
                    raise ValueError("R8_3_JOURNAL_RUN_NOT_FOUND")
                count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM r8_3_fake_call_attempt WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()[0]
                )
                if count >= int(meta[0]):
                    raise ValueError("R8_3_TOTAL_FAKE_CALL_BUDGET_REACHED")
                prior = connection.execute(
                    """
                    SELECT MAX(attempt_index)
                    FROM r8_3_fake_call_attempt
                    WHERE run_id = ? AND round_index = ? AND modality = ?
                    """,
                    (run_id, round_number, modality),
                ).fetchone()[0]
                attempt_index = 1 if prior is None else int(prior) + 1
                attempted_text = attempted.isoformat()
                intent_binding = _attempt_intent_binding(
                    run_id=run_id,
                    round_index=round_number,
                    modality=modality,
                    attempt_index=attempt_index,
                    sequence_number=sequence,
                    correlation_id=correlation,
                    attempted_at=attempted_text,
                )
                connection.execute(
                    """
                    INSERT INTO r8_3_fake_call_attempt (
                        run_id,
                        round_index,
                        modality,
                        attempt_index,
                        sequence_number,
                        correlation_id,
                        state,
                        attempted_at,
                        result_at,
                        source_record_fingerprint,
                        error_code,
                        intent_binding_sha256,
                        result_binding_sha256
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, 'INTENT', ?,
                        NULL, NULL, NULL, ?, NULL
                    )
                    """,
                    (
                        run_id,
                        round_number,
                        modality,
                        attempt_index,
                        sequence,
                        correlation,
                        attempted_text,
                        intent_binding,
                    ),
                )
                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_attempt(
            run_id,
            round_index=round_number,
            modality=modality,
            attempt_index=attempt_index,
        )

    def resolve_attempt(
        self,
        *,
        run_id: str,
        round_index: int,
        modality: str,
        attempt_index: int,
        succeeded: bool,
        result_at: datetime,
        source_record_fingerprint: str | None = None,
        error_code: str | None = None,
    ) -> FakeCallAttempt:
        result = _aware_utc(result_at, name="result_at")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_integrity(connection)
                row = connection.execute(
                    """
                    SELECT state, attempted_at, intent_binding_sha256
                    FROM r8_3_fake_call_attempt
                    WHERE run_id = ? AND round_index = ? AND modality = ? AND attempt_index = ?
                    """,
                    (run_id, round_index, modality, attempt_index),
                ).fetchone()
                if row is None:
                    raise ValueError("R8_3_JOURNAL_ATTEMPT_NOT_FOUND")
                if str(row[0]) != "INTENT":
                    raise ValueError("R8_3_JOURNAL_ATTEMPT_ALREADY_RESOLVED")
                attempted = _aware_utc(
                    datetime.fromisoformat(str(row[1])),
                    name="attempted_at",
                )
                if result < attempted:
                    raise ValueError("R8_3_JOURNAL_RESULT_TIME_REGRESSION")
                intent_binding = _sha256_hex(
                    str(row[2]),
                    name="intent_binding",
                )
                result_text = result.isoformat()
                if succeeded:
                    source_fp = _sha256_hex(
                        str(source_record_fingerprint),
                        name="source_record_fingerprint",
                    )
                    result_binding = _attempt_result_binding(
                        intent_binding_sha256=intent_binding,
                        state="SUCCEEDED",
                        result_at=result_text,
                        source_record_fingerprint=source_fp,
                        error_code=None,
                    )
                    connection.execute(
                        """
                        UPDATE r8_3_fake_call_attempt
                        SET state = 'SUCCEEDED',
                            result_at = ?,
                            source_record_fingerprint = ?,
                            error_code = NULL,
                            result_binding_sha256 = ?
                        WHERE
                            run_id = ?
                            AND round_index = ?
                            AND modality = ?
                            AND attempt_index = ?
                        """,
                        (
                            result_text,
                            source_fp,
                            result_binding,
                            run_id,
                            round_index,
                            modality,
                            attempt_index,
                        ),
                    )
                else:
                    code = _nonempty(str(error_code), name="error_code")
                    result_binding = _attempt_result_binding(
                        intent_binding_sha256=intent_binding,
                        state="FAILED",
                        result_at=result_text,
                        source_record_fingerprint=None,
                        error_code=code,
                    )
                    connection.execute(
                        """
                        UPDATE r8_3_fake_call_attempt
                        SET state = 'FAILED',
                            result_at = ?,
                            source_record_fingerprint = NULL,
                            error_code = ?,
                            result_binding_sha256 = ?
                        WHERE
                            run_id = ?
                            AND round_index = ?
                            AND modality = ?
                            AND attempt_index = ?
                        """,
                        (
                            result_text,
                            code,
                            result_binding,
                            run_id,
                            round_index,
                            modality,
                            attempt_index,
                        ),
                    )
                self._rewrite_anchor(connection)
                self._assert_integrity(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_attempt(
            run_id,
            round_index=round_index,
            modality=modality,
            attempt_index=attempt_index,
        )

    def get_attempt(
        self,
        run_id: str,
        *,
        round_index: int,
        modality: str,
        attempt_index: int,
    ) -> FakeCallAttempt:
        with self._connect() as connection:
            self._assert_integrity(connection)
            row = connection.execute(
                """
                SELECT
                    run_id,
                    round_index,
                    modality,
                    attempt_index,
                    sequence_number,
                    correlation_id,
                    state,
                    attempted_at,
                    result_at,
                    source_record_fingerprint,
                    error_code
                FROM r8_3_fake_call_attempt
                WHERE run_id = ? AND round_index = ? AND modality = ? AND attempt_index = ?
                """,
                (run_id, round_index, modality, attempt_index),
            ).fetchone()
        if row is None:
            raise ValueError("R8_3_JOURNAL_ATTEMPT_NOT_FOUND")
        return FakeCallAttempt(
            run_id=str(row[0]),
            round_index=int(row[1]),
            modality=str(row[2]),
            attempt_index=int(row[3]),
            sequence_number=int(row[4]),
            correlation_id=str(row[5]),
            state=str(row[6]),
            attempted_at=_aware_utc(
                datetime.fromisoformat(str(row[7])),
                name="attempted_at",
            ),
            result_at=(
                None
                if row[8] is None
                else _aware_utc(
                    datetime.fromisoformat(str(row[8])),
                    name="result_at",
                )
            ),
            source_record_fingerprint=(
                None if row[9] is None else str(row[9])
            ),
            error_code=None if row[10] is None else str(row[10]),
        )

    def _assert_cross_ledger_integrity(
        self,
        *,
        control_store: SQLiteBoundedFootballLiveControlStore,
        evidence_store: SQLiteFootballLiveObservationStore,
    ) -> None:
        if not control_store.audit_integrity():
            raise ValueError(
                "R8_3R3_CONTROL_LEDGER_INTEGRITY_REQUIRED"
            )
        if not evidence_store.audit_integrity():
            raise ValueError(
                "R8_3R3_EVIDENCE_LEDGER_INTEGRITY_REQUIRED"
            )

        with self._connect() as journal_connection:
            self._assert_integrity(journal_connection)
            meta_rows = journal_connection.execute(
                """
                SELECT
                    run_id,
                    provider_key,
                    subject_key,
                    resume_count,
                    modalities_json,
                    max_capture_rounds
                FROM r8_3_fake_run_meta
                ORDER BY run_id
                """
            ).fetchall()
            attempts = journal_connection.execute(
                """
                SELECT
                    run_id,
                    round_index,
                    modality,
                    attempt_index,
                    sequence_number,
                    correlation_id,
                    state,
                    source_record_fingerprint,
                    error_code
                FROM r8_3_fake_call_attempt
                ORDER BY
                    run_id,
                    round_index,
                    modality,
                    attempt_index
                """
            ).fetchall()
            resume_events = journal_connection.execute(
                """
                SELECT
                    run_id,
                    resume_index,
                    control_state_before,
                    control_state_version_before
                FROM r8_3_fake_resume_event
                ORDER BY run_id, resume_index
                """
            ).fetchall()
            stop_events = journal_connection.execute(
                """
                SELECT
                    run_id,
                    stop_index,
                    reason_code,
                    stopped_at
                FROM r8_3_fake_stop_event
                ORDER BY run_id, stop_index
                """
            ).fetchall()

        meta_by_run = {
            str(row[0]): (
                str(row[1]),
                str(row[2]),
                int(row[3]),
                tuple(json.loads(str(row[4]))),
                int(row[5]),
            )
            for row in meta_rows
        }

        attempts_by_slot: dict[
            tuple[str, int, str],
            list[tuple[Any, ...]],
        ] = {}
        for row in attempts:
            key = (str(row[0]), int(row[1]), str(row[2]))
            attempts_by_slot.setdefault(key, []).append(row)

        resume_by_run: dict[str, list[tuple[Any, ...]]] = {}
        for row in resume_events:
            resume_by_run.setdefault(str(row[0]), []).append(row)

        stop_by_run: dict[str, list[tuple[str, datetime]]] = {}
        for row in stop_events:
            stop_by_run.setdefault(str(row[0]), []).append(
                (
                    str(row[2]),
                    _aware_utc(
                        datetime.fromisoformat(str(row[3])),
                        name="stopped_at",
                    ),
                )
            )

        with sqlite3.connect(control_store.path) as control_connection:
            for row in attempts:
                run_id = str(row[0])
                round_index = int(row[1])
                modality = str(row[2])
                sequence_number = int(row[4])

                reservation = control_connection.execute(
                    """
                    SELECT sequence_number
                    FROM football_bounded_sequence_reservation
                    WHERE
                        run_id = ?
                        AND round_index = ?
                        AND modality = ?
                    """,
                    (
                        run_id,
                        round_index,
                        modality,
                    ),
                ).fetchone()
                if reservation is None:
                    raise ValueError(
                        "R8_3R3_JOURNAL_ATTEMPT_WITHOUT_CONTROL_RESERVATION"
                    )
                if int(reservation[0]) != sequence_number:
                    raise ValueError(
                        "R8_3R3_JOURNAL_SEQUENCE_NOT_BOUND_TO_CONTROL"
                    )

            for run_id in meta_by_run:
                reservations = control_connection.execute(
                    """
                    SELECT
                        round_index,
                        modality,
                        sequence_number,
                        state
                    FROM football_bounded_sequence_reservation
                    WHERE run_id = ?
                    ORDER BY round_index, modality
                    """,
                    (run_id,),
                ).fetchall()

                for reservation in reservations:
                    round_index = int(reservation[0])
                    modality = str(reservation[1])
                    sequence_number = int(reservation[2])
                    state = str(reservation[3])
                    if state != "COMMITTED":
                        continue

                    slot_attempts = attempts_by_slot.get(
                        (run_id, round_index, modality),
                        [],
                    )
                    succeeded = [
                        item
                        for item in slot_attempts
                        if str(item[6]) == "SUCCEEDED"
                        and int(item[4]) == sequence_number
                    ]
                    if len(succeeded) != 1:
                        raise ValueError(
                            "R8_3R3_COMMITTED_RESERVATION_WITHOUT_SINGLE_SUCCESS"
                        )

                snapshot = control_store.get_run(run_id)
                events = resume_by_run.get(run_id, [])
                resume_count = meta_by_run[run_id][2]
                if len(events) != resume_count:
                    raise ValueError(
                        "R8_3R3_RESUME_EVENT_COUNT_CROSS_LEDGER_MISMATCH"
                    )

                prior_consumed_version = 0
                for event in events:
                    state_before = str(event[2])
                    version_before = int(event[3])
                    if version_before > snapshot.state_version:
                        raise ValueError(
                            "R8_3R4_RESUME_EVENT_VERSION_EXCEEDS_CONTROL"
                        )
                    if version_before < prior_consumed_version:
                        raise ValueError(
                            "R8_3R4_RESUME_TRANSITION_SPAN_OVERLAP"
                        )
                    consumed_version = (
                        version_before + 2
                        if state_before == "IN_PROGRESS"
                        else version_before + 1
                    )
                    if consumed_version > snapshot.state_version:
                        raise ValueError(
                            "R8_3R4_RESUME_TRANSITION_SPAN_EXCEEDS_CONTROL"
                        )
                    prior_consumed_version = consumed_version
                    if snapshot.state in {"COMPLETED", "ABORTED"}:
                        if consumed_version >= snapshot.state_version:
                            raise ValueError(
                                "R8_3R4_RESUME_EVENT_CONSUMES_TERMINAL_TRANSITION"
                            )
                    elif snapshot.state == "PLANNED":
                        raise ValueError(
                            "R8_3R4_RESUME_EVENT_ON_PLANNED_CONTROL_RUN"
                        )

                reasons = stop_by_run.get(run_id, [])
                if snapshot.state in {"COMPLETED", "ABORTED"}:
                    if len(reasons) != 1:
                        raise ValueError(
                            "R8_3R4_TERMINAL_RUN_REQUIRES_SINGLE_DURABLE_STOP_REASON"
                        )
                    reason_code, stopped_at = reasons[0]
                    if stopped_at > snapshot.updated_at:
                        raise ValueError(
                            "R8_3R4_STOP_TIME_POSTDATES_TERMINAL_CONTROL_STATE"
                        )
                    if snapshot.state == "COMPLETED":
                        if reason_code not in {
                            "CAPTURE_ROUND_LIMIT_REACHED",
                            "FIXTURE_TERMINAL_STATUS_WHEN_CONFIGURED",
                        }:
                            raise ValueError(
                                "R8_3R4_COMPLETED_STOP_REASON_CAUSALITY_MISMATCH"
                            )
                    else:
                        if reason_code in {
                            "CAPTURE_ROUND_LIMIT_REACHED",
                            "FIXTURE_TERMINAL_STATUS_WHEN_CONFIGURED",
                        }:
                            raise ValueError(
                                "R8_3R4_ABORTED_STOP_REASON_CAUSALITY_MISMATCH"
                            )
                if snapshot.state == "COMPLETED" and reasons:
                    reason_code = reasons[0][0]
                    modalities = meta_by_run[run_id][3]
                    max_rounds = meta_by_run[run_id][4]
                    if reason_code == "CAPTURE_ROUND_LIMIT_REACHED":
                        expected_slots = max_rounds * len(modalities)
                        committed_slots = sum(
                            1
                            for reservation in reservations
                            if str(reservation[3]) == "COMMITTED"
                        )
                        if committed_slots != expected_slots:
                            raise ValueError(
                                "R8_3R4_CAPTURE_LIMIT_REASON_WITH_INCOMPLETE_PLAN"
                            )

                if snapshot.state == "ABORTED" and reasons:
                    reason_code = reasons[0][0]
                    if reason_code == "SCRIPTED_FAKE_PROVIDER_FAILURE":
                        abandoned = [
                            reservation
                            for reservation in reservations
                            if str(reservation[3]) == "ABANDONED"
                        ]
                        if not abandoned:
                            raise ValueError(
                                "R8_3R4_SCRIPTED_FAILURE_WITHOUT_ABANDONED_SLOT"
                            )
                        for reservation in abandoned:
                            round_index = int(reservation[0])
                            modality = str(reservation[1])
                            sequence_number = int(reservation[2])
                            slot_attempts = attempts_by_slot.get(
                                (run_id, round_index, modality),
                                [],
                            )
                            failed = [
                                item
                                for item in slot_attempts
                                if str(item[6]) == "FAILED"
                                and int(item[4]) == sequence_number
                                and str(item[8])
                                == "SCRIPTED_FAKE_PROVIDER_FAILURE"
                            ]
                            if len(failed) != 1:
                                raise ValueError(
                                    "R8_3R4_ABANDONED_FAILURE_WITHOUT_SINGLE_FAILED_ATTEMPT"
                                )

        with sqlite3.connect(evidence_store.path) as evidence_connection:
            for row in attempts:
                if str(row[6]) != "SUCCEEDED":
                    continue

                run_id = str(row[0])
                modality = str(row[2])
                sequence_number = int(row[4])
                correlation_id = str(row[5])
                source_fp = str(row[7])
                provider_key, subject_key, _, _, _ = meta_by_run[run_id]

                evidence = evidence_connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM football_live_observation
                    WHERE
                        subject_key = ?
                        AND provider_key = ?
                        AND modality = ?
                        AND correlation_id = ?
                        AND sequence_id = ?
                        AND source_record_fingerprint = ?
                        AND status = ?
                    """,
                    (
                        subject_key,
                        provider_key,
                        modality,
                        correlation_id,
                        sequence_number,
                        source_fp,
                        SEQUENCE_ACCEPTED,
                    ),
                ).fetchone()

                if evidence is None or int(evidence[0]) != 1:
                    raise ValueError(
                        "R8_3R3_JOURNAL_SUCCESS_NOT_BOUND_TO_EVIDENCE"
                    )

    def audit_cross_ledger_integrity(
        self,
        *,
        control_store: SQLiteBoundedFootballLiveControlStore,
        evidence_store: SQLiteFootballLiveObservationStore,
    ) -> bool:
        try:
            self._assert_cross_ledger_integrity(
                control_store=control_store,
                evidence_store=evidence_store,
            )
            return True
        except (
            ValueError,
            sqlite3.Error,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ):
            return False

    def counts(self, run_id: str) -> Mapping[str, Any]:
        with self._connect() as connection:
            self._assert_integrity(connection)
            meta = connection.execute(
                "SELECT resume_count FROM r8_3_fake_run_meta WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if meta is None:
                raise ValueError("R8_3_JOURNAL_RUN_NOT_FOUND")
            rows = connection.execute(
                """
                SELECT modality, state, COUNT(*)
                FROM r8_3_fake_call_attempt
                WHERE run_id = ?
                GROUP BY modality, state
                """,
                (run_id,),
            ).fetchall()
        attempted = 0
        succeeded = 0
        failed = 0
        by_modality: dict[str, int] = {}
        for modality, state, count in rows:
            n = int(count)
            attempted += n
            by_modality[str(modality)] = by_modality.get(str(modality), 0) + n
            if str(state) == "SUCCEEDED":
                succeeded += n
            elif str(state) == "FAILED":
                failed += n
        return {
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": failed,
            "uncertain": attempted - succeeded - failed,
            "by_modality": dict(sorted(by_modality.items())),
            "resume_count": int(meta[0]),
        }

    def audit_integrity(self) -> bool:
        try:
            with self._connect() as connection:
                self._assert_integrity(connection)
            return True
        except (ValueError, sqlite3.Error, TypeError, KeyError, json.JSONDecodeError):
            return False


@dataclass(frozen=True)
class FakeProviderBoundedRunTelemetry:
    run_id: str
    plan_fingerprint: str
    run_state: str
    planned_rounds: int
    started_rounds: int
    closed_rounds: int
    planned_slots: int
    reserved_slots: int
    committed_slots: int
    abandoned_slots: int
    fake_calls_attempted: int
    fake_calls_succeeded: int
    fake_calls_failed: int
    fake_calls_uncertain: int
    fake_calls_by_modality: Mapping[str, int]
    sequence_numbers_by_slot: Mapping[str, int]
    correlation_id_by_round: Mapping[int, str]
    duplicate_source_count: int
    quarantine_count: int
    integrity_failure_count: int
    resume_count: int
    stop_reason_codes: tuple[str, ...]
    run_started_at: datetime
    run_finished_at: datetime
    runtime_ms: int
    production_admissible: bool = False
    real_provider_execution_authorized: bool = False
    repeated_provider_execution_authorized: bool = False
    automatic_provider_switch: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False


class _TelemetryBuilder:
    def __init__(self) -> None:
        self.started_rounds: set[int] = set()
        self.closed_rounds: set[int] = set()
        self.reserved_slots = 0
        self.committed_slots = 0
        self.abandoned_slots = 0
        self.sequence_numbers_by_slot: dict[str, int] = {}
        self.correlation_id_by_round: dict[int, str] = {}
        self.duplicate_source_count = 0
        self.quarantine_count = 0
        self.integrity_failure_count = 0
        self.stop_reasons: list[str] = []

    def stop(self, code: str) -> None:
        if code not in R8_3_STOP_REASONS:
            raise ValueError("R8_3_STOP_REASON_INVALID")
        if code not in self.stop_reasons:
            self.stop_reasons.append(code)


def _checked_now(
    clock: Callable[[], datetime],
    *,
    last: datetime | None,
) -> datetime:
    value = _aware_utc(clock(), name="trusted_clock")
    if last is not None and value < last:
        raise ValueError("R8_3_CLOCK_REGRESSION")
    return value


def _maybe_crash(crash_point: str | None, point: str) -> None:
    if crash_point is None:
        return
    if crash_point not in R8_3_CRASH_POINTS:
        raise ValueError("R8_3_CRASH_POINT_INVALID")
    if crash_point == point:
        raise R83InjectedCrash(point)


def _slot_key(round_index: int, modality: str) -> str:
    return f"{round_index}:{modality}"


def _ensure_integrity(
    *,
    control_store: SQLiteBoundedFootballLiveControlStore,
    evidence_store: SQLiteFootballLiveObservationStore,
    journal: SQLiteR83FakeExecutorJournal,
) -> None:
    if not control_store.audit_integrity():
        raise ValueError("R8_3_SEQUENCE_ALLOCATOR_INTEGRITY_FAILURE")
    if not evidence_store.audit_integrity():
        raise ValueError("R8_3_DURABLE_EVIDENCE_INTEGRITY_FAILURE")
    if not journal.audit_integrity():
        raise ValueError("R8_3_FAKE_JOURNAL_INTEGRITY_FAILURE")
    if not journal.audit_cross_ledger_integrity(
        control_store=control_store,
        evidence_store=evidence_store,
    ):
        raise ValueError("R8_3R3_CROSS_LEDGER_INTEGRITY_FAILURE")


def _transition_to_in_progress(
    snapshot: RunControlSnapshot,
    *,
    resume: bool,
    control_store: SQLiteBoundedFootballLiveControlStore,
    guard: BoundedExecutorProcessScopeGuard,
    lease: ProcessScopeLease,
    now: Callable[[], datetime],
) -> RunControlSnapshot:
    if snapshot.state == "PLANNED":
        changed = now()
        return control_store.transition_run_state(
            snapshot.run_id,
            expected_state="PLANNED",
            expected_state_version=snapshot.state_version,
            new_state="IN_PROGRESS",
            changed_at=changed,
            guard=guard,
            lease=lease,
        )
    if snapshot.state == "IN_PROGRESS":
        if not resume:
            raise ValueError("R8_3_ACTIVE_RUN_REQUIRES_EXPLICIT_RESUME")
        changed = now()
        recovering = control_store.transition_run_state(
            snapshot.run_id,
            expected_state="IN_PROGRESS",
            expected_state_version=snapshot.state_version,
            new_state="RECOVERY_REQUIRED",
            changed_at=changed,
            guard=guard,
            lease=lease,
        )
        changed2 = now()
        return control_store.transition_run_state(
            snapshot.run_id,
            expected_state="RECOVERY_REQUIRED",
            expected_state_version=recovering.state_version,
            new_state="IN_PROGRESS",
            changed_at=changed2,
            guard=guard,
            lease=lease,
        )
    if snapshot.state == "RECOVERY_REQUIRED":
        if not resume:
            raise ValueError("R8_3_RECOVERY_RUN_REQUIRES_EXPLICIT_RESUME")
        changed = now()
        return control_store.transition_run_state(
            snapshot.run_id,
            expected_state="RECOVERY_REQUIRED",
            expected_state_version=snapshot.state_version,
            new_state="IN_PROGRESS",
            changed_at=changed,
            guard=guard,
            lease=lease,
        )
    if snapshot.state == "COMPLETED":
        return snapshot
    raise ValueError("R8_3_ABORTED_RUN_NOT_RESUMABLE")


def _durable_slot_telemetry(
    *,
    manifest: BoundedFootballLiveRunManifest,
    control_store: SQLiteBoundedFootballLiveControlStore,
) -> Mapping[str, Any]:
    with sqlite3.connect(control_store.path) as connection:
        rows = connection.execute(
            """
            SELECT
                round_index,
                modality,
                sequence_number,
                state
            FROM football_bounded_sequence_reservation
            WHERE run_id = ?
            ORDER BY round_index, modality
            """,
            (manifest.run_id,),
        ).fetchall()

    started_rounds = sorted({int(row[0]) for row in rows})
    state_by_slot = {
        (int(row[0]), str(row[1])): str(row[3])
        for row in rows
    }
    closed_rounds = [
        round_index
        for round_index in started_rounds
        if all(
            state_by_slot.get((round_index, modality)) == "COMMITTED"
            for modality in manifest.modalities
        )
    ]
    sequence_numbers = {
        _slot_key(int(row[0]), str(row[1])): int(row[2])
        for row in rows
    }
    correlation_ids = {
        round_index: _round_correlation_id(
            manifest.run_id,
            round_index,
        )
        for round_index in started_rounds
    }

    return {
        "started_rounds": len(started_rounds),
        "closed_rounds": len(closed_rounds),
        "reserved_slots": sum(
            1 for row in rows if str(row[3]) == "RESERVED"
        ),
        "committed_slots": sum(
            1 for row in rows if str(row[3]) == "COMMITTED"
        ),
        "abandoned_slots": sum(
            1 for row in rows if str(row[3]) == "ABANDONED"
        ),
        "sequence_numbers_by_slot": sequence_numbers,
        "correlation_id_by_round": correlation_ids,
    }


def _durable_terminal_telemetry(
    *,
    manifest: BoundedFootballLiveRunManifest,
    authority: R83OfflineFakeExecutionAuthorityPlan,
    snapshot: RunControlSnapshot,
    control_store: SQLiteBoundedFootballLiveControlStore,
    journal: SQLiteR83FakeExecutorJournal,
    plan_size: int,
    duplicate_source_count: int = 0,
    quarantine_count: int = 0,
    integrity_failure_count: int = 0,
) -> FakeProviderBoundedRunTelemetry:
    durable = _durable_slot_telemetry(
        manifest=manifest,
        control_store=control_store,
    )
    counts = journal.counts(manifest.run_id)
    reasons = journal.stop_reasons(manifest.run_id)
    if snapshot.state in {"COMPLETED", "ABORTED"} and not reasons:
        raise ValueError(
            "R8_3R3_TERMINAL_TELEMETRY_STOP_REASON_MISSING"
        )

    return FakeProviderBoundedRunTelemetry(
        run_id=manifest.run_id,
        plan_fingerprint=authority.plan_fingerprint,
        run_state=snapshot.state,
        planned_rounds=manifest.max_capture_rounds,
        started_rounds=int(durable["started_rounds"]),
        closed_rounds=int(durable["closed_rounds"]),
        planned_slots=plan_size,
        reserved_slots=int(durable["reserved_slots"]),
        committed_slots=int(durable["committed_slots"]),
        abandoned_slots=int(durable["abandoned_slots"]),
        fake_calls_attempted=int(counts["attempted"]),
        fake_calls_succeeded=int(counts["succeeded"]),
        fake_calls_failed=int(counts["failed"]),
        fake_calls_uncertain=int(counts["uncertain"]),
        fake_calls_by_modality=counts["by_modality"],
        sequence_numbers_by_slot=dict(
            durable["sequence_numbers_by_slot"]
        ),
        correlation_id_by_round=dict(
            durable["correlation_id_by_round"]
        ),
        duplicate_source_count=duplicate_source_count,
        quarantine_count=quarantine_count,
        integrity_failure_count=integrity_failure_count,
        resume_count=int(counts["resume_count"]),
        stop_reason_codes=tuple(reasons),
        run_started_at=snapshot.created_at,
        run_finished_at=snapshot.updated_at,
        runtime_ms=_runtime_ms(
            snapshot.updated_at,
            snapshot.created_at,
        ),
    )


def execute_offline_fake_bounded_run(
    *,
    manifest: BoundedFootballLiveRunManifest,
    authority: R83OfflineFakeExecutionAuthorityPlan,
    control_store: SQLiteBoundedFootballLiveControlStore,
    evidence_store: SQLiteFootballLiveObservationStore,
    journal: SQLiteR83FakeExecutorJournal,
    guard: BoundedExecutorProcessScopeGuard,
    lease: ProcessScopeLease,
    fake_provider: DeterministicFakeFootballLiveProvider,
    clock: Callable[[], datetime],
    resume: bool = False,
    crash_point: str | None = None,
    manual_stop_requested: Callable[[int, str], bool] | None = None,
    stop_on_terminal_fixture: bool = True,
) -> FakeProviderBoundedRunTelemetry:
    authority.validate_manifest(manifest)
    if manifest.provider_key != R8_3_FAKE_PROVIDER_KEY:
        raise ValueError("R8_3_FAKE_PROVIDER_KEY_REQUIRED")
    if crash_point is not None and crash_point not in R8_3_CRASH_POINTS:
        raise ValueError("R8_3_CRASH_POINT_INVALID")
    if not isinstance(stop_on_terminal_fixture, bool):
        raise ValueError("R8_3_TERMINAL_STOP_BOOLEAN_REQUIRED")

    config = _manifest_config(manifest)
    plan = build_bounded_capture_plan(config)
    if len(plan) > manifest.max_total_provider_calls:
        raise ValueError("R8_3_PLANNED_CALLS_EXCEED_BUDGET")

    telemetry = _TelemetryBuilder()
    last_clock: datetime | None = None
    journal_registered = False

    def stop(code: str, *, at: datetime | None = None) -> None:
        telemetry.stop(code)
        if journal_registered:
            timestamp = at
            if timestamp is None:
                timestamp = (
                    last_clock
                    if last_clock is not None
                    else manifest.created_at
                )
            journal.record_stop_reason(
                manifest.run_id,
                reason_code=code,
                stopped_at=timestamp,
            )

    def now() -> datetime:
        nonlocal last_clock
        value = _checked_now(clock, last=last_clock)
        last_clock = value
        if _runtime_ms(value, manifest.created_at) > manifest.max_runtime_ms:
            stop("MAX_RUNTIME_REACHED", at=value)
            raise ValueError("R8_3_MAX_RUNTIME_REACHED")
        return value

    started_at = now()
    _ensure_integrity(
        control_store=control_store,
        evidence_store=evidence_store,
        journal=journal,
    )
    guard.assert_active(lease)

    registered_at = now()
    snapshot = control_store.register_run(
        manifest,
        guard=guard,
        lease=lease,
        registered_at=registered_at,
    )
    journal.register_run(
        manifest=manifest,
        authority=authority,
        registered_at=registered_at,
    )
    journal_registered = True
    _maybe_crash(crash_point, "AFTER_RUN_REGISTERED")

    if (
        resume
        and snapshot.state in {"IN_PROGRESS", "RECOVERY_REQUIRED"}
    ):
        journal.increment_resume(
            manifest.run_id,
            changed_at=now(),
            control_state_before=snapshot.state,
            control_state_version_before=snapshot.state_version,
        )

    snapshot = _transition_to_in_progress(
        snapshot,
        resume=resume,
        control_store=control_store,
        guard=guard,
        lease=lease,
        now=now,
    )

    if snapshot.state == "COMPLETED":
        _ensure_integrity(
            control_store=control_store,
            evidence_store=evidence_store,
            journal=journal,
        )
        return _durable_terminal_telemetry(
            manifest=manifest,
            authority=authority,
            snapshot=snapshot,
            control_store=control_store,
            journal=journal,
            plan_size=len(plan),
        )

    _maybe_crash(crash_point, "AFTER_RUN_IN_PROGRESS")

    terminal_stop = False
    abort_run = False

    for slot in plan:
        if terminal_stop or abort_run:
            break
        telemetry.started_rounds.add(slot.round_index)
        correlation_id = _round_correlation_id(
            manifest.run_id,
            slot.round_index,
        )
        telemetry.correlation_id_by_round[slot.round_index] = correlation_id

        if manual_stop_requested is not None and manual_stop_requested(
            slot.round_index,
            slot.modality,
        ):
            stop("MANUAL_STOP_REQUEST")
            abort_run = True
            break

        try:
            guard.assert_active(lease)
        except ValueError:
            stop("PROCESS_SCOPE_GUARD_NOT_HELD")
            raise

        if authority.provider_key != manifest.provider_key:
            stop("PROVIDER_KEY_CHANGED")
            raise ValueError("R8_3_PROVIDER_KEY_CHANGED")
        if authority.subject_key != manifest.subject_key:
            stop("SUBJECT_KEY_CHANGED")
            raise ValueError("R8_3_SUBJECT_KEY_CHANGED")

        _ensure_integrity(
            control_store=control_store,
            evidence_store=evidence_store,
            journal=journal,
        )

        reserved_at = now()
        reservation = control_store.reserve_next_sequence(
            manifest.run_id,
            round_index=slot.round_index,
            modality=slot.modality,
            reserved_at=reserved_at,
            guard=guard,
            lease=lease,
        )
        telemetry.sequence_numbers_by_slot[
            _slot_key(slot.round_index, slot.modality)
        ] = reservation.sequence_number

        if reservation.state == "COMMITTED":
            telemetry.committed_slots += 1
            continue
        if reservation.state == "ABANDONED":
            telemetry.abandoned_slots += 1
            abort_run = True
            stop("SCRIPTED_FAKE_PROVIDER_FAILURE")
            break

        telemetry.reserved_slots += 1
        _maybe_crash(
            crash_point,
            "AFTER_SLOT_RESERVED_BEFORE_FAKE_CALL",
        )

        latest_attempt = journal.latest_attempt_for_slot(
            manifest.run_id,
            round_index=slot.round_index,
            modality=slot.modality,
        )
        if (
            latest_attempt is not None
            and latest_attempt.state == "FAILED"
        ):
            control_store.transition_reservation(
                manifest.run_id,
                round_index=slot.round_index,
                modality=slot.modality,
                expected_state="RESERVED",
                new_state="ABANDONED",
                changed_at=now(),
                guard=guard,
                lease=lease,
            )
            telemetry.abandoned_slots += 1
            stop("SCRIPTED_FAKE_PROVIDER_FAILURE")
            abort_run = True
            break

        expected_capture = fake_provider.peek(
            run_id=manifest.run_id,
            subject_key=manifest.subject_key,
            round_index=slot.round_index,
            modality=slot.modality,
            sequence_number=reservation.sequence_number,
            reservation_created_at=reservation.created_at,
        )
        expected_observation = expected_capture.observation(
            provider_key=manifest.provider_key,
            subject_key=manifest.subject_key,
        )

        existing = evidence_store.verify_for_fusion(expected_observation)
        if existing.accepted_for_fusion:
            decision = existing
            capture = expected_capture
        elif (
            latest_attempt is not None
            and latest_attempt.state == "SUCCEEDED"
        ):
            if (
                latest_attempt.source_record_fingerprint
                != expected_capture.source_record_fingerprint
            ):
                stop("DURABLE_EVIDENCE_INTEGRITY_FAILURE")
                raise ValueError(
                    "R8_3R3_SUCCEEDED_ATTEMPT_SOURCE_RECONSTRUCTION_MISMATCH"
                )
            capture = expected_capture
            observation = capture.observation(
                provider_key=manifest.provider_key,
                subject_key=manifest.subject_key,
            )
            decision = evidence_store.record(observation)
            if decision.status == SEQUENCE_DUPLICATE_SOURCE:
                telemetry.duplicate_source_count += 1
            elif decision.status != SEQUENCE_ACCEPTED:
                telemetry.quarantine_count += 1
        else:
            try:
                attempt = journal.begin_attempt(
                    run_id=manifest.run_id,
                    round_index=slot.round_index,
                    modality=slot.modality,
                    sequence_number=reservation.sequence_number,
                    correlation_id=correlation_id,
                    attempted_at=now(),
                )
            except ValueError as error:
                if str(error) == "R8_3_TOTAL_FAKE_CALL_BUDGET_REACHED":
                    stop("TOTAL_FAKE_CALL_BUDGET_REACHED")
                    abort_run = True
                    break
                raise

            try:
                capture = fake_provider.capture(
                    run_id=manifest.run_id,
                    subject_key=manifest.subject_key,
                    round_index=slot.round_index,
                    modality=slot.modality,
                    sequence_number=reservation.sequence_number,
                    reservation_created_at=reservation.created_at,
                )
            except ScriptedFakeProviderFailure as error:
                journal.resolve_attempt(
                    run_id=manifest.run_id,
                    round_index=slot.round_index,
                    modality=slot.modality,
                    attempt_index=attempt.attempt_index,
                    succeeded=False,
                    result_at=now(),
                    error_code="SCRIPTED_FAKE_PROVIDER_FAILURE",
                )
                control_store.transition_reservation(
                    manifest.run_id,
                    round_index=slot.round_index,
                    modality=slot.modality,
                    expected_state="RESERVED",
                    new_state="ABANDONED",
                    changed_at=now(),
                    guard=guard,
                    lease=lease,
                )
                telemetry.abandoned_slots += 1
                stop("SCRIPTED_FAKE_PROVIDER_FAILURE")
                abort_run = True
                break

            _maybe_crash(
                crash_point,
                "AFTER_FAKE_CALL_BEFORE_NORMALIZED_PERSIST",
            )

            if capture.source_record_fingerprint != expected_capture.source_record_fingerprint:
                stop("UNEXPECTED_FAKE_RESPONSE_CONTRACT")
                raise ValueError("R8_3_UNEXPECTED_FAKE_RESPONSE_CONTRACT")

            journal.resolve_attempt(
                run_id=manifest.run_id,
                round_index=slot.round_index,
                modality=slot.modality,
                attempt_index=attempt.attempt_index,
                succeeded=True,
                result_at=now(),
                source_record_fingerprint=capture.source_record_fingerprint,
            )
            observation = capture.observation(
                provider_key=manifest.provider_key,
                subject_key=manifest.subject_key,
            )
            decision = evidence_store.record(observation)
            if decision.status == SEQUENCE_DUPLICATE_SOURCE:
                telemetry.duplicate_source_count += 1
            elif decision.status != SEQUENCE_ACCEPTED:
                telemetry.quarantine_count += 1

        if not decision.accepted_for_fusion and decision.status != SEQUENCE_DUPLICATE_SOURCE:
            stop("DURABLE_EVIDENCE_INTEGRITY_FAILURE")
            raise ValueError("R8_3_DURABLE_EVIDENCE_NOT_ACCEPTED")

        _maybe_crash(
            crash_point,
            "AFTER_NORMALIZED_PERSIST_BEFORE_SLOT_COMMIT",
        )

        committed = control_store.transition_reservation(
            manifest.run_id,
            round_index=slot.round_index,
            modality=slot.modality,
            expected_state="RESERVED",
            new_state="COMMITTED",
            changed_at=now(),
            guard=guard,
            lease=lease,
        )
        if committed.state != "COMMITTED":
            raise ValueError("R8_3_SLOT_COMMIT_FAILED")
        telemetry.committed_slots += 1

        if (
            stop_on_terminal_fixture
            and slot.modality == "fixture_status"
            and capture.fixture_terminal
        ):
            stop("FIXTURE_TERMINAL_STATUS_WHEN_CONFIGURED")
            terminal_stop = True

        _maybe_crash(
            crash_point,
            "AFTER_SLOT_COMMIT_BEFORE_NEXT_SLOT",
        )

        next_slots_in_round = [
            item
            for item in plan
            if item.round_index == slot.round_index
            and _slot_key(item.round_index, item.modality)
            not in telemetry.sequence_numbers_by_slot
        ]
        if not next_slots_in_round:
            telemetry.closed_rounds.add(slot.round_index)

    if abort_run:
        snapshot = control_store.get_run(manifest.run_id)
        if snapshot.state in {"IN_PROGRESS", "RECOVERY_REQUIRED", "PLANNED"}:
            snapshot = control_store.transition_run_state(
                manifest.run_id,
                expected_state=snapshot.state,
                expected_state_version=snapshot.state_version,
                new_state="ABORTED",
                changed_at=now(),
                guard=guard,
                lease=lease,
            )
    else:
        if not telemetry.stop_reasons:
            stop("CAPTURE_ROUND_LIMIT_REACHED")
        _maybe_crash(crash_point, "BEFORE_RUN_COMPLETED")
        snapshot = control_store.get_run(manifest.run_id)
        if snapshot.state == "IN_PROGRESS":
            snapshot = control_store.transition_run_state(
                manifest.run_id,
                expected_state="IN_PROGRESS",
                expected_state_version=snapshot.state_version,
                new_state="COMPLETED",
                changed_at=now(),
                guard=guard,
                lease=lease,
            )

    try:
        _ensure_integrity(
            control_store=control_store,
            evidence_store=evidence_store,
            journal=journal,
        )
    except ValueError as error:
        telemetry.integrity_failure_count += 1
        if "SEQUENCE_ALLOCATOR" in str(error):
            stop("SEQUENCE_ALLOCATOR_INTEGRITY_FAILURE")
        else:
            stop("DURABLE_EVIDENCE_INTEGRITY_FAILURE")
        raise

    return _durable_terminal_telemetry(
        manifest=manifest,
        authority=authority,
        snapshot=snapshot,
        control_store=control_store,
        journal=journal,
        plan_size=len(plan),
        duplicate_source_count=telemetry.duplicate_source_count,
        quarantine_count=telemetry.quarantine_count,
        integrity_failure_count=telemetry.integrity_failure_count,
    )
