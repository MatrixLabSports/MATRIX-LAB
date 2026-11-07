from __future__ import annotations

from datetime import date

from tools.tennis_clay_pit_catchup import authority_index, build_state


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


def test_authority_index_uses_unique_precut_source_id_when_top_level_id_absent():
    authority={
        "records":[{
            "provider_player_id":"rapidapi-tennis:player:11",
            "provider_display_name":"Player One",
            "pre_cut_history":{"canonical_source_ids":["P001"]},
        }]
    }
    out=authority_index(authority)
    assert out["11"]["canonical_source_id"]=="P001"
    assert out["11"]["canonical_name"]=="Player One"

def test_causal_identity_closure_ignores_later_only_opponent_branch():
    historical=[
        _hist("A","B",1,20260913),
        _hist("A","B",0,20260914),
    ]
    authority={
        "records":[
            {"provider_player_id":"rapidapi-tennis:player:11","canonical_source_id":"A","canonical_name":"A"},
            {"provider_player_id":"rapidapi-tennis:player:22","canonical_source_id":"B","canonical_name":"B"},
        ]
    }
    results=[
        _result("1","2026-09-15","11","22"),
        _result("2","2026-09-16","22","44"),
    ]
    state=build_state(
        historical_rows=historical,
        result_rows=results,
        authority_payload=authority,
        target_provider_ids={"rapidapi-tennis:player:11"},
        source_start=date(2026,9,15),
        source_stop=date(2026,9,16),
    )
    target=state["targets"][0]
    assert target["ready"] is True
    assert target["component_unmapped_provider_ids"]==[]
    assert state["identity_closure_policy"]=="REVERSE_TIME_CAUSAL_BATCH_DAY"


def test_supplemental_identity_only_crosswalk_can_complete_causal_mapping():
    historical=[
        _hist("A","B",1,20260913),
        _hist("A","B",0,20260914),
    ]
    authority={
        "records":[
            {"provider_player_id":"rapidapi-tennis:player:11","canonical_source_id":"A","canonical_name":"A"},
        ]
    }
    supplemental={
        "events":[{
            "event_id":"identity-only-22",
            "status":"PASS",
            "provider_player_ids":["rapidapi-tennis:player:22"],
            "blockers":[],
        }],
        "mappings":[{
            "provider_player_id":"rapidapi-tennis:player:22",
            "canonical_source_id":"B",
            "canonical_name":"B",
            "status":"PASS",
        }],
    }
    results=[_result("1","2026-09-15","11","22")]
    state=build_state(
        historical_rows=historical,
        result_rows=results,
        authority_payload=authority,
        target_provider_ids={"rapidapi-tennis:player:11"},
        source_start=date(2026,9,15),
        source_stop=date(2026,9,15),
        supplemental_crosswalk_payload=supplemental,
    )
    assert state["targets"][0]["ready"] is True
    assert state["supplemental_identity_crosswalk_used"] is True

