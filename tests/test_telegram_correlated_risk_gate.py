from app.research.football.correlated_exposure import CorrelationLimits, ExposureRecord
from app.research.football.correlated_risk_calibration import (
    calibrate_correlated_risk_from_ledger,
    calibration_evidence,
)
from tools.telegram_green_signal_alerts import (
    correlated_risk_gate_state,
    correlated_risk_limits_from_physical_calibration,
)


def _risk_ledger(n: int = 40) -> dict:
    sent = []
    settlements = []
    for i in range(n):
        key = f"risk-{i}"
        day = f"2026-10-{10 + (i % 4):02d}"
        league = str(100 + (i % 3))
        sent.append({
            "signal_key": key,
            "fixture_id": f"fx-{i}",
            "league_id": league,
            "kickoff": day + "T18:00:00+00:00",
            "paper_bet": {
                "status": "SETTLED",
                "stake_cop": 25_000.0,
                "bankroll_before_cop": 5_000_000.0,
                "kickoff_bogota_date": day,
            },
        })
        settlements.append({"signal_key": key, "won": (i % 3 != 0)})
    return {"sent": sent, "settlements": settlements}


def test_empirical_calibration_uses_settled_paper_rows_and_keeps_caps_conservative():
    cal = calibrate_correlated_risk_from_ledger(_risk_ledger())
    assert cal.status == "PASS_EMPIRICAL_CONCENTRATION_CALIBRATION"
    assert cal.sample_settled == 40
    assert cal.pair_count_same_league_day > 0
    assert 0.0 <= cal.observed_pair_agreement_rate <= 1.0
    assert 0.0 <= cal.agreement_wilson_upper95 <= 1.0
    assert cal.fixture_cap_fraction == 0.005
    assert 0.005 <= cal.tournament_day_cap_fraction <= 0.015
    assert 0.005 <= cal.day_cap_fraction <= 0.30
    proof = calibration_evidence(cal)
    assert proof["protections"]["p_matrix_modified"] is False
    assert proof["protections"]["real_money"] == "BLOCKED"


def test_correlated_gate_blocks_second_signal_same_fixture_before_telegram():
    limits = CorrelationLimits(
        max_fixture_fraction=0.005,
        max_tournament_day_fraction=0.015,
        max_day_fraction=0.30,
    )
    candidate = {
        "fixture_id": "fx-same",
        "league_id": "league-a",
        "kickoff": "2026-10-18T18:00:00+00:00",
    }
    existing = [ExposureRecord("fx-same", "league-a", "2026-10-18", 25_000.0)]
    state, detail, proposed = correlated_risk_gate_state(
        candidate,
        bankroll=5_000_000.0,
        limits=limits,
        existing=existing,
    )
    assert state == "BLOCKED_CORRELATED_EXPOSURE"
    assert "FIXTURE_CORRELATED_EXPOSURE_LIMIT" in detail["blocked_reasons"]
    assert proposed is None


def test_correlated_gate_passes_single_1u_signal_with_complete_identity():
    limits = CorrelationLimits(
        max_fixture_fraction=0.005,
        max_tournament_day_fraction=0.015,
        max_day_fraction=0.30,
    )
    state, detail, proposed = correlated_risk_gate_state(
        {
            "fixture_id": "fx-new",
            "league_id": "league-a",
            "kickoff": "2026-10-18T18:00:00+00:00",
        },
        bankroll=5_000_000.0,
        limits=limits,
        existing=[],
    )
    assert state == "PASS_CORRELATED_EXPOSURE_GATE"
    assert detail["allowed"] is True
    assert proposed is not None
    assert proposed.stake == 25_000.0

def test_physical_caps_preserve_single_flat_1u_after_bankroll_drawdown():
    calibration = {
        "caps": {
            "fixture_cap_cop": 25_000.0,
            "tournament_day_cap_cop": 75_000.0,
            "daily_cap_fraction": 0.13,
        }
    }
    limits = correlated_risk_limits_from_physical_calibration(
        calibration,
        bankroll=4_833_500.0,
    )
    state, detail, proposed = correlated_risk_gate_state(
        {
            "fixture_id": "fx-drawdown",
            "league_id": "league-a",
            "kickoff": "2026-10-18T18:00:00+00:00",
        },
        bankroll=4_833_500.0,
        limits=limits,
        existing=[],
    )
    assert state == "PASS_CORRELATED_EXPOSURE_GATE"
    assert detail["allowed"] is True
    assert proposed is not None
    assert proposed.stake == 25_000.0
    assert round(4_833_500.0 * limits.max_fixture_fraction, 6) == 25_000.0

