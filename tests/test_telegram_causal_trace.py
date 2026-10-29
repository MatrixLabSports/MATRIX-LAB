from tools.telegram_causal_trace import build


def test_trace_separates_identity_and_exact_line():
    rows = [
        {"schema": "MATRIX_TELEGRAM_QUOTE_ATTEMPT_V3", "identity_match": {"state": "LOW_SCORE"},
         "over_2_5_seen_any_authorized": True, "final_discard_reason": "IDENTITY_LOW_SCORE",
         "query_at_utc": "2026-10-29T00:00:00Z"},
        {"schema": "MATRIX_TELEGRAM_QUOTE_ATTEMPT_V3", "identity_match": {"state": "MATCHED"},
         "over_2_5_seen_any_authorized": True, "final_discard_reason": None,
         "query_at_utc": "2026-10-29T00:01:00Z"},
        {"schema": "MATRIX_TELEGRAM_QUOTE_ATTEMPT_V2", "identity_match": {"state": "MATCHED"},
         "over_2_5_seen_any_authorized": True},
    ]
    result = build(rows)
    assert result["current_schema_attempts"] == 2
    assert result["identity_states"] == {"LOW_SCORE": 1, "MATCHED": 1}
    assert result["exact_over_2_5_seen_attempts"] == 2
    assert result["both_identity_not_flagged_and_exact_line"] == 1
    assert result["telegram_delivery_acknowledgment"] == "NOT_VERIFIED_BY_QUOTE_LEDGER"
    assert result["automatic_wagering"] is False


def test_trace_empty_is_fail_safe():
    result = build([])
    assert result["current_schema_attempts"] == 0
    assert result["latest_attempt_observation"] == []
    assert result["telegram_delivery_acknowledgment"] == "NOT_VERIFIED_BY_QUOTE_LEDGER"
