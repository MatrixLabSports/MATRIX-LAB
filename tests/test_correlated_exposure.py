import pytest

from app.research.football.correlated_exposure import (
    CorrelationLimits,
    ExposureRecord,
    assess_correlated_exposure,
)


def test_correlation_limits_have_no_runtime_defaults():
    with pytest.raises(TypeError):
        CorrelationLimits()


def test_same_fixture_aggregates_across_markets_before_admission():
    limits = CorrelationLimits(
        max_fixture_fraction=0.02,
        max_tournament_day_fraction=0.05,
        max_day_fraction=0.10,
    )
    existing = [
        ExposureRecord("fx-1", "league-a", "2026-10-13", 60_000),
    ]
    proposed = ExposureRecord("fx-1", "league-a", "2026-10-13", 50_000)

    result = assess_correlated_exposure(
        existing,
        proposed,
        bankroll=5_000_000,
        limits=limits,
    )

    assert result.allowed is False
    assert "FIXTURE_CORRELATED_EXPOSURE_LIMIT" in result.blocked_reasons
    assert result.fixture_exposure_after == 110_000
    assert result.real_money == "BLOCKED"


def test_tournament_day_and_daily_exposure_are_independent_gates():
    limits = CorrelationLimits(
        max_fixture_fraction=0.10,
        max_tournament_day_fraction=0.02,
        max_day_fraction=0.03,
    )
    existing = [
        ExposureRecord("fx-1", "league-a", "2026-10-13", 60_000),
        ExposureRecord("fx-2", "league-a", "2026-10-13", 40_000),
        ExposureRecord("fx-3", "league-b", "2026-10-13", 40_000),
    ]
    proposed = ExposureRecord("fx-4", "league-a", "2026-10-13", 30_000)

    result = assess_correlated_exposure(
        existing,
        proposed,
        bankroll=5_000_000,
        limits=limits,
    )

    assert result.allowed is False
    assert "TOURNAMENT_DAY_CORRELATED_EXPOSURE_LIMIT" in result.blocked_reasons
    assert "DAILY_AGGREGATE_EXPOSURE_LIMIT" in result.blocked_reasons


def test_within_explicit_limits_passes_in_paper_mode_only():
    limits = CorrelationLimits(
        max_fixture_fraction=0.02,
        max_tournament_day_fraction=0.05,
        max_day_fraction=0.10,
    )
    result = assess_correlated_exposure(
        [],
        ExposureRecord("fx-1", "league-a", "2026-10-13", 25_000),
        bankroll=5_000_000,
        limits=limits,
    )
    assert result.allowed is True
    assert result.status == "PASS_PAPER_EXPOSURE"
    assert result.mode == "PAPER_ONLY"
    assert result.real_money == "BLOCKED"
