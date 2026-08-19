from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .audit_authentication import AuditAuthenticationResult
from .dual_control import DualControlResult


class CriticalActionGateStatus(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class CriticalActionGateResult:
    status: CriticalActionGateStatus
    reasons: tuple[str, ...]
    eligible_for_human_execution_review: bool
    production_release_enabled: bool = False
    automatic_model_promotion_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.production_release_enabled:
            raise ValueError("V15 critical action gate does not authorize production")
        if self.automatic_model_promotion_enabled or self.automatic_wager_execution_enabled:
            raise ValueError("V15 gate may not enable promotion or automatic wagering")
        if self.eligible_for_human_execution_review and self.status is not CriticalActionGateStatus.PASS:
            raise ValueError("only PASS may be eligible for human execution review")


def evaluate_critical_action_gate(
    dual_control: DualControlResult,
    audit_authentications: tuple[AuditAuthenticationResult, ...],
) -> CriticalActionGateResult:
    blockers: list[str] = []
    if not dual_control.passed:
        blockers.extend(f"DUAL_CONTROL:{reason}" for reason in dual_control.reasons)
    if len(audit_authentications) < 2:
        blockers.append("INSUFFICIENT_AUTHENTICATED_AUDIT_EVIDENCE")
    for index, result in enumerate(audit_authentications):
        if not result.passed:
            blockers.extend(f"AUDIT_EVIDENCE_{index}:{reason}" for reason in result.reasons)
    if blockers:
        return CriticalActionGateResult(CriticalActionGateStatus.BLOCK, tuple(dict.fromkeys(blockers)), False)
    return CriticalActionGateResult(CriticalActionGateStatus.PASS, (), True)
