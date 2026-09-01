from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum
from hashlib import sha256
import json
import re

_SHA = re.compile(r"^[0-9a-f]{64}$")


class PushPolicy(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PUSH = "PUSH"
    NO_PUSH_HALF_LINES_ONLY = "NO_PUSH_HALF_LINES_ONLY"
    VENUE_RULE_REQUIRED = "VENUE_RULE_REQUIRED"


class DNPPolicy(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    VOID = "VOID"
    VENUE_RULE_REQUIRED = "VENUE_RULE_REQUIRED"


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name.upper()}_REQUIRED")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name.upper()}_MUST_BE_AWARE")
    return value.astimezone(UTC)


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"{name.upper()}_SHA256_REQUIRED")
    return value


def _canonical_sha(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SettlementRuleDefinition:
    version: str
    market_version: str
    sport: str
    market_family: str
    market_variant: str
    period: str
    venue: str
    jurisdiction: str
    valid_from: datetime
    valid_until: datetime | None
    rule_source_sha256: str
    outcome_source: str
    push_policy: PushPolicy
    dnp_policy: DNPPolicy
    abandonment_rule: str
    postponement_rule: str
    provider_override_required: bool

    def __post_init__(self) -> None:
        _required(self.version, "version")
        if not self.version.startswith("MATRIX-SETTLE-R2/"):
            raise ValueError("SETTLEMENT_VERSION_INVALID")
        if not self.market_version.startswith("MATRIX-MARKET-R2/"):
            raise ValueError("MARKET_VERSION_REQUIRED")
        if self.sport not in {"football", "tennis"}:
            raise ValueError("SPORT_INVALID")
        for name in ("market_family", "market_variant", "period", "venue", "jurisdiction", "outcome_source", "abandonment_rule", "postponement_rule"):
            _required(getattr(self, name), name)
        valid_from = _aware(self.valid_from, "valid_from")
        if self.valid_until is not None and _aware(self.valid_until, "valid_until") <= valid_from:
            raise ValueError("SETTLEMENT_VALIDITY_WINDOW_INVALID")
        _sha(self.rule_source_sha256, "rule_source")
        if self.provider_override_required and self.venue == "CANONICAL_GENERIC":
            raise ValueError("PROVIDER_OVERRIDE_REQUIRES_EXACT_VENUE")
        expected_prefix = f"MATRIX-SETTLE-R2/{self.venue}/{self.sport}/{self.market_family}/{self.market_variant}/"
        if not self.version.startswith(expected_prefix):
            raise ValueError("SETTLEMENT_VERSION_IDENTITY_MISMATCH")

    def payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "market_version": self.market_version,
            "sport": self.sport,
            "market_family": self.market_family,
            "market_variant": self.market_variant,
            "period": self.period,
            "venue": self.venue,
            "jurisdiction": self.jurisdiction,
            "valid_from": _aware(self.valid_from, "valid_from").isoformat(),
            "valid_until": None if self.valid_until is None else _aware(self.valid_until, "valid_until").isoformat(),
            "rule_source_sha256": self.rule_source_sha256,
            "outcome_source": self.outcome_source,
            "push_policy": self.push_policy.value,
            "dnp_policy": self.dnp_policy.value,
            "abandonment_rule": self.abandonment_rule,
            "postponement_rule": self.postponement_rule,
            "provider_override_required": self.provider_override_required,
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_sha(self.payload())

    def applies_at(self, when: datetime) -> bool:
        point = _aware(when, "when")
        start = _aware(self.valid_from, "valid_from")
        if point < start:
            return False
        return self.valid_until is None or point < _aware(self.valid_until, "valid_until")


def validate_settlement_profile_for_market(rule: SettlementRuleDefinition, market_payload: dict[str, object]) -> None:
    exact = {
        "sport": rule.sport,
        "market_family": rule.market_family,
        "market_variant": rule.market_variant,
        "period": rule.period,
        "version": rule.market_version,
    }
    for key, expected in exact.items():
        if market_payload.get(key) != expected:
            raise ValueError(f"SETTLEMENT_MARKET_BINDING_MISMATCH:{key}")
