from pathlib import Path

from tools.cor0203_shelbayh_alias_cert import build_certificate


def _profile():
    return {
        "data":{
            "id":"76009",
            "name":"Abedallah Shelbayh",
            "birthday":"2003-11-16T00:00:00.000Z",
            "countryAcr":"JOR",
            "information":{"plays":"Left-Handed, Two-Handed Backhand"},
            "currentRank":999,
        }
    }


def test_certificate_requires_canonical_history_and_sealed_r706(tmp_path):
    history=tmp_path/"h.csv"
    history.write_text(
        "tourney_level,tourney_date,winner_id,winner_name,winner_hand,winner_ioc,winner_age,"
        "loser_id,loser_name,loser_hand,loser_ioc,loser_age,w_svpt,w_1stWon,w_2ndWon,l_svpt,l_1stWon,l_2ndWon\n"
        "C,20260914,S0NV,Abdullah Shelbayh,L,JOR,22.828,X,Other,R,USA,25,60,30,15,55,28,14\n",
        encoding="utf-8",
    )
    runtime=tmp_path/"runtime"; runtime.mkdir()
    (runtime/"MATRIX_COR0203_PREFEATURE_REGISTRY_R1.json").write_text(
        '{"events":[{"event_id":"E","player_identities":[{"display_name":"Abedallah Shelbayh",'
        '"provider_player_id":"rapidapi-tennis:player:76009","provider_ranking":{'
        '"country":"JOR","place":"250","points":"224","player":"Abedallah Shelbayh",'
        '"snapshot_date":"2026-09-21"}}]}]}',
        encoding="utf-8",
    )
    r706=tmp_path/"r706.json"
    r706.write_text(
        '{"state_mutated":false,"metrics_opened":false,"outcomes_read":0,'
        '"state_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        '"targets":[{"name":"Abdullah Shelbayh","fully_history_ready":true,'
        '"required_components":{"a":true},"counts":{"overall_n":1},"ratings":{"elo_overall_present":true}}]}',
        encoding="utf-8",
    )
    out=build_certificate(profile=_profile(),history_csv=history,runtime_dir=runtime,r706_path=r706)
    row=out["records"][0]
    assert row["canonical_name"]=="Abdullah Shelbayh"
    assert row["pre_cut_history"]["canonical_source_ids"]==["S0NV"]
    assert row["stats_rich_pre_cut_history"]["stats_rich_rows"]==1
    assert row["sealed_r706_history"]["fully_history_ready"] is True
    assert "currentRank" in row["profile_competitive_fields_discarded"]
    assert out["post_cut_competitive_data_used"] is False
