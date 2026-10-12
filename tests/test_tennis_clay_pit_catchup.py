from __future__ import annotations

from datetime import date

from tools.tennis_clay_pit_catchup import build_state


def _hist(a,b,y,day):
    return {
        "tourney_date":day,
        "player_a_id":a,
        "player_b_id":b,
        "label_a_win":y,
        "development_split":"FINAL_HISTORICAL_OOS",
    }


def _result(mid,day,winner,loser):
    return {
        "matchId":mid,
        "date":day+"T12:00:00Z",
        "result_type":"completed",
        "player1":{"id":winner},
        "player2":{"id":loser},
        "tournament":{"id":1,"name":"Test Challenger","rankId":1,"court":{"name":"Clay"}},
    }


def test_catchup_ready_only_when_connected_identity_component_is_complete():
    historical=[
        _hist("A","B",1,20260913),
        _hist("A","B",0,20260914),
    ]
    authority={
        "records":[
            {"provider_player_id":"rapidapi-tennis:player:11","canonical_source_id":"A","canonical_name":"A"},
            {"provider_player_id":"rapidapi-tennis:player:22","canonical_source_id":"B","canonical_name":"B"},
            {"provider_player_id":"rapidapi-tennis:player:33","canonical_source_id":"C","canonical_name":"C"},
        ]
    }
    results=[
        _result("1","2026-09-15","11","22"),
        _result("2","2026-09-16","33","44"),
    ]
    state=build_state(
        historical_rows=historical,
        result_rows=results,
        authority_payload=authority,
        target_provider_ids={"rapidapi-tennis:player:11","rapidapi-tennis:player:33"},
        source_start=date(2026,9,15),
        source_stop=date(2026,9,16),
    )
    by_id={x["provider_player_id"]:x for x in state["targets"]}
    assert by_id["rapidapi-tennis:player:11"]["ready"] is True
    assert by_id["rapidapi-tennis:player:11"]["rating_after_catchup"] is not None
    assert by_id["rapidapi-tennis:player:33"]["ready"] is False
    assert by_id["rapidapi-tennis:player:33"]["blocker"]=="CATCHUP_COMPONENT_HAS_UNMAPPED_IDENTITIES"
    assert by_id["rapidapi-tennis:player:33"]["component_unmapped_provider_ids"]==["rapidapi-tennis:player:44"]
    assert state["silent_imputation"] is False
    assert state["real_money"]=="BLOCKED"
