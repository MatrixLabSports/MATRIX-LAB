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


def _iso(value: datetime) -> str:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            "INVALID_CONTEXT_AS_OF"
        )

    return (
        value.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _normalize_iso(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(
            "INVALID_CONTEXT_AS_OF"
        )

    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )
    return _iso(parsed)


@dataclass(frozen=True)
class AnalysisContextBundle:
    sport: str
    canonical_id: str
    as_of: str
    history_profile_fingerprint: str
    strength_of_schedule_fingerprint: str
    load_context_fingerprint: str
    comparable_cohort_fingerprint: str | None
    bundle_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.analysis-context-bundle/2"
            ),
            "sport": self.sport,
            "canonical_id": self.canonical_id,
            "as_of": self.as_of,
            "history_profile_fingerprint": (
                self.history_profile_fingerprint
            ),
            "strength_of_schedule_fingerprint": (
                self.strength_of_schedule_fingerprint
            ),
            "load_context_fingerprint": (
                self.load_context_fingerprint
            ),
            "comparable_cohort_fingerprint": (
                self.comparable_cohort_fingerprint
            ),
            "bundle_fingerprint": (
                self.bundle_fingerprint
            ),
            "point_in_time_enforced": True,
            "temporal_coherence_enforced": True,
            "fatigue_score_computed": False,
            "recency_weighting_applied": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class AnalysisContextIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


