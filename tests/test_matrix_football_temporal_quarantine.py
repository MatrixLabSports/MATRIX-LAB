import pytest
from tools.matrix_football_temporal_quarantine import build


def fixture(states):
    return {"target_date_bogota": "2026-10-29", "rows": [
        {"flashscore": "F" + str(i), "sofascore": "S" + str(i),
         "display_clock_comparison": state} for i, state in enumerate(states)
    ]}


def test_quarantine_fail_closed_all_clock_states():
    result = build(fixture(["CLOCK_STRING_MATCH", "CLOCK_STRING_MISMATCH", "NOT_COMPARABLE"]))
    assert result["counts"]["total"] == 3
    assert result["counts"]["eligible_for_freeze"] == 0
    assert result["counts"]["eligible_for_telegram_signal"] == 0
    assert [row["block_reason"] for row in result["rows"]] == [
        "TIMEZONE_NOT_CERTIFIED", "CROSS_SOURCE_CLOCK_CONFLICT",
        "CROSS_SOURCE_CLOCK_UNAVAILABLE"]
    assert all(not row["eligible_for_freeze"] and not row["eligible_for_telegram_signal"]
               for row in result["rows"])
    assert result["policy"]["real_money"] == "BLOCKED"


def test_unknown_clock_state_must_fail_closed():
    with pytest.raises(ValueError, match="UNKNOWN_CLOCK_STATE"):
        build(fixture(["UNRECOGNIZED"]))


def test_empty_rows_do_not_generate_signals():
    result = build(fixture([]))
    assert result["rows"] == []
    assert result["counts"]["eligible_for_telegram_signal"] == 0


def test_postponed_fixture_is_not_classified_as_generic_missing_clock():
    data = fixture(["NOT_COMPARABLE"])
    data["rows"][0]["sofascore"] = "29/10/26 Aplazado Numancia Real Oviedo"
    data["rows"][0]["flashscore_normalized_clock"] = "12:00"
    result = build(data)
    row = result["rows"][0]
    assert row["block_reason"] == "POSTPONED_IN_SOFASCORE"
    assert row["flashscore_clock_visible"] is True
    assert row["flashscore_display_clock"] == "12:00"
    assert row["sofascore_postponed"] is True
    assert row["eligible_for_telegram_signal"] is False


def test_visible_clock_without_timezone_is_still_quarantined():
    data = fixture(["CLOCK_STRING_MATCH"])
    data["rows"][0]["flashscore_normalized_clock"] = "18:15"
    data["rows"][0]["sofascore_normalized_clock"] = "18:15"
    row = build(data)["rows"][0]
    assert row["flashscore_clock_visible"] is True
    assert row["block_reason"] == "TIMEZONE_NOT_CERTIFIED"
    assert row["eligible_for_freeze"] is False
