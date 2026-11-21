from tools.matrix_external_tipster_lab import summarize, validate_pick


def _pick(**overrides):
    row={
        "schema":"MATRIX_EXTERNAL_TIPSTER_PICK_V1",
        "channel":"GREENHOUSE GRATIS",
        "pick_id":"gh-001",
        "source_message_id":"telegram-message-001",
        "source_evidence":"USER_SUPPLIED_SCREENSHOT_OR_EXACT_CAPTURE",
        "published_at_utc":"2026-10-25T12:00:00+00:00",
        "event_start_utc":"2026-10-25T14:00:00+00:00",
        "sport":"football",
        "event_identity":"Example A vs Example B",
        "market":"TOTAL_GOALS",
        "selection":"Over 2.5",
        "decimal_odds":1.80,
        "result":"WON",
        "matrix_relation":"AGREES",
        "tipster_used_to_generate_p_matrix":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    row.update(overrides)
    return row


def test_valid_pick_is_prematch_and_isolated_from_p_matrix():
    ok,errors=validate_pick(_pick())
    assert ok is True
    assert errors==[]


def test_post_start_tipster_pick_is_rejected():
    ok,errors=validate_pick(_pick(published_at_utc="2026-10-25T14:00:00+00:00"))
    assert ok is False
    assert "POST_START_PUBLICATION_FORBIDDEN" in errors


def test_tipster_can_never_feed_p_matrix_or_real_money():
    ok,errors=validate_pick(_pick(tipster_used_to_generate_p_matrix=True,real_money="ENABLED"))
    assert ok is False
    assert "TIPSTER_TO_P_MATRIX_NOT_EXPLICITLY_FALSE" in errors
    assert "REAL_MONEY_NOT_BLOCKED" in errors


def test_duplicate_pick_id_does_not_inflate_sample():
    r=summarize([_pick(),_pick()])
    assert r["valid_pick_count"]==1
    assert r["rejected_count"]==1
    assert "DUPLICATE_PICK_ID" in r["rejections"][0]["errors"]


def test_flat_one_unit_metrics_are_reproducible():
    rows=[
        _pick(pick_id="1",decimal_odds=2.0,result="WON",matrix_relation="AGREES"),
        _pick(pick_id="2",decimal_odds=1.8,result="LOST",matrix_relation="DISAGREES"),
        _pick(pick_id="3",decimal_odds=1.7,result="VOID",matrix_relation="NO_SIGNAL"),
    ]
    r=summarize(rows)
    assert r["settled_pick_count"]==3
    assert r["wins"]==1
    assert r["losses"]==1
    assert r["voids"]==1
    assert r["flat_one_unit_profit"]==0.0
    assert r["roi_pct"]==0.0


def test_lab_starts_collecting_and_does_not_fake_100_pick_sample():
    r=summarize([])
    assert r["lab_state"]=="COLLECTING_PHYSICAL_CONSECUTIVE_SAMPLE"
    assert r["valid_pick_count"]==0
    assert r["remaining_to_target"]==100
    assert r["protections"]["cherry_picking_forbidden"] is True
    assert r["protections"]["tipster_can_trigger_bet"] is False
