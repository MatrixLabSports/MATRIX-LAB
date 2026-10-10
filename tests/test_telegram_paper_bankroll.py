from tools.telegram_green_signal_alerts import (
    PAPER_BANKROLL_INITIAL_COP,
    PAPER_DAILY_BASE_EXPOSURE_FRACTION,
    PAPER_DAILY_MAX_EXPOSURE_FRACTION,
    PAPER_UNIT_COP,
    paper_daily_cap_fraction,
    paper_stake_cop,
    paper_stake_level,
    recalc_paper_bankroll,
    green_message,
    paper_assignment_update_message,
)


def candidate(p: float, ev: float) -> dict:
    return {"p_matrix": p, "ev": ev, "eligible_green": True}


def test_paper_bankroll_constants():
    assert PAPER_BANKROLL_INITIAL_COP == 5_000_000.0
    assert PAPER_UNIT_COP == 25_000.0
    assert PAPER_DAILY_BASE_EXPOSURE_FRACTION == 0.30
    assert PAPER_DAILY_MAX_EXPOSURE_FRACTION == 0.40
    assert paper_stake_cop(1) == 25_000.0
    assert paper_stake_cop(2) == 50_000.0
    assert paper_stake_cop(3) == 75_000.0


def test_confidence_stake_levels():
    assert paper_stake_level(candidate(0.66, 0.11)) == 3
    assert paper_stake_level(candidate(0.61, 0.06)) == 2
    assert paper_stake_level(candidate(0.59, 0.20)) == 1
    assert paper_stake_level(candidate(0.70, 0.03)) == 1


def test_daily_cap_uses_40_percent_only_for_high_conviction_day():
    high = [candidate(0.66, 0.11) for _ in range(5)] + [candidate(0.61, 0.06) for _ in range(5)]
    normal = [candidate(0.66, 0.11) for _ in range(4)] + [candidate(0.61, 0.06) for _ in range(6)]
    assert paper_daily_cap_fraction(high) == 0.40
    assert paper_daily_cap_fraction(normal) == 0.30


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
    assert pb["max_open_exposure_cop"] == 2_024_000.0
    assert pb["daily_base_exposure_fraction"] == 0.30
    assert pb["daily_max_exposure_fraction"] == 0.40



def test_green_message_includes_paper_bankroll_and_stake():
    c = {
        "match": "A vs B",
        "market": "Más de 2.5 goles",
        "p_matrix": 0.61,
        "house": "Betano",
        "odds": 1.80,
        "ev": 0.08,
        "kickoff": "2026-10-10T14:00:00+00:00",
        "execution": None,
        "paper_bet": {
            "stake_level": 2,
            "stake_cop": 50_000.0,
            "bankroll_before_cop": 5_000_000.0,
        },
    }
    msg = green_message(c)
    assert "STAKE 2" in msg
    assert "Apuesta de papel: COP 50.000" in msg
    assert "Bankroll papel antes: COP 5.000.000" in msg


def test_retroactive_paper_assignment_message_includes_bankroll_and_stake():
    record = {
        "match": "A vs B",
        "market": "Más de 2.5 goles",
        "p_matrix": 0.64,
        "house": "Betano",
        "odds": 1.82,
        "ev": 0.16,
    }
    paper = {"stake_level": 2, "stake_cop": 50_000.0}
    pb = {
        "current_cop": 5_000_000.0,
        "open_exposure_cop": 1_950_000.0,
        "max_open_exposure_cop": 2_000_000.0,
    }
    msg = paper_assignment_update_message(record, paper, pb)
    assert "STAKE 2" in msg
    assert "Apuesta de papel: COP 50.000" in msg
    assert "Bankroll de papel: COP 5.000.000" in msg
    assert "Exposición abierta de papel: COP 1.950.000 / COP 2.000.000" in msg
