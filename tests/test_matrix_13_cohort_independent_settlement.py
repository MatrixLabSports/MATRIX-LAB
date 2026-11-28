import hashlib
import json
import pytest
from pathlib import Path

from tools.matrix_13_cohort_independent_settlement import build_candidates,append,validated_ledger

def inputs(tmp_path):
    sub=tmp_path/"evidence/football_cohort_recovery"
    sub.mkdir(parents=True)
    raw={"events":[{"id":"761907","date":"2026-10-28T23:30Z","competitions":[{
        "status":{"period":2,"type":{"name":"STATUS_FULL_TIME","completed":True}},
        "competitors":[
            {"homeAway":"home","score":"4","team":{"displayName":"Charlotte FC"}},
            {"homeAway":"away","score":"0","team":{"displayName":"CF Montréal"}}
        ]
    }]}]}
    content=json.dumps(raw).encode()
    (sub/"ESPN_MLS_20261028_RAW.json").write_bytes(content)
    receipt={
        "api_football_fixture_id":"1490574",
        "espn_fixture_id":"761907",
        "raw_archive_path":"evidence/football_cohort_recovery/ESPN_MLS_20261028_RAW.json",
        "raw_espn_response_sha256":hashlib.sha256(content).hexdigest(),
        "fulltime_home":4,"fulltime_away":0,
    }
    triage={"target_market_count":13,"unsettled_fixture_triage_count":1,
            "unsettled_fixture_triage":[{
                "fixture_id":"1490574",
                "kickoff_utc":"2026-10-28T23:30:00Z",
                "freeze_at_utc":"2026-10-25T03:50:08Z",
                "home_team_name":"Charlotte","away_team_name":"CF Montreal"
            }]}
    freeze={"rows":[{
        "fixture_id":"1490574","target_key":"api_football:fixture:1490574",
        "kickoff_utc":"2026-10-28T23:30:00+00:00",
        "freeze_at_utc":"2026-10-25T03:50:08+00:00",
        "home_team_name":"Charlotte","away_team_name":"CF Montreal",
        "input_sha256":"a"*64,
    }]}
    source=("ESPN_MLS",{"real_money":"BLOCKED","canonical_ledger_appends":0,
                        "matches":[receipt]})
    return triage,freeze,source


def test_appended_independent_ft_is_physical_and_original_untouched(tmp_path):
    tri,freeze,source=inputs(tmp_path)
    rows,bad=build_candidates(tri,freeze,[source],root=tmp_path,api_settled=[],already=[])
    assert len(rows)==1 and not bad
    assert rows[0]["terminal_status"]=="FT"
    assert rows[0]["outcomes"]["over_2_5"] is True
    assert rows[0]["real_money"]=="BLOCKED"
    ledger=tmp_path/"independent.jsonl"
    a=append(ledger,rows)
    assert a["new"]==1 and a["total"]==1
    assert a["canonical_api_football_ledger_unchanged"] is True
    assert len(validated_ledger(ledger))==1
    with pytest.raises(ValueError,match="DUPLICATE_INDEPENDENT_SETTLEMENT"):
        append(ledger,rows)


def test_source_score_tamper_and_raw_hash_tamper_fail_closed(tmp_path):
    tri,freeze,src=inputs(tmp_path)
    src[1]["matches"][0]["fulltime_home"]=3
    with pytest.raises(ValueError,match="PROVIDER_REPORT_VS_RAW_DATA_MISMATCH"):
        build_candidates(tri,freeze,[src],root=tmp_path,api_settled=[],already=[])
    src[1]["matches"][0]["fulltime_home"]=4
    src[1]["matches"][0]["raw_espn_response_sha256"]="b"*64
    with pytest.raises(ValueError,match="ORIGINAL_PROVIDER_RESPONSE_HASH_MISMATCH"):
        build_candidates(tri,freeze,[src],root=tmp_path,api_settled=[],already=[])


def test_original_freeze_mismatch_blocks_and_canonical_settled_skips(tmp_path):
    tri,freeze,src=inputs(tmp_path)
    freeze["rows"][0]["freeze_at_utc"]="2026-10-29T00:00:00Z"
    with pytest.raises(ValueError,match="ORIGINAL_PREMATCH_FREEZE_LINEAGE_CONFLICT"):
        build_candidates(tri,freeze,[src],root=tmp_path,api_settled=[],already=[])
    freeze["rows"][0]["freeze_at_utc"]="2026-10-25T03:50:08Z"
    rows,rejected=build_candidates(tri,freeze,[src],root=tmp_path,api_settled=[{"fixture_id":"1490574"}],already=[])
    assert not rows and rejected[0]["reason"]=="UNKNOWN_OR_ALREADY_CANONICAL_FINAL"


def test_hash_chain_detects_mutated_row(tmp_path):
    tri,freeze,src=inputs(tmp_path)
    rows,_=build_candidates(tri,freeze,[src],root=tmp_path,api_settled=[],already=[])
    path=tmp_path/"ledger.jsonl"
    append(path,rows)
    x=json.loads(path.read_text())
    x["fulltime_home_goals"]=7
    path.write_text(json.dumps(x)+"\n")
    with pytest.raises(ValueError,match="INDEPENDENT_FT_CHAIN_INVALID"):
        validated_ledger(path)
