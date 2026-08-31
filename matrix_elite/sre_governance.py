from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ErrorBudgetEvidence:
    slo_name: str
    window: str
    total_events: int
    good_events: int
    target_fraction: float

    def __post_init__(self) -> None:
        if not self.slo_name.strip() or not self.window.strip():
            raise ValueError("SLO_METADATA_REQUIRED")
        if self.total_events < 1 or not 0 <= self.good_events <= self.total_events:
            raise ValueError("SLO_EVENT_COUNTS_INVALID")
        if not 0 < self.target_fraction < 1:
            raise ValueError("SLO_TARGET_INVALID")

    @property
    def achieved_fraction(self) -> float:
        return self.good_events / self.total_events

    @property
    def allowed_bad_events(self) -> float:
        return self.total_events * (1.0 - self.target_fraction)

    @property
    def consumed_bad_events(self) -> int:
        return self.total_events - self.good_events

    @property
    def budget_remaining_fraction(self) -> float:
        allowed = self.allowed_bad_events
        if allowed <= 0:
            return 0.0
        return 1.0 - self.consumed_bad_events / allowed


@dataclass(frozen=True)
class ContinuityDrillEvidence:
    environment: str
    drill_completed_at: datetime
    backup_manifest_sha256: str
    restore_evidence_sha256: str
    recovery_time_seconds: float
    recovery_point_seconds: float
    load_test_evidence_sha256: str
    chaos_test_evidence_sha256: str
    alerting_test_evidence_sha256: str
    telemetry_schema_sha256: str
    real_restore_executed: bool
    load_test_passed: bool
    chaos_test_passed: bool
    telemetry_validation_passed: bool
    real_alert_delivery_verified: bool

    def __post_init__(self) -> None:
        if not self.environment.strip():
            raise ValueError("CONTINUITY_ENVIRONMENT_REQUIRED")
        if self.drill_completed_at.tzinfo is None or self.drill_completed_at.utcoffset() is None:
            raise ValueError("CONTINUITY_TIME_MUST_BE_AWARE")
        for name in (
            "backup_manifest_sha256", "restore_evidence_sha256", "load_test_evidence_sha256",
            "chaos_test_evidence_sha256", "alerting_test_evidence_sha256", "telemetry_schema_sha256",
        ):
            value = getattr(self, name)
            if len(value) != 64:
                raise ValueError(f"{name.upper()}_REQUIRED")
            int(value, 16)
        if self.recovery_time_seconds < 0 or self.recovery_point_seconds < 0:
            raise ValueError("RTO_RPO_INVALID")


def error_budget_gate(evidence: ErrorBudgetEvidence, *, minimum_remaining_fraction: float = 0.0) -> bool:
    if not -10 <= minimum_remaining_fraction <= 1:
        raise ValueError("ERROR_BUDGET_THRESHOLD_INVALID")
    return evidence.achieved_fraction >= evidence.target_fraction and evidence.budget_remaining_fraction >= minimum_remaining_fraction


def sre_continuity_gate(
    evidence: ContinuityDrillEvidence,
    *,
    max_rto_seconds: float,
    max_rpo_seconds: float,
    error_budgets: tuple[ErrorBudgetEvidence, ...],
) -> dict[str, object]:
    reasons: list[str] = []
    if not evidence.real_restore_executed:
        reasons.append("REAL_RESTORE_DRILL_REQUIRED")
    if not evidence.load_test_passed:
        reasons.append("LOAD_TEST_PASS_REQUIRED")
    if not evidence.chaos_test_passed:
        reasons.append("CHAOS_TEST_PASS_REQUIRED")
    if not evidence.telemetry_validation_passed:
        reasons.append("TELEMETRY_VALIDATION_REQUIRED")
    if not evidence.real_alert_delivery_verified:
        reasons.append("REAL_ALERT_DELIVERY_REQUIRED")
    if evidence.recovery_time_seconds > max_rto_seconds:
        reasons.append("RTO_BREACH")
    if evidence.recovery_point_seconds > max_rpo_seconds:
        reasons.append("RPO_BREACH")
    if not error_budgets:
        reasons.append("ERROR_BUDGET_EVIDENCE_REQUIRED")
    for budget in error_budgets:
        if not error_budget_gate(budget):
            reasons.append("ERROR_BUDGET_EXHAUSTED:" + budget.slo_name)
    return {"pass": not reasons, "reasons": tuple(reasons)}
