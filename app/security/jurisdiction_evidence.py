from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .data_inventory import DataInventoryRecord


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sha(value: str) -> str:
    text = value.strip().lower()
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise ValueError("evidence_sha256 must be a 64-character SHA-256 hex digest")
    return text


class ReviewOutcome(str, Enum):
    APPROVED_FOR_GOVERNED_PROCESSING = "APPROVED_FOR_GOVERNED_PROCESSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"


class JurisdictionStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class JurisdictionEvidence:
    evidence_id: str
    jurisdiction: str
    purpose_id: str
    framework_reference: str
    basis_code: str
    reviewer_role: str
    reviewed_at: datetime
    valid_until: datetime
    evidence_sha256: str
    outcome: ReviewOutcome
    revoked: bool = False

    def __post_init__(self) -> None:
        required = (
            self.evidence_id,
            self.jurisdiction,
            self.purpose_id,
            self.framework_reference,
            self.basis_code,
            self.reviewer_role,
        )
        if not all(value.strip() for value in required):
            raise ValueError("jurisdiction evidence metadata is required")
        _aware(self.reviewed_at, "reviewed_at")
        _aware(self.valid_until, "valid_until")
        if self.valid_until <= self.reviewed_at:
            raise ValueError("valid_until must be after reviewed_at")
        object.__setattr__(self, "evidence_sha256", _sha(self.evidence_sha256))


@dataclass(frozen=True)
class JurisdictionAssessment:
    status: JurisdictionStatus
    reasons: tuple[str, ...]
    legal_compliance_certified: bool = False

    def __post_init__(self) -> None:
        if self.legal_compliance_certified:
            raise ValueError("software may not self-certify legal compliance")


def evaluate_jurisdiction_evidence(
    inventory: DataInventoryRecord,
    *,
    purpose_id: str,
    evidences: tuple[JurisdictionEvidence, ...],
    now: datetime,
) -> JurisdictionAssessment:
    _aware(now, "now")
    blockers: list[str] = []
    watches: list[str] = []
    if purpose_id not in inventory.purpose_ids:
        blockers.append("PURPOSE_NOT_IN_INVENTORY")
    seen_keys: set[tuple[str, str]] = set()
    for evidence in evidences:
        key = (evidence.jurisdiction, evidence.purpose_id)
        if key in seen_keys:
            blockers.append(f"DUPLICATE_JURISDICTION_EVIDENCE:{evidence.jurisdiction}")
        seen_keys.add(key)
    for jurisdiction in inventory.jurisdictions:
        matches = [e for e in evidences if e.jurisdiction == jurisdiction and e.purpose_id == purpose_id]
        if not matches:
            blockers.append(f"MISSING_JURISDICTION_EVIDENCE:{jurisdiction}")
            continue
        evidence = matches[0]
        if evidence.reviewed_at > now:
            blockers.append(f"FUTURE_JURISDICTION_EVIDENCE:{jurisdiction}")
        elif evidence.valid_until <= now:
            blockers.append(f"EXPIRED_JURISDICTION_EVIDENCE:{jurisdiction}")
        if evidence.revoked:
            blockers.append(f"REVOKED_JURISDICTION_EVIDENCE:{jurisdiction}")
        if evidence.outcome is ReviewOutcome.REJECTED:
            blockers.append(f"JURISDICTION_REJECTED:{jurisdiction}")
        elif evidence.outcome is ReviewOutcome.REVIEW_REQUIRED:
            watches.append(f"JURISDICTION_REVIEW_REQUIRED:{jurisdiction}")
    if blockers:
        return JurisdictionAssessment(JurisdictionStatus.BLOCK, tuple(dict.fromkeys(blockers + watches)))
    if watches:
        return JurisdictionAssessment(JurisdictionStatus.WATCH, tuple(dict.fromkeys(watches)))
    return JurisdictionAssessment(JurisdictionStatus.PASS, ())
