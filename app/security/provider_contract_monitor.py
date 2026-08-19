from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .provider_rights import ProviderRightsEvidence, ProviderRightsReviewOutcome


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class ContractMonitorStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ContractMonitorResult:
    status: ContractMonitorStatus
    reasons: tuple[str, ...]
    days_until_expiry: int | None
    renewal_verified: bool


def monitor_provider_contract(
    evidence: ProviderRightsEvidence,
    *,
    now: datetime,
    warning_days: int,
    renewal_verified: bool = False,
) -> ContractMonitorResult:
    _require_aware(now, "now")
    if isinstance(warning_days, bool) or not isinstance(warning_days, int):
        raise TypeError("warning_days must be int")
    if warning_days < 0:
        raise ValueError("warning_days may not be negative")
    if evidence.reviewed_at > now or evidence.valid_from > now:
        return ContractMonitorResult(ContractMonitorStatus.BLOCK, ("RIGHTS_EVIDENCE_NOT_YET_VALID",), None, renewal_verified)
    if evidence.revoked:
        return ContractMonitorResult(ContractMonitorStatus.BLOCK, ("RIGHTS_EVIDENCE_REVOKED",), None, renewal_verified)
    if evidence.outcome is ProviderRightsReviewOutcome.REJECTED:
        return ContractMonitorResult(ContractMonitorStatus.BLOCK, ("RIGHTS_EVIDENCE_REJECTED",), None, renewal_verified)
    seconds = (evidence.valid_until - now).total_seconds()
    days = int(seconds // 86400)
    if seconds <= 0:
        return ContractMonitorResult(ContractMonitorStatus.BLOCK, ("RIGHTS_EVIDENCE_EXPIRED",), days, renewal_verified)
    if days < warning_days and not renewal_verified:
        return ContractMonitorResult(ContractMonitorStatus.WATCH, ("RIGHTS_EVIDENCE_EXPIRING_WITHOUT_VERIFIED_RENEWAL",), days, False)
    if evidence.outcome is ProviderRightsReviewOutcome.REVIEW_REQUIRED:
        return ContractMonitorResult(ContractMonitorStatus.WATCH, ("RIGHTS_REVIEW_REQUIRED",), days, renewal_verified)
    return ContractMonitorResult(ContractMonitorStatus.HEALTHY, (), days, renewal_verified)
