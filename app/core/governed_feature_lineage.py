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
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


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
class FeatureLineageEntry:
    feature_definition_fingerprint: str
    transformation_fingerprint: str
    source_record_fingerprints: tuple[str, ...]
    source_fields: tuple[str, ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "feature_definition_fingerprint": (
                self.feature_definition_fingerprint
            ),
            "transformation_fingerprint": (
                self.transformation_fingerprint
            ),
            "source_record_fingerprints": list(
                self.source_record_fingerprints
            ),
            "source_fields": list(
                self.source_fields
            ),
        }


@dataclass(frozen=True)
class GovernedFeatureAdmissionDecision:
    status: str
    downstream_eligible: bool
    sport: str
    canonical_id: str
    snapshot_fingerprint: str
    feature_set_manifest_fingerprint: str
    lineage_fingerprint: str | None
    reason_codes: tuple[str, ...]
    decision_fingerprint: str


def evaluate_governed_feature_snapshot(
    *,
    snapshot: object,
    feature_set_manifest: object,
    lineage_entries: Sequence[FeatureLineageEntry],
    transformation_registry,
) -> GovernedFeatureAdmissionDecision:
    sport = _get(snapshot, "sport")
    canonical_id = _get(
        snapshot,
        "canonical_id",
    )
    snapshot_fp = _hex64(
        "SNAPSHOT_FINGERPRINT",
        _get(snapshot, "snapshot_fingerprint"),
    )

    reasons: list[str] = []

    manifest_sport = _get(
        feature_set_manifest,
        "sport",
    )
    manifest_key = _get(
        feature_set_manifest,
        "feature_set_key",
    )
    manifest_version = _get(
        feature_set_manifest,
        "feature_set_version",
    )
    manifest_fp = _hex64(
        "FEATURE_SET_MANIFEST_FINGERPRINT",
        _get(
            feature_set_manifest,
            "manifest_fingerprint",
        ),
    )

    if sport != manifest_sport:
        reasons.append(
            "FEATURE_SET_SPORT_MISMATCH"
        )

    if (
        _get(snapshot, "feature_set_key")
        != manifest_key
    ):
        reasons.append(
            "FEATURE_SET_KEY_MISMATCH"
        )

    if (
        str(
            _get(
                snapshot,
                "feature_set_version",
            )
        )
        != str(manifest_version)
    ):
        reasons.append(
            "FEATURE_SET_VERSION_MISMATCH"
        )

    snapshot_defs = tuple(
        sorted(
            _hex64(
                "SNAPSHOT_FEATURE_DEFINITION_FINGERPRINT",
                item,
            )
            for item in _get(
                snapshot,
                "definition_fingerprints",
            )
        )
    )

    manifest_defs = tuple(
        sorted(
            _hex64(
                "MANIFEST_FEATURE_DEFINITION_FINGERPRINT",
                item,
            )
            for item in _get(
                feature_set_manifest,
                "feature_definition_fingerprints",
            )
        )
    )

    if snapshot_defs != manifest_defs:
        reasons.append(
            "FEATURE_SET_DEFINITION_MISMATCH"
        )

    snapshot_sources = {
        _hex64(
            "SNAPSHOT_SOURCE_RECORD_FINGERPRINT",
            item,
        )
        for item in _get(
            snapshot,
            "source_record_fingerprints",
        )
    }

    if (
        isinstance(
            lineage_entries,
            (str, bytes),
        )
        or not isinstance(
            lineage_entries,
            Sequence,
        )
        or not lineage_entries
    ):
        reasons.append(
            "MISSING_EXACT_FEATURE_LINEAGE"
        )
        lineage_entries = ()

    normalized_entries: list[
        FeatureLineageEntry
    ] = []
    seen_features: set[str] = set()

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
            reasons.append(
                "DUPLICATE_FEATURE_LINEAGE"
            )
            continue
        seen_features.add(feature_fp)

        sources = tuple(
            sorted(
                {
                    _hex64(
                        "LINEAGE_SOURCE_RECORD_FINGERPRINT",
                        item,
                    )
                    for item
                    in entry.source_record_fingerprints
                }
            )
        )

        fields = tuple(
            sorted(
                {
                    item
                    for item
                    in entry.source_fields
                    if isinstance(item, str)
                    and item
                }
            )
        )

        if not sources:
            reasons.append(
                f"EMPTY_FEATURE_SOURCES:{feature_fp}"
            )

        if not fields:
            reasons.append(
                f"EMPTY_SOURCE_FIELDS:{feature_fp}"
            )

        if not set(sources).issubset(
            snapshot_sources
        ):
            reasons.append(
                f"LINEAGE_SOURCE_OUTSIDE_SNAPSHOT:{feature_fp}"
            )

        transformation = (
            transformation_registry
            .get_by_fingerprint(
                transformation_fp
            )
        )

        if transformation is None:
            reasons.append(
                f"UNKNOWN_TRANSFORMATION:{feature_fp}"
            )
        else:
            if transformation["sport"] != sport:
                reasons.append(
                    f"TRANSFORMATION_SPORT_MISMATCH:{feature_fp}"
                )

            if (
                feature_fp
                not in transformation[
                    "output_feature_definition_fingerprints"
                ]
            ):
                reasons.append(
                    f"TRANSFORMATION_OUTPUT_MISMATCH:{feature_fp}"
                )

            allowed_fields = {
                field
                for input_spec
                in transformation["inputs"]
                for field
                in input_spec["fields"]
            }

            if not set(fields).issubset(
                allowed_fields
            ):
                reasons.append(
                    f"UNDECLARED_TRANSFORMATION_FIELD:{feature_fp}"
                )

        normalized_entries.append(
            FeatureLineageEntry(
                feature_definition_fingerprint=(
                    feature_fp
                ),
                transformation_fingerprint=(
                    transformation_fp
                ),
                source_record_fingerprints=(
                    sources
                ),
                source_fields=fields,
            )
        )

    if seen_features != set(snapshot_defs):
        reasons.append(
            "INCOMPLETE_FEATURE_LINEAGE"
        )

    normalized_entries = sorted(
        normalized_entries,
        key=lambda item: (
            item.feature_definition_fingerprint,
        ),
    )

    lineage_fingerprint = (
        None
        if not normalized_entries
        else _sha(
            {
                "schema": (
                    "matrix.exact-feature-lineage/1"
                ),
                "sport": sport,
                "canonical_id": canonical_id,
                "snapshot_fingerprint": (
                    snapshot_fp
                ),
                "feature_set_manifest_fingerprint": (
                    manifest_fp
                ),
                "entries": [
                    item.payload()
                    for item
                    in normalized_entries
                ],
                "point_in_time_required": True,
                "automatic_model_promotion": False,
            }
        )
    )

    reasons = sorted(set(reasons))
    status = (
        "ADMIT"
        if not reasons
        else "QUARANTINE"
    )
    eligible = status == "ADMIT"

    base = {
        "schema": (
            "matrix.governed-feature-admission/1"
        ),
        "status": status,
        "downstream_eligible": eligible,
        "sport": sport,
        "canonical_id": canonical_id,
        "snapshot_fingerprint": snapshot_fp,
        "feature_set_manifest_fingerprint": (
            manifest_fp
        ),
        "lineage_fingerprint": (
            lineage_fingerprint
        ),
        "reason_codes": reasons,
        "authoritative_for_future_consumers": True,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
    }

    return GovernedFeatureAdmissionDecision(
        status=status,
        downstream_eligible=eligible,
        sport=sport,
        canonical_id=canonical_id,
        snapshot_fingerprint=snapshot_fp,
        feature_set_manifest_fingerprint=(
            manifest_fp
        ),
        lineage_fingerprint=(
            lineage_fingerprint
        ),
        reason_codes=tuple(reasons),
        decision_fingerprint=_sha(base),
    )


