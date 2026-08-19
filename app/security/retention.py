from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from app.release.canonical import canonical_sha256


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class RetentionAction(str, Enum):
    KEEP = "KEEP"
    REVIEW = "REVIEW"
    DELETE = "DELETE"
    LEGAL_HOLD = "LEGAL_HOLD"


@dataclass(frozen=True)
class RetentionPolicy:
    policy_id: str
    retention_days: int
    review_before_delete_days: int = 7

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id is required")
        if self.retention_days <= 0:
            raise ValueError("retention_days must be > 0")
        if self.review_before_delete_days < 0 or self.review_before_delete_days >= self.retention_days:
            raise ValueError("review_before_delete_days must be >= 0 and < retention_days")


@dataclass(frozen=True)
class RetentionRecord:
    asset_id: str
    created_at: datetime
    policy_id: str
    legal_hold: bool = False

    def __post_init__(self) -> None:
        if not self.asset_id.strip() or not self.policy_id.strip():
            raise ValueError("asset_id and policy_id are required")
        _aware(self.created_at, "created_at")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def retention_action(record: RetentionRecord, policy: RetentionPolicy, *, now: datetime) -> RetentionAction:
    _aware(now, "now")
    if record.policy_id != policy.policy_id:
        raise ValueError("retention policy mismatch")
    if now < record.created_at:
        raise ValueError("now cannot precede created_at")
    if record.legal_hold:
        return RetentionAction.LEGAL_HOLD
    age = now - record.created_at
    delete_at = timedelta(days=policy.retention_days)
    review_at = timedelta(days=policy.retention_days - policy.review_before_delete_days)
    if age >= delete_at:
        return RetentionAction.DELETE
    if age >= review_at:
        return RetentionAction.REVIEW
    return RetentionAction.KEEP
