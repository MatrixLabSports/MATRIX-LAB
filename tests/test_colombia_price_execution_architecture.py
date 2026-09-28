from datetime import datetime, timedelta, timezone
import json

import pytest

from app.market.colombia_bookmakers import classify_bookmaker
from app.market.price_execution import (
    CanonicalOddsQuote,
    ModelProbability,
    StakePolicy,
    assess_quote,
    calculate_stake,
    select_best_price,
)
from app.market.price_freeze_ledger import PriceFreezeLedger, build_price_freeze
from app.providers.odds_api_net_adapter import adapt_odds_api_net_snapshot

UTC = timezone.utc
NOW = datetime(2026, 9, 28, 16, 0, tzinfo=UTC)
START = NOW + timedelta(hours=2)


def probability(**overrides):
    data = dict(
        sport="tennis",
        event_id="mx-1",
        market_key="games_total",
        bet_type="total",
        period="match",
        selection_key="games_total:over:22.5",
        side="over",
        probability=0.58,
        generated_at=NOW - timedelta(minutes=5),
        model_binding="MATRIX_TEST_MODEL_V1",
        source_sha256="a" * 64,
        metric="games",
        line=22.5,
    )
    data.update(overrides)
    return ModelProbability(**data)


def quote(bookmaker="betplay", odds=1.90, **overrides):
    data = dict(
        provider="odds_api_net",
        provider_event_id="provider-1",
        sport="tennis",
        event_id="mx-1",
        bookmaker=bookmaker,
        market_key="games_total",
        bet_type="total",
        period="match",
        metric="games",
        line=22.5,
        side="over",
        selection_key="games_total:over:22.5",
        decimal_odds=odds,
        is_available=True,
        quoted_at=NOW - timedelta(seconds=20),
        captured_at=NOW - timedelta(seconds=18),
        event_start_at=START,
        source_payload_sha256="b" * 64,
        source_reference="test:snapshot",
    )
    data.update(overrides)
    return CanonicalOddsQuote(**data)


def test_colombia_execution_and_reference_roles_are_separate():
    assert classify_bookmaker("betplay").execution_eligible is True
    assert classify_bookmaker("stakeco").matrix_key == "stake"
    assert classify_bookmaker("pinnacle").role == "REFERENCE_ONLY"
    assert classify_bookmaker("pinnacle").execution_eligible is False
    assert classify_bookmaker("unibet").role == "QUARANTINED"


def test_probability_forbids_odds_to_p_matrix():
    with pytest.raises(ValueError, match="ODDS_TO_P_MATRIX_FORBIDDEN"):
        probability(odds_used_as_input=True)


def test_best_price_selects_highest_equivalent_execution_quote():
    decision = select_best_price(
        probability(),
        [quote("betplay", 1.91), quote("rushbet", 1.95), quote("betano", 1.93)],
        now=NOW,
    )
    assert decision.status == "PRICE_CANDIDATE"
    assert decision.quote is not None
    assert decision.quote.bookmaker == "rushbet"
    assert decision.quote.decimal_odds == pytest.approx(1.95)
    assert decision.expected_value == pytest.approx(0.58 * 1.95 - 1.0)
    assert decision.accepted_quotes == 3


def test_different_line_never_competes_with_probability_line():
    different = quote(
        bookmaker="betano",
        odds=2.20,
        line=23.5,
        selection_key="games_total:over:23.5",
    )
    decision = select_best_price(probability(), [quote("betplay", 1.91), different], now=NOW)
    assert decision.quote is not None
    assert decision.quote.bookmaker == "betplay"
    assert decision.compared_quotes == 1


def test_reference_only_pinnacle_cannot_be_selected_for_colombia_execution():
    decision = select_best_price(
        probability(),
        [quote("pinnacle", 2.20), quote("betplay", 1.91)],
        now=NOW,
    )
    assert decision.quote is not None
    assert decision.quote.bookmaker == "betplay"
    assert decision.accepted_quotes == 1


def test_stale_unavailable_and_odds_at_or_below_150_are_rejected():
    decision = select_best_price(
        probability(),
        [
            quote("betplay", 1.50),
            quote("rushbet", 2.10, quoted_at=NOW - timedelta(minutes=10), captured_at=NOW - timedelta(minutes=10)),
            quote("betano", 2.00, is_available=False),
        ],
        now=NOW,
    )
    assert decision.status == "NO_BET"
    assert "ODDS_NOT_ABOVE_MINIMUM" in decision.rejection_reasons
    assert "QUOTE_STALE" in decision.rejection_reasons
    assert "SELECTION_UNAVAILABLE" in decision.rejection_reasons


def test_stake_is_blocked_until_calibration_and_real_money_gates_pass():
    price = select_best_price(probability(), [quote("rushbet", 2.00)], now=NOW)
    blocked = calculate_stake(
        price,
        bankroll=100000,
        calibration_gate_pass=False,
        real_money_gate_open=False,
    )
    assert blocked.status == "NO_BET"
    assert blocked.amount == 0
    assert "CALIBRATION_GATE_NOT_PASS" in blocked.reasons
    assert "REAL_MONEY_BLOCKED" in blocked.reasons