class SQLiteGovernedFeatureAdmissionEvidence:
    def __init__(self, path: str | Path) -> None:
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

    def record_decision(
        self,
        decision: GovernedFeatureAdmissionDecision,
    ) -> str:
        evidence_id = _sha(
            {
                "schema": (
                    "matrix.governed-feature-admission-evidence-id/1"
                ),
                "decision_fingerprint": (
                    decision.decision_fingerprint
                ),
            }
        )

        payload = {
            "schema": (
                "matrix.governed-feature-admission-evidence/1"
            ),
            "evidence_id": evidence_id,
            "status": decision.status,
            "downstream_eligible": (
                decision.downstream_eligible
            ),
            "sport": decision.sport,
            "canonical_id": (
                decision.canonical_id
            ),
            "snapshot_fingerprint": (
                decision.snapshot_fingerprint
            ),
            "feature_set_manifest_fingerprint": (
                decision
                .feature_set_manifest_fingerprint
            ),
            "lineage_fingerprint": (
                decision.lineage_fingerprint
            ),
            "reason_codes": list(
                decision.reason_codes
            ),
            "decision_fingerprint": (
                decision.decision_fingerprint
            ),
            "authoritative_for_future_consumers": True,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
        }

        payload_json = _canonical_json(payload)
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
                FROM governed_feature_admission
                WHERE decision_fingerprint = ?
                """,
                (
                    decision.decision_fingerprint,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")

                if (
                    str(existing[0])
                    == evidence_id
                    and str(existing[1])
                    == payload_sha
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
