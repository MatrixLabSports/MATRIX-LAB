from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from app.release.canonical import canonical_sha256


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_nonempty(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} is required")
    return cleaned


def _require_bps(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int basis points")
    if value < 0 or value > 10_000:
        raise ValueError(f"{name} must be between 0 and 10000 basis points")


def _require_nonnegative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value < 0:
        raise ValueError(f"{name} may not be negative")


class ProviderRole(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    REFERENCE = "REFERENCE"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"


class ProviderOperationalStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ProviderOperationalProfile:
    provider_id: str
    profile_version: str
    role: ProviderRole
    availability_slo_bps: int
    max_p95_latency_ms: int
    max_p99_latency_ms: int
    max_p95_freshness_seconds: int
    min_coverage_bps: int
    min_quality_score_bps: int
    min_stable_id_rate_bps: int
    max_error_rate_bps: int
    max_quota_utilization_bps: int
    min_quota_reserve_units: int
    monthly_budget_cents: int
    max_projected_budget_utilization_bps: int
    observation_max_age_minutes: int

    def __post_init__(self) -> None:
        _require_nonempty(self.provider_id, "provider_id")
        _require_nonempty(self.profile_version, "profile_version")
        for value, name in (
            (self.availability_slo_bps, "availability_slo_bps"),
            (self.min_coverage_bps, "min_coverage_bps"),
            (self.min_quality_score_bps, "min_quality_score_bps"),
            (self.min_stable_id_rate_bps, "min_stable_id_rate_bps"),
            (self.max_error_rate_bps, "max_error_rate_bps"),
            (self.max_quota_utilization_bps, "max_quota_utilization_bps"),
            (self.max_projected_budget_utilization_bps, "max_projected_budget_utilization_bps"),
        ):
            _require_bps(value, name)
        for value, name in (
            (self.max_p95_latency_ms, "max_p95_latency_ms"),
            (self.max_p99_latency_ms, "max_p99_latency_ms"),
            (self.max_p95_freshness_seconds, "max_p95_freshness_seconds"),
            (self.min_quota_reserve_units, "min_quota_reserve_units"),
            (self.observation_max_age_minutes, "observation_max_age_minutes"),
            (self.monthly_budget_cents, "monthly_budget_cents"),
        ):
            _require_nonnegative_int(value, name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_p99_latency_ms < self.max_p95_latency_ms:
            raise ValueError("max_p99_latency_ms may not be lower than max_p95_latency_ms")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class ProviderOperationalObservation:
    observation_id: str
    provider_id: str
    profile_fingerprint: str
    observed_at: datetime
    window_start: datetime
    window_end: datetime
    availability_bps: int
    p95_latency_ms: int
    p99_latency_ms: int
    p95_freshness_seconds: int
    coverage_bps: int
    quality_score_bps: int
    stable_id_rate_bps: int
    error_rate_bps: int
    quota_limit_units: int
    quota_remaining_units: int
    expected_units_next_window: int
    current_month_cost_cents: int
    projected_month_cost_cents: int
    provider_incident_open: bool = False
    provider_degraded: bool = False

    def __post_init__(self) -> None:
        _require_nonempty(self.observation_id, "observation_id")
        _require_nonempty(self.provider_id, "provider_id")
        if len(self.profile_fingerprint) != 64 or any(c not in "0123456789abcdef" for c in self.profile_fingerprint):
            raise ValueError("profile_fingerprint must be lowercase SHA-256")
        for value, name in (
            (self.observed_at, "observed_at"),
            (self.window_start, "window_start"),
            (self.window_end, "window_end"),
        ):
            _require_aware(value, name)
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        if self.observed_at < self.window_end:
            raise ValueError("observed_at may not be before window_end")
        for value, name in (
            (self.availability_bps, "availability_bps"),
            (self.coverage_bps, "coverage_bps"),
            (self.quality_score_bps, "quality_score_bps"),
            (self.stable_id_rate_bps, "stable_id_rate_bps"),
            (self.error_rate_bps, "error_rate_bps"),
        ):
            _require_bps(value, name)
        for value, name in (
            (self.p95_latency_ms, "p95_latency_ms"),
            (self.p99_latency_ms, "p99_latency_ms"),
            (self.p95_freshness_seconds, "p95_freshness_seconds"),
            (self.quota_limit_units, "quota_limit_units"),
            (self.quota_remaining_units, "quota_remaining_units"),
            (self.expected_units_next_window, "expected_units_next_window"),
            (self.current_month_cost_cents, "current_month_cost_cents"),
            (self.projected_month_cost_cents, "projected_month_cost_cents"),
        ):
            _require_nonnegative_int(value, name)
        if self.p99_latency_ms < self.p95_latency_ms:
            raise ValueError("p99_latency_ms may not be lower than p95_latency_ms")
        if self.quota_limit_units <= 0:
            raise ValueError("quota_limit_units must be positive")
        if self.quota_remaining_units > self.quota_limit_units:
            raise ValueError("quota_remaining_units may not exceed quota_limit_units")
        if self.projected_month_cost_cents < self.current_month_cost_cents:
            raise ValueError("projected_month_cost_cents may not be lower than current_month_cost_cents")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)

    @property
    def quota_utilization_bps(self) -> int:
        used = self.quota_limit_units - self.quota_remaining_units
        return (used * 10_000) // self.quota_limit_units


@dataclass(frozen=True)
class ProviderOperationalAssessment:
    status: ProviderOperationalStatus
    reasons: tuple[str, ...]
    profile_fingerprint: str
    observation_fingerprint: str | None
    automatic_provider_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.automatic_provider_promotion:
            raise ValueError("provider promotion may not be automatic")
        if self.automatic_wagering:
            raise ValueError("operational provider gate may not enable wagering")


def evaluate_provider_operational(
    profile: ProviderOperationalProfile,
    observation: ProviderOperationalObservation | None,
    *,
    now: datetime,
    warning_margin_bps: int = 1000,
) -> ProviderOperationalAssessment:
    _require_aware(now, "now")
    _require_bps(warning_margin_bps, "warning_margin_bps")
    reasons: list[str] = []
    watch: list[str] = []

    if observation is None:
        return ProviderOperationalAssessment(
            status=ProviderOperationalStatus.BLOCK,
            reasons=("MISSING_OPERATIONAL_OBSERVATION",),
            profile_fingerprint=profile.fingerprint,
            observation_fingerprint=None,
        )

    if observation.provider_id != profile.provider_id:
        reasons.append("PROVIDER_OPERATIONAL_PROFILE_MISMATCH")
    if observation.profile_fingerprint != profile.fingerprint:
        reasons.append("OPERATIONAL_PROFILE_FINGERPRINT_MISMATCH")
    if observation.observed_at > now:
        reasons.append("FUTURE_OPERATIONAL_OBSERVATION")
    if now - observation.observed_at > timedelta(minutes=profile.observation_max_age_minutes):
        reasons.append("STALE_OPERATIONAL_OBSERVATION")

    if observation.availability_bps < profile.availability_slo_bps:
        reasons.append("AVAILABILITY_BELOW_SLO")
    elif observation.availability_bps < min(10_000, profile.availability_slo_bps + max(1, warning_margin_bps // 10)):
        watch.append("AVAILABILITY_NEAR_SLO")

    if observation.p95_latency_ms > profile.max_p95_latency_ms:
        reasons.append("P95_LATENCY_ABOVE_SLO")
    elif observation.p95_latency_ms * 10_000 > profile.max_p95_latency_ms * (10_000 - warning_margin_bps):
        watch.append("P95_LATENCY_NEAR_SLO")

    if observation.p99_latency_ms > profile.max_p99_latency_ms:
        reasons.append("P99_LATENCY_ABOVE_SLO")
    elif observation.p99_latency_ms * 10_000 > profile.max_p99_latency_ms * (10_000 - warning_margin_bps):
        watch.append("P99_LATENCY_NEAR_SLO")

    if observation.p95_freshness_seconds > profile.max_p95_freshness_seconds:
        reasons.append("DATA_FRESHNESS_ABOVE_SLO")
    elif observation.p95_freshness_seconds * 10_000 > profile.max_p95_freshness_seconds * (10_000 - warning_margin_bps):
        watch.append("DATA_FRESHNESS_NEAR_SLO")

    if observation.coverage_bps < profile.min_coverage_bps:
        reasons.append("COVERAGE_BELOW_MINIMUM")
    elif observation.coverage_bps < min(10_000, profile.min_coverage_bps + max(1, warning_margin_bps // 10)):
        watch.append("COVERAGE_NEAR_MINIMUM")

    if observation.quality_score_bps < profile.min_quality_score_bps:
        reasons.append("QUALITY_BELOW_MINIMUM")
    elif observation.quality_score_bps < min(10_000, profile.min_quality_score_bps + max(1, warning_margin_bps // 10)):
        watch.append("QUALITY_NEAR_MINIMUM")

    if observation.stable_id_rate_bps < profile.min_stable_id_rate_bps:
        reasons.append("STABLE_ID_RATE_BELOW_MINIMUM")
    elif observation.stable_id_rate_bps < min(10_000, profile.min_stable_id_rate_bps + max(1, warning_margin_bps // 10)):
        watch.append("STABLE_ID_RATE_NEAR_MINIMUM")

    if observation.error_rate_bps > profile.max_error_rate_bps:
        reasons.append("ERROR_RATE_ABOVE_MAXIMUM")
    elif observation.error_rate_bps * 10_000 > profile.max_error_rate_bps * (10_000 - warning_margin_bps):
        watch.append("ERROR_RATE_NEAR_MAXIMUM")

    if observation.quota_utilization_bps > profile.max_quota_utilization_bps:
        reasons.append("QUOTA_UTILIZATION_ABOVE_MAXIMUM")
    if observation.quota_remaining_units < profile.min_quota_reserve_units:
        reasons.append("QUOTA_RESERVE_BELOW_MINIMUM")
    if observation.expected_units_next_window > observation.quota_remaining_units:
        reasons.append("INSUFFICIENT_QUOTA_FOR_NEXT_WINDOW")

    projected_budget_bps = (observation.projected_month_cost_cents * 10_000) // profile.monthly_budget_cents
    if projected_budget_bps > profile.max_projected_budget_utilization_bps:
        reasons.append("PROJECTED_COST_ABOVE_BUDGET_POLICY")
    elif projected_budget_bps * 10_000 > profile.max_projected_budget_utilization_bps * (10_000 - warning_margin_bps):
        watch.append("PROJECTED_COST_NEAR_BUDGET_POLICY")

    if observation.provider_incident_open:
        reasons.append("PROVIDER_INCIDENT_OPEN")
    elif observation.provider_degraded:
        watch.append("PROVIDER_MARKED_DEGRADED")

    if reasons:
        status = ProviderOperationalStatus.BLOCK
        all_reasons = tuple(dict.fromkeys(reasons + watch))
    elif watch:
        status = ProviderOperationalStatus.WATCH
        all_reasons = tuple(dict.fromkeys(watch))
    else:
        status = ProviderOperationalStatus.PASS
        all_reasons = ()

    return ProviderOperationalAssessment(
        status=status,
        reasons=all_reasons,
        profile_fingerprint=profile.fingerprint,
        observation_fingerprint=observation.fingerprint,
    )
