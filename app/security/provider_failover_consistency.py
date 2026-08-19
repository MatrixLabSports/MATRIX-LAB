from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from app.release.canonical import canonical_sha256
from app.security.provider_reconciliation import ReconciliationAssessment, ReconciliationStatus


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sha(value: str, name: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase SHA-256")


@dataclass(frozen=True)
class FailoverConsistencySample:
    sample_id: str
    primary_provider_id: str
    fallback_provider_id: str
    checked_at: datetime
    reconciliation: ReconciliationAssessment

    def __post_init__(self) -> None:
        if not self.sample_id.strip():
            raise ValueError("sample_id is required")
        if not self.primary_provider_id.strip() or not self.fallback_provider_id.strip():
            raise ValueError("provider ids are required")
        if self.primary_provider_id == self.fallback_provider_id:
            raise ValueError("primary and fallback providers must differ")
        _aware(self.checked_at, "checked_at")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class FailoverConsistencyPolicy:
    min_consecutive_passes: int
    max_sample_age_minutes: int
    max_gap_seconds: int
    allow_watch_samples: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.min_consecutive_passes, "min_consecutive_passes"),
            (self.max_sample_age_minutes, "max_sample_age_minutes"),
            (self.max_gap_seconds, "max_gap_seconds"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be positive int")


class FailoverConsistencyStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class FailoverConsistencyAssessment:
    status: FailoverConsistencyStatus
    reasons: tuple[str, ...]
    sample_fingerprints: tuple[str, ...]
    consistent_samples: int
    automatic_provider_switch: bool = False
    automatic_wagering: bool = False
    production_certified: bool = False

    def __post_init__(self) -> None:
        if self.automatic_provider_switch:
            raise ValueError("V21 may not enable automatic provider switching")
        if self.automatic_wagering:
            raise ValueError("V21 may not enable wagering")
        if self.production_certified:
            raise ValueError("V21 may not certify production readiness")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def evaluate_failover_consistency(
    samples: tuple[FailoverConsistencySample, ...],
    policy: FailoverConsistencyPolicy,
    *,
    now: datetime,
) -> FailoverConsistencyAssessment:
    _aware(now, "now")
    if not samples:
        return FailoverConsistencyAssessment(
            FailoverConsistencyStatus.BLOCK,
            ("MISSING_FAILOVER_CONSISTENCY_SAMPLES",),
            (),
            0,
        )
    ordered = tuple(sorted(samples, key=lambda item: item.checked_at))
    reasons: list[str] = []
    watch: list[str] = []
    pair = (ordered[0].primary_provider_id, ordered[0].fallback_provider_id)
    if len({item.sample_id for item in ordered}) != len(ordered):
        reasons.append("DUPLICATE_FAILOVER_SAMPLE_ID")
    if any((item.primary_provider_id, item.fallback_provider_id) != pair for item in ordered):
        reasons.append("FAILOVER_PROVIDER_PAIR_CHANGED")
    if any(item.checked_at > now for item in ordered):
        reasons.append("FAILOVER_SAMPLE_FROM_FUTURE")
    if now - ordered[-1].checked_at > timedelta(minutes=policy.max_sample_age_minutes):
        reasons.append("FAILOVER_CONSISTENCY_WINDOW_STALE")
    for left, right in zip(ordered, ordered[1:]):
        if int((right.checked_at - left.checked_at).total_seconds()) > policy.max_gap_seconds:
            reasons.append("FAILOVER_SAMPLE_GAP_EXCEEDED")
            break

    pass_count = 0
    for sample in ordered:
        if sample.reconciliation.status is ReconciliationStatus.BLOCK:
            reasons.append("RECONCILIATION_BLOCK_IN_WINDOW")
            pass_count = 0
        elif sample.reconciliation.status is ReconciliationStatus.WATCH:
            if policy.allow_watch_samples:
                watch.append("RECONCILIATION_WATCH_IN_WINDOW")
            else:
                reasons.append("RECONCILIATION_WATCH_NOT_ALLOWED")
            pass_count = 0
        else:
            pass_count += 1

    if pass_count < policy.min_consecutive_passes:
        watch.append("INSUFFICIENT_CONSECUTIVE_RECONCILIATIONS")

    fingerprints = tuple(item.fingerprint for item in ordered)
    if reasons:
        return FailoverConsistencyAssessment(
            FailoverConsistencyStatus.BLOCK,
            tuple(dict.fromkeys(reasons + watch)),
            fingerprints,
            pass_count,
        )
    if watch:
        return FailoverConsistencyAssessment(
            FailoverConsistencyStatus.WATCH,
            tuple(dict.fromkeys(watch)),
            fingerprints,
            pass_count,
        )
    return FailoverConsistencyAssessment(
        FailoverConsistencyStatus.PASS,
        (),
        fingerprints,
        pass_count,
    )
