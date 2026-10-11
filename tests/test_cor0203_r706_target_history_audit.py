import json

from tools.cor0203_r706_target_history_audit import audit_player, discover_target_names


def test_audit_requires_every_model_history_component():
    state={
        "history":{
            "matches":{"P":[1,0,1]},
            "overall":{"P":[2,3]},
            "surface":{"P":{"Hard":[1,2]}},
            "serve":{"P":[30,50]},
            "ret":{"P":[20,50]},
            "opp_strength":{"P":[1.5,3]},
        },
        "elo_overall":{"P":1510},
        "elo_surface":{"Hard":{"P":1505}},
        "glicko_overall":{"P":{"r":1510,"rd":200}},
        "glicko_surface":{"Hard":{"P":{"r":1505,"rd":210}}},
    }
    row=audit_player(state,"P")
    assert row["fully_history_ready"] is True
    del state["history"]["serve"]["P"]
    row=audit_player(state,"P")
    assert row["fully_history_ready"] is False
    assert row["required_components"]["serve_history"] is False


def test_alias_names_are_audited_independently():
    state={
        "history":{
            "matches":{"Abdullah Shelbayh":[1,0]},
            "overall":{"Abdullah Shelbayh":[1,2]},
            "surface":{"Abdullah Shelbayh":{"Hard":[1,2]}},
            "serve":{"Abdullah Shelbayh":[50,100]},
            "ret":{"Abdullah Shelbayh":[40,100]},
            "opp_strength":{"Abdullah Shelbayh":[1.0,2]},
        },
        "elo_overall":{"Abdullah Shelbayh":1500},
        "elo_surface":{"Hard":{"Abdullah Shelbayh":1500}},
        "glicko_overall":{"Abdullah Shelbayh":{"r":1500,"rd":200}},
        "glicko_surface":{"Hard":{"Abdullah Shelbayh":{"r":1500,"rd":200}}},
    }
    canonical=audit_player(state,"Abdullah Shelbayh")
    provider_alias=audit_player(state,"Abedallah Shelbayh")
    assert canonical["fully_history_ready"] is True
    assert provider_alias["fully_history_ready"] is False


def test_dynamic_target_selection_adds_current_world_player_without_authority(tmp_path):
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

    names=discover_target_names(
        world_discovery_path=world,
        authority_path=authority,
    )

    assert "Thijs Boogaard" in names
    assert "Charles Chen" in names
    assert "Known Player" not in names
