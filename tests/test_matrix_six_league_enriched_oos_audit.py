"""Synthetic contract tests only. These are NOT production or league evidence."""
from copy import deepcopy
import json
from datetime import datetime,timezone
from pathlib import Path

import pytest
from tools.matrix_six_league_enriched_oos_audit import (
    calculate, enriched_pair_ok,scan_archived_references,audit,
)

SIX=["TEST_L1","TEST_L2","TEST_L3","TEST_L4","TEST_L5","TEST_L6"]

def sample(league="TEST_L1",i=0):
    histories={}
    cross={"500":"500","1":"1","2":"2","3":"3"}
    for side,team,opponent in (("home",1,2),("away",2,1)):
        histories[side]=[]
        for k in range(5):
            h=str(700+k+side.count("away")*10)
            cross[h]=h
            histories[side].append({
                "fixture_id":h,
                "kickoff_utc":f"2026-09-{11+k:02d}T16:00:00+00:00",
                "team_id":str(team),"team_name":"Home" if side=="home" else "Away",
                "opponent_id":str(opponent),"opponent_name":"Opponent",
                "venue_role":side,"goals_for":k%3,"goals_against":(k+1)%3,
                "competition":league,"source_provider":"TEST_SOURCE",
                "observed_at_utc":f"2026-09-{12+k:02d}T12:00:00+00:00",
                "source_payload_sha256":"a"*64,
            })
    p={"benchmark_id":"TEST_ONLY","target_key":f"synthetic:{i}",
       "fixture_id":"500","as_of_utc":"2026-11-01T13:00:00+00:00",
       "kickoff_utc":"2026-11-10T17:45:00+00:00",
       "home_team_id":"1","home_team_name":"Home",
       "away_team_id":"2","away_team_name":"Away",
       "competition_id":league,"competition_name":league,
       "season":2026,"round_name":"Test Round","venue_name":"Test Venue",
       "fixture_source_provider":"TEST_SOURCE",
       "fixture_payload_sha256":"b"*64,
       "home_history":histories["home"],
       "away_history":histories["away"],
    }
    return {
        "league":league,"fixture_id":f"TEST:{league}:{i}",
        "frozen_at_utc":"2026-11-01T13:00:00+00:00",
        "kickoff_utc":"2026-11-10T17:45:00+00:00",
        "result_observed_at_utc":"2026-11-11T13:00:00+00:00",
        "over25_result":i%2,
        "original_p_over25":.55,"alternative_p_over25":.55,
        "original_probability_frozen":True,
        "alternative_probability_frozen":True,
        "result_verified_by_independent_source":True,
        "training_or_original_holdout_overlap":False,
        "source_verified":True,
        "original_input":deepcopy(p),"alternative_input":deepcopy(p),
        "original_to_canonical_id":dict(cross),
        "alternative_to_canonical_id":dict(cross),
    }

def test_complete_synthetic_fixture_exercises_all_six_scopes_without_telegram():
    rows=[sample(l,i) for l in SIX for i in range(30)]
    out=calculate(rows,SIX)
    assert out["six_league_scientific_validation_passed"] is True
    assert all(r["validated_prospective_rows"]==30 for r in out["leagues"])
    assert out["production_p_matrix_authorized"] is False
    assert out["telegram_signal_authorized"] is False
    assert out["calibration_parameters_mutated"] is False

def test_enriched_goal_mismatch_blocks_pair():
    x=sample()
    assert enriched_pair_ok(x)
    x["alternative_input"]["home_history"][0]["goals_for"]=9
    assert not enriched_pair_ok(x)

def test_leakage_or_holdout_overlap_blocks_all_six():
    rows=[sample(l,i) for l in SIX for i in range(30)]
    rows[0]["result_observed_at_utc"]="2026-11-01T00:00:00+00:00"
    rows[1]["training_or_original_holdout_overlap"]=True
    result=calculate(rows,SIX)
    assert result["six_league_scientific_validation_passed"] is False
    assert result["leagues"][0]["validated_prospective_rows"]==28
    assert result["telegram_signal_authorized"] is False

def test_no_qualified_six_league_manifest_never_passes():
    result=calculate([],SIX)
    assert result["six_league_scientific_validation_passed"] is False
    assert all(x["validated_prospective_rows"]==0 for x in result["leagues"])
    with pytest.raises(ValueError,match="SIX_LEAGUE"):
        calculate([],["TEST_L1"]*6)

def test_no_source_archive_is_not_a_certification(tmp_path):
    result=scan_archived_references(tmp_path)
    assert result["archived_reference_group_count"]==0
    assert result["six_original_leagues_confirmed"] is False
    assert result["telegram_signal_authorized"] is False

def test_manufactured_historical_table_without_three_source_hashes_is_rejected(tmp_path):
    path=tmp_path/"untrusted_oos.json"
    payload={"schema":"MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE_V1",
             "real_money":"BLOCKED","signal_generation_authorized":False,
             "original_six_league_ids":SIX,
             "rows":[sample(l,i) for l in SIX for i in range(30)]}
    path.write_text(json.dumps(payload),encoding="utf-8")
    with pytest.raises(ValueError,match="OOS_ORIGINAL_SIX_LEAGUES_NOT_GROUNDED_IN_ARCHIVE"):
        audit(path)
