from datetime import datetime,timedelta,timezone
import pytest

from matrix_elite.odds import OddsSnapshot
from matrix_elite.market_history import MarketLineHistory, market_snapshot_sha256, probability_clv, fair_odds_clv_ratio

UTC=timezone.utc
T0=datetime(2026,1,1,tzinfo=UTC)

def market(provider,at,odds=(1.91,1.91),event='e',live=False):
    return [
        OddsSnapshot(event,'BTTS','YES',provider,at,odds[0],live),
        OddsSnapshot(event,'BTTS','NO',provider,at,odds[1],live),
    ]


def test_complete_snapshot_requires_exact_selection_set():
    h=MarketLineHistory()
    with pytest.raises(ValueError,match="SELECTION_SET_MISMATCH"):
        h.add_complete_snapshot(market('book',T0),expected_selection_ids={'YES','NO','VOID'})


def test_market_snapshot_hash_is_order_independent():
    rows=market('book',T0)
    assert market_snapshot_sha256(rows)==market_snapshot_sha256(list(reversed(rows)))


def test_conflicting_same_timestamp_snapshot_is_rejected():
    h=MarketLineHistory();h.add_complete_snapshot(market('book',T0),expected_selection_ids={'YES','NO'})
    with pytest.raises(ValueError,match="CONFLICTING"):
        h.add_complete_snapshot(market('book',T0,(2.0,1.8)),expected_selection_ids={'YES','NO'})


def test_decision_state_selects_best_valid_nonstale_price_across_books():
    h=MarketLineHistory()
    h.add_complete_snapshot(market('a',T0,(2.0,1.8)),expected_selection_ids={'YES','NO'})
    h.add_complete_snapshot(market('b',T0+timedelta(seconds=10),(2.1,1.75)),expected_selection_ids={'YES','NO'})
    d=h.decision_state(event_id='e',market_id='BTTS',selection_id='YES',decision_at=T0+timedelta(seconds=20),model_probability=.55,max_quote_age=timedelta(minutes=1),is_live=False)
    assert d.provider=='b' and d.decimal_odds==2.1 and d.expected_value>0 and len(d.quote_sha256)==64


def test_decision_state_rejects_all_stale_quotes():
    h=MarketLineHistory();h.add_complete_snapshot(market('a',T0),expected_selection_ids={'YES','NO'})
    with pytest.raises(ValueError,match="NO_VALID_NONSTALE_PRICE"):
        h.decision_state(event_id='e',market_id='BTTS',selection_id='YES',decision_at=T0+timedelta(minutes=2),model_probability=.55,max_quote_age=timedelta(seconds=30),is_live=False)


def test_decision_state_never_uses_quote_captured_after_decision():
    h=MarketLineHistory();h.add_complete_snapshot(market('a',T0),expected_selection_ids={'YES','NO'});h.add_complete_snapshot(market('b',T0+timedelta(minutes=2),(3.0,1.2)),expected_selection_ids={'YES','NO'})
    d=h.decision_state(event_id='e',market_id='BTTS',selection_id='YES',decision_at=T0+timedelta(minutes=1),model_probability=.55,max_quote_age=timedelta(minutes=2),is_live=False)
    assert d.provider=='a'


def test_prematch_closing_line_uses_last_prematch_not_live_or_post_start():
    h=MarketLineHistory();start=T0+timedelta(hours=1)
    h.add_complete_snapshot(market('a',start-timedelta(minutes=10),(2.0,1.8)),expected_selection_ids={'YES','NO'})
    h.add_complete_snapshot(market('a',start-timedelta(minutes=1),(1.9,1.9)),expected_selection_ids={'YES','NO'})
    h.add_complete_snapshot(market('a',start+timedelta(minutes=1),(1.5,2.5),live=True),expected_selection_ids={'YES','NO'})
    close=h.prematch_closing_line(event_id='e',market_id='BTTS',selection_id='YES',event_start_at=start,max_close_age=timedelta(minutes=15))
    assert close.providers_used==1 and close.latest_provider_capture_at==start-timedelta(minutes=1)


def test_closing_consensus_uses_multiple_recent_providers_and_excludes_old():
    h=MarketLineHistory();start=T0+timedelta(hours=1)
    h.add_complete_snapshot(market('a',start-timedelta(minutes=1),(2.0,1.8)),expected_selection_ids={'YES','NO'})
    h.add_complete_snapshot(market('b',start-timedelta(minutes=2),(2.1,1.75)),expected_selection_ids={'YES','NO'})
    h.add_complete_snapshot(market('old',start-timedelta(hours=2),(5.0,1.1)),expected_selection_ids={'YES','NO'})
    close=h.prematch_closing_line(event_id='e',market_id='BTTS',selection_id='YES',event_start_at=start,max_close_age=timedelta(minutes=10))
    assert close.providers_used==2 and {p for p,_ in close.provider_probabilities}=={'a','b'}


def test_clv_metrics_are_bound_to_fair_closing_probability():
    h=MarketLineHistory();start=T0+timedelta(hours=1)
    h.add_complete_snapshot(market('a',start-timedelta(minutes=1),(1.8,2.0)),expected_selection_ids={'YES','NO'})
    close=h.prematch_closing_line(event_id='e',market_id='BTTS',selection_id='YES',event_start_at=start,max_close_age=timedelta(minutes=5))
    assert probability_clv(taken_decimal_odds=2.0,closing=close)>0
    assert fair_odds_clv_ratio(taken_decimal_odds=2.0,closing=close)>0


def test_closing_line_fails_without_recent_prematch_snapshot():
    h=MarketLineHistory();start=T0+timedelta(hours=1)
    h.add_complete_snapshot(market('a',start-timedelta(hours=2)),expected_selection_ids={'YES','NO'})
    with pytest.raises(ValueError,match="NO_VALID_PREMATCH_CLOSING_LINE"):
        h.prematch_closing_line(event_id='e',market_id='BTTS',selection_id='YES',event_start_at=start,max_close_age=timedelta(minutes=5))
