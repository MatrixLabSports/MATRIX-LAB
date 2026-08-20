from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from app.core.admission_fingerprint import AdmissionEvidence


_ALLOWED_SPORTS = {"football", "tennis"}


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_payload(value: Any) -> str:
    return sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class DatasetRowEvidence:
    sport: str
    canonical_entity_key: str
    admission_evidence: AdmissionEvidence
    row_payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.sport not in _ALLOWED_SPORTS:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")

        if (
            not isinstance(self.canonical_entity_key, str)
            or not self.canonical_entity_key.strip()
        ):
            raise ValueError("MISSING_CANONICAL_ENTITY_KEY")

        if self.admission_evidence.sport != self.sport:
            raise ValueError("CROSS_SPORT_ADMISSION_EVIDENCE")

        if (
            self.admission_evidence.entity_key.strip()
            != self.canonical_entity_key.strip()
        ):
            raise ValueError("ADMISSION_ENTITY_KEY_MISMATCH")

        if not isinstance(self.row_payload, Mapping):
            raise ValueError("INVALID_ROW_PAYLOAD")

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "schema": "matrix.dataset-row-evidence/1",
            "sport": self.sport,
            "canonical_entity_key": self.canonical_entity_key.strip(),
            "admission_fingerprint": (
                self.admission_evidence.decision_fingerprint
            ),
            "source_fingerprint": (
                self.admission_evidence.source_fingerprint.lower()
            ),
            "row_payload": dict(self.row_payload),
        }

    @property
    def row_fingerprint(self) -> str:
        return sha256_payload(self.fingerprint_payload())


def build_dataset_manifest(
    *,
    sport: str,
    dataset_key: str,
    as_of: str,
    rows: Sequence[DatasetRowEvidence],
    policy_version: str = "P51/1",
) -> dict[str, Any]:
    if sport not in _ALLOWED_SPORTS:
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    if not isinstance(dataset_key, str) or not dataset_key.strip():
        raise ValueError("MISSING_DATASET_KEY")

    if any(row.sport != sport for row in rows):
        raise ValueError("CROSS_SPORT_ROW_CONTAMINATION")

    ordered = sorted(
        rows,
        key=lambda row: (
            row.canonical_entity_key.strip(),
            row.admission_evidence.decision_fingerprint,
            row.row_fingerprint,
        ),
    )

    entity_keys = [
        row.canonical_entity_key.strip()
        for row in ordered
    ]
    if len(entity_keys) != len(set(entity_keys)):
        raise ValueError("DUPLICATE_CANONICAL_ENTITY_KEY")

    row_records = [
        {
            "canonical_entity_key": row.canonical_entity_key.strip(),
            "admission_fingerprint": (
                row.admission_evidence.decision_fingerprint
            ),
            "source_fingerprint": (
                row.admission_evidence.source_fingerprint.lower()
            ),
            "row_fingerprint": row.row_fingerprint,
        }
        for row in ordered
    ]

    body = {
        "schema": "matrix.point-in-time-dataset-manifest/1",
        "policy_version": policy_version,
        "sport": sport,
        "dataset_key": dataset_key.strip(),
        "as_of": as_of,
        "row_count": len(row_records),
        "rows": row_records,
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return {
        **body,
        "dataset_fingerprint": sha256_payload(body),
    }


def verify_dataset_manifest(
    *,
    manifest: Mapping[str, Any],
    rows: Sequence[DatasetRowEvidence],
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []

    manifest_sport = manifest.get("sport")
    if manifest_sport not in _ALLOWED_SPORTS:
        reasons.append("INVALID_MANIFEST_SPORT")

    if any(row.sport != manifest_sport for row in rows):
        reasons.append("CROSS_SPORT_ROW_CONTAMINATION")

    body = {
        key: value
        for key, value in manifest.items()
        if key != "dataset_fingerprint"
    }

    try:
        expected_dataset_fingerprint = sha256_payload(body)
    except (TypeError, ValueError):
        reasons.append("INVALID_MANIFEST_PAYLOAD")
        expected_dataset_fingerprint = None

    if manifest.get("dataset_fingerprint") != expected_dataset_fingerprint:
        reasons.append("MANIFEST_FINGERPRINT_MISMATCH")

    manifest_rows = manifest.get("rows")
    if not isinstance(manifest_rows, list):
        reasons.append("INVALID_MANIFEST_ROWS")
        return False, tuple(sorted(set(reasons)))

    if manifest.get("row_count") != len(manifest_rows):
        reasons.append("ROW_COUNT_MISMATCH")

    current_by_key: dict[str, DatasetRowEvidence] = {}
    duplicate_current = False

    for row in rows:
        key = row.canonical_entity_key.strip()
        if key in current_by_key:
            duplicate_current = True
        current_by_key[key] = row

    if duplicate_current:
        reasons.append("DUPLICATE_CURRENT_ENTITY_KEY")

    seen_manifest_keys: set[str] = set()

    for record in manifest_rows:
        if not isinstance(record, Mapping):
            reasons.append("INVALID_MANIFEST_ROW")
            continue

        key = record.get("canonical_entity_key")

        if not isinstance(key, str):
            reasons.append("INVALID_MANIFEST_ENTITY_KEY")
            continue

        if key in seen_manifest_keys:
            reasons.append("DUPLICATE_MANIFEST_ENTITY_KEY")

        seen_manifest_keys.add(key)
        current = current_by_key.get(key)

        if current is None:
            reasons.append("ROW_MISSING_FROM_CURRENT_DATASET")
            continue

        if (
            record.get("admission_fingerprint")
            != current.admission_evidence.decision_fingerprint
        ):
            reasons.append("ADMISSION_FINGERPRINT_CHANGED")

        if (
            record.get("source_fingerprint")
            != current.admission_evidence.source_fingerprint.lower()
        ):
            reasons.append("SOURCE_FINGERPRINT_CHANGED")

        if record.get("row_fingerprint") != current.row_fingerprint:
            reasons.append("ROW_CONTENT_CHANGED")

    if set(current_by_key) != seen_manifest_keys:
        reasons.append("UNMANIFESTED_ROW_PRESENT")

    return not reasons, tuple(sorted(set(reasons)))
