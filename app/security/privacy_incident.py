from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re

from app.release.canonical import canonical_sha256
from .data_classification import DataAsset, DataClass


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_LEGAL_STATUSES = {"NOT_ASSESSED", "ASSESSED_NO_NOTIFICATION", "NOTIFICATION_REQUIRED", "NOTIFICATION_COMPLETED"}


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class PrivacyIncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PrivacyIncidentCategory(str, Enum):
    CONFIDENTIALITY = "CONFIDENTIALITY"
    INTEGRITY = "INTEGRITY"
    ACCESS_CONTROL = "ACCESS_CONTROL"
    RETENTION = "RETENTION"
    EXPORT = "EXPORT"
    BACKUP = "BACKUP"
    ENCRYPTION = "ENCRYPTION"
    OTHER = "OTHER"


class PrivacyIncidentState(str, Enum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    CONTAINED = "CONTAINED"
    REMEDIATED = "REMEDIATED"
    CLOSED = "CLOSED"


_ALLOWED_INCIDENT_TRANSITIONS = {
    PrivacyIncidentState.DETECTED: {PrivacyIncidentState.TRIAGED},
    PrivacyIncidentState.TRIAGED: {PrivacyIncidentState.CONTAINED},
    PrivacyIncidentState.CONTAINED: {PrivacyIncidentState.REMEDIATED},
    PrivacyIncidentState.REMEDIATED: {PrivacyIncidentState.CLOSED},
    PrivacyIncidentState.CLOSED: set(),
}


@dataclass(frozen=True)
class PrivacyIncident:
    incident_id: str
    category: PrivacyIncidentCategory
    severity: PrivacyIncidentSeverity
    state: PrivacyIncidentState
    detected_at: datetime
    updated_at: datetime
    source: str
    summary: str
    affected_asset_ids: tuple[str, ...]
    personal_data_involved: bool
    confirmed_external_exposure: bool
    evidence_references: tuple[str, ...]
    previous_incident_fingerprint: str | None = None
    root_cause: str | None = None
    remediation_reference: str | None = None
    independent_review_reference: str | None = None
    legal_assessment_required: bool = False
    legal_notification_status: str = "NOT_ASSESSED"

    def __post_init__(self) -> None:
        if not self.incident_id.strip() or not self.source.strip() or not self.summary.strip():
            raise ValueError("incident_id, source and summary are required")
        if not self.affected_asset_ids or any(not value.strip() for value in self.affected_asset_ids):
            raise ValueError("affected_asset_ids are required")
        if len(set(self.affected_asset_ids)) != len(self.affected_asset_ids):
            raise ValueError("affected_asset_ids must be unique")
        _aware(self.detected_at, "detected_at")
        _aware(self.updated_at, "updated_at")
        if self.updated_at < self.detected_at:
            raise ValueError("updated_at cannot precede detected_at")
        if self.previous_incident_fingerprint is not None and not _HEX64.fullmatch(self.previous_incident_fingerprint):
            raise ValueError("previous_incident_fingerprint must be SHA-256")
        if not self.evidence_references or any(not value.strip() for value in self.evidence_references):
            raise ValueError("evidence references are required")
        if len(set(self.evidence_references)) != len(self.evidence_references):
            raise ValueError("evidence references must be unique")
        if self.legal_notification_status not in _LEGAL_STATUSES:
            raise ValueError("invalid legal notification status")
        if self.state is PrivacyIncidentState.CLOSED:
            if not self.root_cause or not self.remediation_reference:
                raise ValueError("closed incident requires root cause and remediation reference")
            if self.severity in {PrivacyIncidentSeverity.HIGH, PrivacyIncidentSeverity.CRITICAL} and not self.independent_review_reference:
                raise ValueError("high/critical incident closure requires independent review")
            if self.legal_assessment_required and self.legal_notification_status == "NOT_ASSESSED":
                raise ValueError("legal assessment must be completed before closure")
            if self.legal_notification_status == "NOTIFICATION_REQUIRED":
                raise ValueError("incident cannot close while required notification is incomplete")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def assess_technical_severity(
    assets: tuple[DataAsset, ...],
    *,
    confirmed_external_exposure: bool,
    integrity_compromised: bool = False,
    credentials_exposed: bool = False,
) -> PrivacyIncidentSeverity:
    if not assets:
        raise ValueError("at least one asset is required")
    highest = max((asset.data_class for asset in assets), key=lambda c: {
        DataClass.PUBLIC: 1,
        DataClass.INTERNAL: 2,
        DataClass.CONFIDENTIAL: 3,
        DataClass.RESTRICTED: 4,
    }[c])
    any_personal = any(asset.contains_personal_data for asset in assets)
    if credentials_exposed or (confirmed_external_exposure and highest is DataClass.RESTRICTED):
        return PrivacyIncidentSeverity.CRITICAL
    if confirmed_external_exposure and (highest is DataClass.CONFIDENTIAL or any_personal):
        return PrivacyIncidentSeverity.HIGH
    if integrity_compromised and highest in {DataClass.CONFIDENTIAL, DataClass.RESTRICTED}:
        return PrivacyIncidentSeverity.HIGH
    if highest in {DataClass.CONFIDENTIAL, DataClass.RESTRICTED} or any_personal:
        return PrivacyIncidentSeverity.MEDIUM
    return PrivacyIncidentSeverity.LOW


def transition_incident(
    current: PrivacyIncident,
    target: PrivacyIncidentState,
    *,
    updated_at: datetime,
    evidence_references: tuple[str, ...] | None = None,
    root_cause: str | None = None,
    remediation_reference: str | None = None,
    independent_review_reference: str | None = None,
    legal_notification_status: str | None = None,
) -> PrivacyIncident:
    _aware(updated_at, "updated_at")
    if updated_at < current.updated_at:
        raise ValueError("incident transition cannot move backward in time")
    if target not in _ALLOWED_INCIDENT_TRANSITIONS[current.state]:
        raise ValueError(f"invalid incident transition: {current.state.value}->{target.value}")
    refs = current.evidence_references if evidence_references is None else evidence_references
    if len(set(refs)) != len(refs):
        raise ValueError("evidence references must be unique")
    return PrivacyIncident(
        incident_id=current.incident_id,
        category=current.category,
        severity=current.severity,
        state=target,
        detected_at=current.detected_at,
        updated_at=updated_at,
        source=current.source,
        summary=current.summary,
        affected_asset_ids=current.affected_asset_ids,
        personal_data_involved=current.personal_data_involved,
        confirmed_external_exposure=current.confirmed_external_exposure,
        evidence_references=refs,
        previous_incident_fingerprint=current.fingerprint,
        root_cause=root_cause if root_cause is not None else current.root_cause,
        remediation_reference=remediation_reference if remediation_reference is not None else current.remediation_reference,
        independent_review_reference=(independent_review_reference if independent_review_reference is not None else current.independent_review_reference),
        legal_assessment_required=current.legal_assessment_required,
        legal_notification_status=(legal_notification_status if legal_notification_status is not None else current.legal_notification_status),
    )


def verify_incident_chain(records: tuple[PrivacyIncident, ...]) -> tuple[bool, tuple[str, ...]]:
    if not records:
        return False, ("EMPTY_INCIDENT_CHAIN",)
    reasons: list[str] = []
    first = records[0]
    if first.state is not PrivacyIncidentState.DETECTED:
        reasons.append("INCIDENT_CHAIN_MUST_BEGIN_DETECTED")
    if first.previous_incident_fingerprint is not None:
        reasons.append("FIRST_INCIDENT_RECORD_HAS_PREVIOUS")
    previous = first
    for record in records[1:]:
        if record.incident_id != first.incident_id:
            reasons.append("INCIDENT_ID_CHANGED")
        if record.previous_incident_fingerprint != previous.fingerprint:
            reasons.append(f"INCIDENT_CHAIN_BROKEN:{record.state.value}")
        if record.state not in _ALLOWED_INCIDENT_TRANSITIONS[previous.state]:
            reasons.append(f"INVALID_INCIDENT_TRANSITION:{previous.state.value}->{record.state.value}")
        if record.updated_at < previous.updated_at:
            reasons.append("INCIDENT_TIME_REGRESSION")
        if record.severity is not previous.severity or record.category is not previous.category:
            reasons.append("INCIDENT_CLASSIFICATION_MUTATED_IN_CHAIN")
        previous = record
    return not reasons, tuple(dict.fromkeys(reasons))
