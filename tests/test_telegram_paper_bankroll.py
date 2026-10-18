from app.research.football.correlated_risk_calibration import calibrate_correlated_risk_from_ledger
# PHYSICAL_RECHECK_AVAILABLE_BANKROLL_20261010
from datetime import datetime, timezone

from tools.telegram_green_signal_alerts import (
    PAPER_BANKROLL_INITIAL_COP,
    PAPER_DAILY_BASE_EXPOSURE_FRACTION,
    PAPER_DAILY_MAX_EXPOSURE_FRACTION,
    PAPER_STAKE_MAX_LEVEL,
    PAPER_STAKE_RISK_OVERRIDE,
    PAPER_UNIT_COP,
    GREEN_PREMATCH_REVALIDATION_WINDOW_MINUTES,
    PAPER_MAX_SIGNALS_PER_LEAGUE_DAY,
    SIGNAL_QUALITY_MIN_P_MATRIX,
    SIGNAL_QUALITY_MIN_REVALIDATED_EV,
    signal_quality_gate_state,
    odds_api_net_exact_over25_offer,
    shadow_watch_candidate,
    paper_daily_cap_fraction,
    paper_daily_exposure_by_date,
    paper_stake_cop,
    paper_stake_level,
    prematch_revalidation_state,
    final_prematch_quote_state,
    paper_league_day_key,
    paper_league_concentration_blocked,
    correlated_risk_gate_state,
    recalc_paper_bankroll,
    green_message,
    paper_assignment_update_message,
    paper_bankroll_balance_correction_message,
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
    # Temporary 17-OCT risk override: preserve candidate quality inputs but cap
    # all paper exposure at 1u until the high-P/high-EV tail is recalibrated.
    assert paper_stake_level(candidate(0.66, 0.11)) == 1
    assert paper_stake_level(candidate(0.61, 0.06)) == 1
    assert paper_stake_level(candidate(0.59, 0.20)) == 1
    assert paper_stake_level(candidate(0.70, 0.03)) == 1


def test_risk_override_is_physically_active_and_persisted():
    assert PAPER_STAKE_MAX_LEVEL == 1
    assert PAPER_STAKE_RISK_OVERRIDE == "TEMPORARY_FLAT_1U_CAP_17OCT2026"
    ledger = {"sent": [], "settlements": []}
    pb = recalc_paper_bankroll(ledger)
    assert pb["stake_risk_override"]["status"] == "ACTIVE"
    assert pb["stake_risk_override"]["max_stake_level"] == 1
    assert pb["stake_risk_override"]["max_stake_cop"] == 25_000.0
    assert pb["confidence_policy"]["stake_2"] == "TEMPORARILY_DISABLED_BY_RISK_OVERRIDE"
    assert pb["confidence_policy"]["stake_3"] == "TEMPORARILY_DISABLED_BY_RISK_OVERRIDE"
    assert pb["effective_daily_cap_fraction_under_risk_override"] == 0.30


def test_daily_cap_uses_40_percent_only_for_high_conviction_day():
    high = [candidate(0.66, 0.11) for _ in range(5)] + [candidate(0.61, 0.06) for _ in range(5)]
    normal = [candidate(0.66, 0.11) for _ in range(4)] + [candidate(0.61, 0.06) for _ in range(6)]
    # Temporary 1u risk override disables the historical 40% high-conviction cap.
    assert paper_daily_cap_fraction(high) == 0.30
    assert paper_daily_cap_fraction(normal) == 0.30


def test_recalc_separates_realized_and_open_exposure():
    ledger = {
        "sent": [
            {"signal_key": "open-1", "paper_bet": {"status": "OPEN", "stake_cop": 50_000.0}},
            {
                "signal_key": "settled-1",
                "paper_bet": {
                    "status": "SETTLED",
                    "stake_cop": 75_000.0,
                    "profit_cop": 60_000.0,
                },
            },
        ],
        # The historical settlement entry may contain the same paper result.
        # recalc_paper_bankroll must not double count it.
        "settlements": [
            {
                "signal_key": "settled-1",
                "paper_stake_cop": 75_000.0,
                "paper_profit_cop": 60_000.0,
            },
        ],
    }
    pb = recalc_paper_bankroll(ledger)
    assert pb["current_cop"] == 5_060_000.0
    assert pb["open_exposure_cop"] == 50_000.0
    assert pb["available_after_open_exposure_cop"] == 5_010_000.0
    assert pb["max_open_exposure_cop"] == 2_024_000.0
    assert pb["daily_base_exposure_fraction"] == 0.30
    assert pb["daily_max_exposure_fraction"] == 0.40
    assert pb["settled_paper_bets"] == 1
    assert pb["realized_profit_cop"] == 60_000.0




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
    assert "Capital total de papel: COP 5.000.000" in msg
    assert "Bankroll disponible antes: COP" in msg
    assert "Bankroll disponible después: COP" in msg


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
    assert "Capital total de papel: COP 5.000.000" in msg
    assert "Exposición abierta de papel: COP 1.950.000 / COP 2.000.000" in msg
    assert "BANKROLL DISPONIBLE: COP" in msg



def test_bankroll_balance_correction_uses_available_after_open_exposure():
    pb = {
        "current_cop": 5_000_000.0,
        "open_exposure_cop": 1_950_000.0,
        "available_after_open_exposure_cop": 3_050_000.0,
        "open_bets": 50,
    }
    msg = paper_bankroll_balance_correction_message(pb)
    assert "Capital total de papel: COP 5.000.000" in msg
    assert "Exposición actualmente comprometida: COP 1.950.000" in msg
    assert "BANKROLL DISPONIBLE PARA NUEVAS SEÑALES: COP 3.050.000" in msg
    assert "Apuestas de papel abiertas: 50" in msg



def test_green_message_still_sends_when_paper_cap_blocks_assignment():
    c = {
        "match": "Cap Test FC vs Flow United",
        "market": "Más de 2.5 goles",
        "p_matrix": 0.62,
        "house": "Betano",
        "odds": 1.90,
        "ev": 0.09,
        "kickoff": "2026-10-10T16:00:00+00:00",
        "execution": None,
        "paper_bet": None,
        "paper_plan": {
            "stake_level": 2,
            "stake_cop": 50_000.0,
            "available_now_cop": 3_050_000.0,
            "assignment_status": "NO_ASIGNADO_LIMITE_EXPOSICION",
            "reason": "DAILY_EXPOSURE_CAP_REACHED",
        },
    }
    msg = green_message(c)
    assert "SEÑAL VERDE SIMULADA" in msg
    assert "Stake MATRIX recomendado: STAKE 2" in msg
    assert "Monto recomendado de papel: COP 50.000" in msg
    assert "Bankroll disponible: COP 3.050.000" in msg
    assert "NO ASIGNADA — límite de exposición alcanzado" in msg


def test_reconciliation_adjustment_and_cancelled_exposure_are_governed():
    ledger = {
        "paper_bankroll_adjustments": [
            {
                "adjustment_id": "TEST_CLOSE_CORRECTION",
                "status": "APPLIED",
                "amount_cop": 57_750.0,
            }
        ],
        "sent": [
            {
                "signal_key": "open",
                "kickoff": "2026-10-13T23:00:00+00:00",
                "paper_bet": {"status": "OPEN", "stake_cop": 25_000.0},
            },
            {
                "signal_key": "settled",
                "kickoff": "2026-10-13T18:00:00+00:00",
                "paper_bet": {
                    "status": "SETTLED",
                    "stake_cop": 50_000.0,
                    "profit_cop": 30_000.0,
                },
            },
            {
                "signal_key": "cancelled",
                "kickoff": "2026-10-13T17:00:00+00:00",
                "paper_bet": {"status": "CANCELLED_NO_BET", "stake_cop": 75_000.0},
            },
            {
                "signal_key": "void",
                "kickoff": "2026-10-13T16:00:00+00:00",
                "paper_bet": {"status": "VOID_POSTPONED", "stake_cop": 25_000.0},
            },
        ],
        "settlements": [],
    }
    pb = recalc_paper_bankroll(ledger)
    assert pb["reconciliation_adjustment_cop"] == 57_750.0
    assert pb["current_cop"] == 5_087_750.0
    assert pb["open_exposure_cop"] == 25_000.0
    assert pb["available_after_open_exposure_cop"] == 5_062_750.0
    assert paper_daily_exposure_by_date(ledger)["2026-10-13"] == 75_000.0


def test_final_prematch_revalidation_window_is_120_minutes():
    now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    assert GREEN_PREMATCH_REVALIDATION_WINDOW_MINUTES == 120
    assert prematch_revalidation_state(
        {"kickoff": "2026-10-15T14:00:00+00:00"}, now
    ) == "READY_FOR_FINAL_REVALIDATION"
    assert prematch_revalidation_state(
        {"kickoff": "2026-10-15T14:00:01+00:00"}, now
    ) == "WAITING_FINAL_REVALIDATION_WINDOW"
    assert prematch_revalidation_state(
        {"kickoff": "2026-10-15T12:00:00+00:00"}, now
    ) == "BLOCKED_KICKOFF_REACHED"


def test_league_day_concentration_policy_is_three():
    assert PAPER_MAX_SIGNALS_PER_LEAGUE_DAY == 3
    c = {
        "league_id": "848",
        "kickoff": "2026-10-15T16:45:00+00:00",
    }
    assert paper_league_day_key(c) == ("2026-10-15", "848")
    assert paper_league_day_key({"kickoff": c["kickoff"]}) is None


def test_final_prematch_quote_state_blocks_missing_or_nonpositive_ev():
    assert final_prematch_quote_state(None) == "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25"
    assert final_prematch_quote_state({"ev": 0.0}) == "BLOCKED_NONPOSITIVE_EV"
    assert final_prematch_quote_state({"ev": -0.01}) == "BLOCKED_NONPOSITIVE_EV"
    assert final_prematch_quote_state({"ev": 0.01}) == "PASS_FINAL_PREMATCH_REVALIDATION"


def test_league_concentration_blocks_fourth_signal_same_day():
    assert paper_league_concentration_blocked(0) is False
    assert paper_league_concentration_blocked(2) is False
    assert paper_league_concentration_blocked(3) is True
    assert paper_league_concentration_blocked(4) is True


def test_precision_quality_gate_requires_p60_and_ev5():
    assert SIGNAL_QUALITY_MIN_P_MATRIX == 0.60
    assert SIGNAL_QUALITY_MIN_REVALIDATED_EV == 0.05
    assert signal_quality_gate_state(
        {"p_matrix": 0.5999},
        {"ev": 0.20},
    ) == "BLOCKED_QUALITY_P_MATRIX_BELOW_60PCT"
    assert signal_quality_gate_state(
        {"p_matrix": 0.61},
        {"ev": 0.0499},
    ) == "BLOCKED_QUALITY_REVALIDATED_EV_BELOW_5PCT"
    assert signal_quality_gate_state(
        {"p_matrix": 0.60},
        {"ev": 0.05},
    ) == "PASS_API_COST_RECOVERY_PRECISION_GATE"


class _QuoteResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
    def json(self):
        return self._payload


class _MultiBookSession:
    def get(self, url, headers=None, params=None, timeout=None):
        if url.endswith("/fixtures"):
            return _QuoteResponse({
                "response": [{
                    "teams": {
                        "home": {"name": "Alpha FC"},
                        "away": {"name": "Beta United"},
                    }
                }]
            })
        if url.endswith("/events"):
            return _QuoteResponse({
                "items": [{
                    "event_id": "oa-1",
                    "home_team": "Alpha FC",
                    "away_team": "Beta United",
                }]
            })
        if "/odds/snapshot" in url:
            return _QuoteResponse({
                "bookmaker_as_of_ts_ms": {
                    "betplay": 1792140000000,
                    "rushbet": 1792140000000,
                },
                "items": [
                    {
                        "bookmaker": "betplay",
                        "market_key": "total_goals",
                        "bet_type": "total",
                        "period": "full time",
                        "line": 2.5,
                        "side": "over",
                        "odds": 1.75,
                        "is_available": True,
                    },
                    {
                        "bookmaker": "rushbet",
                        "market_key": "total_goals",
                        "bet_type": "total",
                        "period": "full time",
                        "line": 2.5,
                        "side": "over",
                        "odds": 1.80,
                        "is_available": True,
                    },
                ],
            })
        raise AssertionError(url)


def test_odds_api_net_fallback_selects_best_authorized_colombia_book():
    offer = odds_api_net_exact_over25_offer(
        _MultiBookSession(),
        "secret",
        "fixture-1",
        "2026-10-16T18:00:00+00:00",
        0.61,
        "api-football-secret",
    )
    assert offer is not None
    assert offer["house_key"] == "rushbet"
    assert offer["house"] == "Rushbet"
    assert offer["odds"] == 1.80
    assert round(offer["ev"], 3) == 0.098
    assert offer["provider"] == "odds-api.net"
    assert offer["fallback_multi_book"] is True


class _SingleBookSession:
    def __init__(self, house_key, odds):
        self.house_key = house_key
        self.odds = odds
    def get(self, url, headers=None, params=None, timeout=None):
        if url.endswith("/fixtures"):
            return _QuoteResponse({
                "response": [{
                    "teams": {
                        "home": {"name": "Gamma FC"},
                        "away": {"name": "Delta United"},
                    }
                }]
            })
        if url.endswith("/events"):
            return _QuoteResponse({
                "items": [{
                    "event_id": "oa-single",
                    "home_team": "Gamma FC",
                    "away_team": "Delta United",
                }]
            })
        if "/odds/snapshot" in url:
            return _QuoteResponse({
                "bookmaker_as_of_ts_ms": {self.house_key: 1792140000000},
                "items": [{
                    "bookmaker": self.house_key,
                    "market_key": "total_goals",
                    "bet_type": "total",
                    "period": "full time",
                    "line": 2.5,
                    "side": "over",
                    "odds": self.odds,
                    "is_available": True,
                }],
            })
        raise AssertionError(url)


def test_multibook_gate_accepts_betplay_when_other_two_are_absent():
    offer = odds_api_net_exact_over25_offer(
        _SingleBookSession("betplay", 1.82),
        "secret",
        "fixture-betplay",
        "2026-10-16T18:00:00+00:00",
        0.62,
        "api-football-secret",
    )
    assert offer is not None
    assert offer["house_key"] == "betplay"
    assert offer["house"] == "BetPlay"
    assert round(offer["ev"], 4) == 0.1284


def test_multibook_gate_accepts_rushbet_when_other_two_are_absent():
    offer = odds_api_net_exact_over25_offer(
        _SingleBookSession("rushbet", 1.77),
        "secret",
        "fixture-rushbet",
        "2026-10-16T18:00:00+00:00",
        0.63,
        "api-football-secret",
    )
    assert offer is not None
    assert offer["house_key"] == "rushbet"
    assert offer["house"] == "Rushbet"
    assert round(offer["ev"], 4) == 0.1151


def test_odds_api_parser_accepts_current_period_str_and_string_line_contract():
    class Session:
        def get(self, url, headers=None, params=None, timeout=None):
            if url.endswith("/fixtures"):
                return _QuoteResponse({"response":[{"teams":{"home":{"name":"Alpha FC"},"away":{"name":"Beta United"}}}]})
            if url.endswith("/events"):
                return _QuoteResponse({"items":[{"event_id":"oa-contract","home_team":"Alpha FC","away_team":"Beta United"}]})
            if "/odds/snapshot" in url:
                return _QuoteResponse({
                    "bookmaker_as_of_ts_ms":{"betplay":1792140000000},
                    "items":[{
                        "bookmaker":"betplay",
                        "market_key":"match total goals",
                        "bet_type":"total",
                        "metric":"goals",
                        "period_str":"full time",
                        "line":"2.5",
                        "side":"over",
                        "selection_name":"Over 2.5",
                        "odds":1.84,
                        "is_available":True
                    }]
                })
            raise AssertionError(url)

    offer = odds_api_net_exact_over25_offer(
        Session(),
        "secret",
        "fixture-contract",
        "2026-10-16T18:00:00+00:00",
        0.62,
        "api-football-secret",
    )
    assert offer is not None
    assert offer["house_key"] == "betplay"
    assert offer["odds"] == 1.84


def test_shadow_watch_candidate_promotes_quality_eligible_p_matrix_without_initial_odds():
    row={
        "fixture_id":"future-1",
        "match":"Alpha vs Beta",
        "league_id":"999",
        "kickoff_utc":"2026-10-16T23:00:00+00:00",
        "p_over_2_5":0.64,
        "decision":"BLOCKED",
        "best_policy_offer":None,
    }
    c=shadow_watch_candidate(row, __import__("pathlib").Path("report.json"))
    assert c is not None
    assert c["watch_candidate"] is True
    assert c["eligible_green"] is True
    assert c["p_matrix"] == 0.64
    assert c["odds"] is None
    assert c["ev"] is None
    assert c["physical_quote_verified"] is False
    assert c["house"] == "MULTIBOOK_REVALIDATION"


def test_shadow_watch_candidate_rejects_p_matrix_below_quality_floor():
    row={
        "fixture_id":"future-2",
        "match":"Gamma vs Delta",
        "league_id":"999",
        "kickoff_utc":"2026-10-16T23:00:00+00:00",
        "p_over_2_5":0.5999,
        "best_policy_offer":None,
    }
    assert shadow_watch_candidate(row, __import__("pathlib").Path("report.json")) is None


def test_empirical_correlated_risk_calibration_uses_physical_ledger():
    from app.research.football.correlated_exposure import calibrate_paper_correlated_exposure

    ledger = {
        "sent": [
            {"fixture_id": "fx1", "league_id": "L1", "paper_bet": {"status": "SETTLED", "stake_cop": 25000, "kickoff_bogota_date": "2026-10-17"}},
            {"fixture_id": "fx2", "league_id": "L1", "paper_bet": {"status": "SETTLED", "stake_cop": 25000, "kickoff_bogota_date": "2026-10-17"}},
            {"fixture_id": "fx3", "league_id": "L1", "paper_bet": {"status": "SETTLED", "stake_cop": 25000, "kickoff_bogota_date": "2026-10-17"}},
            {"fixture_id": "fx4", "league_id": "L2", "paper_bet": {"status": "SETTLED", "stake_cop": 25000, "kickoff_bogota_date": "2026-10-17"}},
        ]
    }
    out = calibrate_paper_correlated_exposure(
        ledger,
        initial_bankroll_cop=5_000_000,
        unit_cop=25_000,
        max_signals_per_tournament_day=3,
        daily_policy_cap_fraction=0.30,
    )
    assert out["status"] == "READY_FAIL_CLOSED"
    assert out["sample_records"] == 4
    assert out["observed_maxima_cop"]["same_tournament_day"] == 75_000
    assert out["caps"]["fixture_cap_cop"] == 25_000
    assert out["caps"]["tournament_day_cap_cop"] == 75_000
    assert out["pairwise_cross_market_correlation"]["calibrated"] is False
    assert out["h02_closed"] is False


def test_correlated_risk_gate_blocks_second_same_fixture_before_telegram():
    from app.research.football.correlated_exposure import (
        assess_paper_correlated_exposure,
        calibrate_paper_correlated_exposure,
    )
    ledger = {
        "sent": [
            {"fixture_id": "fx1", "league_id": "L1", "paper_bet": {"status": "OPEN", "stake_cop": 25000, "kickoff_bogota_date": "2026-10-18"}}
        ]
    }
    calibration = calibrate_paper_correlated_exposure(
        ledger,
        initial_bankroll_cop=5_000_000,
        unit_cop=25_000,
        max_signals_per_tournament_day=3,
        daily_policy_cap_fraction=0.30,
    )
    decision = assess_paper_correlated_exposure(
        ledger,
        {"fixture_id": "fx1", "tournament_key": "L1", "operational_date": "2026-10-18", "stake_cop": 25_000},
        calibration=calibration,
        bankroll_cop=4_833_500,
    )
    assert decision["allowed"] is False
    assert "FIXTURE_CORRELATED_EXPOSURE_LIMIT" in decision["blocked_reasons"]
    assert decision["real_money"] == "BLOCKED"


def test_correlated_risk_gate_fails_closed_on_missing_tournament_identity():
    from app.research.football.correlated_exposure import (
        assess_paper_correlated_exposure,
        calibrate_paper_correlated_exposure,
    )
    ledger = {
        "sent": [
            {"fixture_id": "fx0", "league_id": "L0", "paper_bet": {"status": "SETTLED", "stake_cop": 25000, "kickoff_bogota_date": "2026-10-17"}}
        ]
    }
    calibration = calibrate_paper_correlated_exposure(
        ledger,
        initial_bankroll_cop=5_000_000,
        unit_cop=25_000,
        max_signals_per_tournament_day=3,
        daily_policy_cap_fraction=0.30,
    )
    decision = assess_paper_correlated_exposure(
        ledger,
        {"fixture_id": "fx2", "tournament_key": "", "operational_date": "2026-10-18", "stake_cop": 25_000},
        calibration=calibration,
        bankroll_cop=4_833_500,
    )
    assert decision["allowed"] is False
    assert decision["status"] == "BLOCKED_CORRELATED_RISK_METADATA_MISSING"


def _risk_calibration_ledger(n: int = 40) -> dict:
    sent=[]; settlements=[]
    for i in range(n):
        day=f"2026-10-{10 + (i % 4):02d}"
        key=f"risk-{i}"
        sent.append({
            "signal_key":key,
            "fixture_id":f"fx-{i}",
            "league_id":f"league-{i % 3}",
            "kickoff":f"{day}T18:00:00+00:00",
            "paper_bet":{
                "status":"SETTLED",
                "stake_cop":25000.0,
                "bankroll_before_cop":5000000.0,
                "kickoff_bogota_date":day,
            },
        })
        settlements.append({"signal_key":key,"won": bool(i % 2)})
    return {"sent":sent,"settlements":settlements}


def test_empirical_correlated_risk_calibration_requires_real_sample_and_caps_history():
    blocked=calibrate_correlated_risk_from_ledger({"sent":[],"settlements":[]})
    assert blocked.status == "BLOCKED_INSUFFICIENT_REAL_SETTLED_SAMPLE"
    ledger=_risk_calibration_ledger()
    cal=calibrate_correlated_risk_from_ledger(ledger)
    assert cal.status == "PASS_EMPIRICAL_CONCENTRATION_CALIBRATION"
    assert cal.sample_settled == 40
    assert cal.fixture_cap_fraction == 0.005
    assert 0.005 <= cal.tournament_day_cap_fraction <= 0.015
    assert 0.005 <= cal.day_cap_fraction <= 0.30
    assert cal.pair_count_same_league_day > 0
    assert cal.agreement_wilson_upper95 is not None


def test_correlated_risk_gate_blocks_second_signal_same_fixture_before_telegram():
    ledger=_risk_calibration_ledger()
    cal=calibrate_correlated_risk_from_ledger(ledger)
    ledger["sent"].append({
        "signal_key":"open-same-fixture",
        "fixture_id":"future-fx",
        "league_id":"future-league",
        "kickoff":"2026-10-18T18:00:00+00:00",
        "paper_bet":{
            "status":"OPEN",
            "stake_cop":25000.0,
            "bankroll_before_cop":5000000.0,
            "kickoff_bogota_date":"2026-10-18",
        },
    })
    state, detail=correlated_risk_gate_state(
        ledger,
        {
            "fixture_id":"future-fx",
            "league_id":"future-league",
            "kickoff":"2026-10-18T18:30:00+00:00",
        },
        bankroll=5000000.0,
        calibration=cal,
    )
    assert state == "BLOCKED_CORRELATED_EXPOSURE"
    assert "FIXTURE_CORRELATED_EXPOSURE_LIMIT" in detail["blocked_reasons"]


def test_correlated_risk_gate_fails_closed_without_calibration():
    cal=calibrate_correlated_risk_from_ledger({"sent":[],"settlements":[]})
    state, detail=correlated_risk_gate_state(
        {},
        {"fixture_id":"fx-new","league_id":"league-new","kickoff":"2026-10-18T18:00:00+00:00"},
        bankroll=5000000.0,
        calibration=cal,
    )
    assert state == "BLOCKED_CORRELATED_RISK_CALIBRATION_NOT_READY"
    assert detail["real_money"] == "BLOCKED"
