from pathlib import Path
import json

from tools.cor0203_dual_provider_reconcile import reconcile_dual_discovery


def static_cut():
    return {
        "ranking_cut":"20260921",
        "post_cut_data_used":False,
        "silent_imputation":False,
        "players":{
            "A":{"canonical_name":"Player Alpha","canonical_source_id":"A","rank":100,"rank_points":600,"ioc":"USA"},
            "B":{"canonical_name":"Player Beta","canonical_source_id":"B","rank":120,"rank_points":500,"ioc":"GBR"},
            "C":{"canonical_name":"Player Gamma","canonical_source_id":"C","rank":140,"rank_points":400,"ioc":"FRA"},
        },
    }


def rapid():
    return {
        "provider":"rapidapi_tennis",
        "status":"DISCOVERY_COMPLETED",
        "eligible_candidates":[{
            "event_id":"rapidapi-tennis:match:10",
            "canonical_source_event_id":"rapidapi-tennis:match:10",
            "competition_id":"rapidapi-tennis:tournament:1",
            "competition":"Example Challenger",
            "round":"Quarter-Final",
            "surface":"Hard",
            "tour_level":"C",
            "event_start_utc":"2026-10-05T12:00:00+00:00",
            "source_snapshot_sha256":"a"*64,
            "players":[
                {"name":"Player Alpha","provider_player_id":"rapidapi-tennis:player:1","provider_ranking":{"place":"100","points":"600","player":"Player Alpha","snapshot_date":"2026-09-21"}},
                {"name":"Player Beta","provider_player_id":"rapidapi-tennis:player:2","provider_ranking":{"place":"120","points":"500","player":"Player Beta","snapshot_date":"2026-09-21"}},
            ],
        }],
    }


def api(overlap=True):
    opponent="Player Beta" if overlap else "Player Gamma"
    opp_id="22" if overlap else "33"
    return {
        "provider":"api_tennis",
        "status":"DISCOVERY_COMPLETED",
        "eligible_candidates":[{
            "event_id":"api-tennis:event:900",
            "canonical_source_event_id":"api-tennis:event:900",
            "competition_id":"api-tennis:tournament:99",
            "competition":"Example",
            "round":"Example - 1/4-finals",
            "surface":"Hard",
            "tour_level":"C",
            "event_start_utc":"2026-10-05T12:15:00+00:00",
            "source_snapshot_sha256":"b"*64,
            "players":[
                {"name":"P. Alpha","provider_player_id":"api-tennis:player:11","provider_ranking":{"place":"1","points":"9999","player":"Player Alpha"}},
                {"name":"P. Opp","provider_player_id":f"api-tennis:player:{opp_id}","provider_ranking":{"place":"2","points":"9998","player":opponent}},
            ],
        }],
    }


def test_cross_provider_same_match_is_not_emitted_twice(tmp_path):
    r,a,audit=reconcile_dual_discovery(
        rapidapi=rapid(),api_tennis=api(True),static_cut=static_cut(),
        runtime_dir=tmp_path,certified_aliases=None,
    )
    assert len(r["eligible_candidates"])==1
    assert len(a["eligible_candidates"])==0
    assert audit["cross_provider_alias_count"]==1
    assert audit["api_tennis_current_rank_used"] is False


def test_api_only_match_is_enriched_from_sealed_static_cut(tmp_path):
    r,a,audit=reconcile_dual_discovery(
        rapidapi=rapid(),api_tennis=api(False),static_cut=static_cut(),
        runtime_dir=tmp_path,certified_aliases=None,
    )
    assert len(a["eligible_candidates"])==1
    row=a["eligible_candidates"][0]
    assert row["players"][0]["provider_ranking"]["place"]=="100"
    assert row["players"][0]["provider_ranking"]["points"]=="600"
    assert row["players"][0]["provider_ranking"]["authority"]=="SEALED_STATIC_CUT_20260921"
    assert row["players"][0]["provider_current_ranking_discarded"] is True
    assert len(row["physical_event_key"])==64
    assert audit["api_tennis_unique_candidates_output"]==1


def test_unresolved_api_identity_fails_closed(tmp_path):
    payload=api(False)
    payload["eligible_candidates"][0]["players"][1]["provider_ranking"]["player"]="Unknown Person"
    r,a,audit=reconcile_dual_discovery(
        rapidapi=rapid(),api_tennis=payload,static_cut=static_cut(),
        runtime_dir=tmp_path,certified_aliases=None,
    )
    assert a["eligible_candidates"]==[]
    assert audit["api_tennis_identity_blocked_count"]==1
    assert "PIT_STATIC_IDENTITY_NOT_RESOLVED" in audit["api_tennis_identity_blocked"][0]["blockers"][0]


def test_existing_prefeature_is_not_reintroduced_by_second_provider(tmp_path):
    runtime=tmp_path
    (runtime/"MATRIX_COR0203_PREFEATURE_REGISTRY_R1.json").write_text(json.dumps({
        "events":[{
            "event_id":"OLD",
            "canonical_source_event_id":"rapidapi-tennis:match:old",
            "round":"Quarter-Final",
            "event_start_utc":"2026-10-05T12:00:00+00:00",
            "player_identities":[
                {"display_name":"Player Alpha","provider_player_id":"rapidapi-tennis:player:1"},
                {"display_name":"Player Beta","provider_player_id":"rapidapi-tennis:player:2"},
            ],
        }]
    }),encoding="utf-8")
    r,a,audit=reconcile_dual_discovery(
        rapidapi=rapid(),api_tennis=api(True),static_cut=static_cut(),
        runtime_dir=runtime,certified_aliases=None,
    )
    assert r["eligible_candidates"]==[]
    assert a["eligible_candidates"]==[]
    assert audit["existing_provider_neutral_keys"]==1


def test_api_identity_can_use_existing_precut_authority(tmp_path):
    cut=static_cut()
    cut["players"].pop("C")
    authority={
        "records":[{
            "provider_player_id":"rapidapi-tennis:player:303",
            "provider_display_name":"Player Gamma",
            "provider_ioc_canonical":"FRA",
            "provider_ioc_raw":"FRA",
            "provider_rank":"140",
            "provider_rank_points":"400",
            "ranking_cut":"2026-09-21",
            "pre_cut_history":{
                "canonical_source_ids":["C"],
                "canonical_iocs":["FRA"],
                "observed_hands":["R"],
                "rows":12,
            },
            "biographical_candidates":[{
                "name":"Player Gamma",
                "dob":"20000101",
                "hand":"R",
                "ioc":"FRA",
            }],
            "biography_source":"TEST_PRECUT_AUTHORITY",
        }]
    }
    r,a,audit=reconcile_dual_discovery(
        rapidapi=rapid(),api_tennis=api(False),static_cut=cut,
        runtime_dir=tmp_path,certified_aliases=None,
        identity_authority=authority,
    )
    assert len(a["eligible_candidates"])==1
    p=a["eligible_candidates"][0]["players"][1]
    assert p["provider_ranking"]["place"]=="140"
    assert p["provider_ranking"]["points"]=="400"
    assert p["provider_ranking"]["authority"]=="IDENTITY_AUTHORITY_PRECUT_20260921"
    assert audit["cross_provider_identity_aliases_generated"]==1
    payload=audit["_identity_alias_payload"]
    ids={row["provider_player_id"] for row in payload["records"]}
    assert "api-tennis:player:33" in ids
