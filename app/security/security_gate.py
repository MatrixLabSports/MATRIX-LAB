from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

from .dependencies import VulnerabilityScanEvidence
from .secrets import SecretFinding
from .threat_model import ThreatModelReport


class SecurityStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class SecurityGateInput:
    threat_report: ThreatModelReport
    secret_findings: tuple[SecretFinding, ...]
    config_integrity_ok: bool
    dependency_lock_ok: bool
    vulnerability_scan: VulnerabilityScanEvidence | None
    environments_separated: bool
    access_logging_enabled: bool
    least_privilege_enforced: bool


@dataclass(frozen=True)
class SecurityGateResult:
    status: SecurityStatus
    reasons: tuple[str, ...]
    automatic_promotion_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.automatic_promotion_enabled or self.automatic_wager_execution_enabled:
            raise ValueError("security gate may never enable promotion or wagering")


def evaluate_security_gate(
    data: SecurityGateInput,
    *,
    now: datetime,
    max_scan_age_hours: float = 24.0,
    max_db_age_hours: float = 24.0,
) -> SecurityGateResult:
    blockers: list[str] = []
    watches: list[str] = []
    if not data.threat_report.passed:
        blockers.append("UNMITIGATED_HIGH_OR_CRITICAL_THREAT")
    if data.threat_report.review_threat_ids:
        watches.append("RESIDUAL_OR_MEDIUM_RISK_REVIEW")
    if data.secret_findings:
        blockers.append("HARDCODED_SECRET_EVIDENCE")
    if not data.config_integrity_ok:
        blockers.append("CONFIG_INTEGRITY_FAILURE")
    if not data.dependency_lock_ok:
        blockers.append("DEPENDENCY_LOCK_FAILURE")
    if data.vulnerability_scan is None:
        blockers.append("MISSING_VULNERABILITY_SCAN_EVIDENCE")
    elif not data.vulnerability_scan.acceptable(
        now=now,
        max_scan_age_hours=max_scan_age_hours,
        max_db_age_hours=max_db_age_hours,
    ):
        blockers.append("VULNERABILITY_SCAN_NOT_ACCEPTABLE")
    if not data.environments_separated:
        blockers.append("ENVIRONMENT_SEPARATION_MISSING")
    if not data.access_logging_enabled:
        blockers.append("ACCESS_LOGGING_MISSING")
    if not data.least_privilege_enforced:
        blockers.append("LEAST_PRIVILEGE_MISSING")
    if blockers:
        return SecurityGateResult(SecurityStatus.BLOCK, tuple(dict.fromkeys(blockers + watches)))
    if watches:
        return SecurityGateResult(SecurityStatus.WATCH, tuple(watches))
    return SecurityGateResult(SecurityStatus.PASS, ())
