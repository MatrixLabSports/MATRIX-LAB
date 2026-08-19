from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.release.canonical import canonical_sha256


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class EncryptionEvidence:
    asset_id: str
    at_rest_enabled: bool
    in_transit_enabled: bool
    key_reference: str
    key_managed_externally: bool
    verified_at: datetime
    verifier: str
    algorithm_policy_id: str

    def __post_init__(self) -> None:
        if not self.asset_id.strip() or not self.verifier.strip() or not self.algorithm_policy_id.strip():
            raise ValueError("asset_id, verifier and algorithm_policy_id are required")
        _aware(self.verified_at, "verified_at")
        if (self.at_rest_enabled or self.in_transit_enabled) and not self.key_reference.strip():
            raise ValueError("key_reference is required when encryption is enabled")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)

    def acceptable(self, *, now: datetime, max_age_hours: float = 24.0, require_at_rest: bool = True, require_in_transit: bool = True) -> bool:
        _aware(now, "now")
        if self.verified_at > now + timedelta(minutes=5):
            return False
        if now - self.verified_at > timedelta(hours=max_age_hours):
            return False
        if require_at_rest and not self.at_rest_enabled:
            return False
        if require_in_transit and not self.in_transit_enabled:
            return False
        if (require_at_rest or require_in_transit) and not self.key_managed_externally:
            return False
        return True
