from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .provider_rights import DataForm, ProviderRightsProfile, TerminationTreatment


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class DataDispositionStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class DataDispositionResult:
    status: DataDispositionStatus
    reasons: tuple[str, ...]
    retention_permitted: bool
    deletion_required: bool


def evaluate_post_termination_disposition(
    profile: ProviderRightsProfile,
    *,
    data_form: DataForm,
    termination_at: datetime,
    now: datetime,
    deletion_evidence_verified: bool,
) -> DataDispositionResult:
    _require_aware(termination_at, "termination_at")
    _require_aware(now, "now")
    if termination_at > now:
        return DataDispositionResult(DataDispositionStatus.NOT_APPLICABLE, (), True, False)

    treatment = profile.termination_treatment
    if treatment is TerminationTreatment.DELETE_ALL_PROVIDER_DATA:
        if not deletion_evidence_verified:
            return DataDispositionResult(
                DataDispositionStatus.BLOCK,
                ("POST_TERMINATION_DELETION_EVIDENCE_REQUIRED",),
                False,
                True,
            )
        return DataDispositionResult(DataDispositionStatus.PASS, (), False, True)

    if treatment is TerminationTreatment.DELETE_RAW_RETAIN_DERIVED:
        if data_form is DataForm.RAW:
            if not deletion_evidence_verified:
                return DataDispositionResult(
                    DataDispositionStatus.BLOCK,
                    ("POST_TERMINATION_RAW_DELETION_EVIDENCE_REQUIRED",),
                    False,
                    True,
                )
            return DataDispositionResult(DataDispositionStatus.PASS, (), False, True)
        return DataDispositionResult(DataDispositionStatus.PASS, (), True, False)

    if treatment is TerminationTreatment.RETAIN_GOVERNED_DATA:
        return DataDispositionResult(DataDispositionStatus.PASS, (), True, False)

    return DataDispositionResult(
        DataDispositionStatus.WATCH,
        ("POST_TERMINATION_EXTERNAL_REVIEW_REQUIRED",),
        False,
        False,
    )
