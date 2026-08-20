from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


_ALLOWED_SOURCE_STATUS = {"PASS", "WATCH", "BLOCK"}


@dataclass(frozen=True)
class FootballAdmissionDecision:
    admission_status: str
    model_eligible: bool
    reason_codes: tuple[str, ...]


def _is_timezone_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def evaluate_football_admission(
    *,
    fixture_key: str,
    kickoff: datetime,
    cutoff: datetime,
    known_at: datetime,
    source_status: str,
    match_finished: bool,
) -> FootballAdmissionDecision:
    if not isinstance(fixture_key, str) or not fixture_key.strip():
        return FootballAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("MISSING_CANONICAL_FIXTURE_KEY",),
        )

    if not all(
        _is_timezone_aware(value)
        for value in (kickoff, cutoff, known_at)
    ):
        return FootballAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("TIMEZONE_UNVERIFIED",),
        )

    if known_at > cutoff:
        return FootballAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("KNOWN_AFTER_CUTOFF",),
        )

    if kickoff >= cutoff:
        return FootballAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("KICKOFF_NOT_BEFORE_CUTOFF",),
        )

    if match_finished is not True:
        return FootballAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("MATCH_NOT_FINISHED",),
        )

    if source_status not in _ALLOWED_SOURCE_STATUS:
        return FootballAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("INVALID_SOURCE_STATUS",),
        )

    if source_status == "BLOCK":
        return FootballAdmissionDecision(
            admission_status="BLOCK",
            model_eligible=False,
            reason_codes=("SOURCE_BLOCK",),
        )

    if source_status == "WATCH":
        return FootballAdmissionDecision(
            admission_status="WATCH",
            model_eligible=False,
            reason_codes=("SOURCE_WATCH_EXCLUDED",),
        )

    return FootballAdmissionDecision(
        admission_status="ADMIT",
        model_eligible=True,
        reason_codes=(),
    )