def build_analysis_context_bundle(
    *,
    history_profile,
    strength_of_schedule_profile,
    load_context,
    comparable_cohort=None,
) -> AnalysisContextBundle:
    sports = {
        history_profile.sport,
        strength_of_schedule_profile.sport,
        load_context.sport,
    }

    if comparable_cohort is not None:
        sports.add(comparable_cohort.sport)

    if len(sports) != 1:
        raise ValueError(
            "SPORT_BOUNDARY_VIOLATION"
        )

    sport = next(iter(sports))

    canonical_ids = {
        history_profile.canonical_id,
        strength_of_schedule_profile.canonical_id,
        load_context.canonical_id,
    }

    if len(canonical_ids) != 1:
        raise ValueError(
            "CANONICAL_ID_MISMATCH"
        )

    canonical_id = next(iter(canonical_ids))

    if (
        strength_of_schedule_profile
        .history_fingerprint
        != history_profile.history_fingerprint
    ):
        raise ValueError(
            "HISTORY_LINEAGE_MISMATCH"
        )

    history_as_of = _normalize_iso(
        history_profile.as_of
    )
    sos_as_of = _normalize_iso(
        strength_of_schedule_profile.as_of
    )
    load_as_of = _iso(load_context.as_of)

    as_of_values = {
        history_as_of,
        sos_as_of,
        load_as_of,
    }

    if comparable_cohort is not None:
        as_of_values.add(
            _iso(comparable_cohort.as_of)
        )

    if len(as_of_values) != 1:
        raise ValueError(
            "CONTEXT_AS_OF_MISMATCH"
        )

    as_of = next(iter(as_of_values))

    comparable_fp = (
        None
        if comparable_cohort is None
        else comparable_cohort.cohort_fingerprint
    )

    base = {
        "schema": (
            "matrix.analysis-context-bundle/2"
        ),
        "sport": sport,
        "canonical_id": canonical_id,
        "as_of": as_of,
        "history_profile_fingerprint": (
            history_profile.profile_fingerprint
        ),
        "strength_of_schedule_fingerprint": (
            strength_of_schedule_profile
            .profile_fingerprint
        ),
        "load_context_fingerprint": (
            load_context.context_fingerprint
        ),
        "comparable_cohort_fingerprint": (
            comparable_fp
        ),
        "point_in_time_enforced": True,
        "temporal_coherence_enforced": True,
        "fatigue_score_computed": False,
        "recency_weighting_applied": False,
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return AnalysisContextBundle(
        sport=sport,
        canonical_id=canonical_id,
        as_of=as_of,
        history_profile_fingerprint=(
            history_profile.profile_fingerprint
        ),
        strength_of_schedule_fingerprint=(
            strength_of_schedule_profile
            .profile_fingerprint
        ),
        load_context_fingerprint=(
            load_context.context_fingerprint
        ),
        comparable_cohort_fingerprint=(
            comparable_fp
        ),
        bundle_fingerprint=_sha(base),
    )


class SQLiteAnalysisContextEvidenceStore:
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
                CREATE TABLE IF NOT EXISTS analysis_context_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    bundle_fingerprint TEXT NOT NULL UNIQUE,
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
    def _expected_bundle_fingerprint(
        payload: Mapping[str, Any],
    ) -> str:
        base = dict(payload)
        base.pop("evidence_id", None)
        base.pop("bundle_fingerprint", None)
        return _sha(base)

    @staticmethod
    def _evidence_id(
        bundle_fingerprint: str,
    ) -> str:
        return _sha(
            {
                "schema": (
                    "matrix.analysis-context-evidence-id/1"
                ),
                "bundle_fingerprint": (
                    bundle_fingerprint
                ),
            }
        )

    def record_bundle(
        self,
        bundle: AnalysisContextBundle,
    ) -> str:
        payload = dict(bundle.payload())

        expected_fp = (
            self._expected_bundle_fingerprint(
                payload
            )
        )

        if expected_fp != bundle.bundle_fingerprint:
            raise ValueError(
                "ANALYSIS_CONTEXT_DERIVATION_MISMATCH"
            )

        evidence_id = self._evidence_id(
            bundle.bundle_fingerprint
        )

        evidence_payload = dict(payload)
        evidence_payload[
            "evidence_id"
        ] = evidence_id

        payload_json = _canonical_json(
            evidence_payload
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
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
                FROM analysis_context_evidence
                WHERE bundle_fingerprint = ?
                """,
                (bundle.bundle_fingerprint,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1])
                    == payload_sha
                ):
                    return evidence_id

                raise ValueError(
                    "ANALYSIS_CONTEXT_MUTATION_VIOLATION"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO analysis_context_evidence (
                        evidence_id,
                        sport,
                        canonical_id,
                        bundle_fingerprint,
                        payload_json,
                        payload_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        bundle.sport,
                        bundle.canonical_id,
                        bundle.bundle_fingerprint,
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "ANALYSIS_CONTEXT_APPEND_ONLY_VIOLATION"
                ) from error

        return evidence_id

    def audit_integrity(
        self,
    ) -> AnalysisContextIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    sport,
                    canonical_id,
                    bundle_fingerprint,
                    payload_json,
                    payload_sha256
                FROM analysis_context_evidence
                ORDER BY created_at, evidence_id
                """
            ).fetchall()

        for (
            evidence_id,
            sport,
            canonical_id,
            bundle_fp,
            payload_json,
            stored_sha,
        ) in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(
                    f"INVALID_JSON:{bundle_fp}"
                )
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode(
                    "utf-8"
                )
            ).hexdigest()

            if actual_sha != stored_sha:
                errors.append(
                    f"PAYLOAD_HASH_MISMATCH:"
                    f"{bundle_fp}"
                )

            expected_fp = (
                self._expected_bundle_fingerprint(
                    payload
                )
            )

            if expected_fp != bundle_fp:
                errors.append(
                    f"BUNDLE_FINGERPRINT_MISMATCH:"
                    f"{bundle_fp}"
                )

            expected_evidence_id = (
                self._evidence_id(bundle_fp)
            )

            if (
                expected_evidence_id
                != evidence_id
            ):
                errors.append(
                    f"EVIDENCE_ID_MISMATCH:"
                    f"{bundle_fp}"
                )

            expected_pairs = {
                "evidence_id": evidence_id,
                "sport": sport,
                "canonical_id": canonical_id,
                "bundle_fingerprint": (
                    bundle_fp
                ),
                "point_in_time_enforced": True,
                "temporal_coherence_enforced": True,
                "fatigue_score_computed": False,
                "recency_weighting_applied": False,
                "automatic_model_promotion": False,
                "automatic_provider_switch": False,
                "automatic_wagering": False,
            }

            for key, expected in expected_pairs.items():
                if payload.get(key) != expected:
                    errors.append(
                        f"{key.upper()}_MISMATCH:"
                        f"{bundle_fp}"
                    )

        return AnalysisContextIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
