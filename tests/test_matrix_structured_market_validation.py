"""Regression tests for structural quote validation, including ambiguous markets."""
import pytest
from tools.matrix_structured_market_validation import validate_full_match_over_25


def fixture():
    event = {"event_id": "match-1"}
    market = {"event_id": "match-1", "market_id": "market-1",
              "period": "FULL_MATCH", "market_type": "TOTAL_GOALS",
              "line": 2.5, "selections": [
                  {"side": "UNDER", "selection_id": "under-1", "price": "1,75"},
                  {"side": "OVER", "selection_id": "over-1", "price": "1.91"}]}
    return event, market


def test_exact_structured_quote_accepted():
    event, market = fixture()
    assert validate_full_match_over_25(event, market) == {
        "event_id": "match-1", "market_id": "market-1",
        "selection_id": "over-1", "market": "OVER_2_5", "price": 1.91}


@pytest.mark.parametrize("field,value", [
    ("event_id", "different"), ("period", "FIRST_HALF"),
    ("market_type", "TEAM_TOTAL_GOALS"), ("line", 1.5),
    ("line", "not-a-number"), ("market_id", None)])
def test_wrong_market_rejected(field, value):
    event, market = fixture()
    market[field] = value
    assert validate_full_match_over_25(event, market) is None


def test_duplicate_over_selection_rejected():
    event, market = fixture()
    market["selections"].append({"side": "OVER", "selection_id": "over-2", "price": 1.92})
    assert validate_full_match_over_25(event, market) is None


@pytest.mark.parametrize("price", [None, "NaN", "Infinity", 1, "not-a-price"])
def test_invalid_price_rejected(price):
    event, market = fixture()
    market["selections"][1]["price"] = price
    assert validate_full_match_over_25(event, market) is None


def test_flat_accessibility_text_is_not_structured_market():
    assert validate_full_match_over_25(
        {"event_id": "match-1"},
        {"market_id": "market-1", "text": "Menos/Más goles 2.5 Más 1,91"}) is None
