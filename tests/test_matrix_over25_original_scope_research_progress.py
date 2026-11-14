"""Offline regression: original cohort ledger admits only authentic prematch sources."""
import base64
import hashlib
import json
from pathlib import Path

from tools.matrix_over25_original_scope_research_progress import assess, attest

CID=("39","61","78","135","140","239")
LEAGUE_NAMES=("Premier League","Ligue 1","Bundesliga","Serie A","LaLiga","Primera A")

def serial(obj):
    return (json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()

def save(root,rel,obj):
    path=root/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=serial(obj)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest(),rel

def registry(root):
    save(root,"evidence/api_football/governance/alternative_producer_original_six_league_registry.json",
         {"schema":"MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1",
          "scope_approved":True,"original_six_league_ids":list(CID),
          "leagues":[{"id":id,"name":name} for id,name in zip(CID,LEAGUE_NAMES)],
          "real_money":"BLOCKED"})

def frozen(root,cid="2021",fid="123",*,too_late=False,corrupt=False):
    folder="evidence/football_research_freezes/2026-11-06"
    kickoff="2026-11-06T20:00:00+00:00"
    before="2026-11-05T15:00:00+00:00"
    raw=json.dumps({"matches":[]}).encode()
    raw_sha=hashlib.sha256(raw).hexdigest()
    intake={"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
       "source":"FOOTBALL_DATA_ORG","signal_generation_authorized":False,
       "fixtures":[{"source_fixture_id":fid,
                    "source_competition_id":int(cid),
                    "source_status":"TIMED","kickoff_utc":kickoff}]}
    shadow={"schema":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
       "source":"FOOTBALL_DATA_ORG","market_signal_authorized":False,
       "parameter_refit":False,
       "authenticated_raw_group_replay_evidence":{cid:{
           "observed_at_utc":"2026-11-05T15:01:00+00:00",
           "response_base64":base64.b64encode(raw).decode(),
           "source_payload_sha256":raw_sha}},
       "scored":[{"source_fixture_id":fid,"competition_id":int(cid),
                  "kickoff_utc":kickoff,"p_over25_research":0.61}]}
    intsha,intpath=save(root,folder+"/sources/PLACEHOLDER.json",intake)
    # rewrite to immutable sha file
    (root/intpath).rename(root/folder/"sources"/(intsha+".json"))
    shsha,shpath=save(root,folder+"/sources/SHADOW.json",shadow)
    (root/shpath).rename(root/folder/"sources"/(shsha+".json"))
    row={"schema":"MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1",
       "provider":"FOOTBALL_DATA_ORG","provider_competition_id":cid,
       "provider_fixture_id":fid,"real_money":"BLOCKED",
       "telegram_signal_authorized":False,"automatic_wagering":False,
       "production_p_matrix_authorized":False,
       "original_vs_alternative_equivalence_certified":False,
       "scientific_holdout_certified":False,
       "frozen_calibrated_model_parameters_mutated":False,
       "intake_captured_at_utc":before,
       "history_captured_at_utc":"2026-11-05T15:01:00+00:00",
       "model_calculated_at_utc":"2026-11-05T15:02:00+00:00",
       "sealed_at_utc":kickoff if too_late else "2026-11-05T15:03:00+00:00",
       "kickoff_utc":kickoff,"source_history_home_count":5,
       "source_history_away_count":6,"research_probability_over25":0.61,
       "source_intake_file_path":folder+"/sources/"+intsha+".json",
       "source_intake_file_sha256":intsha,
       "source_shadow_file_path":folder+"/sources/"+shsha+".json",
       "source_shadow_file_sha256":shsha,
       "source_snapshot_sha256":"0"*64 if corrupt else raw_sha}
    _,p=save(root,folder+"/"+fid+"_"+shsha[:20]+".json",row)
    return root/p

def test_prospective_shas_and_original_scope_are_separate(tmp_path):
    registry(tmp_path)
    original=frozen(tmp_path,"2021","123")
    brazil=frozen(tmp_path,"2013","456")
    x=assess(tmp_path)
    assert x["unique_sha_attested_research_freezes_in_original_scope"]==1
    assert x["per_league"][0]["eligible_prematch_research_fixture_count"]==1
    assert x["per_league"][0]["remaining_to_research_screening_30"]==29
    assert x["per_league"][5]["eligible_prematch_research_fixture_count"]==0
    assert x["out_of_scope_or_invalid_counts"]["OTHER_COMPETITION_NOT_PART_OF_ORIGINAL_SIX"]==1
    assert x["same_fixture_cross_provider_pit_pairs"]==0
    assert x["telegram_signal_authorized"] is False
    assert x["production_p_matrix_authorized"] is False
    assert attest(tmp_path,original,{})["original_league_id"]=="39"
    assert attest(tmp_path,brazil,{})["original_league_id"] is None

def test_any_late_freeze_fails_closed(tmp_path):
    registry(tmp_path)
    frozen(tmp_path,too_late=True)
    x=assess(tmp_path)
    assert x["unique_sha_attested_research_freezes_in_original_scope"]==0
    assert x["out_of_scope_or_invalid_counts"]["INVALID_SHA_OR_PREMATCH_EVIDENCE"]==1

def test_any_raw_provider_hash_mismatch_fails_closed(tmp_path):
    registry(tmp_path)
    frozen(tmp_path,corrupt=True)
    x=assess(tmp_path)
    assert x["unique_sha_attested_research_freezes_in_original_scope"]==0

def test_intake_shadow_sha_mismatch_fails_closed(tmp_path):
    registry(tmp_path)
    row=frozen(tmp_path)
    sourcefile=next((tmp_path/"evidence/football_research_freezes/2026-11-06/sources").glob("*.json"))
    sourcefile.write_bytes(b'{"tampered":true}')
    x=assess(tmp_path)
    assert x["unique_sha_attested_research_freezes_in_original_scope"]==0

def test_modified_approved_league_scope_blocks(tmp_path):
    registry(tmp_path)
    path=tmp_path/"evidence/api_football/governance/alternative_producer_original_six_league_registry.json"
    obj=json.loads(path.read_text())
    obj["original_six_league_ids"]=["39","61","78","135","140","2013"]
    path.write_bytes(serial(obj))
    try:
        assess(tmp_path)
    except ValueError as e:
        assert str(e)=="ORIGINAL_SIX_LEAGUE_SCOPE_CHANGED"
    else:
        raise AssertionError("Original six league registry silently changed")
