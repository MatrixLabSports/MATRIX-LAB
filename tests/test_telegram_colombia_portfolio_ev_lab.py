from app.market.colombia_bookmakers import EXECUTION_BOOKMAKERS
from tools.telegram_green_signal_alerts import (
    POLICY_BOOKS,
    SIGNAL_QUALITY_MIN_REVALIDATED_EV,
    SIGNAL_QUALITY_MIN_P_MATRIX,
    is_ev_marginal_lab_candidate,
    ev_marginal_band,
)


def test_telegram_policy_books_cover_full_canonical_colombia_portfolio():
    assert set(POLICY_BOOKS) == set(EXECUTION_BOOKMAKERS)
    assert len(POLICY_BOOKS) == 14


def test_full_colombia_portfolio_contains_expected_14_current_books():
    assert set(POLICY_BOOKS) == {
        "betano", "betplay", "betsson", "bwin", "codere", "luckia",
        "mryoker", "rivalo", "rushbet", "sportium", "stake", "wplay",
        "yajuego", "zamba",
    }


def test_marginal_ev_lab_does_not_weaken_production_gate():
    assert SIGNAL_QUALITY_MIN_P_MATRIX == 0.60
    assert SIGNAL_QUALITY_MIN_REVALIDATED_EV == 0.05
    assert is_ev_marginal_lab_candidate(0.67, 1.53, 0.0349) is True
    assert is_ev_marginal_lab_candidate(0.67, 1.53, 0.0500) is False
    assert is_ev_marginal_lab_candidate(0.67, 1.50, 0.0349) is False
    assert is_ev_marginal_lab_candidate(0.59, 1.80, 0.0349) is False
    assert is_ev_marginal_lab_candidate(0.67, 1.53, 0.0) is False


def test_marginal_ev_lab_bands_are_separate():
    assert ev_marginal_band(0.003) == "EV_0_2PCT"
    assert ev_marginal_band(0.0199) == "EV_0_2PCT"
    assert ev_marginal_band(0.0200) == "EV_2_5PCT"
    assert ev_marginal_band(0.0499) == "EV_2_5PCT"
