from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.release.canonical import canonical_sha256
from .provider_rights import ProviderRightsEvidence, ProviderRightsProfile


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class ProviderRightsInventoryRecord:
    provider_id: str
    profile: ProviderRightsProfile
    evidence: ProviderRightsEvidence
    dataset_references: tuple[str, ...]
    owner: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.owner.strip():
            raise ValueError("provider_id and owner are required")
        _require_aware(self.recorded_at, "recorded_at")
        if self.profile.provider_id != self.provider_id or self.evidence.provider_id != self.provider_id:
            raise ValueError("provider inventory components must reference the same provider")
        if self.evidence.profile_fingerprint != self.profile.fingerprint:
            raise ValueError("evidence must bind exact provider rights profile")
        cleaned = tuple(value.strip() for value in self.dataset_references)
        if not cleaned or any(not value for value in cleaned):
            raise ValueError("dataset_references are required and may not be blank")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("dataset_references may not contain duplicates")
        if self.evidence.reviewed_at > self.recorded_at:
            raise ValueError("evidence may not be reviewed after inventory record time")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class ProviderRightsInventorySnapshot:
    snapshot_id: str
    records: tuple[ProviderRightsInventoryRecord, ...]
    generated_at: datetime
    policy_version: str

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.policy_version.strip():
            raise ValueError("snapshot_id and policy_version are required")
        _require_aware(self.generated_at, "generated_at")
        if not self.records:
            raise ValueError("provider rights inventory may not be empty")
        provider_versions = [(record.provider_id, record.profile.profile_version) for record in self.records]
        if len(set(provider_versions)) != len(provider_versions):
            raise ValueError("duplicate provider/profile version in inventory snapshot")
        evidence_ids = [record.evidence.evidence_id for record in self.records]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("duplicate rights evidence in inventory snapshot")
        if any(record.recorded_at > self.generated_at for record in self.records):
            raise ValueError("inventory record may not be newer than snapshot")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)
