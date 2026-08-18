import pytest

from app.research.football.paper_trading import (
    OddsSnapshot,
    PaperTradeObservation,
    summarize_paper_trading,
)


def _odds(**changes):
    payload = dict(
        fixture_id="fx-1",
        market_key="over_2_5",
        selection_key="over",
        source_provider="licensed_feed",
        source_reference="provider://fixture/fx-1",
        observed_at_utc="2026-08-18T17:00:00+00:00",
        fixture_kickoff_utc="2026-08-18T19:00:00+00:00",
        decimal_odds=2.0,
        source_authorized=True,
    )
    payload.update(changes)
    return OddsSnapshot(**payload)


def _trade(index=1, *, outcome=True, odds=2.0, probability=0.60, fixture_id=None):
    snapshot = _odds(fixture_id=fixture_id or f"fx-{index}", decimal_odds=odds)
    return PaperTradeObservation(
        decision_id=f"d-{index}",
        fixture_id=snapshot.fixture_id,
        market_key=snapshot.market_key,
        selection_key=snapshot.selection_key,
        model_version="football-over25-v1",
        model_probability=probability,
        decision_at_utc=snapshot.observed_at_utc,
        odds_snapshot_sha256=snapshot.canonical_sha256(),
        decimal_odds=snapshot.decimal_odds,
        outcome=outcome,
        settled_at_utc="2026-08-18T21:00:00+00:00" if outcome is not None else None,
    )


def test_prematch_odds_require_strict_temporal_order():
    with pytest.raises(ValueError, match="strictly before kickoff"):
        _odds(observed_at_utc="2026-08-18T19:00:00+00:00")


def test_odds_snapshot_is_hashable_and_exposes_implied_probability():
    value = _odds(decimal_odds=2.5)
    assert value.implied_probability == pytest.approx(0.4)
    assert len(value.canonical_sha256()) == 64


def test_paper_trade_uses_unit_simulation_only_and_computes_edge():
    value = _trade(probability=0.6, odds=2.0)
    assert value.theoretical_edge == pytest.approx(0.2)
    assert value.realized_unit_return == pytest.approx(1.0)
    assert len(value.canonical_sha256()) == 64


def test_unsettled_trade_has_no_realized_return():
    value = _trade(outcome=None)
    assert value.realized_unit_return is None


def test_summary_is_market_and_model_specific():
    summary = summarize_paper_trading([_trade(1, outcome=True), _trade(2, outcome=False)])
    assert summary.observation_count == 2
    assert summary.settled_count == 2
    assert summary.realized_units == pytest.approx(0.0)
    assert summary.market_key == "over_2_5"


def test_summary_rejects_duplicate_fixture_market_selection():
    a = _trade(1, fixture_id="same")
    b = PaperTradeObservation(
        decision_id="d-other",
        fixture_id="same",
        market_key=a.market_key,
        selection_key=a.selection_key,
        model_version=a.model_version,
        model_probability=a.model_probability,
        decision_at_utc=a.decision_at_utc,
        odds_snapshot_sha256=a.odds_snapshot_sha256,
        decimal_odds=a.decimal_odds,
        outcome=False,
        settled_at_utc="2026-08-18T21:00:00+00:00",
    )
    with pytest.raises(ValueError, match="one paper decision"):
        summarize_paper_trading([a, b])
