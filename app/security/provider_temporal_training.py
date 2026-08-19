from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.release.canonical import canonical_sha256
from app.security.provider_temporal_truth import (
    ProviderTruthVersion,
    TemporalTruthPolicy,
    TemporalTruthStatus,
    resolve_point_in_time_truth,
)


@dataclass(frozen=True)
class TrainingTruthCutoff:
    sample_id: str
    provider_id: str
    canonical_fixture_id: str
    feature_cutoff_at: datetime
    label_cutoff_at: datetime
    selected_feature_truth_fingerprint: str | None
    leakage_detected: bool
    status: TemporalTruthStatus
    reasons: tuple[str, ...]
    automatic_model_promotion: bool = False

    def __post_init__(self) -> None:
        if self.feature_cutoff_at.tzinfo is None or self.feature_cutoff_at.utcoffset() is None:
            raise ValueError("feature_cutoff_at must be timezone-aware")
        if self.label_cutoff_at.tzinfo is None or self.label_cutoff_at.utcoffset() is None:
            raise ValueError("label_cutoff_at must be timezone-aware")
        if self.label_cutoff_at < self.feature_cutoff_at:
            raise ValueError("label_cutoff_at may not be before feature_cutoff_at")
        if self.automatic_model_promotion:
            raise ValueError("training cutoff may not promote models")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def build_training_truth_cutoff(
    *,
    sample_id: str,
    provider_id: str,
    canonical_fixture_id: str,
    feature_cutoff_at: datetime,
    label_cutoff_at: datetime,
    versions: tuple[ProviderTruthVersion, ...],
    now: datetime,
    policy: TemporalTruthPolicy,
) -> TrainingTruthCutoff:
    historical = resolve_point_in_time_truth(
        versions,
        provider_id=provider_id,
        canonical_fixture_id=canonical_fixture_id,
        as_of=feature_cutoff_at,
        event_time=feature_cutoff_at,
        now=now,
        policy=policy,
    )
    if historical.status is TemporalTruthStatus.BLOCK:
        return TrainingTruthCutoff(
            sample_id,
            provider_id,
            canonical_fixture_id,
            feature_cutoff_at,
            label_cutoff_at,
            None,
            True,
            TemporalTruthStatus.BLOCK,
            tuple(dict.fromkeys(("FEATURE_TRUTH_NOT_RECONSTRUCTABLE",) + historical.reasons)),
        )
    # Labels may legitimately be known later; only feature truth is restricted to the feature cutoff.
    return TrainingTruthCutoff(
        sample_id,
        provider_id,
        canonical_fixture_id,
        feature_cutoff_at,
        label_cutoff_at,
        historical.selected_version_fingerprint,
        False,
        TemporalTruthStatus.WATCH if historical.status is TemporalTruthStatus.WATCH else TemporalTruthStatus.PASS,
        historical.reasons,
    )
