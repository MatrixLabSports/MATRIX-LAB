from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

from app.release.canonical import canonical_sha256


def _required(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} is required")
    return cleaned


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256")


def _bps(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int basis points")
    if not 0 <= value <= 10_000:
        raise ValueError(f"{name} must be between 0 and 10000")


class TruthDomain(str, Enum):
    FIXTURE_IDENTITY = "FIXTURE_IDENTITY"
    EVENT_STATE = "EVENT_STATE"
    SCORE = "SCORE"
    STATISTICS = "STATISTICS"
    MARKET_IDENTITY = "MARKET_IDENTITY"
    TIMING = "TIMING"


class AuthorityStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class SourceOfTruthRule:
    rule_id: str
    provider_id: str
    sport: str
    competition_id: str
    domain: TruthDomain
    valid_from: datetime
    valid_to: datetime | None
    evidence_sha256: str
    confidence_bps: int
    human_approved: bool
    independent_reviewed: bool
    policy_version: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.rule_id, "rule_id"),
            (self.provider_id, "provider_id"),
            (self.sport, "sport"),
            (self.competition_id, "competition_id"),
            (self.policy_version, "policy_version"),
        ):
            _required(value, name)
        _aware(self.valid_from, "valid_from")
        if self.valid_to is not None:
            _aware(self.valid_to, "valid_to")
            if self.valid_to <= self.valid_from:
                raise ValueError("valid_to must be after valid_from")
        _sha256(self.evidence_sha256, "evidence_sha256")
        _bps(self.confidence_bps, "confidence_bps")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)

    def active_at(self, at: datetime) -> bool:
        _aware(at, "at")
        return self.valid_from <= at and (self.valid_to is None or at < self.valid_to)


@dataclass(frozen=True)
class AuthorityAssessment:
    status: AuthorityStatus
    reasons: tuple[str, ...]
    provider_id: str | None
    domain: TruthDomain
    rule_fingerprint: str | None
    source_of_truth_certified: bool = False
    automatic_provider_switch: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.source_of_truth_certified:
            raise ValueError("software may not self-certify a provider as universally authoritative")
        if self.automatic_provider_switch:
            raise ValueError("authority assessment may not switch providers automatically")
        if self.automatic_wagering:
            raise ValueError("authority assessment may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def resolve_source_of_truth(
    rules: Iterable[SourceOfTruthRule],
    *,
    provider_ids: tuple[str, ...],
    sport: str,
    competition_id: str,
    domain: TruthDomain,
    at: datetime,
    min_confidence_bps: int = 9900,
) -> AuthorityAssessment:
    _aware(at, "at")
    _bps(min_confidence_bps, "min_confidence_bps")
    sport = _required(sport, "sport")
    competition_id = _required(competition_id, "competition_id")
    if not provider_ids or len(set(provider_ids)) != len(provider_ids):
        return AuthorityAssessment(
            AuthorityStatus.BLOCK,
            ("PROVIDER_SET_INVALID",),
            None,
            domain,
            None,
        )

    active = [
        rule
        for rule in rules
        if rule.provider_id in provider_ids
        and rule.sport == sport
        and rule.competition_id == competition_id
        and rule.domain is domain
        and rule.active_at(at)
    ]
    if not active:
        return AuthorityAssessment(
            AuthorityStatus.BLOCK,
            ("NO_ACTIVE_SOURCE_OF_TRUTH_RULE",),
            None,
            domain,
            None,
        )

    providers = {rule.provider_id for rule in active}
    if len(providers) != 1:
        return AuthorityAssessment(
            AuthorityStatus.BLOCK,
            ("CONFLICTING_SOURCE_OF_TRUTH_RULES",),
            None,
            domain,
            None,
        )

    ranked = sorted(active, key=lambda rule: (rule.confidence_bps, rule.valid_from, rule.rule_id), reverse=True)
    selected = ranked[0]
    reasons: list[str] = []
    if selected.confidence_bps < min_confidence_bps:
        reasons.append("SOURCE_OF_TRUTH_CONFIDENCE_BELOW_MINIMUM")
    if not selected.human_approved:
        reasons.append("SOURCE_OF_TRUTH_NOT_HUMAN_APPROVED")
    if not selected.independent_reviewed:
        reasons.append("SOURCE_OF_TRUTH_NOT_INDEPENDENTLY_REVIEWED")

    if reasons:
        return AuthorityAssessment(
            AuthorityStatus.WATCH,
            tuple(reasons),
            selected.provider_id,
            domain,
            selected.fingerprint,
        )
    return AuthorityAssessment(
        AuthorityStatus.PASS,
        (),
        selected.provider_id,
        domain,
        selected.fingerprint,
    )


def audit_source_of_truth_conflicts(rules: Iterable[SourceOfTruthRule]) -> tuple[str, ...]:
    grouped: dict[tuple[str, str, TruthDomain], list[SourceOfTruthRule]] = {}
    for rule in rules:
        key = (rule.sport, rule.competition_id, rule.domain)
        grouped.setdefault(key, []).append(rule)

    issues: list[str] = []
    for key, values in grouped.items():
        values = sorted(values, key=lambda rule: rule.valid_from)
        for index, left in enumerate(values):
            for right in values[index + 1 :]:
                overlaps = (
                    (left.valid_to is None or right.valid_from < left.valid_to)
                    and (right.valid_to is None or left.valid_from < right.valid_to)
                )
                if overlaps and left.provider_id != right.provider_id:
                    issues.append(
                        "SOURCE_OF_TRUTH_TEMPORAL_CONFLICT:"
                        + ":".join((key[0], key[1], key[2].value))
                    )
    return tuple(dict.fromkeys(issues))
