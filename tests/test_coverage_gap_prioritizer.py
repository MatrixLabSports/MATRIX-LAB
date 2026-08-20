import pytest

from app.application.football.coverage_gap_prioritizer import (
    prioritize_football_coverage_gaps,
)
from app.application.tennis.coverage_gap_prioritizer import (
    prioritize_tennis_coverage_gaps,
)
from app.core.coverage_gap_prioritizer import (
    CoverageGapCandidate,
    prioritize_gap,
)


def ledger(
    sport: str,
    subject_key: str,
    *,
    eligible: int,
    deep: int,
    blocked: int = 0,
    coverage: float | None = 0.8,
):
    return {
        "schema": "matrix.historical-coverage-ledger/1",
        "sport": sport,
        "subject_key": subject_key,
        "eligible_observations": eligible,
        "deep_ready_observations": deep,
        "blocked_observations": blocked,
        "average_core_stat_coverage": coverage,
    }


def candidate(
    sport: str,
    subject_key: str,
    *,
    eligible: int,
    deep: int,
    expected: int = 2,
    expected_deep: int = 2,
    blocked: int = 0,
    coverage: float | None = 0.8,
    rights: str = "PASS",
    identity: str = "PASS",
    chronology: str = "PASS",
):
    return CoverageGapCandidate(
        sport=sport,
        subject_key=subject_key,
        provider_key="PROVIDER:1",
        competition_key="COMP:1",
        season_key="2026",
        coverage_ledger=ledger(
            sport,
            subject_key,
            eligible=eligible,
            deep=deep,
            blocked=blocked,
            coverage=coverage,
        ),
        expected_new_eligible_rows=expected,
        expected_new_deep_rows=expected_deep,
        rights_status=rights,
        identity_status=identity,
        chronology_status=chronology,
    )


def test_closing_10_window_outranks_progress_toward_20():
    close_10 = candidate(
        "tennis",
        "PLAYER:A",
        eligible=9,
        deep=9,
    )
    toward_20 = candidate(
        "tennis",
        "PLAYER:B",
        eligible=11,
        deep=11,
    )

    ranked = prioritize_tennis_coverage_gaps(
        candidates=[toward_20, close_10]
    )

    assert ranked[0]["subject_key"] == "PLAYER:A"
    assert ranked[0]["closes_next_window"] is True


def test_deep_ready_rows_receive_more_value():
    shallow = candidate(
        "football",
        "TEAM:SHALLOW",
        eligible=9,
        deep=2,
        expected=3,
        expected_deep=0,
    )
    deep = candidate(
        "football",
        "TEAM:DEEP",
        eligible=9,
        deep=2,
        expected=3,
        expected_deep=3,
    )

    ranked = prioritize_football_coverage_gaps(
        candidates=[shallow, deep]
    )

    assert ranked[0]["subject_key"] == "TEAM:DEEP"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("rights", "WATCH", "RIGHTS_NOT_VERIFIED"),
        ("identity", "WATCH", "IDENTITY_NOT_VERIFIED"),
        ("chronology", "BLOCK", "CHRONOLOGY_NOT_VERIFIED"),
    ],
)
def test_governance_blockers_override_high_score(field, value, reason):
    kwargs = {field: value}
    row = candidate(
        "tennis",
        "PLAYER:Q",
        eligible=4,
        deep=4,
        expected=50,
        expected_deep=50,
        **kwargs,
    )

    result = prioritize_gap(row)

    assert result["disposition"] == "QUARANTINE"
    assert result["priority_score"] == 0.0
    assert reason in result["blockers"]


def test_research_only_can_be_prioritized_for_research():
    row = candidate(
        "tennis",
        "PLAYER:R",
        eligible=4,
        deep=4,
        rights="RESEARCH_ONLY",
    )

    result = prioritize_gap(row)

    assert result["disposition"] == "PRIORITIZE"
    assert result["rights_status"] == "RESEARCH_ONLY"


def test_zero_expected_rows_is_no_action():
    row = candidate(
        "football",
        "TEAM:ZERO",
        eligible=49,
        deep=49,
        expected=0,
        expected_deep=0,
    )

    result = prioritize_gap(row)

    assert result["disposition"] == "NO_ACTION"


def test_blocked_history_reduces_priority():
    clean = candidate(
        "football",
        "TEAM:CLEAN",
        eligible=9,
        deep=9,
        blocked=0,
    )
    noisy = candidate(
        "football",
        "TEAM:NOISY",
        eligible=9,
        deep=9,
        blocked=10,
    )

    ranked = prioritize_football_coverage_gaps(
        candidates=[noisy, clean]
    )

    assert ranked[0]["subject_key"] == "TEAM:CLEAN"


def test_missing_coverage_remains_none():
    row = candidate(
        "tennis",
        "PLAYER:MISSING",
        eligible=4,
        deep=4,
        coverage=None,
    )

    result = prioritize_gap(row)

    assert result["missing_core_ratio"] is None


def test_cross_sport_candidate_mix_is_blocked():
    rows = [
        candidate(
            "football",
            "TEAM:1",
            eligible=4,
            deep=4,
        ),
        candidate(
            "tennis",
            "PLAYER:1",
            eligible=4,
            deep=4,
        ),
    ]

    with pytest.raises(
        ValueError,
        match="CROSS_SPORT_CANDIDATE_CONTAMINATION",
    ):
        prioritize_football_coverage_gaps(candidates=rows)


def test_candidate_must_match_coverage_ledger_subject():
    with pytest.raises(
        ValueError,
        match="COVERAGE_LEDGER_SUBJECT_MISMATCH",
    ):
        CoverageGapCandidate(
            sport="tennis",
            subject_key="PLAYER:A",
            provider_key="PROVIDER:1",
            competition_key="COMP:1",
            season_key="2026",
            coverage_ledger=ledger(
                "tennis",
                "PLAYER:B",
                eligible=4,
                deep=4,
            ),
            expected_new_eligible_rows=2,
            expected_new_deep_rows=2,
            rights_status="PASS",
            identity_status="PASS",
            chronology_status="PASS",
        )


def test_safety_flags_remain_false():
    row = candidate(
        "football",
        "TEAM:SAFE",
        eligible=4,
        deep=4,
    )

    result = prioritize_gap(row)

    assert result["automatic_model_promotion"] is False
    assert result["automatic_provider_switch"] is False
    assert result["automatic_wagering"] is False
