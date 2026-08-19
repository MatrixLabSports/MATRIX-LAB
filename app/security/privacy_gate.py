from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .data_classification import DataAsset, classification_is_acceptable
from .data_minimization import MinimizationReport
from .encryption_evidence import EncryptionEvidence
from .backup_protection import BackupProtectionEvidence


class PrivacyStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class PrivacyGateInput:
    asset: DataAsset
    minimization: MinimizationReport
    encryption: EncryptionEvidence | None
    retention_policy_assigned: bool
    deletion_procedure_verified: bool
    backup_protection: BackupProtectionEvidence | None
    access_control_verified: bool
    export_controls_verified: bool


@dataclass(frozen=True)
class PrivacyGateResult:
    status: PrivacyStatus
    reasons: tuple[str, ...]
    automatic_model_promotion_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.automatic_model_promotion_enabled or self.automatic_wager_execution_enabled:
            raise ValueError("privacy gate may never enable model promotion or wagering")


def evaluate_privacy_gate(data: PrivacyGateInput, *, now: datetime, max_encryption_evidence_age_hours: float = 24.0) -> PrivacyGateResult:
    blockers: list[str] = []
    watches: list[str] = []
    if not classification_is_acceptable(data.asset):
        blockers.append("DATA_CLASSIFICATION_TOO_LOW")
    if not data.minimization.passed:
        blockers.append("DATA_MINIMIZATION_FAILURE")
    if data.asset.data_class.value in {"CONFIDENTIAL", "RESTRICTED"} or data.asset.contains_personal_data:
        if data.encryption is None:
            blockers.append("MISSING_ENCRYPTION_EVIDENCE")
        elif data.encryption.asset_id != data.asset.asset_id or not data.encryption.acceptable(now=now, max_age_hours=max_encryption_evidence_age_hours):
            blockers.append("ENCRYPTION_EVIDENCE_NOT_ACCEPTABLE")
    elif data.encryption is None:
        watches.append("NO_ENCRYPTION_EVIDENCE_FOR_LOWER_CLASS_DATA")
    if not data.retention_policy_assigned:
        blockers.append("RETENTION_POLICY_MISSING")
    if not data.deletion_procedure_verified:
        blockers.append("DELETION_PROCEDURE_NOT_VERIFIED")
    if data.backup_protection is None:
        blockers.append("BACKUP_PROTECTION_NOT_VERIFIED")
    elif (data.backup_protection.source_asset_id != data.asset.asset_id
          or data.backup_protection.source_data_class is not data.asset.data_class
          or not data.backup_protection.acceptable(now=now)):
        blockers.append("BACKUP_PROTECTION_NOT_ACCEPTABLE")
    if not data.access_control_verified:
        blockers.append("ACCESS_CONTROL_NOT_VERIFIED")
    if not data.export_controls_verified:
        blockers.append("EXPORT_CONTROLS_NOT_VERIFIED")
    if blockers:
        return PrivacyGateResult(PrivacyStatus.BLOCK, tuple(dict.fromkeys(blockers + watches)))
    if watches:
        return PrivacyGateResult(PrivacyStatus.WATCH, tuple(watches))
    return PrivacyGateResult(PrivacyStatus.PASS, ())
