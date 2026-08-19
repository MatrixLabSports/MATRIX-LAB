from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.release.canonical import canonical_sha256


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class DeletionStatus(str, Enum):
    REQUESTED = "REQUESTED"
    COMPLETED = "COMPLETED"
    BLOCKED_LEGAL_HOLD = "BLOCKED_LEGAL_HOLD"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DeletionEvidence:
    deletion_id: str
    asset_id: str
    requested_at: datetime
    completed_at: datetime | None
    actor_id: str
    method: str
    status: DeletionStatus
    source_fingerprint: str
    tombstone_fingerprint: str | None
    scope_complete: bool = False

    def __post_init__(self) -> None:
        if not self.deletion_id.strip() or not self.asset_id.strip() or not self.actor_id.strip() or not self.method.strip():
            raise ValueError("deletion_id, asset_id, actor_id and method are required")
        if len(self.source_fingerprint) != 64:
            raise ValueError("source_fingerprint must be SHA-256 hex")
        _aware(self.requested_at, "requested_at")
        if self.completed_at is not None:
            _aware(self.completed_at, "completed_at")
            if self.completed_at < self.requested_at:
                raise ValueError("completed_at cannot precede requested_at")
        if self.status is DeletionStatus.COMPLETED:
            if self.completed_at is None or not self.tombstone_fingerprint or len(self.tombstone_fingerprint) != 64:
                raise ValueError("completed deletion requires completed_at and tombstone_fingerprint")
            if not self.scope_complete:
                raise ValueError("completed deletion requires scope_complete evidence")
        elif self.tombstone_fingerprint is not None:
            raise ValueError("non-completed deletion must not claim tombstone_fingerprint")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)
