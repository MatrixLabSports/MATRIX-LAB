from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re

from app.release.canonical import canonical_sha256
from .data_classification import DataAsset
from .data_lifecycle import LifecycleRecord, LifecycleStage
from .privacy_policy_monitor import PrivacyMonitoringReport, MonitorStatus

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class EvidenceAutomationStatus(str, Enum):
    COMPLETE = "COMPLETE"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class PrivacyEvidenceSnapshot:
    snapshot_id: str
    asset_id: str
    asset_fingerprint: str
    lifecycle_fingerprint: str
    lifecycle_stage: LifecycleStage
    monitoring_status: MonitorStatus
    monitoring_reasons: tuple[str, ...]
    generated_at: datetime
    source_evidence_sha256: tuple[str, ...]
    policy_version: str

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.asset_id.strip() or not self.policy_version.strip():
            raise ValueError("snapshot identity and policy version are required")
        if not _HEX64.fullmatch(self.asset_fingerprint) or not _HEX64.fullmatch(self.lifecycle_fingerprint):
            raise ValueError("asset/lifecycle fingerprints must be SHA-256")
        if not self.source_evidence_sha256:
            raise ValueError("source evidence is required")
        if any(not _HEX64.fullmatch(value) for value in self.source_evidence_sha256):
            raise ValueError("source evidence references must be SHA-256")
        if len(set(self.source_evidence_sha256)) != len(self.source_evidence_sha256):
            raise ValueError("source evidence references must be unique")
        _aware(self.generated_at, "generated_at")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class EvidenceAutomationResult:
    status: EvidenceAutomationStatus
    reasons: tuple[str, ...]
    snapshot: PrivacyEvidenceSnapshot | None
    automatic_legal_notification_enabled: bool = False
    automatic_model_promotion_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.automatic_legal_notification_enabled or self.automatic_model_promotion_enabled or self.automatic_wager_execution_enabled:
            raise ValueError("evidence automation cannot enable legal notification, model promotion or wagering")


def build_privacy_evidence_snapshot(
    asset: DataAsset,
    lifecycle: LifecycleRecord,
    monitoring: PrivacyMonitoringReport,
    *,
    generated_at: datetime,
    source_evidence_sha256: tuple[str, ...],
    policy_version: str,
    snapshot_id: str,
) -> EvidenceAutomationResult:
    _aware(generated_at, "generated_at")
    blockers: list[str] = []
    watches: list[str] = []
    if lifecycle.asset_id != asset.asset_id or lifecycle.asset_fingerprint != asset.fingerprint:
        blockers.append("LIFECYCLE_ASSET_BINDING_FAILURE")
    if lifecycle.occurred_at > generated_at:
        blockers.append("LIFECYCLE_EVENT_FROM_FUTURE")
    if lifecycle.stage is LifecycleStage.DELETED and monitoring.status is MonitorStatus.HEALTHY:
        watches.append("DELETED_ASSET_MONITORING_STILL_ACTIVE")
    if monitoring.status is MonitorStatus.UNKNOWN:
        blockers.append("PRIVACY_MONITORING_UNKNOWN")
    if monitoring.status is MonitorStatus.INCIDENT_CANDIDATE:
        blockers.append("OPEN_PRIVACY_INCIDENT_CANDIDATE")
    elif monitoring.status is MonitorStatus.WATCH:
        watches.extend(monitoring.reasons or ("PRIVACY_MONITOR_WATCH",))
    if not source_evidence_sha256:
        blockers.append("SOURCE_EVIDENCE_MISSING")
    elif any(not _HEX64.fullmatch(value) for value in source_evidence_sha256):
        blockers.append("SOURCE_EVIDENCE_INVALID")
    elif len(set(source_evidence_sha256)) != len(source_evidence_sha256):
        blockers.append("SOURCE_EVIDENCE_DUPLICATED")

    if blockers:
        return EvidenceAutomationResult(EvidenceAutomationStatus.BLOCK, tuple(dict.fromkeys(blockers + watches)), None)

    snapshot = PrivacyEvidenceSnapshot(
        snapshot_id=snapshot_id,
        asset_id=asset.asset_id,
        asset_fingerprint=asset.fingerprint,
        lifecycle_fingerprint=lifecycle.fingerprint,
        lifecycle_stage=lifecycle.stage,
        monitoring_status=monitoring.status,
        monitoring_reasons=monitoring.reasons,
        generated_at=generated_at,
        source_evidence_sha256=source_evidence_sha256,
        policy_version=policy_version,
    )
    if watches:
        return EvidenceAutomationResult(EvidenceAutomationStatus.WATCH, tuple(dict.fromkeys(watches)), snapshot)
    return EvidenceAutomationResult(EvidenceAutomationStatus.COMPLETE, (), snapshot)
