from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re

from app.release.canonical import canonical_sha256
from .data_classification import DataAsset, DataClass
from .privacy_gate import PrivacyGateResult, PrivacyStatus
from .privacy_incident import (
    PrivacyIncident,
    PrivacyIncidentCategory,
    PrivacyIncidentSeverity,
    PrivacyIncidentState,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class MonitorStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WATCH = "WATCH"
    INCIDENT_CANDIDATE = "INCIDENT_CANDIDATE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PrivacyControlObservation:
    observation_id: str
    asset_id: str
    control: str
    status: PrivacyStatus
    observed_at: datetime
    evidence_sha256: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.observation_id.strip() or not self.asset_id.strip() or not self.control.strip():
            raise ValueError("observation_id, asset_id and control are required")
        _aware(self.observed_at, "observed_at")
        if not _HEX64.fullmatch(self.evidence_sha256):
            raise ValueError("evidence_sha256 must be SHA-256")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("reasons must be unique")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class PrivacyMonitoringReport:
    status: MonitorStatus
    reasons: tuple[str, ...]
    incident_candidate: PrivacyIncident | None
    automatic_legal_notification_enabled: bool = False
    automatic_model_promotion_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.automatic_legal_notification_enabled:
            raise ValueError("monitor must never send legal notifications automatically")
        if self.automatic_model_promotion_enabled or self.automatic_wager_execution_enabled:
            raise ValueError("monitor may never enable promotion or wagering")


def observation_from_privacy_gate(
    asset: DataAsset,
    result: PrivacyGateResult,
    *,
    observed_at: datetime,
    evidence_sha256: str,
    observation_id: str,
) -> PrivacyControlObservation:
    return PrivacyControlObservation(
        observation_id=observation_id,
        asset_id=asset.asset_id,
        control="PRIVACY_GATE",
        status=result.status,
        observed_at=observed_at,
        evidence_sha256=evidence_sha256,
        reasons=result.reasons,
    )


def _candidate_severity(asset: DataAsset, reasons: tuple[str, ...]) -> PrivacyIncidentSeverity:
    reason_blob = "|".join(reasons)
    if asset.contains_credentials or asset.data_class is DataClass.RESTRICTED:
        return PrivacyIncidentSeverity.CRITICAL if any(token in reason_blob for token in ("EXPORT", "ACCESS", "ENCRYPTION")) else PrivacyIncidentSeverity.HIGH
    if asset.contains_personal_data or asset.data_class is DataClass.CONFIDENTIAL:
        return PrivacyIncidentSeverity.HIGH if any(token in reason_blob for token in ("EXPORT", "ACCESS", "ENCRYPTION")) else PrivacyIncidentSeverity.MEDIUM
    return PrivacyIncidentSeverity.MEDIUM


def _candidate_category(reasons: tuple[str, ...]) -> PrivacyIncidentCategory:
    blob = "|".join(reasons)
    if "EXPORT" in blob:
        return PrivacyIncidentCategory.EXPORT
    if "ACCESS" in blob:
        return PrivacyIncidentCategory.ACCESS_CONTROL
    if "ENCRYPTION" in blob:
        return PrivacyIncidentCategory.ENCRYPTION
    if "BACKUP" in blob:
        return PrivacyIncidentCategory.BACKUP
    if "RETENTION" in blob or "DELETION" in blob:
        return PrivacyIncidentCategory.RETENTION
    if "INTEGRITY" in blob or "CLASSIFICATION" in blob:
        return PrivacyIncidentCategory.INTEGRITY
    return PrivacyIncidentCategory.OTHER


def evaluate_privacy_observations(
    asset: DataAsset,
    observations: tuple[PrivacyControlObservation, ...],
    *,
    now: datetime,
    max_observation_age_hours: float = 24.0,
    incident_id: str = "auto-privacy-candidate",
) -> PrivacyMonitoringReport:
    _aware(now, "now")
    if max_observation_age_hours <= 0:
        raise ValueError("max_observation_age_hours must be > 0")
    if not observations:
        return PrivacyMonitoringReport(MonitorStatus.UNKNOWN, ("NO_PRIVACY_OBSERVATIONS",), None)

    reasons: list[str] = []
    blocking_reasons: list[str] = []
    watch = False
    seen_ids: set[str] = set()
    seen_controls: set[str] = set()
    evidence_refs: list[str] = []
    for obs in observations:
        if obs.observation_id in seen_ids:
            reasons.append(f"DUPLICATE_OBSERVATION_ID:{obs.observation_id}")
            blocking_reasons.append("OBSERVATION_IDENTITY_FAILURE")
        seen_ids.add(obs.observation_id)
        control_key = obs.control.casefold()
        if control_key in seen_controls:
            reasons.append(f"DUPLICATE_CONTROL_OBSERVATION:{obs.control}")
            blocking_reasons.append("OBSERVATION_IDENTITY_FAILURE")
        seen_controls.add(control_key)
        if obs.asset_id != asset.asset_id:
            reasons.append("OBSERVATION_ASSET_MISMATCH")
            blocking_reasons.append("OBSERVATION_ASSET_MISMATCH")
        if obs.observed_at > now + timedelta(minutes=5):
            reasons.append("OBSERVATION_FROM_FUTURE")
            blocking_reasons.append("OBSERVATION_FROM_FUTURE")
        elif now - obs.observed_at > timedelta(hours=max_observation_age_hours):
            reasons.append("STALE_PRIVACY_OBSERVATION")
            blocking_reasons.append("STALE_PRIVACY_OBSERVATION")
        evidence_refs.append(obs.evidence_sha256)
        if obs.status is PrivacyStatus.BLOCK:
            blocking_reasons.extend(obs.reasons or (f"{obs.control}_BLOCK",))
        elif obs.status is PrivacyStatus.WATCH:
            watch = True
            reasons.extend(obs.reasons or (f"{obs.control}_WATCH",))

    if blocking_reasons:
        combined = tuple(dict.fromkeys(reasons + blocking_reasons))
        candidate = PrivacyIncident(
            incident_id=incident_id,
            category=_candidate_category(combined),
            severity=_candidate_severity(asset, combined),
            state=PrivacyIncidentState.DETECTED,
            detected_at=now,
            updated_at=now,
            source="privacy_policy_monitor",
            summary="Technical privacy policy violation candidate; legal assessment remains human-governed.",
            affected_asset_ids=(asset.asset_id,),
            personal_data_involved=asset.contains_personal_data,
            confirmed_external_exposure=False,
            evidence_references=tuple(dict.fromkeys(evidence_refs)),
            legal_assessment_required=asset.contains_personal_data or asset.data_class in {DataClass.CONFIDENTIAL, DataClass.RESTRICTED},
        )
        return PrivacyMonitoringReport(MonitorStatus.INCIDENT_CANDIDATE, combined, candidate)
    if watch:
        return PrivacyMonitoringReport(MonitorStatus.WATCH, tuple(dict.fromkeys(reasons)), None)
    return PrivacyMonitoringReport(MonitorStatus.HEALTHY, (), None)
