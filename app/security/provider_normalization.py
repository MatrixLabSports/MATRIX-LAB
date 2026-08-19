from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

from app.release.canonical import canonical_sha256


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _nonempty(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} is required")
    return cleaned


def _sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase SHA-256")


def _bps(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int basis points")
    if value < 0 or value > 10_000:
        raise ValueError(f"{name} must be between 0 and 10000")


class EntityKind(str, Enum):
    TEAM = "TEAM"
    PLAYER = "PLAYER"
    COMPETITION = "COMPETITION"
    VENUE = "VENUE"
    FIXTURE = "FIXTURE"


@dataclass(frozen=True)
class EntityCrosswalkEntry:
    provider_id: str
    entity_kind: EntityKind
    provider_entity_id: str
    canonical_entity_id: str
    mapping_version: str
    valid_from: datetime
    valid_to: datetime | None
    confidence_bps: int
    evidence_sha256: str
    human_reviewed: bool

    def __post_init__(self) -> None:
        for value, name in (
            (self.provider_id, "provider_id"),
            (self.provider_entity_id, "provider_entity_id"),
            (self.canonical_entity_id, "canonical_entity_id"),
            (self.mapping_version, "mapping_version"),
        ):
            _nonempty(value, name)
        _aware(self.valid_from, "valid_from")
        if self.valid_to is not None:
            _aware(self.valid_to, "valid_to")
            if self.valid_to <= self.valid_from:
                raise ValueError("valid_to must be after valid_from")
        _bps(self.confidence_bps, "confidence_bps")
        _sha256(self.evidence_sha256, "evidence_sha256")

    @property
    def provider_key(self) -> tuple[str, EntityKind, str]:
        return (self.provider_id, self.entity_kind, self.provider_entity_id)

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)

    def active_at(self, at: datetime) -> bool:
        _aware(at, "at")
        return self.valid_from <= at and (self.valid_to is None or at < self.valid_to)


class CrosswalkStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class CrosswalkResolution:
    status: CrosswalkStatus
    canonical_entity_id: str | None
    reasons: tuple[str, ...]
    mapping_fingerprint: str | None


def resolve_entity(
    entries: Iterable[EntityCrosswalkEntry],
    *,
    provider_id: str,
    entity_kind: EntityKind,
    provider_entity_id: str,
    at: datetime,
    min_confidence_bps: int = 9900,
    require_human_review: bool = True,
) -> CrosswalkResolution:
    _aware(at, "at")
    _bps(min_confidence_bps, "min_confidence_bps")
    provider_id = _nonempty(provider_id, "provider_id")
    provider_entity_id = _nonempty(provider_entity_id, "provider_entity_id")
    matches = [
        item
        for item in entries
        if item.provider_id == provider_id
        and item.entity_kind is entity_kind
        and item.provider_entity_id == provider_entity_id
        and item.active_at(at)
    ]
    if not matches:
        return CrosswalkResolution(CrosswalkStatus.BLOCK, None, ("MISSING_ACTIVE_CROSSWALK",), None)
    canonical_ids = {item.canonical_entity_id for item in matches}
    if len(canonical_ids) != 1:
        return CrosswalkResolution(CrosswalkStatus.BLOCK, None, ("CONFLICTING_ACTIVE_CROSSWALK",), None)
    ranked = sorted(matches, key=lambda item: (item.confidence_bps, item.valid_from, item.mapping_version), reverse=True)
    selected = ranked[0]
    reasons: list[str] = []
    if selected.confidence_bps < min_confidence_bps:
        reasons.append("CROSSWALK_CONFIDENCE_BELOW_MINIMUM")
    if require_human_review and not selected.human_reviewed:
        reasons.append("CROSSWALK_NOT_HUMAN_REVIEWED")
    if reasons:
        return CrosswalkResolution(CrosswalkStatus.WATCH, selected.canonical_entity_id, tuple(reasons), selected.fingerprint)
    return CrosswalkResolution(CrosswalkStatus.PASS, selected.canonical_entity_id, (), selected.fingerprint)


def audit_crosswalk_conflicts(entries: Iterable[EntityCrosswalkEntry]) -> tuple[str, ...]:
    grouped: dict[tuple[str, EntityKind, str], list[EntityCrosswalkEntry]] = {}
    for item in entries:
        grouped.setdefault(item.provider_key, []).append(item)
    reasons: list[str] = []
    for key, values in grouped.items():
        values = sorted(values, key=lambda item: item.valid_from)
        for i, left in enumerate(values):
            for right in values[i + 1 :]:
                left_end = left.valid_to
                right_end = right.valid_to
                overlaps = (left_end is None or right.valid_from < left_end) and (right_end is None or left.valid_from < right_end)
                if overlaps and left.canonical_entity_id != right.canonical_entity_id:
                    reasons.append(
                        "CROSSWALK_TEMPORAL_CONFLICT:"
                        + ":".join((key[0], key[1].value, key[2]))
                    )
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True)
class CanonicalFixtureIdentity:
    sport: str
    canonical_fixture_id: str
    competition_id: str
    home_entity_id: str
    away_entity_id: str
    kickoff_utc: datetime
    venue_entity_id: str | None = None
    round_key: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.sport, "sport"),
            (self.canonical_fixture_id, "canonical_fixture_id"),
            (self.competition_id, "competition_id"),
            (self.home_entity_id, "home_entity_id"),
            (self.away_entity_id, "away_entity_id"),
        ):
            _nonempty(value, name)
        if self.home_entity_id == self.away_entity_id:
            raise ValueError("home and away canonical entities must differ")
        _aware(self.kickoff_utc, "kickoff_utc")
        if self.venue_entity_id is not None:
            _nonempty(self.venue_entity_id, "venue_entity_id")
        if self.round_key is not None:
            _nonempty(self.round_key, "round_key")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)
