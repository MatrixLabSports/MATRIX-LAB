from tools.telegram_green_signal_alerts import (
    PAPER_BANKROLL_INITIAL_COP,
    PAPER_UNIT_COP,
    paper_stake_cop,
    paper_stake_level,
    recalc_paper_bankroll,
)


def candidate(p: float, ev: float) -> dict:
    return {"p_matrix": p, "ev": ev}


def test_paper_bankroll_constants():
    assert PAPER_BANKROLL_INITIAL_COP == 5_000_000.0
    assert PAPER_UNIT_COP == 25_000.0
    assert paper_stake_cop(1) == 25_000.0
    assert paper_stake_cop(2) == 50_000.0
    assert paper_stake_cop(3) == 75_000.0


def test_confidence_stake_levels():
    assert paper_stake_level(candidate(0.66, 0.11)) == 3
    assert paper_stake_level(candidate(0.61, 0.06)) == 2
    assert paper_stake_level(candidate(0.59, 0.20)) == 1
    assert paper_stake_level(candidate(0.70, 0.03)) == 1


def test_recalc_separates_realized_and_open_exposure():
    ledger = {
        "sent": [
            {"paper_bet": {"status": "OPEN", "stake_cop": 50_000.0}},
            {"paper_bet": {"status": "SETTLED", "stake_cop": 75_000.0}},
        ],
        "settlements": [
            {"paper_stake_cop": 75_000.0, "paper_profit_cop": 60_000.0},
        ],
    }
    pb = recalc_paper_bankroll(ledger)
    assert pb["current_cop"] == 5_060_000.0
    assert pb["open_exposure_cop"] == 50_000.0
    assert pb["available_after_open_exposure_cop"] == 5_010_000.0
    assert pb["max_open_exposure_cop"] == 1_265_000.0
