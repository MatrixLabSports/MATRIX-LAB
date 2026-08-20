from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any, Mapping, Sequence

from app.core.canonical_observation_store import (
    SQLiteCanonicalObservationStore,
)
from app.core.feature_definition_registry import (
    SQLiteFeatureDefinitionRegistry,
)


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
    return (
        value.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _aware_utc(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"INVALID_{name}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"INVALID_{name}")
    return value.astimezone(UTC)


def _validate_hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


def _validate_feature_value(
    *,
    value: Any,
    value_type: str,
    nullable: bool,
) -> Any:
    if value is None:
        if nullable:
            return None
        raise ValueError("NON_NULLABLE_FEATURE_IS_MISSING")

    if value_type == "float":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            raise ValueError("INVALID_FLOAT_FEATURE_VALUE")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("NONFINITE_FEATURE_VALUE")
        return value

    if value_type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("INVALID_INT_FEATURE_VALUE")
        return value

    if value_type == "bool":
        if not isinstance(value, bool):
            raise ValueError("INVALID_BOOL_FEATURE_VALUE")
        return value

    if value_type in {"string", "category"}:
        if not isinstance(value, str):
            raise ValueError("INVALID_STRING_FEATURE_VALUE")
        return value

    raise ValueError("UNKNOWN_FEATURE_VALUE_TYPE")


@dataclass(frozen=True)
class PointInTimeFeatureSnapshot:
    sport: str
    entity_type: str
    canonical_id: str
    feature_set_key: str
    feature_set_version: str
    as_of: datetime
    feature_values: tuple[tuple[str, Any], ...]
    definition_fingerprints: tuple[str, ...]
    source_record_fingerprints: tuple[str, ...]
    snapshot_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.point-in-time-feature-snapshot/1",
            "sport": self.sport,
            "entity_type": self.entity_type,
            "canonical_id": self.canonical_id,
            "feature_set_key": self.feature_set_key,
            "feature_set_version": self.feature_set_version,
            "as_of": _iso(self.as_of),
            "feature_values": [
                {
                    "feature_id": feature_id,
                    "value": value,
                }
                for feature_id, value in self.feature_values
            ],
            "definition_fingerprints": list(
                self.definition_fingerprints
            ),
            "source_record_fingerprints": list(
                self.source_record_fingerprints
            ),
            "snapshot_fingerprint": (
                self.snapshot_fingerprint
            ),
            "point_in_time_enforced": True,
            "missing_is_zero": False,
            "name_join_used": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def build_point_in_time_feature_snapshot(
    *,
    sport: str,
    entity_type: str,
    canonical_id: str,
    feature_set_key: str,
    feature_set_version: str,
    as_of: datetime,
    feature_values: Mapping[str, Any],
    source_record_fingerprints: Sequence[str],
    feature_registry: SQLiteFeatureDefinitionRegistry,
    observation_store: SQLiteCanonicalObservationStore,
) -> PointInTimeFeatureSnapshot:
    if sport not in {"football", "tennis"}:
        raise ValueError("INVALID_SPORT")

    if not isinstance(entity_type, str) or not entity_type:
        raise ValueError("INVALID_ENTITY_TYPE")

    if not isinstance(canonical_id, str) or not canonical_id:
        raise ValueError("INVALID_CANONICAL_ID")

    if not isinstance(feature_set_key, str) or not feature_set_key:
        raise ValueError("INVALID_FEATURE_SET_KEY")

    if (
        not isinstance(feature_set_version, str)
        or not feature_set_version
    ):
        raise ValueError("INVALID_FEATURE_SET_VERSION")

    as_of = _aware_utc("AS_OF", as_of)

    if not isinstance(feature_values, Mapping) or not feature_values:
        raise ValueError("EMPTY_FEATURE_VALUES")

    if (
        isinstance(source_record_fingerprints, (str, bytes))
        or not isinstance(source_record_fingerprints, Sequence)
        or not source_record_fingerprints
    ):
        raise ValueError("EMPTY_SOURCE_RECORDS")

    feature_integrity = feature_registry.audit_integrity()
    if not feature_integrity.ok:
        raise ValueError(
            "FEATURE_DEFINITION_INTEGRITY_FAILED"
        )

    observation_integrity = observation_store.audit_integrity()
    if not observation_integrity.ok:
        raise ValueError(
            "CANONICAL_OBSERVATION_INTEGRITY_FAILED"
        )

    normalized_features: list[tuple[str, Any]] = []
    definition_fingerprints: list[str] = []
    allowed_source_schemas: set[str] = set()

    for feature_id in sorted(feature_values):
        definition = feature_registry.get_by_feature_id(
            feature_id
        )
        if definition is None:
            raise ValueError(
                f"FEATURE_DEFINITION_NOT_FOUND:{feature_id}"
            )

        if definition.get("sport") != sport:
            raise ValueError(
                f"FEATURE_SPORT_MISMATCH:{feature_id}"
            )

        if definition.get("entity_type") != entity_type:
            raise ValueError(
                f"FEATURE_ENTITY_TYPE_MISMATCH:{feature_id}"
            )

        value = _validate_feature_value(
            value=feature_values[feature_id],
            value_type=definition["value_type"],
            nullable=bool(definition["nullable"]),
        )

        normalized_features.append(
            (feature_id, value)
        )
        definition_fingerprints.append(
            definition["definition_fingerprint"]
        )
        allowed_source_schemas.update(
            definition["source_schema_names"]
        )

    normalized_source_fingerprints = tuple(
        sorted(
            {
                _validate_hex64(
                    "SOURCE_RECORD_FINGERPRINT",
                    value,
                )
                for value in source_record_fingerprints
            }
        )
    )

    observed_source_schemas: set[str] = set()

    for record_fingerprint in normalized_source_fingerprints:
        observation = (
            observation_store.get_by_record_fingerprint(
                record_fingerprint
            )
        )

        if observation is None:
            raise ValueError(
                f"SOURCE_RECORD_NOT_FOUND:"
                f"{record_fingerprint}"
            )

        if observation.get("sport") != sport:
            raise ValueError(
                "SOURCE_RECORD_SPORT_MISMATCH"
            )

        if observation.get("entity_type") != entity_type:
            raise ValueError(
                "SOURCE_RECORD_ENTITY_TYPE_MISMATCH"
            )

        if observation.get("canonical_id") != canonical_id:
            raise ValueError(
                "SOURCE_RECORD_CANONICAL_ID_MISMATCH"
            )

        available_at = datetime.fromisoformat(
            observation["available_at"].replace(
                "Z",
                "+00:00",
            )
        ).astimezone(UTC)

        if available_at > as_of:
            raise ValueError(
                "FUTURE_SOURCE_RECORD_FOR_FEATURE"
            )

        observed_source_schemas.add(
            observation["schema_name"]
        )

    if not observed_source_schemas.issubset(
        allowed_source_schemas
    ):
        unexpected = sorted(
            observed_source_schemas
            - allowed_source_schemas
        )
        raise ValueError(
            "UNDECLARED_SOURCE_SCHEMA:"
            + ",".join(unexpected)
        )

    base = {
        "schema": "matrix.point-in-time-feature-snapshot/1",
        "sport": sport,
        "entity_type": entity_type,
        "canonical_id": canonical_id,
        "feature_set_key": feature_set_key,
        "feature_set_version": feature_set_version,
        "as_of": _iso(as_of),
        "feature_values": [
            {
                "feature_id": feature_id,
                "value": value,
            }
            for feature_id, value in normalized_features
        ],
        "definition_fingerprints": sorted(
            definition_fingerprints
        ),
        "source_record_fingerprints": list(
            normalized_source_fingerprints
        ),
        "point_in_time_enforced": True,
        "missing_is_zero": False,
        "name_join_used": False,
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return PointInTimeFeatureSnapshot(
        sport=sport,
        entity_type=entity_type,
        canonical_id=canonical_id,
        feature_set_key=feature_set_key,
        feature_set_version=feature_set_version,
        as_of=as_of,
        feature_values=tuple(normalized_features),
        definition_fingerprints=tuple(
            sorted(definition_fingerprints)
        ),
        source_record_fingerprints=(
            normalized_source_fingerprints
        ),
        snapshot_fingerprint=_sha(base),
    )
