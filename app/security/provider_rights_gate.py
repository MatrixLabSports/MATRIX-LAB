from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .provider_rights import ProviderRightsAssessment, ProviderRightsStatus


class ProviderRightsGateStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ProviderRightsGateInput:
    acquisition: ProviderRightsAssessment
    storage: ProviderRightsAssessment
    analytics_or_training: ProviderRightsAssessment
    display_or_distribution: ProviderRightsAssessment
    termination_plan_verified: bool
    attribution_control_verified: bool
    provider_inventory_verified: bool
    independent_legal_review_reference: str | None


@dataclass(frozen=True)
class ProviderRightsGateResult:
    status: ProviderRightsGateStatus
    reasons: tuple[str, ...]
    eligible_for_provider_integration_review: bool
    legal_rights_certified: bool = False
    automatic_model_promotion_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.legal_rights_certified:
            raise ValueError("provider-rights gate may not self-certify legal rights")
        if self.automatic_model_promotion_enabled or self.automatic_wager_execution_enabled:
            raise ValueError("provider-rights gate may not promote models or enable wagering")


def evaluate_provider_rights_gate(data: ProviderRightsGateInput) -> ProviderRightsGateResult:
    blockers: list[str] = []
    watches: list[str] = []

    assessments = (
        ("ACQUISITION", data.acquisition),
        ("STORAGE", data.storage),
        ("ANALYTICS_OR_TRAINING", data.analytics_or_training),
        ("DISPLAY_OR_DISTRIBUTION", data.display_or_distribution),
    )
    for label, assessment in assessments:
        if assessment.status is ProviderRightsStatus.BLOCK:
            blockers.extend(f"{label}:{reason}" for reason in (assessment.reasons or ("BLOCKED",)))
        elif assessment.status is ProviderRightsStatus.WATCH:
            watches.extend(f"{label}:{reason}" for reason in (assessment.reasons or ("WATCH",)))

    if not data.termination_plan_verified:
        blockers.append("PROVIDER_TERMINATION_PLAN_NOT_VERIFIED")
    if not data.attribution_control_verified:
        blockers.append("ATTRIBUTION_CONTROL_NOT_VERIFIED")
    if not data.provider_inventory_verified:
        blockers.append("PROVIDER_INVENTORY_NOT_VERIFIED")
    if not (data.independent_legal_review_reference or "").strip():
        watches.append("INDEPENDENT_PROVIDER_RIGHTS_REVIEW_NOT_RECORDED")

    reasons = tuple(dict.fromkeys(blockers + watches))
    if blockers:
        return ProviderRightsGateResult(
            ProviderRightsGateStatus.BLOCK,
            reasons,
            eligible_for_provider_integration_review=False,
        )
    if watches:
        return ProviderRightsGateResult(
            ProviderRightsGateStatus.WATCH,
            reasons,
            eligible_for_provider_integration_review=True,
        )
    return ProviderRightsGateResult(
        ProviderRightsGateStatus.PASS,
        (),
        eligible_for_provider_integration_review=True,
    )
