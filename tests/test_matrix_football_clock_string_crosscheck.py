from tools.matrix_football_clock_string_crosscheck import compare, normalize_clock


def test_normalize_clocks():
    assert normalize_clock("7:30") == "07:30"
    assert normalize_clock("07:30") == "07:30"
    assert normalize_clock("25:00") is None
    assert normalize_clock("-") is None


def test_compare_preserves_time_uncertainty():
    recon = {"status": "PASS_OPEN_RECONCILIATION", "target_date_bogota": "2026-10-29",
             "confirmed_both": [
                 {"flashscore": "A - B", "sofascore": "29/10/26 7:30 A A B B"},
                 {"flashscore": "C - D", "sofascore": "29/10/26 10:00 C C D D"},
                 {"flashscore": "E - F", "sofascore": "29/10/26 Aplazado E E F F"}]}
    capture = {"target_date_bogota": "2026-10-29",
               "rows": [{"link": {"name": "A - B"}, "time": "07:30"},
                        {"link": {"name": "C - D"}, "time": "12:00"},
                        {"link": {"name": "E - F"}, "time": "-"}]}
    result = compare(recon, capture)
    assert result["clock_comparison_counts"] == {
        "CLOCK_STRING_MATCH": 1, "CLOCK_STRING_MISMATCH": 1, "NOT_COMPARABLE": 1}
    assert all(not row["timezone_certified"] for row in result["rows"])
    assert result["policy"]["no_freeze_from_uncertified_clock"] is True


def test_date_mismatch_rejected():
    recon = {"status": "PASS_OPEN_RECONCILIATION", "target_date_bogota": "2026-10-29"}
    try:
        compare(recon, {"target_date_bogota": "2026-10-28"})
    except ValueError as exc:
        assert str(exc) == "TARGET_DATE_MISMATCH"
    else:
        raise AssertionError("date mismatch must fail closed")
