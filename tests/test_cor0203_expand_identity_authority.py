import csv
import json
from pathlib import Path

from tools.cor0203_expand_identity_authority import expand_authority


def _write_json(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _history(path: Path, rows):
    header = [
        "tourney_id","tourney_name","surface","draw_size","tourney_level","indoor","tourney_date","match_num",
        "winner_id","winner_seed","winner_entry","winner_name","winner_hand","winner_ht","winner_ioc","winner_age","winner_rank","winner_rank_points",
        "loser_id","loser_seed","loser_entry","loser_name","loser_hand","loser_ht","loser_ioc","loser_age","loser_rank","loser_rank_points",
        "score","best_of","round"
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for row in rows:
            base={k:"" for k in header}
            base.update(row)
            w.writerow(base)


def _pref(runtime: Path, pid="111", name="Player One", country="USA", rank="200", points="300"):
    payload={
        "revision":"R900","holdout_id":"A22_POST_AUDIT_VIRGIN_HOLDOUT_V1","discovery_provider":"rapidapi_tennis",
        "events":[{
            "event_id":"E1","identity_crosswalk_required":True,
            "player_identities":[{
                "display_name":name,"provider":"rapidapi_tennis","provider_player_id":f"rapidapi-tennis:player:{pid}",
                "provider_ranking":{"country":country,"place":rank,"player":name,"points":points,"snapshot_date":"2026-09-21"}
            }]
        }]
    }
    _write_json(runtime/"MATRIX_COR0203_PREFEATURE_REGISTRY_R900.json",payload)


def _authority():
    return {
        "schema":"BASE_V1","records":[],"country_code_aliases":{},
        "post_cut_competitive_data_used":False,"outcomes_used":False,"odds_used":False,
        "automatic_wagering":False,"real_money":"BLOCKED"
    }


def _static(path: Path):
    _write_json(path,{"ranking_cut":"20260921","players":{},"silent_imputation":False,"post_cut_data_used":False})


def test_expands_only_from_strict_pre_cut_unique_history(tmp_path):
    runtime=tmp_path/"runtime"; runtime.mkdir()
    _pref(runtime)
    hist=tmp_path/"h.csv"
    _history(hist,[{
        "tourney_level":"C","tourney_date":"20260914",
        "winner_id":"CAN1","winner_name":"Player One","winner_hand":"R","winner_ioc":"USA"
    }])
    static=tmp_path/"s.json"; _static(static)
    calls=[]
    def profile(pid):
        calls.append(pid)
        return {"data":{"id":pid,"name":"Player One","birthday":"2000-01-02T00:00:00.000Z","countryAcr":"USA",
                        "currentRank":999,"information":{"plays":"Right-Handed, Two-Handed Backhand"}}}
    out,audit=expand_authority(runtime_dir=runtime,history_csv=hist,static_cut_path=static,authority=_authority(),profile_fetcher=profile)
    assert audit["new_records"]==1
    assert calls==["111"]
    row=out["records"][0]
    assert row["pre_cut_history"]["canonical_source_ids"]==["CAN1"]
    assert row["profile_competitive_fields_discarded"]==["currentRank"]
    assert out["post_cut_competitive_data_used"] is False


def test_post_cut_history_cannot_create_authority(tmp_path):
    runtime=tmp_path/"runtime"; runtime.mkdir(); _pref(runtime)
    hist=tmp_path/"h.csv"
    _history(hist,[{
        "tourney_level":"C","tourney_date":"20260922",
        "winner_id":"CAN1","winner_name":"Player One","winner_hand":"R","winner_ioc":"USA"
    }])
    static=tmp_path/"s.json"; _static(static)
    out,audit=expand_authority(runtime_dir=runtime,history_csv=hist,static_cut_path=static,authority=_authority(),
        profile_fetcher=lambda pid: (_ for _ in ()).throw(AssertionError("profile should not be called")))
    assert audit["new_records"]==0
    assert audit["blocked"][0]["reason"]=="NO_PRE_CUT_CHALLENGER_HISTORY"
    assert out["records"]==[]


def test_profile_identity_conflict_fails_closed(tmp_path):
    runtime=tmp_path/"runtime"; runtime.mkdir(); _pref(runtime)
    hist=tmp_path/"h.csv"
    _history(hist,[{
        "tourney_level":"C","tourney_date":"20260914",
        "winner_id":"CAN1","winner_name":"Player One","winner_hand":"R","winner_ioc":"USA"
    }])
    static=tmp_path/"s.json"; _static(static)
    _,audit=expand_authority(runtime_dir=runtime,history_csv=hist,static_cut_path=static,authority=_authority(),
        profile_fetcher=lambda pid: {"data":{"id":pid,"name":"Different Player","birthday":"2000-01-02","countryAcr":"USA","information":{"plays":"Right-Handed"}}})
    assert audit["new_records"]==0
    assert audit["blocked"][0]["reason"]=="PROFILE_NAME_MISMATCH"


def test_existing_authority_is_idempotent_and_avoids_profile_call(tmp_path):
    runtime=tmp_path/"runtime"; runtime.mkdir(); _pref(runtime)
    hist=tmp_path/"h.csv"; _history(hist,[])
    static=tmp_path/"s.json"; _static(static)
    authority=_authority()
    authority["records"]=[{"provider_player_id":"rapidapi-tennis:player:111"}]
    out,audit=expand_authority(runtime_dir=runtime,history_csv=hist,static_cut_path=static,authority=authority,
        profile_fetcher=lambda pid: (_ for _ in ()).throw(AssertionError("profile should not be called")))
    assert audit["candidate_count"]==0
    assert audit["new_records"]==0
    assert len(out["records"])==1


def test_static_cut_resolvable_identity_does_not_request_profile(tmp_path):
    runtime=tmp_path/"runtime"; runtime.mkdir(); _pref(runtime,rank="200",points="300")
    hist=tmp_path/"h.csv"; _history(hist,[])
    static=tmp_path/"s.json"
    _write_json(static,{
        "ranking_cut":"20260921","silent_imputation":False,"post_cut_data_used":False,
        "players":{"CAN1":{"canonical_name":"Player One","rank":200,"rank_points":300}}
    })
    _,audit=expand_authority(runtime_dir=runtime,history_csv=hist,static_cut_path=static,authority=_authority(),
        profile_fetcher=lambda pid: (_ for _ in ()).throw(AssertionError("profile should not be called")))
    assert audit["candidate_count"]==0
    assert audit["new_records"]==0
