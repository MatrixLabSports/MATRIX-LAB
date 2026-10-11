import json

from tools.cor0203_rapidapi_stats_rich_history_probe import (
    _eligible,
    _stat_summary,
    _embedded_stats,
    _has_model_required_stats,
    discover_targets,
)


def test_eligible_requires_strict_pre_cut_and_nonterminal():
    row={
        "date":"2026-09-20T12:00:00Z",
        "result_type":"completed",
        "tournament":{"rankId":1,"court":{"name":"Hard"}},
    }
    assert _eligible(row) is True
    row2=dict(row); row2["date"]="2026-09-21T00:00:00Z"
    assert _eligible(row2) is False
    row3=dict(row); row3["result_type"]="retired"
    assert _eligible(row3) is False


def test_stat_summary_keeps_model_required_service_counts():
    payload={"data":{
        "player1Stats":{"player1Id":1,"firstServeOf":70,"winningOnFirstServe":30,"winningOnFirstServeOf":40,"winningOnSecondServe":15,"winningOnSecondServeOf":30},
        "player2Stats":{"player2Id":2,"firstServeOf":65,"winningOnFirstServe":28,"winningOnFirstServeOf":39,"winningOnSecondServe":14,"winningOnSecondServeOf":26},
    }}
    out=_stat_summary(payload)
    assert out["player1Stats"]["firstServeOf"]==70
    assert out["player1Stats"]["winningOnFirstServe"]==30
    assert out["player1Stats"]["winningOnSecondServe"]==15


def test_inline_past_match_stats_are_model_usable():
    row={
        "player1":{"id":1,"name":"A","stats":{
            "winningOnFirstServe":30,"winningOnFirstServeOf":45,
            "winningOnSecondServe":14,"winningOnSecondServeOf":25,
        }},
        "player2":{"id":2,"name":"B","stats":{
            "winningOnFirstServe":28,"winningOnFirstServeOf":42,
            "winningOnSecondServe":12,"winningOnSecondServeOf":23,
        }},
    }
    out=_embedded_stats(row)
    assert _has_model_required_stats(out) is True
    assert out["player1Stats"]["winningOnFirstServe"]==30


def test_inline_stats_fail_closed_when_one_side_missing():
    row={"player1":{"stats":{
        "winningOnFirstServe":30,"winningOnFirstServeOf":45,
        "winningOnSecondServe":14,"winningOnSecondServeOf":25,
    }},"player2":{"stats":{}}}
    assert _has_model_required_stats(_embedded_stats(row)) is False


def test_dynamic_probe_targets_only_current_players_without_authority(tmp_path):
    world=tmp_path/"world.json"
    authority=tmp_path/"authority.json"
    world.write_text(json.dumps({
        "eligible_candidates":[{
            "player_identities":[
                {"provider_player_id":"rapidapi-tennis:player:103054","display_name":"Thijs Boogaard"},
                {"provider_player_id":"rapidapi-tennis:player:111","display_name":"Known Player"},
            ]
        }],
        "provider_rejected":[{
            "players":[{
                "provider_player_id":"rapidapi-tennis:player:92242",
                "name":"Charles Chen",
            }]
        }],
    }),encoding="utf-8")
    authority.write_text(json.dumps({
        "records":[{
            "provider_player_id":"rapidapi-tennis:player:111",
        }]
    }),encoding="utf-8")

    targets=discover_targets(
        world_discovery_path=world,
        authority_path=authority,
        max_targets=32,
    )

    assert targets["103054"]=="Thijs Boogaard"
    assert targets["92242"]=="Charles Chen"
    assert "111" not in targets
