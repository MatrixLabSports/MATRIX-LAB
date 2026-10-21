from datetime import datetime, timezone
import json

from app.research.football.correlated_exposure import CorrelationLimits, ExposureRecord
from app.research.football.correlated_risk_calibration import (
    calibrate_correlated_risk_from_ledger,
    calibration_evidence,
)
from tools.telegram_green_signal_alerts import (
    _identity_similarity,
    blocker_recovery_profile,
    physical_book_over25_offer,
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



def test_identity_aliases_cover_fukushima_kitakyushu_revalidation():
    assert _identity_similarity("Fukushima United", "Fukushima Utd") == 1.0
    assert _identity_similarity("Kitakyushu", "Giravanz Kitakyushu") == 1.0


def test_empty_odds_provider_event_set_is_coverage_not_identity():
    profile = blocker_recovery_profile({
        "state": "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25",
        "odds_api_net_diagnostic": {
            "status": "BLOCKED_EVENT_NOT_COVERED",
            "identity_top_scores": [],
            "identity_top_candidates": [],
        },
    })
    assert profile["missing_or_failed_variable"] == "ODDS_PROVIDER_EVENT_COVERAGE"
    assert "Betano" in profile["sources_available_for_recovery"]
    assert profile["recoverability"] == "RECOVERABLE_WHILE_PREMATCH"


def test_physical_rushbet_quote_is_recovered_and_remains_negative_ev(tmp_path):
    day = tmp_path / "2026-10-21"
    day.mkdir()
    artifact = {
        "schema": "MATRIX_PHYSICAL_BOOK_QUOTE_V1",
        "fixture_id": "1555752",
        "captured_at_bogota": "2026-10-20T21:41:45-05:00",
        "kickoff_utc": "2026-10-21T04:00:00+00:00",
        "market": "Más de 2.5 goles",
        "house": "Rushbet",
        "decimal_odds": 1.53,
    }
    (day / "MATRIX_FUKUSHIMA_KITAKYUSHU_RUSHBET_QUOTE_214145_BOG.json").write_text(
        json.dumps(artifact),
        encoding="utf-8",
    )
    offer = physical_book_over25_offer(
        "1555752",
        0.6471259148,
        datetime(2026, 10, 21, 2, 42, 0, tzinfo=timezone.utc),
        root=tmp_path,
    )
    assert offer is not None
    assert offer["house"] == "Rushbet"
    assert offer["odds"] == 1.53
    assert offer["provider"] == "physical-browser-evidence"
    assert offer["ev"] < 0


def test_physical_quote_fails_closed_when_stale(tmp_path):
    day = tmp_path / "2026-10-21"
    day.mkdir()
    artifact = {
        "schema": "MATRIX_PHYSICAL_BOOK_QUOTE_V1",
        "fixture_id": "1555752",
        "captured_at_bogota": "2026-10-20T20:00:00-05:00",
        "kickoff_utc": "2026-10-21T04:00:00+00:00",
        "market": "Más de 2.5 goles",
        "house": "Rushbet",
        "decimal_odds": 1.53,
    }
    (day / "MATRIX_STALE_QUOTE.json").write_text(json.dumps(artifact), encoding="utf-8")
    offer = physical_book_over25_offer(
        "1555752",
        0.6471259148,
        datetime(2026, 10, 21, 2, 42, 0, tzinfo=timezone.utc),
        root=tmp_path,
    )
    assert offer is None


def test_physical_negative_ev_is_classified_as_positive_ev_gap():
    profile = blocker_recovery_profile({
        "state": "BLOCKED_NONPOSITIVE_EV",
        "offer": {
            "house": "Rushbet",
            "odds": 1.53,
            "ev": -0.009897350356,
            "provider": "physical-browser-evidence",
        },
        "physical_browser_offer": {
            "house": "Rushbet",
            "odds": 1.53,
            "ev": -0.009897350356,
            "provider": "physical-browser-evidence",
        },
        "odds_api_net_diagnostic": {"status": "BLOCKED_EVENT_NOT_COVERED"},
    })
    assert profile["missing_or_failed_variable"] == "POSITIVE_EXPECTED_VALUE"
    assert profile["recoverability"] == "RECOVERABLE_WITH_BETTER_AUTHORIZED_QUOTE_WHILE_PREMATCH"
    assert "Rushbet" in profile["sources_already_checked"]
    assert profile["final_disposition"] == "RETRY_BETTER_AUTHORIZED_QUOTE_UNTIL_KICKOFF"