def test_stake_uses_fractional_kelly_and_cap_after_gates_pass():
    price = select_best_price(probability(probability=0.60), [quote("rushbet", 2.00)], now=NOW)
    stake = calculate_stake(
        price,
        bankroll=100000,
        calibration_gate_pass=True,
        real_money_gate_open=True,
        policy=StakePolicy(fractional_kelly=0.25, max_bankroll_fraction=0.02, min_bankroll_fraction=0.0025),
    )
    assert stake.status == "BET_CANDIDATE"
    assert stake.full_kelly_fraction == pytest.approx(0.20)
    assert stake.fractional_kelly_fraction == pytest.approx(0.05)
    assert stake.bankroll_fraction == pytest.approx(0.02)
    assert stake.amount == pytest.approx(2000)


def test_odds_api_net_adapter_preserves_exact_line_and_bookmaker_freshness():
    snapshot = {
        "event_id": "provider-1",
        "as_of_ts_ms": int((NOW - timedelta(seconds=10)).timestamp() * 1000),
        "bookmaker_as_of_ts_ms": {
            "betplay": int((NOW - timedelta(seconds=12)).timestamp() * 1000),
            "rushbet": int((NOW - timedelta(seconds=8)).timestamp() * 1000),
        },
        "items": [
            {
                "bookmaker": "betplay",
                "market_key": "games_total",
                "bet_type": "total",
                "metric": "games",
                "period": "match",
                "line": 22.5,
                "side": "over",
                "selection_key": "games_total:over:22.5",
                "odds": 1.91,
                "is_available": True,
            },
            {
                "bookmaker": "rushbet",
                "market_key": "games_total",
                "bet_type": "total",
                "metric": "games",
                "period": "match",
                "line": 22.5,
                "side": "over",
                "selection_key": "games_total:over:22.5",
                "odds": 1.95,
                "is_available": True,
            },
        ],
        "complete": True,
        "next_cursor": None,
        "resume": "x-1",
    }
    quotes, meta = adapt_odds_api_net_snapshot(
        snapshot,
        sport="tennis",
        matrix_event_id="mx-1",
        event_start_at=START,
        captured_at=NOW,
    )
    assert len(quotes) == 2
    assert quotes[0].comparison_key == quotes[1].comparison_key
    assert quotes[0].freshness_basis == "BOOKMAKER_AS_OF"
    assert meta["adapted_quotes"] == 2
    assert meta["provider_selection_keys"] == 2
    assert meta["odds_used_to_generate_model_probability"] is False


def test_adapter_uses_explicitly_labeled_snapshot_fallback_when_book_timestamp_missing():
    snapshot = {
        "event_id": "provider-1",
        "as_of_ts_ms": int((NOW - timedelta(seconds=10)).timestamp() * 1000),
        "items": [{
            "bookmaker": "betplay",
            "market_key": "moneyline",
            "bet_type": "moneyline",
            "period": "full time",
            "side": "home",
            "selection_name": "Home",
            "odds": 1.91,
            "is_available": True,
        }],
    }
    quotes, meta = adapt_odds_api_net_snapshot(
        snapshot,
        sport="football",
        matrix_event_id="fx-1",
        event_start_at=START,
        captured_at=NOW,
    )
    assert len(quotes) == 1
    assert quotes[0].freshness_basis == "SNAPSHOT_AS_OF_FALLBACK"
    assert quotes[0].selection_key.startswith("matrix-local:")
    assert meta["local_selection_keys"] == 1
    assert meta["local_selection_key_history_eligible"] is False


def test_controlled_live_freeze_requires_open_gate_and_is_append_only(tmp_path):
    p = probability(probability=0.60)
    price = select_best_price(p, [quote("rushbet", 2.00)], now=NOW)
    stake = calculate_stake(
        price,
        bankroll=100000,
        calibration_gate_pass=True,
        real_money_gate_open=True,
    )
    freeze = build_price_freeze(
        p,
        price,
        stake,
        frozen_at=NOW,
        event_start_at=START,
        mode="CONTROLLED_LIVE",
        real_money_gate_open=True,
    )
    ledger = PriceFreezeLedger(tmp_path / "freezes.jsonl")
    entry = ledger.append(freeze)
    assert entry.sequence == 1
    assert len(ledger.load()) == 1
    with pytest.raises(ValueError, match="DUPLICATE"):
        ledger.append(freeze)


def test_controlled_live_freeze_fails_closed_when_money_gate_is_blocked():
    p = probability(probability=0.60)
    price = select_best_price(p, [quote("rushbet", 2.00)], now=NOW)
    stake = calculate_stake(
        price,
        bankroll=100000,
        calibration_gate_pass=True,
        real_money_gate_open=False,
    )
    with pytest.raises(ValueError):
        build_price_freeze(
            p,
            price,
            stake,
            frozen_at=NOW,
            event_start_at=START,
            mode="CONTROLLED_LIVE",
            real_money_gate_open=False,
        )


def test_stake_is_shrunk_by_calibration_reliability_and_risk():
    price = select_best_price(probability(probability=0.60), [quote("rushbet", 2.00)], now=NOW)
    stake = calculate_stake(
        price,
        bankroll=100000,
        calibration_gate_pass=True,
        real_money_gate_open=True,
        calibration_reliability=0.50,
        risk_multiplier=0.50,
        policy=StakePolicy(
            fractional_kelly=0.25,
            max_bankroll_fraction=0.02,
            min_bankroll_fraction=0.0025,
        ),
    )
    # Full Kelly 20%; quarter Kelly 5%; calibration/risk shrink => 1.25%.
    assert stake.status == "BET_CANDIDATE"
    assert stake.bankroll_fraction == pytest.approx(0.0125)
    assert stake.amount == pytest.approx(1250)
