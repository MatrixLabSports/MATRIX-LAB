from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .data_inventory import DataInventoryRecord


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class TransferOutcome(str, Enum):
    APPROVED_FOR_GOVERNED_TRANSFER = "APPROVED_FOR_GOVERNED_TRANSFER"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"


class TransferStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class TransferEvidence:
    transfer_id: str
    asset_id: str
    purpose_id: str
    source_jurisdiction: str
    destination_jurisdiction: str
    mechanism_reference: str
    assessment_reference: str
    approved_by_role: str
    assessed_at: datetime
    valid_until: datetime
    evidence_sha256: str
    outcome: TransferOutcome
    revoked: bool = False

    def __post_init__(self) -> None:
        required = (
            self.transfer_id,
            self.asset_id,
            self.purpose_id,
            self.source_jurisdiction,
            self.destination_jurisdiction,
            self.mechanism_reference,
            self.assessment_reference,
            self.approved_by_role,
        )
        if not all(value.strip() for value in required):
            raise ValueError("transfer evidence metadata is required")
        _aware(self.assessed_at, "assessed_at")
        _aware(self.valid_until, "valid_until")
        if self.valid_until <= self.assessed_at:
            raise ValueError("valid_until must be after assessed_at")
        digest = self.evidence_sha256.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("evidence_sha256 must be SHA-256 hex")
        object.__setattr__(self, "evidence_sha256", digest)


@dataclass(frozen=True)
class TransferAssessment:
    status: TransferStatus
    reasons: tuple[str, ...]
    legal_adequacy_certified: bool = False

    def __post_init__(self) -> None:
        if self.legal_adequacy_certified:
            raise ValueError("software may not self-certify transfer legal adequacy")


def evaluate_transfer(
    inventory: DataInventoryRecord,
    *,
    purpose_id: str,
    source_jurisdiction: str,
    destination_jurisdiction: str,
    evidence: TransferEvidence | None,
    now: datetime,
) -> TransferAssessment:
    _aware(now, "now")
    if source_jurisdiction == destination_jurisdiction:
        return TransferAssessment(TransferStatus.NOT_REQUIRED, ())
    reasons: list[str] = []
    if source_jurisdiction not in inventory.jurisdictions:
        reasons.append("SOURCE_JURISDICTION_NOT_IN_INVENTORY")
    if destination_jurisdiction not in inventory.jurisdictions:
        reasons.append("DESTINATION_JURISDICTION_NOT_IN_INVENTORY")
    if purpose_id not in inventory.purpose_ids:
        reasons.append("PURPOSE_NOT_IN_INVENTORY")
    if evidence is None:
        reasons.append("MISSING_TRANSFER_EVIDENCE")
        return TransferAssessment(TransferStatus.BLOCK, tuple(reasons))
    if evidence.asset_id != inventory.asset.asset_id:
        reasons.append("TRANSFER_ASSET_MISMATCH")
    if evidence.purpose_id != purpose_id:
        reasons.append("TRANSFER_PURPOSE_MISMATCH")
    if evidence.source_jurisdiction != source_jurisdiction or evidence.destination_jurisdiction != destination_jurisdiction:
        reasons.append("TRANSFER_ROUTE_MISMATCH")
    if evidence.assessed_at > now:
        reasons.append("FUTURE_TRANSFER_EVIDENCE")
    elif evidence.valid_until <= now:
        reasons.append("EXPIRED_TRANSFER_EVIDENCE")
    if evidence.revoked:
        reasons.append("REVOKED_TRANSFER_EVIDENCE")
    if evidence.outcome is TransferOutcome.REJECTED:
        reasons.append("TRANSFER_REJECTED")
    if reasons:
        return TransferAssessment(TransferStatus.BLOCK, tuple(dict.fromkeys(reasons)))
    if evidence.outcome is TransferOutcome.REVIEW_REQUIRED:
        return TransferAssessment(TransferStatus.WATCH, ("TRANSFER_REVIEW_REQUIRED",))
    return TransferAssessment(TransferStatus.PASS, ())
