from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from app.release.canonical import canonical_sha256


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class FailoverDrillStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class FailoverDrillEvidence:
    drill_id: str
    primary_provider_id: str
    fallback_provider_id: str
    started_at: datetime
    completed_at: datetime
    recovery_time_seconds: int
    expected_recovery_time_seconds: int
    data_loss_events: int
    duplicate_events: int
    reconciliation_passed: bool
    schema_compatible: bool
    identifiers_reconciled: bool
    rights_revalidated: bool
    human_observed: bool

    def __post_init__(self) -> None:
        for value, name in (
            (self.drill_id, "drill_id"),
            (self.primary_provider_id, "primary_provider_id"),
            (self.fallback_provider_id, "fallback_provider_id"),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        _aware(self.started_at, "started_at")
        _aware(self.completed_at, "completed_at")
        if self.completed_at <= self.started_at:
            raise ValueError("completed_at must be after started_at")
        for value, name in (
            (self.recovery_time_seconds, "recovery_time_seconds"),
            (self.expected_recovery_time_seconds, "expected_recovery_time_seconds"),
            (self.data_loss_events, "data_loss_events"),
            (self.duplicate_events, "duplicate_events"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be int")
            if value < 0:
                raise ValueError(f"{name} may not be negative")
        if self.expected_recovery_time_seconds <= 0:
            raise ValueError("expected_recovery_time_seconds must be positive")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class FailoverDrillAssessment:
    status: FailoverDrillStatus
    reasons: tuple[str, ...]
    evidence_fingerprint: str | None
    automatic_failover_enabled: bool = False

    def __post_init__(self) -> None:
        if self.automatic_failover_enabled:
            raise ValueError("drill assessment may not enable automatic failover")


def evaluate_failover_drill(
    evidence: FailoverDrillEvidence | None,
    *,
    now: datetime,
    max_age_days: int = 90,
) -> FailoverDrillAssessment:
    _aware(now, "now")
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or max_age_days <= 0:
        raise ValueError("max_age_days must be positive int")
    if evidence is None:
        return FailoverDrillAssessment(FailoverDrillStatus.BLOCK, ("MISSING_FAILOVER_DRILL_EVIDENCE",), None)
    reasons: list[str] = []
    watch: list[str] = []
    if evidence.completed_at > now:
        reasons.append("FUTURE_FAILOVER_DRILL_EVIDENCE")
    if now - evidence.completed_at > timedelta(days=max_age_days):
        reasons.append("STALE_FAILOVER_DRILL_EVIDENCE")
    if evidence.recovery_time_seconds > evidence.expected_recovery_time_seconds:
        reasons.append("FAILOVER_RECOVERY_TIME_EXCEEDED")
    if evidence.data_loss_events > 0:
        reasons.append("FAILOVER_DATA_LOSS_DETECTED")
    if evidence.duplicate_events > 0:
        watch.append("FAILOVER_DUPLICATE_EVENTS_DETECTED")
    if not evidence.reconciliation_passed:
        reasons.append("FAILOVER_RECONCILIATION_FAILED")
    if not evidence.schema_compatible:
        reasons.append("FAILOVER_SCHEMA_INCOMPATIBLE")
    if not evidence.identifiers_reconciled:
        reasons.append("FAILOVER_IDENTIFIERS_NOT_RECONCILED")
    if not evidence.rights_revalidated:
        reasons.append("FAILOVER_RIGHTS_NOT_REVALIDATED")
    if not evidence.human_observed:
        watch.append("FAILOVER_DRILL_NOT_HUMAN_OBSERVED")
    if reasons:
        return FailoverDrillAssessment(FailoverDrillStatus.BLOCK, tuple(dict.fromkeys(reasons + watch)), evidence.fingerprint)
    if watch:
        return FailoverDrillAssessment(FailoverDrillStatus.WATCH, tuple(dict.fromkeys(watch)), evidence.fingerprint)
    return FailoverDrillAssessment(FailoverDrillStatus.PASS, (), evidence.fingerprint)
