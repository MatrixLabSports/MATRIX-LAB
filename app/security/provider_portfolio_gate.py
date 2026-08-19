from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.release.canonical import canonical_sha256
from app.security.provider_failover import FailoverDrillAssessment, FailoverDrillStatus
from app.security.provider_portfolio import ProviderPortfolioAssessment, PortfolioStatus


class ProviderPortfolioGateStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ProviderPortfolioGateResult:
    status: ProviderPortfolioGateStatus
    reasons: tuple[str, ...]
    portfolio_fingerprint: str
    failover_evidence_fingerprint: str | None
    provider_portfolio_certified: bool = False
    automatic_provider_switch: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.provider_portfolio_certified:
            raise ValueError("software may not self-certify provider portfolio suitability")
        if self.automatic_provider_switch:
            raise ValueError("provider switching remains human-controlled")
        if self.automatic_wagering:
            raise ValueError("provider portfolio gate may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def evaluate_provider_portfolio_gate(
    portfolio: ProviderPortfolioAssessment,
    failover: FailoverDrillAssessment,
) -> ProviderPortfolioGateResult:
    reasons: list[str] = []
    if portfolio.status is PortfolioStatus.BLOCK:
        reasons.append("PORTFOLIO_ASSESSMENT_BLOCK")
    elif portfolio.status is PortfolioStatus.WATCH:
        reasons.append("PORTFOLIO_ASSESSMENT_WATCH")
    if not portfolio.failover_ready:
        reasons.append("PORTFOLIO_FAILOVER_NOT_READY")
    if failover.status is FailoverDrillStatus.BLOCK:
        reasons.append("FAILOVER_DRILL_BLOCK")
    elif failover.status is FailoverDrillStatus.WATCH:
        reasons.append("FAILOVER_DRILL_WATCH")

    if any(reason.endswith("BLOCK") or reason == "PORTFOLIO_FAILOVER_NOT_READY" for reason in reasons):
        status = ProviderPortfolioGateStatus.BLOCK
    elif reasons:
        status = ProviderPortfolioGateStatus.WATCH
    else:
        status = ProviderPortfolioGateStatus.PASS
    return ProviderPortfolioGateResult(
        status=status,
        reasons=tuple(dict.fromkeys(reasons)),
        portfolio_fingerprint=portfolio.plan_fingerprint,
        failover_evidence_fingerprint=failover.evidence_fingerprint,
    )
