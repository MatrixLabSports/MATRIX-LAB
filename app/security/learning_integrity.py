from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.release.canonical import canonical_sha256
from app.security.analysis_accountability import AnalysisAccountabilityAssessment, AttributionCategory
from app.security.provider_temporal_truth import TemporalTruthStatus


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


class LearningDisposition(str, Enum):
    CONFIRMED_SIGNAL_ERROR = "CONFIRMED_SIGNAL_ERROR"
    CONFIRMED_DATA_QUALITY_ERROR = "CONFIRMED_DATA_QUALITY_ERROR"
    CONFIRMED_DATA_COVERAGE_ERROR = "CONFIRMED_DATA_COVERAGE_ERROR"
    CONFIRMED_TIMING_ERROR = "CONFIRMED_TIMING_ERROR"
    CONFIRMED_PROVIDER_REVISION_IMPACT = "CONFIRMED_PROVIDER_REVISION_IMPACT"
    CONFIRMED_EXECUTION_ERROR = "CONFIRMED_EXECUTION_ERROR"
    INCONCLUSIVE = "INCONCLUSIVE"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True)
class IndependentLearningReview:
    review_id: str
    decision_id: str
    assessment_fingerprint: str
    decision_owner_id: str
    reviewer_id: str
    reviewed_at: datetime
    disposition: LearningDisposition
    review_evidence_sha256: str
    independent_review: bool

    def __post_init__(self) -> None:
        for value, name in (
            (self.review_id, "review_id"),
            (self.decision_id, "decision_id"),
            (self.decision_owner_id, "decision_owner_id"),
            (self.reviewer_id, "reviewer_id"),
        ):
            _nonempty(value, name)
        _sha256(self.assessment_fingerprint, "assessment_fingerprint")
        _sha256(self.review_evidence_sha256, "review_evidence_sha256")
        _aware(self.reviewed_at, "reviewed_at")
        if self.independent_review and self.decision_owner_id == self.reviewer_id:
            raise ValueError("independent reviewer must differ from decision owner")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class LearningIntegrityResult:
    decision_id: str
    status: TemporalTruthStatus
    reasons: tuple[str, ...]
    disposition: LearningDisposition
    assessment_fingerprint: str
    review_fingerprint: str
    eligible_for_model_error_dataset: bool
    eligible_for_process_improvement_dataset: bool
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        _nonempty(self.decision_id, "decision_id")
        _sha256(self.assessment_fingerprint, "assessment_fingerprint")
        _sha256(self.review_fingerprint, "review_fingerprint")
        if self.status is TemporalTruthStatus.BLOCK and (
            self.eligible_for_model_error_dataset or self.eligible_for_process_improvement_dataset
        ):
            raise ValueError("blocked review may not emit learning labels")
        if self.automatic_model_promotion:
            raise ValueError("learning integrity may not promote models")
        if self.automatic_wagering:
            raise ValueError("learning integrity may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


_REQUIRED_CANDIDATE: dict[LearningDisposition, AttributionCategory | None] = {
    LearningDisposition.CONFIRMED_SIGNAL_ERROR: AttributionCategory.SIGNAL_ERROR_CANDIDATE,
    LearningDisposition.CONFIRMED_DATA_QUALITY_ERROR: AttributionCategory.DATA_QUALITY_AT_DECISION,
    LearningDisposition.CONFIRMED_DATA_COVERAGE_ERROR: AttributionCategory.DATA_COVERAGE_GAP,
    LearningDisposition.CONFIRMED_TIMING_ERROR: AttributionCategory.ENTRY_TIMING_ISSUE,
    LearningDisposition.CONFIRMED_PROVIDER_REVISION_IMPACT: AttributionCategory.PROVIDER_CORRECTION_AFTER_DECISION,
    LearningDisposition.CONFIRMED_EXECUTION_ERROR: AttributionCategory.EXECUTION_MISMATCH,
    LearningDisposition.INCONCLUSIVE: None,
    LearningDisposition.NO_ACTION: None,
}


def evaluate_learning_integrity(
    assessment: AnalysisAccountabilityAssessment,
    review: IndependentLearningReview,
    *,
    now: datetime,
) -> LearningIntegrityResult:
    _aware(now, "now")
    block: list[str] = []
    watch: list[str] = []

    if review.decision_id != assessment.decision_id:
        block.append("REVIEW_DECISION_SCOPE_MISMATCH")
    if review.assessment_fingerprint != assessment.fingerprint:
        block.append("REVIEW_ASSESSMENT_FINGERPRINT_MISMATCH")
    if review.reviewed_at > now:
        block.append("REVIEW_FROM_FUTURE")
    # A BLOCK means the case cannot be used to judge model quality. Some
    # process failures (for example an execution mismatch) may still be useful
    # as process-improvement evidence if the underlying decision evidence is
    # trustworthy. Data-integrity or settlement-evidence failures remain fatal.
    if AttributionCategory.DATA_INTEGRITY_FAILURE in assessment.candidate_attributions:
        block.append("UNTRUSTED_DECISION_EVIDENCE_NOT_ELIGIBLE_FOR_LEARNING")
    if AttributionCategory.SETTLEMENT_EVIDENCE_GAP in assessment.candidate_attributions:
        block.append("UNVERIFIED_SETTLEMENT_NOT_ELIGIBLE_FOR_LEARNING")
    if assessment.status is TemporalTruthStatus.BLOCK and review.disposition is LearningDisposition.CONFIRMED_SIGNAL_ERROR:
        block.append("BLOCKED_ACCOUNTABILITY_ASSESSMENT_NOT_ELIGIBLE_FOR_MODEL_ERROR_LABEL")
    if not review.independent_review:
        block.append("INDEPENDENT_REVIEW_REQUIRED")
    if review.decision_owner_id == review.reviewer_id:
        block.append("SELF_REVIEW_NOT_ALLOWED")

    required = _REQUIRED_CANDIDATE[review.disposition]
    if required is not None and required not in assessment.candidate_attributions:
        block.append(f"DISPOSITION_NOT_SUPPORTED_BY_ASSESSMENT:{review.disposition.value}")

    model_error = review.disposition is LearningDisposition.CONFIRMED_SIGNAL_ERROR
    process_improvement = review.disposition in {
        LearningDisposition.CONFIRMED_DATA_QUALITY_ERROR,
        LearningDisposition.CONFIRMED_DATA_COVERAGE_ERROR,
        LearningDisposition.CONFIRMED_TIMING_ERROR,
        LearningDisposition.CONFIRMED_PROVIDER_REVISION_IMPACT,
        LearningDisposition.CONFIRMED_EXECUTION_ERROR,
    }

    if review.disposition is LearningDisposition.INCONCLUSIVE:
        watch.append("REVIEW_INCONCLUSIVE")
        model_error = False
        process_improvement = False
    elif review.disposition is LearningDisposition.NO_ACTION:
        model_error = False
        process_improvement = False

    if block:
        status = TemporalTruthStatus.BLOCK
        model_error = False
        process_improvement = False
        reasons = tuple(dict.fromkeys(block + watch))
    elif watch:
        status = TemporalTruthStatus.WATCH
        reasons = tuple(dict.fromkeys(watch))
    else:
        status = TemporalTruthStatus.PASS
        reasons = ()

    return LearningIntegrityResult(
        decision_id=assessment.decision_id,
        status=status,
        reasons=reasons,
        disposition=review.disposition,
        assessment_fingerprint=assessment.fingerprint,
        review_fingerprint=review.fingerprint,
        eligible_for_model_error_dataset=model_error,
        eligible_for_process_improvement_dataset=process_improvement,
    )
