from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence


WINDOWS = (5, 10, 20, 30, 50)
_ALLOWED_SPORTS = {"football", "tennis"}
_ALLOWED_RIGHTS = {"PASS", "RESEARCH_ONLY"}


def _next_window_gap(count: int) -> tuple[int | None, int]:
    for window in WINDOWS:
        if count < window:
            return window, window - count
    return None, 0


def _validate_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"INVALID_{name.upper()}")
    return value


@dataclass(frozen=True)
class CoverageGapCandidate:
    sport: str
    subject_key: str
    provider_key: str
    competition_key: str
    season_key: str
    coverage_ledger: Mapping[str, Any]
    expected_new_eligible_rows: int
    expected_new_deep_rows: int
    rights_status: str
    identity_status: str
    chronology_status: str

    def __post_init__(self) -> None:
        if self.sport not in _ALLOWED_SPORTS:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")

        for field_name, value in (
            ("subject_key", self.subject_key),
            ("provider_key", self.provider_key),
            ("competition_key", self.competition_key),
            ("season_key", self.season_key),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"MISSING_{field_name.upper()}")

        _validate_non_negative_int(
            "EXPECTED_NEW_ELIGIBLE_ROWS",
            self.expected_new_eligible_rows,
        )
        _validate_non_negative_int(
            "EXPECTED_NEW_DEEP_ROWS",
            self.expected_new_deep_rows,
        )

        if self.expected_new_deep_rows > self.expected_new_eligible_rows:
            raise ValueError("DEEP_EXCEEDS_ELIGIBLE")

        ledger_sport = self.coverage_ledger.get("sport")
        if ledger_sport != self.sport:
            raise ValueError("COVERAGE_LEDGER_SPORT_MISMATCH")

        ledger_subject = self.coverage_ledger.get("subject_key")
        if ledger_subject != self.subject_key:
            raise ValueError("COVERAGE_LEDGER_SUBJECT_MISMATCH")

        for field in (
            "eligible_observations",
            "deep_ready_observations",
            "blocked_observations",
        ):
            _validate_non_negative_int(
                field,
                self.coverage_ledger.get(field),
            )

        average_coverage = self.coverage_ledger.get(
            "average_core_stat_coverage"
        )
        if average_coverage is not None:
            if (
                isinstance(average_coverage, bool)
                or not isinstance(average_coverage, (int, float))
                or not isfinite(float(average_coverage))
                or not 0.0 <= float(average_coverage) <= 1.0
            ):
                raise ValueError("INVALID_AVERAGE_CORE_STAT_COVERAGE")

    @property
    def eligible_count(self) -> int:
        return int(self.coverage_ledger["eligible_observations"])

    @property
    def deep_ready_count(self) -> int:
        return int(self.coverage_ledger["deep_ready_observations"])

    @property
    def blocked_count(self) -> int:
        return int(self.coverage_ledger["blocked_observations"])

    @property
    def missing_core_ratio(self) -> float | None:
        coverage = self.coverage_ledger.get("average_core_stat_coverage")
        if coverage is None:
            return None
        return 1.0 - float(coverage)


def _hard_blockers(candidate: CoverageGapCandidate) -> tuple[str, ...]:
    reasons: list[str] = []

    if candidate.rights_status not in _ALLOWED_RIGHTS:
        reasons.append("RIGHTS_NOT_VERIFIED")

    if candidate.identity_status != "PASS":
        reasons.append("IDENTITY_NOT_VERIFIED")

    if candidate.chronology_status != "PASS":
        reasons.append("CHRONOLOGY_NOT_VERIFIED")

    return tuple(sorted(set(reasons)))


def prioritize_gap(candidate: CoverageGapCandidate) -> Mapping[str, Any]:
    blockers = _hard_blockers(candidate)

    next_window, next_gap = _next_window_gap(candidate.eligible_count)
    deep_next_window, deep_next_gap = _next_window_gap(
        candidate.deep_ready_count
    )

    marginal_window_gain = (
        0
        if next_window is None
        else min(candidate.expected_new_eligible_rows, next_gap)
    )

    deep_window_gain = (
        0
        if deep_next_window is None
        else min(candidate.expected_new_deep_rows, deep_next_gap)
    )

    closes_next_window = (
        next_window is not None
        and candidate.expected_new_eligible_rows >= next_gap
    )

    closes_next_deep_window = (
        deep_next_window is not None
        and candidate.expected_new_deep_rows >= deep_next_gap
    )

    missingness_gain = 0.0
    if candidate.missing_core_ratio is not None:
        missingness_gain = (
            candidate.missing_core_ratio
            * min(candidate.expected_new_deep_rows, 10)
        )

    raw_score = (
        4.0 * marginal_window_gain
        + 6.0 * deep_window_gain
        + 12.0 * int(closes_next_window)
        + 18.0 * int(closes_next_deep_window)
        + 2.0 * missingness_gain
        - 1.0 * candidate.blocked_count
    )

    if blockers:
        disposition = "QUARANTINE"
        priority_score = 0.0
    elif candidate.expected_new_eligible_rows == 0:
        disposition = "NO_ACTION"
        priority_score = max(0.0, raw_score)
    else:
        disposition = "PRIORITIZE"
        priority_score = max(0.0, raw_score)

    return {
        "schema": "matrix.coverage-gap-priority/1",
        "sport": candidate.sport,
        "subject_key": candidate.subject_key,
        "provider_key": candidate.provider_key,
        "competition_key": candidate.competition_key,
        "season_key": candidate.season_key,
        "current_eligible_count": candidate.eligible_count,
        "current_deep_ready_count": candidate.deep_ready_count,
        "blocked_count": candidate.blocked_count,
        "next_window": next_window,
        "next_window_gap": next_gap,
        "deep_next_window": deep_next_window,
        "deep_next_window_gap": deep_next_gap,
        "expected_new_eligible_rows": candidate.expected_new_eligible_rows,
        "expected_new_deep_rows": candidate.expected_new_deep_rows,
        "marginal_window_gain": marginal_window_gain,
        "deep_window_gain": deep_window_gain,
        "closes_next_window": closes_next_window,
        "closes_next_deep_window": closes_next_deep_window,
        "missing_core_ratio": candidate.missing_core_ratio,
        "blockers": blockers,
        "priority_score": round(priority_score, 6),
        "disposition": disposition,
        "rights_status": candidate.rights_status,
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }


def rank_gap_candidates(
    *,
    sport: str,
    candidates: Sequence[CoverageGapCandidate],
) -> list[Mapping[str, Any]]:
    if sport not in _ALLOWED_SPORTS:
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    if any(candidate.sport != sport for candidate in candidates):
        raise ValueError("CROSS_SPORT_CANDIDATE_CONTAMINATION")

    rows = [prioritize_gap(candidate) for candidate in candidates]
    disposition_order = {
        "PRIORITIZE": 0,
        "NO_ACTION": 1,
        "QUARANTINE": 2,
    }

    return sorted(
        rows,
        key=lambda row: (
            disposition_order[row["disposition"]],
            -float(row["priority_score"]),
            str(row["subject_key"]),
            str(row["provider_key"]),
        ),
    )
