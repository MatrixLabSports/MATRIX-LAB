from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable

from app.release.canonical import canonical_sha256


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class SecretMetadata:
    name: str
    provider: str
    version: str
    created_at: datetime
    expires_at: datetime
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.provider.strip() or not self.version.strip():
            raise ValueError("secret metadata fields are required")
        _aware(self.created_at, "created_at")
        _aware(self.expires_at, "expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool")


@dataclass(frozen=True)
class RotationEvidence:
    secret_name: str
    provider: str
    previous_version: str
    new_version: str
    rotated_at: datetime
    actor_id: str
    actor_verified: bool
    old_version_revoked: bool
    validation_passed: bool

    def __post_init__(self) -> None:
        for name in ("secret_name", "provider", "previous_version", "new_version", "actor_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.previous_version == self.new_version:
            raise ValueError("rotation must change secret version")
        _aware(self.rotated_at, "rotated_at")
        for name in ("actor_verified", "old_version_revoked", "validation_passed"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class SecretRotationPolicy:
    max_age_days: int
    warning_days_before_expiry: int
    max_rotation_evidence_age_days: int

    def __post_init__(self) -> None:
        if self.max_age_days <= 0 or self.warning_days_before_expiry < 0 or self.max_rotation_evidence_age_days <= 0:
            raise ValueError("invalid secret rotation policy")


class SecretRotationStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class SecretRotationResult:
    status: SecretRotationStatus
    reasons: tuple[str, ...]


def evaluate_secret_rotation(
    inventory: Iterable[SecretMetadata],
    *,
    required_secret_names: Iterable[str],
    rotation_evidence: Iterable[RotationEvidence],
    policy: SecretRotationPolicy,
    now: datetime,
) -> SecretRotationResult:
    _aware(now, "now")
    items = tuple(inventory)
    evidence = tuple(rotation_evidence)
    by_name: dict[str, SecretMetadata] = {}
    blockers: list[str] = []
    watches: list[str] = []

    for item in items:
        if item.name in by_name:
            blockers.append(f"DUPLICATE_SECRET_METADATA:{item.name}")
        by_name[item.name] = item
        if item.created_at > now or item.expires_at <= item.created_at:
            blockers.append(f"INVALID_SECRET_TIME:{item.name}")

    for required in tuple(required_secret_names):
        item = by_name.get(required)
        if item is None:
            blockers.append(f"MISSING_REQUIRED_SECRET:{required}")
            continue
        if not item.enabled:
            blockers.append(f"REQUIRED_SECRET_DISABLED:{required}")
            continue
        if now >= item.expires_at:
            blockers.append(f"SECRET_EXPIRED:{required}")
        age = now - item.created_at
        if age > timedelta(days=policy.max_age_days):
            blockers.append(f"SECRET_MAX_AGE_EXCEEDED:{required}")
        elif item.expires_at - now <= timedelta(days=policy.warning_days_before_expiry):
            watches.append(f"SECRET_EXPIRING_SOON:{required}")

    for ev in evidence:
        if ev.rotated_at > now:
            blockers.append(f"ROTATION_EVIDENCE_FROM_FUTURE:{ev.secret_name}")
        if now - ev.rotated_at > timedelta(days=policy.max_rotation_evidence_age_days):
            watches.append(f"STALE_ROTATION_EVIDENCE:{ev.secret_name}")
        if not ev.actor_verified:
            blockers.append(f"ROTATION_ACTOR_NOT_VERIFIED:{ev.secret_name}")
        if not ev.old_version_revoked:
            blockers.append(f"OLD_SECRET_VERSION_NOT_REVOKED:{ev.secret_name}")
        if not ev.validation_passed:
            blockers.append(f"ROTATED_SECRET_NOT_VALIDATED:{ev.secret_name}")
        current = by_name.get(ev.secret_name)
        if current is not None and current.version != ev.new_version:
            blockers.append(f"ROTATION_CURRENT_VERSION_MISMATCH:{ev.secret_name}")

    reasons = tuple(dict.fromkeys(blockers + watches))
    if blockers:
        return SecretRotationResult(SecretRotationStatus.BLOCK, reasons)
    if watches:
        return SecretRotationResult(SecretRotationStatus.WATCH, reasons)
    return SecretRotationResult(SecretRotationStatus.PASS, ())
