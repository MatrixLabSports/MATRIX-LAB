from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .jurisdiction_evidence import JurisdictionAssessment, JurisdictionStatus
from .purpose_governance import PurposeAssessment, PurposeStatus
from .transfer_governance import TransferAssessment, TransferStatus


class ComplianceGateStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ComplianceEvidenceGateInput:
    inventory_verified: bool
    purpose_assessment: PurposeAssessment
    jurisdiction_assessment: JurisdictionAssessment
    transfer_assessments: tuple[TransferAssessment, ...]
    access_control_verified: bool
    retention_control_verified: bool
    deletion_control_verified: bool
    incident_response_verified: bool
    independent_legal_review_reference: str | None


@dataclass(frozen=True)
class ComplianceEvidenceGateResult:
    status: ComplianceGateStatus
    reasons: tuple[str, ...]
    eligible_for_legal_review: bool
    legal_compliance_certified: bool = False
    automatic_model_promotion_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.legal_compliance_certified:
            raise ValueError("compliance gate may not self-certify legal compliance")
        if self.automatic_model_promotion_enabled or self.automatic_wager_execution_enabled:
            raise ValueError("compliance gate may not enable models or wagering")


def evaluate_compliance_evidence_gate(data: ComplianceEvidenceGateInput) -> ComplianceEvidenceGateResult:
    blockers: list[str] = []
    watches: list[str] = []
    if not data.inventory_verified:
        blockers.append("DATA_INVENTORY_NOT_VERIFIED")
    if data.purpose_assessment.status is PurposeStatus.BLOCK:
        blockers.extend(data.purpose_assessment.reasons or ("PURPOSE_GOVERNANCE_BLOCKED",))
    if data.jurisdiction_assessment.status is JurisdictionStatus.BLOCK:
        blockers.extend(data.jurisdiction_assessment.reasons or ("JURISDICTION_EVIDENCE_BLOCKED",))
    elif data.jurisdiction_assessment.status is JurisdictionStatus.WATCH:
        watches.extend(data.jurisdiction_assessment.reasons or ("JURISDICTION_REVIEW_REQUIRED",))
    for assessment in data.transfer_assessments:
        if assessment.status is TransferStatus.BLOCK:
            blockers.extend(assessment.reasons or ("TRANSFER_BLOCKED",))
        elif assessment.status is TransferStatus.WATCH:
            watches.extend(assessment.reasons or ("TRANSFER_REVIEW_REQUIRED",))
    if not data.access_control_verified:
        blockers.append("ACCESS_CONTROL_NOT_VERIFIED")
    if not data.retention_control_verified:
        blockers.append("RETENTION_CONTROL_NOT_VERIFIED")
    if not data.deletion_control_verified:
        blockers.append("DELETION_CONTROL_NOT_VERIFIED")
    if not data.incident_response_verified:
        blockers.append("INCIDENT_RESPONSE_NOT_VERIFIED")
    if not (data.independent_legal_review_reference or "").strip():
        watches.append("INDEPENDENT_LEGAL_REVIEW_NOT_RECORDED")
    if blockers:
        return ComplianceEvidenceGateResult(
            ComplianceGateStatus.BLOCK,
            tuple(dict.fromkeys(blockers + watches)),
            eligible_for_legal_review=False,
        )
    if watches:
        return ComplianceEvidenceGateResult(
            ComplianceGateStatus.WATCH,
            tuple(dict.fromkeys(watches)),
            eligible_for_legal_review=True,
        )
    return ComplianceEvidenceGateResult(ComplianceGateStatus.PASS, (), eligible_for_legal_review=True)
