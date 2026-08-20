from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping


_ALLOWED_SPORTS = {"football", "tennis"}
_ALLOWED_SOURCE_STATUS = {"PASS", "WATCH", "BLOCK"}
_ALLOWED_ADMISSION_STATUS = {"ADMIT", "WATCH", "BLOCK"}


def _is_timezone_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _utc_iso(value: datetime) -> str:
    if not _is_timezone_aware(value):
        raise ValueError("TIMEZONE_UNVERIFIED")
    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_payload(payload: Mapping[str, Any]) -> str:
    return sha256(canonical_json(payload)).hexdigest()


def _validate_sha256(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("SOURCE_FINGERPRINT_MUST_BE_SHA256")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError("SOURCE_FINGERPRINT_MUST_BE_SHA256") from error


@dataclass(frozen=True)
class AdmissionEvidence:
    sport: str
    entity_key: str
    cutoff: datetime
    known_at: datetime
    source_status: str
    admission_status: str
    model_eligible: bool
    reason_codes: tuple[str, ...]
    source_fingerprint: str
    policy_version: str = "P50/1"

    def __post_init__(self) -> None:
        if self.sport not in _ALLOWED_SPORTS:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")

        if not isinstance(self.entity_key, str) or not self.entity_key.strip():
            raise ValueError("MISSING_CANONICAL_ENTITY_KEY")

        if not _is_timezone_aware(self.cutoff):
            raise ValueError("TIMEZONE_UNVERIFIED")
        if not _is_timezone_aware(self.known_at):
            raise ValueError("TIMEZONE_UNVERIFIED")

        if self.source_status not in _ALLOWED_SOURCE_STATUS:
            raise ValueError("INVALID_SOURCE_STATUS")

        if self.admission_status not in _ALLOWED_ADMISSION_STATUS:
            raise ValueError("INVALID_ADMISSION_STATUS")

        if self.model_eligible and self.admission_status != "ADMIT":
            raise ValueError("MODEL_ELIGIBILITY_CONTRADICTION")

        if self.known_at > self.cutoff and self.admission_status != "BLOCK":
            raise ValueError("FUTURE_KNOWLEDGE_MUST_BLOCK")

        _validate_sha256(self.source_fingerprint)

    @property
    def normalized_reason_codes(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.reason_codes)))

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "matrix.point-in-time-admission-evidence/1",
            "policy_version": self.policy_version,
            "sport": self.sport,
            "entity_key": self.entity_key.strip(),
            "cutoff": _utc_iso(self.cutoff),
            "known_at": _utc_iso(self.known_at),
            "source_status": self.source_status,
            "admission_status": self.admission_status,
            "model_eligible": self.model_eligible,
            "reason_codes": list(self.normalized_reason_codes),
            "source_fingerprint": self.source_fingerprint.lower(),
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }

    @property
    def decision_fingerprint(self) -> str:
        return sha256_payload(self.payload())
