from pathlib import Path
from tools.cor0203_api_tennis_rank_history_recovery import recover_rank_history_aliases


def _history(path: Path):
    path.write_text(
        "tourney_level,tourney_date,winner_id,winner_name,winner_hand,winner_ioc,"
        "loser_id,loser_name,loser_hand,loser_ioc\n"
        "C,20260914,AW,Aoran Wang,R,CHN,X,Other Player,R,USA\n",
        encoding="utf-8",
    )


def test_exact_21sep_history_recovers_player_outside_global_snapshot(tmp_path):
    h=tmp_path/"h.csv"; _history(h)
    audit={"ranking_cut":"20260921","blocked":[{
        "provider_player_id":"api-tennis:player:2225",
        "player":"Aoran Wang",
        "reason":"RAPIDAPI_CUT_RANKING_NAME_NOT_FOUND",
    }]}
    aliases={
        "schema":"MATRIX_COR0203_CERTIFIED_IDENTITY_ALIASES_V1",
        "strict_before_period":20260921,
        "records":[],
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,"odds_used":False,"metrics_opened":False,
        "automatic_wagering":False,"real_money":"BLOCKED",
    }
    authority={
        "schema":"X","records":[],
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,"odds_used":False,
    }
    profile=lambda name:{"data":{
        "id":9991,"name":"Aoran Wang","countryAcr":"CHN",
        "birthday":"1997-02-02","information":{"plays":"Right-Handed"},
        "currentRank":700,
    }}
    ranking=lambda pid:{"player":{"id":9991,"name":"Aoran Wang"},"history":[
        {"date":"2026-09-14T00:00:00Z","position":955,"pts":18},
        {"date":"2026-09-21T00:00:00Z","position":941,"pts":20},
        {"date":"2026-09-28T00:00:00Z","position":930,"pts":22},
    ]}
    updated,out,a=recover_rank_history_aliases(
        bridge_audit=audit,aliases=aliases,authority=authority,history_csv=h,
        profile_fetcher=profile,ranking_history_fetcher=ranking,max_recoveries=10,
    )
    assert a["recovered_count"]==1
    row=out["records"][0]
    assert row["provider_rank"]=="941"
    assert row["provider_rank_points"]=="20"
    assert row["ranking_cut"]=="2026-09-21"
    assert row["pre_cut_history"]["canonical_source_ids"]==["AW"]
    assert "currentRank" in row["profile_competitive_fields_discarded"]
    assert len(updated["records"])==1
    assert a["current_rank_used"] is False


def test_no_exact_cut_rank_fails_closed(tmp_path):
    h=tmp_path/"h.csv"; _history(h)
    audit={"ranking_cut":"20260921","blocked":[{
        "provider_player_id":"api-tennis:player:2225","player":"Aoran Wang",
        "reason":"RAPIDAPI_CUT_RANKING_NAME_NOT_FOUND",
    }]}
    aliases={"strict_before_period":20260921,"records":[],
        "post_cut_competitive_data_used":False,"outcomes_used":False,
        "odds_used":False,"metrics_opened":False,"real_money":"BLOCKED"}
    authority={"records":[],"post_cut_competitive_data_used":False,
        "outcomes_used":False,"odds_used":False}
    profile=lambda name:{"data":{"id":9991,"name":"Aoran Wang","countryAcr":"CHN",
        "birthday":"1997-02-02","information":{"plays":"Right-Handed"}}}
    ranking=lambda pid:{"history":[{"date":"2026-09-14","position":955,"pts":18}]}
    _,out,a=recover_rank_history_aliases(
        bridge_audit=audit,aliases=aliases,authority=authority,history_csv=h,
        profile_fetcher=profile,ranking_history_fetcher=ranking,
    )
    assert a["recovered_count"]==0
    assert out["records"]==[]
    assert a["blocked"][0]["reason"]=="EXACT_20260921_RANKING_NOT_FOUND"
