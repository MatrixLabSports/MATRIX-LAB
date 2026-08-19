from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.release.canonical import canonical_sha256
from .data_classification import DataClass


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class BackupProtectionEvidence:
    backup_id: str
    source_asset_id: str
    source_data_class: DataClass
    encrypted_at_rest: bool
    key_separated_from_backup: bool
    integrity_verified: bool
    restore_test_verified: bool
    immutable_or_write_protected: bool
    verified_at: datetime
    verifier: str

    def __post_init__(self) -> None:
        if not self.backup_id.strip() or not self.source_asset_id.strip() or not self.verifier.strip():
            raise ValueError("backup_id, source_asset_id and verifier are required")
        _aware(self.verified_at, "verified_at")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)

    def acceptable(self, *, now: datetime, max_age_hours: float = 168.0) -> bool:
        _aware(now, "now")
        if self.verified_at > now + timedelta(minutes=5):
            return False
        if now - self.verified_at > timedelta(hours=max_age_hours):
            return False
        if not self.encrypted_at_rest or not self.key_separated_from_backup:
            return False
        if not self.integrity_verified or not self.restore_test_verified:
            return False
        if self.source_data_class is DataClass.RESTRICTED and not self.immutable_or_write_protected:
            return False
        return True
