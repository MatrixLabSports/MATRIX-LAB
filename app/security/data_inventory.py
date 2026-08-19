from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.release.canonical import canonical_sha256
from .data_classification import DataAsset


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _clean_unique(values: tuple[str, ...], name: str, *, required: bool = True) -> tuple[str, ...]:
    cleaned = tuple(value.strip() for value in values)
    if required and not cleaned:
        raise ValueError(f"{name} is required")
    if any(not value for value in cleaned):
        raise ValueError(f"{name} may not contain blank values")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{name} may not contain duplicates")
    return cleaned


@dataclass(frozen=True)
class DataInventoryRecord:
    inventory_id: str
    asset: DataAsset
    systems: tuple[str, ...]
    source_references: tuple[str, ...]
    data_categories: tuple[str, ...]
    data_subject_categories: tuple[str, ...]
    purpose_ids: tuple[str, ...]
    jurisdictions: tuple[str, ...]
    processor_references: tuple[str, ...]
    retention_policy_reference: str
    privacy_review_reference: str | None
    owner: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.inventory_id.strip() or not self.owner.strip() or not self.retention_policy_reference.strip():
            raise ValueError("inventory_id, owner and retention_policy_reference are required")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at may not precede created_at")
        _clean_unique(self.systems, "systems")
        _clean_unique(self.source_references, "source_references")
        _clean_unique(self.data_categories, "data_categories")
        _clean_unique(self.purpose_ids, "purpose_ids")
        _clean_unique(self.jurisdictions, "jurisdictions")
        _clean_unique(self.processor_references, "processor_references", required=False)
        _clean_unique(self.data_subject_categories, "data_subject_categories", required=False)
        if self.asset.contains_personal_data and not self.data_subject_categories:
            raise ValueError("personal-data assets require data_subject_categories")
        if self.asset.contains_personal_data and not (self.privacy_review_reference or "").strip():
            raise ValueError("personal-data assets require privacy_review_reference")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class DataInventorySnapshot:
    snapshot_id: str
    records: tuple[DataInventoryRecord, ...]
    generated_at: datetime
    policy_version: str

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.policy_version.strip():
            raise ValueError("snapshot_id and policy_version are required")
        _require_aware(self.generated_at, "generated_at")
        if not self.records:
            raise ValueError("inventory snapshot must contain at least one record")
        inventory_ids = [record.inventory_id for record in self.records]
        asset_ids = [record.asset.asset_id for record in self.records]
        if len(set(inventory_ids)) != len(inventory_ids):
            raise ValueError("duplicate inventory_id in snapshot")
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("duplicate asset_id in snapshot")
        if any(record.updated_at > self.generated_at for record in self.records):
            raise ValueError("inventory record may not be newer than snapshot")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)
