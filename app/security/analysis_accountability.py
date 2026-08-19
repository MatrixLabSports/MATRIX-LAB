from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

from app.release.canonical import canonical_sha256
from app.security.decision_replay import DecisionReplayResult, replay_decision_as_known
from app.security.provider_temporal_truth import (
    DecisionEvidenceFreeze,
    ProviderTruthVersion,
    RevisionImpactLevel,
    TemporalTruthPolicy,
    TemporalTruthStatus,
    assess_post_decision_revision_impact,
)


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _nonempty(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} is required")
    return cleaned


def _sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256")


class SettledOutcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    PUSH = "PUSH"
    VOID = "VOID"
    UNSETTLED = "UNSETTLED"


class CoverageState(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class EntryTimingState(str, Enum):
    ON_TIME = "ON_TIME"
    LATE = "LATE"
    MISSED = "MISSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AttributionCategory(str, Enum):
    NO_PERFORMANCE_JUDGMENT = "NO_PERFORMANCE_JUDGMENT"
    DATA_INTEGRITY_FAILURE = "DATA_INTEGRITY_FAILURE"
    SETTLEMENT_EVIDENCE_GAP = "SETTLEMENT_EVIDENCE_GAP"
    MARKET_IDENTITY_MISMATCH = "MARKET_IDENTITY_MISMATCH"
    EXECUTION_MISMATCH = "EXECUTION_MISMATCH"
    DATA_QUALITY_AT_DECISION = "DATA_QUALITY_AT_DECISION"
    DATA_COVERAGE_GAP = "DATA_COVERAGE_GAP"
    ENTRY_TIMING_ISSUE = "ENTRY_TIMING_ISSUE"
    PROVIDER_CORRECTION_AFTER_DECISION = "PROVIDER_CORRECTION_AFTER_DECISION"
    SIGNAL_ERROR_CANDIDATE = "SIGNAL_ERROR_CANDIDATE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class DecisionOutcomeEvidence:
    decision_id: str
    market_key: str | None
    outcome: SettledOutcome
    settled_at: datetime
    settlement_verified: bool
    settlement_evidence_sha256: str

    def __post_init__(self) -> None:
        _nonempty(self.decision_id, "decision_id")
        _aware(self.settled_at, "settled_at")
        _sha256(self.settlement_evidence_sha256, "settlement_evidence_sha256")
        if self.market_key is not None:
            _nonempty(self.market_key, "market_key")
        if self.outcome is SettledOutcome.UNSETTLED and self.settlement_verified:
            raise ValueError("UNSETTLED outcome may not be settlement_verified")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class DecisionOperationalContext:
    decision_id: str
    captured_at: datetime
    coverage_state: CoverageState
    entry_timing_state: EntryTimingState
    data_quality_gate_passed: bool
    market_identity_verified: bool
    execution_matches_recommendation: bool
    context_evidence_sha256: str

    def __post_init__(self) -> None:
        _nonempty(self.decision_id, "decision_id")
        _aware(self.captured_at, "captured_at")
        _sha256(self.context_evidence_sha256, "context_evidence_sha256")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class AnalysisAccountabilityAssessment:
    decision_id: str
    status: TemporalTruthStatus
    reasons: tuple[str, ...]
    candidate_attributions: tuple[AttributionCategory, ...]
    replay_fingerprint: str
    correction_impact_fingerprint: str
    outcome_fingerprint: str
    context_fingerprint: str
    human_review_required: bool
    controlled_reanalysis_required: bool
    analysis_quality_determined: bool = False
    learning_label_allowed: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        _nonempty(self.decision_id, "decision_id")
        for value, name in (
            (self.replay_fingerprint, "replay_fingerprint"),
            (self.correction_impact_fingerprint, "correction_impact_fingerprint"),
            (self.outcome_fingerprint, "outcome_fingerprint"),
            (self.context_fingerprint, "context_fingerprint"),
        ):
            _sha256(value, name)
        if self.analysis_quality_determined:
            raise ValueError("automatic accountability may not determine analysis quality")
        if self.learning_label_allowed:
            raise ValueError("accountability assessment may not label training data without review")
        if self.automatic_model_promotion:
            raise ValueError("accountability assessment may not promote models")
        if self.automatic_wagering:
            raise ValueError("accountability assessment may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def assess_analysis_accountability(
    freeze: DecisionEvidenceFreeze,
    versions: Iterable[ProviderTruthVersion],
    outcome: DecisionOutcomeEvidence,
    context: DecisionOperationalContext,
    *,
    policy: TemporalTruthPolicy,
    now: datetime,
) -> AnalysisAccountabilityAssessment:
    _aware(now, "now")
    values = tuple(versions)
    replay: DecisionReplayResult = replay_decision_as_known(freeze, values, policy=policy, now=now)
    impact = assess_post_decision_revision_impact(freeze, values, now=now, policy=policy)

    block: list[str] = []
    watch: list[str] = []
    candidates: list[AttributionCategory] = []

    if outcome.decision_id != freeze.decision_id or context.decision_id != freeze.decision_id:
        block.append("DECISION_SCOPE_MISMATCH")
        candidates.append(AttributionCategory.DATA_INTEGRITY_FAILURE)

    if replay.status is TemporalTruthStatus.BLOCK:
        block.extend(("DECISION_REPLAY_BLOCKED",) + replay.reasons)
        candidates.append(AttributionCategory.DATA_INTEGRITY_FAILURE)

    if outcome.settled_at > now:
        block.append("SETTLEMENT_FROM_FUTURE")
        candidates.append(AttributionCategory.SETTLEMENT_EVIDENCE_GAP)
    if outcome.settled_at < freeze.decision_at:
        block.append("SETTLEMENT_BEFORE_DECISION")
        candidates.append(AttributionCategory.SETTLEMENT_EVIDENCE_GAP)
    if context.captured_at > freeze.decision_at:
        block.append("FUTURE_CONTEXT_EVIDENCE_USED_FOR_RETROSPECTIVE_ATTRIBUTION")
        candidates.append(AttributionCategory.DATA_INTEGRITY_FAILURE)

    if freeze.market_key != outcome.market_key:
        block.append("OUTCOME_MARKET_DOES_NOT_MATCH_FROZEN_DECISION")
        candidates.append(AttributionCategory.MARKET_IDENTITY_MISMATCH)
    if not context.market_identity_verified:
        block.append("MARKET_IDENTITY_NOT_VERIFIED")
        candidates.append(AttributionCategory.MARKET_IDENTITY_MISMATCH)
    if not context.execution_matches_recommendation:
        block.append("EXECUTION_DOES_NOT_MATCH_RECOMMENDATION")
        candidates.append(AttributionCategory.EXECUTION_MISMATCH)

    if outcome.outcome is SettledOutcome.UNSETTLED:
        watch.append("OUTCOME_NOT_SETTLED")
        candidates.append(AttributionCategory.UNRESOLVED)
    elif not outcome.settlement_verified:
        block.append("SETTLEMENT_NOT_VERIFIED")
        candidates.append(AttributionCategory.SETTLEMENT_EVIDENCE_GAP)

    if not context.data_quality_gate_passed:
        watch.append("DATA_QUALITY_GATE_DID_NOT_PASS_AT_DECISION")
        candidates.append(AttributionCategory.DATA_QUALITY_AT_DECISION)
    if context.coverage_state is CoverageState.PARTIAL:
        watch.append("PARTIAL_DATA_COVERAGE_AT_DECISION")
        candidates.append(AttributionCategory.DATA_COVERAGE_GAP)
    elif context.coverage_state is CoverageState.MISSING:
        watch.append("MISSING_DATA_COVERAGE_AT_DECISION")
        candidates.append(AttributionCategory.DATA_COVERAGE_GAP)
    if context.entry_timing_state in {EntryTimingState.LATE, EntryTimingState.MISSED}:
        watch.append(f"ENTRY_TIMING_{context.entry_timing_state.value}")
        candidates.append(AttributionCategory.ENTRY_TIMING_ISSUE)

    material_correction = impact.impact_level in {
        RevisionImpactLevel.MEDIUM,
        RevisionImpactLevel.HIGH,
        RevisionImpactLevel.CRITICAL,
    }
    if impact.status is TemporalTruthStatus.BLOCK:
        block.extend(("POST_DECISION_CORRECTION_IMPACT_BLOCKED",) + impact.reasons)
        candidates.append(AttributionCategory.DATA_INTEGRITY_FAILURE)
    elif material_correction:
        watch.extend(impact.reasons)
        candidates.append(AttributionCategory.PROVIDER_CORRECTION_AFTER_DECISION)

    # A settled loss with clean, complete, on-time evidence is a signal-error
    # *candidate*, not proof of bad analysis. Randomness and model uncertainty
    # remain possible and require independent review before a learning label.
    if (
        outcome.outcome is SettledOutcome.LOSS
        and not block
        and not material_correction
        and context.data_quality_gate_passed
        and context.coverage_state is CoverageState.COMPLETE
        and context.entry_timing_state in {EntryTimingState.ON_TIME, EntryTimingState.NOT_APPLICABLE}
        and context.market_identity_verified
        and context.execution_matches_recommendation
        and outcome.settlement_verified
    ):
        watch.append("LOSS_WITH_CLEAN_DECISION_TIME_EVIDENCE_REQUIRES_SIGNAL_REVIEW")
        candidates.append(AttributionCategory.SIGNAL_ERROR_CANDIDATE)

    if outcome.outcome in {SettledOutcome.PUSH, SettledOutcome.VOID}:
        candidates.append(AttributionCategory.NO_PERFORMANCE_JUDGMENT)
    elif outcome.outcome is SettledOutcome.WIN and not candidates:
        candidates.append(AttributionCategory.NO_PERFORMANCE_JUDGMENT)

    if block:
        status = TemporalTruthStatus.BLOCK
        reasons = tuple(dict.fromkeys(block + watch))
    elif watch or replay.status is TemporalTruthStatus.WATCH or impact.status is TemporalTruthStatus.WATCH:
        status = TemporalTruthStatus.WATCH
        reasons = tuple(dict.fromkeys(watch + list(replay.reasons)))
    else:
        status = TemporalTruthStatus.PASS
        reasons = ()

    unique_candidates = tuple(dict.fromkeys(candidates))
    human_review_required = status is not TemporalTruthStatus.PASS or outcome.outcome is SettledOutcome.LOSS
    return AnalysisAccountabilityAssessment(
        decision_id=freeze.decision_id,
        status=status,
        reasons=reasons,
        candidate_attributions=unique_candidates,
        replay_fingerprint=replay.fingerprint,
        correction_impact_fingerprint=impact.fingerprint,
        outcome_fingerprint=outcome.fingerprint,
        context_fingerprint=context.fingerprint,
        human_review_required=human_review_required,
        controlled_reanalysis_required=impact.reanalysis_required,
    )
