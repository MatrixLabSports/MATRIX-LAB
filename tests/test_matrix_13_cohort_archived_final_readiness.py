"""Unit checks for a fail-closed, offline archived-FINAL candidate audit."""
import copy
import hashlib
import json
from pathlib import Path

from tools.matrix_13_cohort_archived_final_readiness import build, inspect_receipt

LANES = (
    "TOTAL_GOALS_OVER_UNDER","MATCH_RESULT_1X2","DOUBLE_CHANCE_1X",
    "DOUBLE_CHANCE_X2","DOUBLE_CHANCE_12","TEAM_TOTAL_GOALS_HOME",
    "TEAM_TOTAL_GOALS_AWAY","FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER","FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY","SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
)


def freeze(fid="fixture-1"):
    return {
      "fixture_id":fid,
      "kickoff_utc":"2026-10-31T20:00:00+00:00",
      "freeze_at_utc":"2026-10-31T19:00:00+00:00",
      "home_team_id":"55","away_team_id":"66",
    }


def receipt():
    return {
      "errors":[],"results":1,
      "response":[{
        "fixture":{"id":"fixture-1","date":"2026-10-31T20:00:00+00:00","status":{"short":"FT"}},
        "teams":{"home":{"id":55},"away":{"id":66}},
        "score":{"halftime":{"home":1,"away":0},"fulltime":{"home":2,"away":1}},
        "goals":{"home":2,"away":1},
      }],
    }


def test_verifies_archived_ft_and_half_without_network(tmp_path):
    p=tmp_path/"fixture_fixture-1.bin"
    p.write_text(json.dumps(receipt()),encoding="utf-8")
    r=inspect_receipt(p,freeze())
    assert r["code"]=="VERIFIED_ARCHIVED_STANDARD_FT"
    assert r["halftime_verified"] is True
    assert len(r["raw_sha256"])==64
    assert r["fulltime_score"]==[2,1]


def test_rejects_nonstandard_ft_identity_and_missing(tmp_path):
    p=tmp_path/"fixture_fixture-1.bin"
    assert inspect_receipt(p,freeze())["code"]=="MISSING_ARCHIVED_RESPONSE"
    x=receipt()
    x["response"][0]["teams"]["home"]["id"]=77
    p.write_text(json.dumps(x),encoding="utf-8")
    assert inspect_receipt(p,freeze())["code"]=="TEAM_IDENTITY_MISMATCH"
    x=receipt()
    x["response"][0]["fixture"]["status"]["short"]="AET"
    p.write_text(json.dumps(x),encoding="utf-8")
    assert inspect_receipt(p,freeze())["code"]=="NON_STANDARD_FT_OR_NOT_YET_FINAL"


def test_missing_halftime_never_counted_as_verified(tmp_path):
    p=tmp_path/"fixture_fixture-1.bin"
    x=receipt()
    x["response"][0]["score"]["halftime"]={"home":None,"away":None}
    p.write_text(json.dumps(x),encoding="utf-8")
    out=inspect_receipt(p,freeze())
    assert out["code"]=="VERIFIED_ARCHIVED_STANDARD_FT"
    assert out["halftime_verified"] is False


def test_market_readiness_uses_only_unssettled_fixture_ids(tmp_path):
    raw=tmp_path/"fixture_fixture-1.bin"
    raw.write_text(json.dumps(receipt()),encoding="utf-8")
    registry={"status":"PASS","total_lanes":42,"protections":{"real_money":"BLOCKED"},
              "lanes":{k:{"prospective_unique_count":650} for k in LANES}}
    portfolio=[{"market_lane":k,"fixture_id":"fixture-1","prospective_admitted":True} for k in LANES]
    r=build({"rows":[freeze()]},[],registry,portfolio,tmp_path)
    assert r["target_market_count"]==13
    assert all(x["recoverable_archived_standard_ft_events"]==1 for x in r["lanes"])
    assert all(x["recoverable_archived_halftime_events"]==1 for x in r["lanes"])
    assert all(x["settlements_appended"]==0 for x in r["lanes"])
    assert r["protections"]["real_money"]=="BLOCKED"
    already=build({"rows":[freeze()]},[{"fixture_id":"fixture-1"}],registry,portfolio,tmp_path)
    assert all(x["missing_settlement_event_count"]==0 for x in already["lanes"])


def test_post_kickoff_freeze_is_not_recoverable(tmp_path):
    raw=tmp_path/"fixture_fixture-1.bin"
    raw.write_text(json.dumps(receipt()),encoding="utf-8")
    registry={"status":"PASS","total_lanes":42,"protections":{"real_money":"BLOCKED"},
              "lanes":{k:{"prospective_unique_count":650} for k in LANES}}
    row=freeze();row["freeze_at_utc"]=row["kickoff_utc"]
    r=build({"rows":[row]},[],registry,[{"market_lane":"TOTAL_GOALS_OVER_UNDER",
                                         "fixture_id":"fixture-1","prospective_admitted":True}],tmp_path)
    target=next(x for x in r["lanes"] if x["market_key"]=="TOTAL_GOALS_OVER_UNDER")
    assert target["recoverable_archived_standard_ft_events"]==0
    assert target["reasons"]["NOT_STRICTLY_PREMATCH_FROZEN"]==1


def test_triage_is_one_row_per_missing_fixture_and_is_never_auto_settled(tmp_path):
    p=tmp_path/"fixture_fixture-1.bin"
    p.write_text(json.dumps(receipt()),encoding="utf-8")
    registry={"status":"PASS","total_lanes":42,"protections":{"real_money":"BLOCKED"},
              "lanes":{k:{"prospective_unique_count":650} for k in LANES}}
    portfolio=[{"market_lane":k,"fixture_id":"fixture-1","prospective_admitted":True} for k in LANES]
    r=build({"rows":[freeze()]},[],registry,portfolio,tmp_path)
    assert r["unsettled_fixture_triage_count"]==1
    item=r["unsettled_fixture_triage"][0]
    assert item["fixture_id"]=="fixture-1"
    assert len(item["affected_gate600_lanes"])==13
    assert item["safe_to_settle_from_present_archive"] is True
    assert item["prospective_freeze_not_to_be_rewritten"] is True
    assert r["protections"]["no_auto_provider_retry_or_paid_api_calls"] is True
    assert all(x["settlements_appended"]==0 for x in r["lanes"])
