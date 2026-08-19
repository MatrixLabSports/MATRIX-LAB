from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.release.canonical import canonical_sha256
from app.security.provider_temporal_truth import (
    DecisionEvidenceFreeze,
    ProviderTruthVersion,
    TemporalTruthPolicy,
    TemporalTruthStatus,
    resolve_point_in_time_truth,
    validate_decision_evidence_freeze,
)


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class DecisionReplayResult:
    decision_id: str
    status: TemporalTruthStatus
    reasons: tuple[str, ...]
    freeze_fingerprint: str
    selected_truth_version_id: str | None
    selected_truth_version_fingerprint: str | None
    selected_snapshot_fingerprint: str | None
    replayed_at: datetime
    future_knowledge_used: bool
    exact_frozen_evidence_reproduced: bool
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        _aware(self.replayed_at, "replayed_at")
        if self.future_knowledge_used:
            if self.status is not TemporalTruthStatus.BLOCK:
                raise ValueError("future knowledge must block decision replay")
        if self.exact_frozen_evidence_reproduced and self.status is TemporalTruthStatus.BLOCK:
            raise ValueError("blocked replay may not claim exact reproduction")
        if self.automatic_model_promotion:
            raise ValueError("decision replay may not promote models")
        if self.automatic_wagering:
            raise ValueError("decision replay may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def replay_decision_as_known(
    freeze: DecisionEvidenceFreeze,
    versions: Iterable[ProviderTruthVersion],
    *,
    policy: TemporalTruthPolicy,
    now: datetime,
) -> DecisionReplayResult:
    """Reconstruct exactly the provider truth MATRIX could use at decision time.

    The replay intentionally ignores revisions first known after ``decision_at``.
    It is therefore suitable for audit/accountability, not for reconstructing the
    provider's current best view of the event.
    """

    _aware(now, "now")
    assessment = validate_decision_evidence_freeze(freeze, versions, now=now, policy=policy)
    if assessment.status is TemporalTruthStatus.BLOCK:
        return DecisionReplayResult(
            decision_id=freeze.decision_id,
            status=TemporalTruthStatus.BLOCK,
            reasons=tuple(dict.fromkeys(("FROZEN_DECISION_EVIDENCE_INVALID",) + assessment.reasons)),
            freeze_fingerprint=freeze.fingerprint,
            selected_truth_version_id=None,
            selected_truth_version_fingerprint=None,
            selected_snapshot_fingerprint=None,
            replayed_at=now,
            future_knowledge_used=assessment.temporal_leakage_detected,
            exact_frozen_evidence_reproduced=False,
        )

    truth = resolve_point_in_time_truth(
        tuple(versions),
        provider_id=freeze.provider_id,
        canonical_fixture_id=freeze.canonical_fixture_id,
        as_of=freeze.decision_at,
        event_time=freeze.decision_at,
        now=now,
        policy=policy,
    )
    if truth.status is TemporalTruthStatus.BLOCK or truth.selected_version_id is None:
        return DecisionReplayResult(
            decision_id=freeze.decision_id,
            status=TemporalTruthStatus.BLOCK,
            reasons=tuple(dict.fromkeys(("POINT_IN_TIME_TRUTH_NOT_RECONSTRUCTABLE",) + truth.reasons)),
            freeze_fingerprint=freeze.fingerprint,
            selected_truth_version_id=truth.selected_version_id,
            selected_truth_version_fingerprint=truth.selected_version_fingerprint,
            selected_snapshot_fingerprint=truth.selected_snapshot_fingerprint,
            replayed_at=now,
            future_knowledge_used=True,
            exact_frozen_evidence_reproduced=False,
        )

    exact = (
        truth.selected_version_id == freeze.truth_version_id
        and truth.selected_version_fingerprint == freeze.truth_version_fingerprint
        and truth.selected_snapshot_fingerprint == freeze.snapshot_fingerprint
    )
    if not exact:
        return DecisionReplayResult(
            decision_id=freeze.decision_id,
            status=TemporalTruthStatus.BLOCK,
            reasons=("REPLAY_DOES_NOT_MATCH_FROZEN_DECISION_EVIDENCE",),
            freeze_fingerprint=freeze.fingerprint,
            selected_truth_version_id=truth.selected_version_id,
            selected_truth_version_fingerprint=truth.selected_version_fingerprint,
            selected_snapshot_fingerprint=truth.selected_snapshot_fingerprint,
            replayed_at=now,
            future_knowledge_used=True,
            exact_frozen_evidence_reproduced=False,
        )

    reasons = tuple(dict.fromkeys(truth.reasons))
    status = TemporalTruthStatus.WATCH if reasons else TemporalTruthStatus.PASS
    return DecisionReplayResult(
        decision_id=freeze.decision_id,
        status=status,
        reasons=reasons,
        freeze_fingerprint=freeze.fingerprint,
        selected_truth_version_id=truth.selected_version_id,
        selected_truth_version_fingerprint=truth.selected_version_fingerprint,
        selected_snapshot_fingerprint=truth.selected_snapshot_fingerprint,
        replayed_at=now,
        future_knowledge_used=False,
        exact_frozen_evidence_reproduced=True,
    )
