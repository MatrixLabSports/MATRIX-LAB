from tools.live_tennis_api_tennis_fallback import normalize_live_event


def test_normalize_live_event_singles_quality_valid():
    row={
        "event_key":"123",
        "event_first_player":"Player A",
        "first_player_key":"11",
        "event_second_player":"Player B",
        "second_player_key":"22",
        "event_live":"1",
        "event_type_type":"Atp Singles",
        "event_status":"Set 2",
        "event_serve":"First Player",
        "event_game_result":"30 - 15",
        "event_final_result":"1 - 0",
        "scores":[
            {"score_set":"1","score_first":"6","score_second":"4"},
            {"score_set":"2","score_first":"2","score_second":"1"},
        ],
        "pointbypoint":[],
        "tournament_name":"Example",
    }
    x=normalize_live_event(row,captured_at_utc="2026-10-12T04:00:00+00:00",response_sha256="a"*64)
    assert x is not None
    assert x["provider"]=="api_tennis"
    assert x["match_id"]=="123"
    assert x["server"]==1
    assert x["current_set_index_zero_based"]==1
    assert x["current_set_game_diff_p1"]==1
    assert x["total_game_diff_p1"]==3
    assert x["set_diff_p1"]==1
    assert x["point_p1_code"]==2
    assert x["point_p2_code"]==1
    assert x["quality_state_valid"] is True
    assert x["calibration_admitted"] is False
    assert x["automatic_model_feed"] is False


def test_normalize_doubles_not_quality_admitted():
    row={
        "event_key":"124",
        "event_first_player":"A/B",
        "event_second_player":"C/D",
        "event_live":"1",
        "event_type_type":"Atp Doubles",
        "event_status":"Set 1",
        "event_serve":"Second Player",
        "event_game_result":"40 - 40",
        "event_final_result":"0 - 0",
        "scores":[{"score_set":"1","score_first":"3","score_second":"3"}],
        "pointbypoint":[],
    }
    x=normalize_live_event(row,captured_at_utc="2026-10-12T04:00:00+00:00",response_sha256="b"*64)
    assert x is not None
    assert x["quality_state_valid"] is False
    assert x["calibration_blocker"]=="CROSS_PROVIDER_EQUIVALENCE_AND_IDENTITY_RECONCILIATION_REQUIRED"


def test_semantically_identical_state_has_same_key():
    row={
        "event_key":"125",
        "event_first_player":"A",
        "event_second_player":"B",
        "event_live":"1",
        "event_type_type":"Wta Singles",
        "event_status":"Set 1",
        "event_serve":"First Player",
        "event_game_result":"15 - 0",
        "event_final_result":"0 - 0",
        "scores":[{"score_set":"1","score_first":"1","score_second":"0"}],
        "pointbypoint":[],
    }
    a=normalize_live_event(row,captured_at_utc="2026-10-12T04:00:00+00:00",response_sha256="c"*64)
    b=normalize_live_event(row,captured_at_utc="2026-10-12T04:01:00+00:00",response_sha256="d"*64)
    assert a is not None and b is not None
    assert a["state_key"]==b["state_key"]
