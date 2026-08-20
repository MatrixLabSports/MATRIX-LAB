from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
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


def _aware(name: str, value: object) -> datetime:
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


def _get(record: object, name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def _type_matches(
    value: object,
    value_type: str,
) -> bool:
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "integer":
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
        )
    if value_type == "float":
        return (
            isinstance(value, float)
            and math.isfinite(value)
        )
    if value_type == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
    if value_type == "object":
        return isinstance(value, Mapping)
    if value_type == "array":
        return (
            isinstance(value, (list, tuple))
            and not isinstance(value, (str, bytes))
        )
    return False


@dataclass(frozen=True)
class SchemaAdmissionDecision:
    status: str
    downstream_eligible: bool
    sport: str
    entity_type: str
    schema_name: str
    schema_version: str
    schema_fingerprint: str | None
    reason_codes: tuple[str, ...]
    decision_fingerprint: str


def evaluate_schema_compatibility(
    *,
    record: object,
    entity_type: str,
    as_of: datetime,
    registry,
) -> SchemaAdmissionDecision:
    as_of = _aware("AS_OF", as_of)

    sport = _get(record, "sport")
    schema_name = _get(
        record,
        "schema_name",
    )
    schema_version = _get(
        record,
        "schema_version",
    )
    payload = _get(record, "payload")

    reasons: list[str] = []
    schema_fingerprint: str | None = None

    if sport not in {"football", "tennis"}:
        reasons.append("INVALID_SPORT")

    if not isinstance(entity_type, str) or not entity_type:
        reasons.append("INVALID_ENTITY_TYPE")

    if not isinstance(schema_name, str) or not schema_name:
        reasons.append("INVALID_SCHEMA_NAME")

    if (
        not isinstance(schema_version, str)
        or not schema_version
    ):
        reasons.append("INVALID_SCHEMA_VERSION")

    if not isinstance(payload, Mapping):
        reasons.append("INVALID_PAYLOAD")

    contract = None
    if not reasons:
        contract = registry.get_exact(
            sport=sport,
            entity_type=entity_type,
            schema_name=schema_name,
            schema_version=schema_version,
        )

        if contract is None:
            reasons.append(
                "UNKNOWN_SCHEMA_VERSION"
            )

    if contract is not None:
        contract_available = datetime.fromisoformat(
            contract["available_at"].replace(
                "Z",
                "+00:00",
            )
        ).astimezone(UTC)

        if contract_available > as_of:
            reasons.append(
                "SCHEMA_NOT_AVAILABLE_AS_OF"
            )

        schema_fingerprint = contract[
            "schema_fingerprint"
        ]

        fields = {
            item["name"]: item
            for item in contract["fields"]
        }

        for name, field in fields.items():
            if name not in payload:
                if field["required"]:
                    reasons.append(
                        f"MISSING_REQUIRED_FIELD:{name}"
                    )
                continue

            value = payload[name]

            if value is None:
                if not field["nullable"]:
                    reasons.append(
                        f"NULL_NOT_ALLOWED:{name}"
                    )
                continue

            if not _type_matches(
                value,
                field["value_type"],
            ):
                reasons.append(
                    f"TYPE_MISMATCH:{name}"
                )

        extras = (
            set(payload)
            - set(fields)
        )

        if (
            extras
            and not contract[
                "allow_additional_fields"
            ]
        ):
            for name in sorted(extras):
                reasons.append(
                    f"UNDECLARED_FIELD:{name}"
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
            "matrix.schema-admission-decision/1"
        ),
        "status": status,
        "downstream_eligible": eligible,
        "sport": sport,
        "entity_type": entity_type,
        "schema_name": schema_name,
        "schema_version": schema_version,
        "schema_fingerprint": (
            schema_fingerprint
        ),
        "as_of": _iso(as_of),
        "reason_codes": reasons,
        "automatic_schema_promotion": False,
        "automatic_model_promotion": False,
    }

    return SchemaAdmissionDecision(
        status=status,
        downstream_eligible=eligible,
        sport=sport,
        entity_type=entity_type,
        schema_name=schema_name,
        schema_version=schema_version,
        schema_fingerprint=(
            schema_fingerprint
        ),
        reason_codes=tuple(reasons),
        decision_fingerprint=_sha(base),
    )
