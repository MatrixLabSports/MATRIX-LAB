from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.release.canonical import canonical_sha256
from .data_classification import DataAsset
from .deletion_evidence import DeletionEvidence, DeletionStatus


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class LifecycleStage(str, Enum):
    INGESTED = "INGESTED"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    QUARANTINED = "QUARANTINED"
    DELETION_PENDING = "DELETION_PENDING"
    DELETED = "DELETED"


_ALLOWED_TRANSITIONS: dict[LifecycleStage, set[LifecycleStage]] = {
    LifecycleStage.INGESTED: {LifecycleStage.VALIDATED, LifecycleStage.QUARANTINED},
    LifecycleStage.VALIDATED: {LifecycleStage.ACTIVE, LifecycleStage.QUARANTINED},
    LifecycleStage.ACTIVE: {LifecycleStage.ARCHIVED, LifecycleStage.QUARANTINED},
    LifecycleStage.ARCHIVED: {LifecycleStage.DELETION_PENDING, LifecycleStage.QUARANTINED},
    LifecycleStage.QUARANTINED: {LifecycleStage.ARCHIVED, LifecycleStage.DELETION_PENDING},
    LifecycleStage.DELETION_PENDING: {LifecycleStage.DELETED, LifecycleStage.QUARANTINED},
    LifecycleStage.DELETED: set(),
}


@dataclass(frozen=True)
class LifecycleRecord:
    asset_id: str
    asset_fingerprint: str
    stage: LifecycleStage
    occurred_at: datetime
    actor_id: str
    reason: str
    previous_record_fingerprint: str | None = None
    legal_hold: bool = False

    def __post_init__(self) -> None:
        if not self.asset_id.strip() or not self.actor_id.strip() or not self.reason.strip():
            raise ValueError("asset_id, actor_id and reason are required")
        if len(self.asset_fingerprint) != 64:
            raise ValueError("asset_fingerprint must be SHA-256")
        if self.previous_record_fingerprint is not None and len(self.previous_record_fingerprint) != 64:
            raise ValueError("previous_record_fingerprint must be SHA-256")
        _aware(self.occurred_at, "occurred_at")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def initial_lifecycle_record(asset: DataAsset, *, occurred_at: datetime, actor_id: str, reason: str = "ingestion") -> LifecycleRecord:
    return LifecycleRecord(
        asset_id=asset.asset_id,
        asset_fingerprint=asset.fingerprint,
        stage=LifecycleStage.INGESTED,
        occurred_at=occurred_at,
        actor_id=actor_id,
        reason=reason,
    )


def transition_lifecycle(
    current: LifecycleRecord,
    target: LifecycleStage,
    *,
    occurred_at: datetime,
    actor_id: str,
    reason: str,
    deletion_evidence: DeletionEvidence | None = None,
    legal_hold: bool | None = None,
) -> LifecycleRecord:
    _aware(occurred_at, "occurred_at")
    if occurred_at < current.occurred_at:
        raise ValueError("lifecycle transition cannot move backward in time")
    if target not in _ALLOWED_TRANSITIONS[current.stage]:
        raise ValueError(f"invalid lifecycle transition: {current.stage.value}->{target.value}")

    effective_hold = current.legal_hold if legal_hold is None else bool(legal_hold)
    if current.legal_hold and legal_hold is False:
        raise ValueError("legal hold cannot be removed by lifecycle transition")
    if effective_hold and target in {LifecycleStage.DELETION_PENDING, LifecycleStage.DELETED}:
        raise ValueError("legal hold blocks deletion lifecycle transitions")

    if target is LifecycleStage.DELETED:
        if deletion_evidence is None:
            raise ValueError("DELETED requires deletion evidence")
        if deletion_evidence.asset_id != current.asset_id:
            raise ValueError("deletion evidence asset mismatch")
        if deletion_evidence.status is not DeletionStatus.COMPLETED:
            raise ValueError("DELETED requires completed deletion evidence")
        if deletion_evidence.source_fingerprint != current.asset_fingerprint:
            raise ValueError("deletion evidence source fingerprint mismatch")
        if deletion_evidence.completed_at is None or deletion_evidence.completed_at > occurred_at:
            raise ValueError("deletion evidence must be completed before lifecycle DELETED event")

    return LifecycleRecord(
        asset_id=current.asset_id,
        asset_fingerprint=current.asset_fingerprint,
        stage=target,
        occurred_at=occurred_at,
        actor_id=actor_id,
        reason=reason,
        previous_record_fingerprint=current.fingerprint,
        legal_hold=effective_hold,
    )


def verify_lifecycle_chain(records: tuple[LifecycleRecord, ...]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if not records:
        return False, ("EMPTY_LIFECYCLE_CHAIN",)
    first = records[0]
    if first.stage is not LifecycleStage.INGESTED:
        reasons.append("LIFECYCLE_MUST_BEGIN_AT_INGESTED")
    if first.previous_record_fingerprint is not None:
        reasons.append("FIRST_LIFECYCLE_RECORD_HAS_PREVIOUS")
    asset_id = first.asset_id
    asset_fingerprint = first.asset_fingerprint
    previous = first
    for record in records[1:]:
        if record.asset_id != asset_id:
            reasons.append("LIFECYCLE_ASSET_ID_CHANGED")
        if record.asset_fingerprint != asset_fingerprint:
            reasons.append("LIFECYCLE_ASSET_FINGERPRINT_CHANGED")
        if record.previous_record_fingerprint != previous.fingerprint:
            reasons.append(f"LIFECYCLE_CHAIN_BROKEN:{record.stage.value}")
        if record.occurred_at < previous.occurred_at:
            reasons.append("LIFECYCLE_TIME_REGRESSION")
        if record.stage not in _ALLOWED_TRANSITIONS[previous.stage]:
            reasons.append(f"INVALID_LIFECYCLE_TRANSITION:{previous.stage.value}->{record.stage.value}")
        if previous.legal_hold and not record.legal_hold:
            reasons.append("LEGAL_HOLD_REMOVED_WITHOUT_SEPARATE_GOVERNANCE")
        if previous.legal_hold and record.stage in {LifecycleStage.DELETION_PENDING, LifecycleStage.DELETED}:
            reasons.append("LEGAL_HOLD_BYPASSED_IN_CHAIN")
        previous = record
    return not reasons, tuple(dict.fromkeys(reasons))
