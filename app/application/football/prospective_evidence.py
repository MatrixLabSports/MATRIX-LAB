from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from app.application.football.controlled_live_readiness import (
    ControlledLiveEvidence,
    ControlledLiveReadiness,
    ControlledLivePolicy,
    assess_controlled_live_readiness,
)
from app.research.football.prospective_ledger import (
    FootballProspectiveEvidenceLedger,
    ProspectiveLedgerAudit,
    ProspectivePerformancePolicy,
    ProspectivePerformanceSummary,
)


@dataclass(frozen=True)
class ValidatedMarketEvidence:
    market_key: str
    model_version: str
    model_state: str
    protected_test_samples: int
    brier_score: float | None
    calibration_error: float | None
    baseline_dominance_confirmed: bool
    walk_forward_folds: int
    reproducibility_verified: bool
    risk_policy_approved: bool
    kill_switch_verified: bool
    human_approval_required: bool
    compliance_review_complete: bool
    unresolved_p0_count: int
    evidence_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.market_key.strip() or not self.model_version.strip():
            raise ValueError("market_key and model_version are required")
        if self.model_state.strip().upper() not in {"BACKTESTED", "PAPER_TRADING", "CONTROLLED_LIVE"}:
            raise ValueError("invalid model_state")
        object.__setattr__(self, "market_key", self.market_key.strip())
        object.__setattr__(self, "model_version", self.model_version.strip())
        object.__setattr__(self, "model_state", self.model_state.strip().upper())

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ValidatedMarketEvidence":
        data = dict(payload)
        if isinstance(data.get("evidence_sha256s"), list):
            data["evidence_sha256s"] = tuple(data["evidence_sha256s"])
        return cls(**data)


@dataclass(frozen=True)
class ProspectiveReadinessBundle:
    ledger_audit: ProspectiveLedgerAudit
    prospective_performance: ProspectivePerformanceSummary
    prospective_blocked_reasons: tuple[str, ...]
    controlled_live_evidence: ControlledLiveEvidence
    readiness: ControlledLiveReadiness

    def as_dict(self) -> dict[str, Any]:
        return {
            "ledger_audit": asdict(self.ledger_audit),
            "prospective_performance": asdict(self.prospective_performance),
            "prospective_blocked_reasons": list(self.prospective_blocked_reasons),
            "controlled_live_evidence": asdict(self.controlled_live_evidence),
            "readiness": self.readiness.as_dict(),
        }


def build_prospective_readiness_bundle(
    *,
    ledger: FootballProspectiveEvidenceLedger,
    validation: ValidatedMarketEvidence,
    performance_policy: ProspectivePerformancePolicy = ProspectivePerformancePolicy(),
    controlled_live_policy: ControlledLivePolicy = ControlledLivePolicy(),
    bootstrap_iterations: int = 2000,
) -> ProspectiveReadinessBundle:
    audit = ledger.audit()
    summary = ledger.performance_summary(
        market_key=validation.market_key,
        model_version=validation.model_version,
        bootstrap_iterations=bootstrap_iterations,
    )
    prospective_reasons = performance_policy.reasons_blocked(summary)

    evidence_hashes = tuple(dict.fromkeys((*validation.evidence_sha256s, audit.ledger_sha256)))
    controlled = ControlledLiveEvidence(
        market_key=validation.market_key,
        model_version=validation.model_version,
        model_state=validation.model_state,
        protected_test_samples=validation.protected_test_samples,
        brier_score=validation.brier_score,
        calibration_error=validation.calibration_error,
        baseline_dominance_confirmed=validation.baseline_dominance_confirmed,
        walk_forward_folds=validation.walk_forward_folds,
        paper_trading_samples=summary.decision_count,
        settled_paper_trading_samples=summary.settled_count,
        odds_capture_samples=summary.decision_count,
        odds_source_authorized=audit.authorized_entry_odds and audit.authorized_closing_odds,
        odds_timestamp_integrity_verified=audit.timestamp_integrity_verified,
        reproducibility_verified=validation.reproducibility_verified,
        risk_policy_approved=validation.risk_policy_approved,
        kill_switch_verified=validation.kill_switch_verified,
        human_approval_required=validation.human_approval_required,
        compliance_review_complete=validation.compliance_review_complete,
        unresolved_p0_count=validation.unresolved_p0_count,
        evidence_sha256s=evidence_hashes,
        closing_odds_samples=summary.closing_odds_count,
        closing_odds_integrity_verified=(
            audit.timestamp_integrity_verified
            and audit.authorized_closing_odds
            and "closing_odds_not_near_kickoff" not in prospective_reasons
        ),
        prospective_performance_verified=not prospective_reasons,
        positive_clv_confirmed=(summary.mean_log_clv_ci_low is not None and summary.mean_log_clv_ci_low > 0),
    )
    readiness = assess_controlled_live_readiness(controlled, policy=controlled_live_policy)
    return ProspectiveReadinessBundle(
        ledger_audit=audit,
        prospective_performance=summary,
        prospective_blocked_reasons=prospective_reasons,
        controlled_live_evidence=controlled,
        readiness=readiness,
    )
