from pathlib import Path

from tools.cor0203_api_tennis_rank_bridge import build_bridge


def discovery():
    return {
        "status":"DISCOVERY_COMPLETED",
        "eligible_candidates":[{
            "players":[
                {
                    "name":"P. Alpha",
                    "provider_player_id":"api-tennis:player:11",
                    "provider_ranking":{"player":"Player Alpha","place":"1","points":"9999"},
                },
                {
                    "name":"P. Beta",
                    "provider_player_id":"api-tennis:player:22",
                    "provider_ranking":{"player":"Player Beta","place":"2","points":"9998"},
                },
            ]
        }],
    }


def authority():
    return {
        "schema":"MATRIX_COR0203_IDENTITY_AUTHORITY_AUTOEXPAND_V1",
        "records":[],
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,
        "odds_used":False,
    }


def ranking_rows():
    return [
        {
            "position":100,"pts":600,
            "player":{"id":101,"name":"Player Alpha","countryAcr":"USA"},
        },
        {
            "position":120,"pts":500,
            "player":{"id":202,"name":"Player Beta","countryAcr":"FRA"},
        },
    ]


def write_history(path: Path):
    path.write_text(
        "tourney_level,tourney_date,winner_id,winner_name,winner_hand,winner_ioc,"
        "loser_id,loser_name,loser_hand,loser_ioc\n"
        "C,20260914,A,Player Alpha,R,USA,X,Other One,R,GBR\n"
        "C,20260914,B,Player Beta,L,FRA,Y,Other Two,R,ESP\n",
        encoding="utf-8",
    )


def profiles(pid):
    data={
        "101":{
            "data":{"id":"101","name":"Player Alpha","countryAcr":"USA",
                    "birthday":"2000-01-01","information":{"plays":"Right-Handed"}},
        },
        "202":{
            "data":{"id":"202","name":"Player Beta","countryAcr":"FRA",
                    "birthday":"2001-02-02","information":{"plays":"Left-Handed"}},
        },
    }
    return data[pid]


def test_bridge_uses_cut_ranking_not_api_tennis_current_rank(tmp_path):
    history=tmp_path/"h.csv"; write_history(history)
    updated,aliases,audit=build_bridge(
        discovery=discovery(),authority=authority(),history_csv=history,
        ranking_rows=ranking_rows(),profile_fetcher=profiles,max_profiles=12,
    )
    assert audit["status"]=="PASS"
    assert audit["new_aliases_generated"]==2
    assert len(updated["records"])==2
    rows={x["provider_player_id"]:x for x in aliases["records"]}
    assert rows["api-tennis:player:11"]["provider_rank"]=="100"
    assert rows["api-tennis:player:11"]["provider_rank_points"]=="600"
    assert "API_TENNIS_CURRENT_STANDINGS_RANK" in rows["api-tennis:player:11"]["profile_competitive_fields_discarded"]
    assert aliases["post_cut_competitive_data_used"] is False


def test_bridge_fails_closed_without_precut_history(tmp_path):
    history=tmp_path/"h.csv"
    history.write_text(
        "tourney_level,tourney_date,winner_id,winner_name,winner_hand,winner_ioc,"
        "loser_id,loser_name,loser_hand,loser_ioc\n",
        encoding="utf-8",
    )
    updated,aliases,audit=build_bridge(
        discovery=discovery(),authority=authority(),history_csv=history,
        ranking_rows=ranking_rows(),profile_fetcher=profiles,max_profiles=12,
    )
    assert audit["new_aliases_generated"]==0
    assert audit["blocked_count"]==2
    assert updated["records"]==[]


def test_bridge_requires_unique_cut_ranking_name(tmp_path):
    history=tmp_path/"h.csv"; write_history(history)
    rows=ranking_rows()+[
        {
            "position":999,"pts":1,
            "player":{"id":999,"name":"Player Alpha","countryAcr":"USA"},
        }
    ]
    updated,aliases,audit=build_bridge(
        discovery=discovery(),authority=authority(),history_csv=history,
        ranking_rows=rows,profile_fetcher=profiles,max_profiles=12,
    )
    blocked={x["provider_player_id"]:x["reason"] for x in audit["blocked"]}
    assert blocked["api-tennis:player:11"]=="RAPIDAPI_CUT_RANKING_NAME_NOT_UNIQUE"
