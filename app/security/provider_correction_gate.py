from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.release.canonical import canonical_sha256
from app.security.provider_temporal_truth import (
    DecisionEvidenceFreeze,
    PostDecisionRevisionImpact,
    ProviderTruthVersion,
    RevisionImpactLevel,
    TemporalTruthPolicy,
    TemporalTruthStatus,
    assess_post_decision_revision_impact,
    assess_truth_chain,
)


@dataclass(frozen=True)
class ProviderCorrectionGateResult:
    status: TemporalTruthStatus
    reasons: tuple[str, ...]
    truth_chain_fingerprint: str
    decision_impact_fingerprint: str | None
    controlled_reanalysis_required: bool
    historical_backfill_allowed: bool = False
    automatic_model_promotion: bool = False
    automatic_provider_switch: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.historical_backfill_allowed:
            raise ValueError("correction gate may not silently backfill historical decision evidence")
        if self.automatic_model_promotion:
            raise ValueError("correction gate may not promote models")
        if self.automatic_provider_switch:
            raise ValueError("correction gate may not switch providers")
        if self.automatic_wagering:
            raise ValueError("correction gate may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def evaluate_provider_correction_gate(
    versions: tuple[ProviderTruthVersion, ...],
    *,
    policy: TemporalTruthPolicy,
    now: datetime,
    decision_freeze: DecisionEvidenceFreeze | None = None,
) -> ProviderCorrectionGateResult:
    chain = assess_truth_chain(versions, policy=policy, now=now)
    if chain.status is TemporalTruthStatus.BLOCK:
        return ProviderCorrectionGateResult(
            TemporalTruthStatus.BLOCK,
            tuple(dict.fromkeys(("TRUTH_CHAIN_BLOCKED",) + chain.reasons)),
            chain.fingerprint,
            None,
            True,
        )

    reasons = list(chain.reasons if chain.status is TemporalTruthStatus.WATCH else ())
    impact: PostDecisionRevisionImpact | None = None
    if decision_freeze is not None:
        impact = assess_post_decision_revision_impact(
            decision_freeze,
            versions,
            now=now,
            policy=policy,
        )
        if impact.status is TemporalTruthStatus.BLOCK:
            return ProviderCorrectionGateResult(
                TemporalTruthStatus.BLOCK,
                tuple(dict.fromkeys(reasons + list(impact.reasons))),
                chain.fingerprint,
                impact.fingerprint,
                True,
            )
        reasons.extend(impact.reasons)

    reanalysis = impact is not None and impact.reanalysis_required
    if impact is not None and impact.impact_level in {RevisionImpactLevel.HIGH, RevisionImpactLevel.CRITICAL}:
        reasons.append("HIGH_IMPACT_CORRECTION_REQUIRES_CONTROLLED_REVIEW")

    status = TemporalTruthStatus.WATCH if reasons else TemporalTruthStatus.PASS
    return ProviderCorrectionGateResult(
        status,
        tuple(dict.fromkeys(reasons)),
        chain.fingerprint,
        impact.fingerprint if impact is not None else None,
        reanalysis,
    )
