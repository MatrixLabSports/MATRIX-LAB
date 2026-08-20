from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


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
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


def _get(value: object, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


@dataclass(frozen=True)
class FeatureLineageSource:
    source_record_fingerprint: str
    schema_name: str
    schema_version: str
    source_fields: tuple[str, ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "source_record_fingerprint": self.source_record_fingerprint,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "source_fields": list(self.source_fields),
        }


@dataclass(frozen=True)
class FeatureLineageEntry:
    feature_definition_fingerprint: str
    transformation_fingerprint: str
    sources: tuple[FeatureLineageSource, ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "feature_definition_fingerprint": (
                self.feature_definition_fingerprint
            ),
            "transformation_fingerprint": self.transformation_fingerprint,
            "sources": [source.payload() for source in self.sources],
        }


@dataclass(frozen=True)
class GovernedFeatureAdmissionDecision:
    status: str
    downstream_eligible: bool
    sport: str
    canonical_id: str
    snapshot_fingerprint: str
    base_snapshot_admission_fingerprint: str
    feature_set_manifest_fingerprint: str
    lineage_fingerprint: str | None
    reason_codes: tuple[str, ...]
    decision_fingerprint: str


def _decision_fingerprint(
    *,
    status: str,
    downstream_eligible: bool,
    sport: str,
    canonical_id: str,
    snapshot_fingerprint: str,
    base_snapshot_admission_fingerprint: str,
    feature_set_manifest_fingerprint: str,
    lineage_fingerprint: str | None,
    reason_codes: Sequence[str],
) -> str:
    return _sha(
        {
            "schema": "matrix.governed-feature-admission/2",
            "status": status,
            "downstream_eligible": downstream_eligible,
            "sport": sport,
            "canonical_id": canonical_id,
            "snapshot_fingerprint": snapshot_fingerprint,
            "base_snapshot_admission_fingerprint": (
                base_snapshot_admission_fingerprint
            ),
            "feature_set_manifest_fingerprint": (
                feature_set_manifest_fingerprint
            ),
            "lineage_fingerprint": lineage_fingerprint,
            "reason_codes": list(sorted(reason_codes)),
            "authoritative_for_future_consumers": True,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
        }
    )


def evaluate_governed_feature_snapshot(
    *,
    snapshot: object,
    base_snapshot_admission_fingerprint: str,
    feature_set_manifest_fingerprint: str,
    feature_set_manifest_registry,
    lineage_entries: Sequence[FeatureLineageEntry],
    transformation_registry,
) -> GovernedFeatureAdmissionDecision:
    sport = _get(snapshot, "sport")
    canonical_id = _get(snapshot, "canonical_id")
    snapshot_fp = _hex64(
        "SNAPSHOT_FINGERPRINT",
        _get(snapshot, "snapshot_fingerprint"),
    )
    base_snapshot_admission_fingerprint = _hex64(
        "BASE_SNAPSHOT_ADMISSION_FINGERPRINT",
        base_snapshot_admission_fingerprint,
    )
    manifest_fp = _hex64(
        "FEATURE_SET_MANIFEST_FINGERPRINT",
        feature_set_manifest_fingerprint,
    )

    reasons: list[str] = []

    try:
        manifest = feature_set_manifest_registry.get_by_fingerprint(
            manifest_fp
        )
    except ValueError as error:
        manifest = None
        reasons.append(f"FEATURE_SET_REGISTRY_INTEGRITY:{error}")

    if manifest is None:
        reasons.append("UNREGISTERED_FEATURE_SET_MANIFEST")
        manifest_sport = None
        manifest_key = None
        manifest_version = None
        manifest_defs: tuple[str, ...] = ()
    else:
        manifest_sport = manifest["sport"]
        manifest_key = manifest["feature_set_key"]
        manifest_version = manifest["feature_set_version"]
        manifest_defs = tuple(
            sorted(
                _hex64(
                    "MANIFEST_FEATURE_DEFINITION_FINGERPRINT",
                    item,
                )
                for item in manifest["feature_definition_fingerprints"]
            )
        )

    if sport != manifest_sport:
        reasons.append("FEATURE_SET_SPORT_MISMATCH")

    if _get(snapshot, "feature_set_key") != manifest_key:
        reasons.append("FEATURE_SET_KEY_MISMATCH")

    if str(_get(snapshot, "feature_set_version")) != str(manifest_version):
        reasons.append("FEATURE_SET_VERSION_MISMATCH")

    snapshot_defs = tuple(
        sorted(
            _hex64(
                "SNAPSHOT_FEATURE_DEFINITION_FINGERPRINT",
                item,
            )
            for item in _get(snapshot, "definition_fingerprints")
        )
    )

    if snapshot_defs != manifest_defs:
        reasons.append("FEATURE_SET_DEFINITION_MISMATCH")

    snapshot_sources = {
        _hex64(
            "SNAPSHOT_SOURCE_RECORD_FINGERPRINT",
            item,
        )
        for item in _get(snapshot, "source_record_fingerprints")
    }

    if (
        isinstance(lineage_entries, (str, bytes))
        or not isinstance(lineage_entries, Sequence)
        or not lineage_entries
    ):
        reasons.append("MISSING_EXACT_FEATURE_LINEAGE")
        lineage_entries = ()

    normalized_entries: list[FeatureLineageEntry] = []
    seen_features: set[str] = set()
    lineage_source_union: set[str] = set()

    for entry in lineage_entries:
        feature_fp = _hex64(
            "LINEAGE_FEATURE_FINGERPRINT",
            entry.feature_definition_fingerprint,
        )
        transformation_fp = _hex64(
            "LINEAGE_TRANSFORMATION_FINGERPRINT",
            entry.transformation_fingerprint,
        )

        if feature_fp in seen_features:
            reasons.append("DUPLICATE_FEATURE_LINEAGE")
            continue
        seen_features.add(feature_fp)

        try:
            transformation = transformation_registry.get_by_fingerprint(
                transformation_fp
            )
        except ValueError as error:
            transformation = None
            reasons.append(
                f"TRANSFORMATION_REGISTRY_INTEGRITY:{feature_fp}:{error}"
            )

        if transformation is None:
            reasons.append(f"UNKNOWN_TRANSFORMATION:{feature_fp}")
            declared_inputs: dict[tuple[str, str], set[str]] = {}
        else:
            if transformation["sport"] != sport:
                reasons.append(
                    f"TRANSFORMATION_SPORT_MISMATCH:{feature_fp}"
                )

            if feature_fp not in transformation[
                "output_feature_definition_fingerprints"
            ]:
                reasons.append(
                    f"TRANSFORMATION_OUTPUT_MISMATCH:{feature_fp}"
                )

            declared_inputs = {
                (
                    item["schema_name"],
                    item["schema_version"],
                ): set(item["fields"])
                for item in transformation["inputs"]
            }

        if not entry.sources:
            reasons.append(f"EMPTY_FEATURE_SOURCES:{feature_fp}")

        normalized_sources: list[FeatureLineageSource] = []

        for source in entry.sources:
            source_fp = _hex64(
                "LINEAGE_SOURCE_RECORD_FINGERPRINT",
                source.source_record_fingerprint,
            )
            lineage_source_union.add(source_fp)

            if source_fp not in snapshot_sources:
                reasons.append(
                    f"LINEAGE_SOURCE_OUTSIDE_SNAPSHOT:{feature_fp}"
                )

            if (
                not isinstance(source.schema_name, str)
                or not source.schema_name
                or not isinstance(source.schema_version, str)
                or not source.schema_version
            ):
                reasons.append(
                    f"INVALID_SOURCE_SCHEMA:{feature_fp}"
                )
                continue

            fields = tuple(
                sorted(
                    {
                        item
                        for item in source.source_fields
                        if isinstance(item, str) and item
                    }
                )
            )
            if not fields:
                reasons.append(f"EMPTY_SOURCE_FIELDS:{feature_fp}")

            declared_fields = declared_inputs.get(
                (source.schema_name, source.schema_version)
            )

            if declared_fields is None:
                reasons.append(
                    f"UNDECLARED_TRANSFORMATION_SOURCE_SCHEMA:{feature_fp}"
                )
            elif not set(fields).issubset(declared_fields):
                reasons.append(
                    f"UNDECLARED_TRANSFORMATION_FIELD:{feature_fp}"
                )

            normalized_sources.append(
                FeatureLineageSource(
                    source_record_fingerprint=source_fp,
                    schema_name=source.schema_name,
                    schema_version=source.schema_version,
                    source_fields=fields,
                )
            )

        normalized_sources = sorted(
            normalized_sources,
            key=lambda item: (
                item.source_record_fingerprint,
                item.schema_name,
                item.schema_version,
                item.source_fields,
            ),
        )

        normalized_entries.append(
            FeatureLineageEntry(
                feature_definition_fingerprint=feature_fp,
                transformation_fingerprint=transformation_fp,
                sources=tuple(normalized_sources),
            )
        )

    if seen_features != set(snapshot_defs):
        reasons.append("INCOMPLETE_FEATURE_LINEAGE")

    if lineage_source_union != snapshot_sources:
        reasons.append("SNAPSHOT_SOURCE_LINEAGE_MISMATCH")

    normalized_entries = sorted(
        normalized_entries,
        key=lambda item: item.feature_definition_fingerprint,
    )

    lineage_fingerprint = (
        None
        if not normalized_entries
        else _sha(
            {
                "schema": "matrix.exact-feature-lineage/2",
                "sport": sport,
                "canonical_id": canonical_id,
                "snapshot_fingerprint": snapshot_fp,
                "base_snapshot_admission_fingerprint": (
                    base_snapshot_admission_fingerprint
                ),
                "feature_set_manifest_fingerprint": manifest_fp,
                "entries": [
                    item.payload()
                    for item in normalized_entries
                ],
                "point_in_time_required": True,
                "automatic_model_promotion": False,
            }
        )
    )

    reasons = sorted(set(reasons))
    status = "ADMIT" if not reasons else "QUARANTINE"
    eligible = status == "ADMIT"

    decision_fp = _decision_fingerprint(
        status=status,
        downstream_eligible=eligible,
        sport=sport,
        canonical_id=canonical_id,
        snapshot_fingerprint=snapshot_fp,
        base_snapshot_admission_fingerprint=(
            base_snapshot_admission_fingerprint
        ),
        feature_set_manifest_fingerprint=manifest_fp,
        lineage_fingerprint=lineage_fingerprint,
        reason_codes=reasons,
    )

    return GovernedFeatureAdmissionDecision(
        status=status,
        downstream_eligible=eligible,
        sport=sport,
        canonical_id=canonical_id,
        snapshot_fingerprint=snapshot_fp,
        base_snapshot_admission_fingerprint=(
            base_snapshot_admission_fingerprint
        ),
        feature_set_manifest_fingerprint=manifest_fp,
        lineage_fingerprint=lineage_fingerprint,
        reason_codes=tuple(reasons),
        decision_fingerprint=decision_fp,
    )


@dataclass(frozen=True)
class GovernedFeatureAdmissionIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteGovernedFeatureAdmissionEvidence:
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
                CREATE TABLE IF NOT EXISTS governed_feature_admission (
                    evidence_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    snapshot_fingerprint TEXT NOT NULL,
                    decision_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )

    @staticmethod
    def _evidence_id(decision_fingerprint: str) -> str:
        return _sha(
            {
                "schema": (
                    "matrix.governed-feature-admission-evidence-id/2"
                ),
                "decision_fingerprint": decision_fingerprint,
            }
        )

    @staticmethod
    def _rederive_decision_fingerprint(
        decision: GovernedFeatureAdmissionDecision,
    ) -> str:
        return _decision_fingerprint(
            status=decision.status,
            downstream_eligible=decision.downstream_eligible,
            sport=decision.sport,
            canonical_id=decision.canonical_id,
            snapshot_fingerprint=decision.snapshot_fingerprint,
            base_snapshot_admission_fingerprint=(
                decision.base_snapshot_admission_fingerprint
            ),
            feature_set_manifest_fingerprint=(
                decision.feature_set_manifest_fingerprint
            ),
            lineage_fingerprint=decision.lineage_fingerprint,
            reason_codes=decision.reason_codes,
        )

    def record_decision(
        self,
        decision: GovernedFeatureAdmissionDecision,
    ) -> str:
        expected_decision_fp = self._rederive_decision_fingerprint(decision)
        if expected_decision_fp != decision.decision_fingerprint:
            raise ValueError(
                "GOVERNED_FEATURE_DECISION_DERIVATION_MISMATCH"
            )

        expected_status = (
            "ADMIT"
            if not decision.reason_codes
            else "QUARANTINE"
        )
        if decision.status != expected_status:
            raise ValueError("GOVERNED_FEATURE_STATUS_MISMATCH")
        if decision.downstream_eligible != (decision.status == "ADMIT"):
            raise ValueError("GOVERNED_FEATURE_ELIGIBILITY_MISMATCH")

        evidence_id = self._evidence_id(decision.decision_fingerprint)

        payload = {
            "schema": (
                "matrix.governed-feature-admission-evidence/2"
            ),
            "evidence_id": evidence_id,
            "status": decision.status,
            "downstream_eligible": decision.downstream_eligible,
            "sport": decision.sport,
            "canonical_id": decision.canonical_id,
            "snapshot_fingerprint": decision.snapshot_fingerprint,
            "base_snapshot_admission_fingerprint": (
                decision.base_snapshot_admission_fingerprint
            ),
            "feature_set_manifest_fingerprint": (
                decision.feature_set_manifest_fingerprint
            ),
            "lineage_fingerprint": decision.lineage_fingerprint,
            "reason_codes": list(decision.reason_codes),
            "decision_fingerprint": decision.decision_fingerprint,
            "authoritative_for_future_consumers": True,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
        }

        payload_json = _canonical_json(payload)
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT evidence_id, payload_sha256
                FROM governed_feature_admission
                WHERE decision_fingerprint = ?
                """,
                (decision.decision_fingerprint,),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")
                if (
                    str(existing[0]) == evidence_id
                    and str(existing[1]) == payload_sha
                ):
                    return evidence_id
                raise ValueError(
                    "GOVERNED_FEATURE_ADMISSION_MUTATION_VIOLATION"
                )

            connection.execute(
                """
                INSERT INTO governed_feature_admission (
                    evidence_id,
                    sport,
                    canonical_id,
                    snapshot_fingerprint,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    decision.sport,
                    decision.canonical_id,
                    decision.snapshot_fingerprint,
                    decision.decision_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")

        return evidence_id

    def audit_integrity(self) -> GovernedFeatureAdmissionIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    sport,
                    canonical_id,
                    snapshot_fingerprint,
                    decision_fingerprint,
                    payload_json,
                    payload_sha256
                FROM governed_feature_admission
                ORDER BY evidence_id
                """
            ).fetchall()

        for (
            evidence_id,
            sport,
            canonical_id,
            snapshot_fp,
            decision_fp,
            payload_json,
            stored_sha,
        ) in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                errors.append(f"INVALID_JSON:{decision_fp}")
                continue

            actual_sha = sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest()
            if actual_sha != stored_sha:
                errors.append(f"PAYLOAD_HASH_MISMATCH:{decision_fp}")

            expected_decision_fp = _decision_fingerprint(
                status=payload.get("status"),
                downstream_eligible=payload.get("downstream_eligible"),
                sport=payload.get("sport"),
                canonical_id=payload.get("canonical_id"),
                snapshot_fingerprint=payload.get("snapshot_fingerprint"),
                base_snapshot_admission_fingerprint=payload.get(
                    "base_snapshot_admission_fingerprint"
                ),
                feature_set_manifest_fingerprint=payload.get(
                    "feature_set_manifest_fingerprint"
                ),
                lineage_fingerprint=payload.get("lineage_fingerprint"),
                reason_codes=payload.get("reason_codes", []),
            )

            if expected_decision_fp != decision_fp:
                errors.append(
                    f"DECISION_FINGERPRINT_MISMATCH:{decision_fp}"
                )

            expected_evidence_id = self._evidence_id(decision_fp)
            if expected_evidence_id != evidence_id:
                errors.append(f"EVIDENCE_ID_MISMATCH:{decision_fp}")

            for key, expected in {
                "evidence_id": evidence_id,
                "sport": sport,
                "canonical_id": canonical_id,
                "snapshot_fingerprint": snapshot_fp,
                "decision_fingerprint": decision_fp,
                "authoritative_for_future_consumers": True,
                "automatic_model_promotion": False,
                "automatic_wagering": False,
            }.items():
                if payload.get(key) != expected:
                    errors.append(f"{key.upper()}_MISMATCH:{decision_fp}")

        return GovernedFeatureAdmissionIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
