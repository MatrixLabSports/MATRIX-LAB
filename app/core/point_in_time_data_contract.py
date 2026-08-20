from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping

from app.core.canonical_identity import (
    SQLiteCanonicalIdentityRegistry,
)
from app.core.provider_identity_mapping import (
    SQLiteProviderIdentityMappingLedger,
)


UTC = timezone.utc

_ALLOWED_ENTITY_TYPES = {
    "football": {
        "team",
        "player",
        "competition",
        "season",
        "match",
    },
    "tennis": {
        "player",
        "competition",
        "season",
        "match",
    },
}


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


def _validate_sport(value: object) -> str:
    if (
        not isinstance(value, str)
        or value not in _ALLOWED_ENTITY_TYPES
    ):
        raise ValueError("INVALID_SPORT")
    return value


def _validate_entity_type(
    *,
    sport: str,
    entity_type: object,
) -> str:
    if (
        not isinstance(entity_type, str)
        or entity_type not in _ALLOWED_ENTITY_TYPES[sport]
    ):
        raise ValueError("INVALID_ENTITY_TYPE_FOR_SPORT")
    return entity_type


def _nonempty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_{name}")
    return value.strip()


def _aware_utc(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"INVALID_{name}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"INVALID_{name}")
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class PointInTimeDataRecord:
    sport: str
    entity_type: str
    canonical_id: str
    provider_key: str
    provider_entity_id: str
    source_record_id: str
    schema_name: str
    schema_version: str
    transformation_version: str
    observed_at: datetime
    available_at: datetime
    payload: Mapping[str, Any]
    record_fingerprint: str

    def evidence_payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.point-in-time-data-record/1",
            "sport": self.sport,
            "entity_type": self.entity_type,
            "canonical_id": self.canonical_id,
            "provider_key": self.provider_key,
            "provider_entity_id": self.provider_entity_id,
            "source_record_id": self.source_record_id,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "transformation_version": (
                self.transformation_version
            ),
            "observed_at": _iso(self.observed_at),
            "available_at": _iso(self.available_at),
            "payload": dict(self.payload),
            "record_fingerprint": self.record_fingerprint,
            "missing_is_zero": False,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class PointInTimeAdmissionDecision:
    sport: str
    canonical_id: str
    decision_status: str
    downstream_eligible: bool
    as_of: datetime
    record_fingerprint: str
    mapping_fingerprint: str | None
    reason_codes: tuple[str, ...]
    decision_fingerprint: str


def compute_point_in_time_admission_decision_fingerprint(
    *,
    sport: str,
    canonical_id: str,
    decision_status: str,
    downstream_eligible: bool,
    as_of: datetime,
    record_fingerprint: str,
    mapping_fingerprint: str | None,
    reason_codes: tuple[str, ...],
) -> str:
    return _sha(
        {
            "schema": "matrix.point-in-time-admission/1",
            "sport": sport,
            "canonical_id": canonical_id,
            "decision_status": decision_status,
            "downstream_eligible": downstream_eligible,
            "as_of": _iso(as_of),
            "record_fingerprint": record_fingerprint,
            "mapping_fingerprint": mapping_fingerprint,
            "reason_codes": list(reason_codes),
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }
    )


def build_point_in_time_record(
    *,
    sport: str,
    entity_type: str,
    canonical_id: str,
    provider_key: str,
    provider_entity_id: str,
    source_record_id: str,
    schema_name: str,
    schema_version: str,
    transformation_version: str,
    observed_at: datetime,
    available_at: datetime,
    payload: Mapping[str, Any],
) -> PointInTimeDataRecord:
    sport = _validate_sport(sport)
    entity_type = _validate_entity_type(
        sport=sport,
        entity_type=entity_type,
    )

    canonical_id = _nonempty(
        "CANONICAL_ID",
        canonical_id,
    )
    provider_key = _nonempty(
        "PROVIDER_KEY",
        provider_key,
    )
    provider_entity_id = _nonempty(
        "PROVIDER_ENTITY_ID",
        provider_entity_id,
    )
    source_record_id = _nonempty(
        "SOURCE_RECORD_ID",
        source_record_id,
    )
    schema_name = _nonempty(
        "SCHEMA_NAME",
        schema_name,
    )
    schema_version = _nonempty(
        "SCHEMA_VERSION",
        schema_version,
    )
    transformation_version = _nonempty(
        "TRANSFORMATION_VERSION",
        transformation_version,
    )

    observed_at = _aware_utc(
        "OBSERVED_AT",
        observed_at,
    )
    available_at = _aware_utc(
        "AVAILABLE_AT",
        available_at,
    )

    if available_at < observed_at:
        raise ValueError(
            "AVAILABLE_AT_BEFORE_OBSERVED_AT"
        )

    if not isinstance(payload, Mapping):
        raise ValueError("INVALID_PAYLOAD")

    base = {
        "schema": "matrix.point-in-time-data-record/1",
        "sport": sport,
        "entity_type": entity_type,
        "canonical_id": canonical_id,
        "provider_key": provider_key,
        "provider_entity_id": provider_entity_id,
        "source_record_id": source_record_id,
        "schema_name": schema_name,
        "schema_version": schema_version,
        "transformation_version": transformation_version,
        "observed_at": _iso(observed_at),
        "available_at": _iso(available_at),
        "payload": dict(payload),
        "missing_is_zero": False,
        "name_join_used": False,
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return PointInTimeDataRecord(
        sport=sport,
        entity_type=entity_type,
        canonical_id=canonical_id,
        provider_key=provider_key,
        provider_entity_id=provider_entity_id,
        source_record_id=source_record_id,
        schema_name=schema_name,
        schema_version=schema_version,
        transformation_version=transformation_version,
        observed_at=observed_at,
        available_at=available_at,
        payload=dict(payload),
        record_fingerprint=_sha(base),
    )


def evaluate_point_in_time_record(
    *,
    record: PointInTimeDataRecord,
    as_of: datetime,
    identity_registry: SQLiteCanonicalIdentityRegistry,
    mapping_ledger: SQLiteProviderIdentityMappingLedger,
    expected_sport: str | None = None,
) -> PointInTimeAdmissionDecision:
    as_of = _aware_utc("AS_OF", as_of)

    if expected_sport is not None:
        expected_sport = _validate_sport(expected_sport)

    reasons: list[str] = []
    mapping_fingerprint: str | None = None

    if (
        expected_sport is not None
        and record.sport != expected_sport
    ):
        reasons.append("SPORT_BOUNDARY_VIOLATION")

    canonical = identity_registry.get_by_canonical_id(
        record.canonical_id
    )

    if canonical is None:
        reasons.append("CANONICAL_ENTITY_NOT_FOUND")
    else:
        if canonical.get("sport") != record.sport:
            reasons.append("SPORT_BOUNDARY_VIOLATION")
        if canonical.get("entity_type") != record.entity_type:
            reasons.append("ENTITY_TYPE_MISMATCH")

    if record.available_at > as_of:
        reasons.append("DATA_NOT_AVAILABLE_AS_OF")

    try:
        mapping = mapping_ledger.resolve_as_of(
            sport=record.sport,
            entity_type=record.entity_type,
            provider_key=record.provider_key,
            provider_entity_id=record.provider_entity_id,
            as_of=as_of,
        )
    except ValueError as error:
        if str(error) == "AMBIGUOUS_PROVIDER_MAPPING_AS_OF":
            reasons.append("AMBIGUOUS_PROVIDER_MAPPING_AS_OF")
            mapping = None
        else:
            raise

    if mapping is None:
        if "AMBIGUOUS_PROVIDER_MAPPING_AS_OF" not in reasons:
            reasons.append(
                "PROVIDER_MAPPING_NOT_AVAILABLE_AS_OF"
            )
    else:
        mapping_fingerprint = mapping.get(
            "mapping_fingerprint"
        )
        if mapping.get("canonical_id") != record.canonical_id:
            reasons.append(
                "PROVIDER_MAPPING_CANONICAL_MISMATCH"
            )

    reason_codes = tuple(dict.fromkeys(reasons))
    decision_status = (
        "ADMIT" if not reason_codes else "QUARANTINE"
    )
    downstream_eligible = decision_status == "ADMIT"

    decision_fingerprint = (
        compute_point_in_time_admission_decision_fingerprint(
            sport=record.sport,
            canonical_id=record.canonical_id,
            decision_status=decision_status,
            downstream_eligible=downstream_eligible,
            as_of=as_of,
            record_fingerprint=record.record_fingerprint,
            mapping_fingerprint=mapping_fingerprint,
            reason_codes=reason_codes,
        )
    )

    return PointInTimeAdmissionDecision(
        sport=record.sport,
        canonical_id=record.canonical_id,
        decision_status=decision_status,
        downstream_eligible=downstream_eligible,
        as_of=as_of,
        record_fingerprint=record.record_fingerprint,
        mapping_fingerprint=mapping_fingerprint,
        reason_codes=reason_codes,
        decision_fingerprint=decision_fingerprint,
    )
