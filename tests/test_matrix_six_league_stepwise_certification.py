"""Five-stage certification must never treat prior historical values as OOS."""
import hashlib
import json
from pathlib import Path
from tools.matrix_six_league_stepwise_certification import assess, original_reports, alternative_refs

SCOPE="evidence/api_football/governance/alternative_producer_original_six_league_registry.json"
LINEAGE="evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_LAST.json"
SHADOW="evidence/api_football/daily_prematch_reports/2026-10-08/over25_shadow_ev/probabilities.json"
REG="evidence/api_football/prospective_daily/2026-10-08/20261008T080000Z/fixtures/future_fixture_registry.json"

def put(root,name,value):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value),encoding="utf-8")
    return hashlib.sha256(p.read_bytes()).hexdigest()

def fixture(root,with_report=True):
    ids=["39","61","78","135","140","239"]
    put(root,SCOPE,{"schema":"MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1",
        "scope_approved":True,"real_money":"BLOCKED",
        "telegram_signal_authorized":False,"original_six_league_ids":ids})
    hashvalue=put(root,REG,{"provider":"api_football",
        "captured_at_utc":"2026-10-08T08:00:00Z",
        "future_only":True,"events":[]})
    put(root,LINEAGE,{
        "schema":"MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_V1",
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "source_registry_catalog_by_sha256":{hashvalue:REG},
        "identity_rows":[{"fixture_id":"123","league_id":"39",
            "status":"ORIGINAL_FIXTURE_IDENTITY_RECOVERED",
            "original_kickoff_utc":"2026-10-08T18:00:00+00:00"}]})
    files=[LINEAGE,REG]
    if with_report:
        put(root,SHADOW,{"generated_at_utc":"2026-10-08T09:00:00Z",
            "all_rows":[{"fixture_id":"123","kickoff_utc":"2026-10-08T18:00:00Z",
                "p_over_2_5":0.62,"league_id":"39"}]})
        files.append(SHADOW)
    return files

def test_one_real_source_claim_does_not_certify_alternative(tmp_path):
    files=fixture(tmp_path)
    out=assess(tmp_path,files)
    assert out["counts"]["39"]["original_identity_valid"]==1
    assert out["counts"]["39"]["original_number_reported_pre_kickoff"]==1
    assert out["counts"]["39"]["validated_prospective_rows"]==0
    assert out["fixture_decisions"][0]["status"]=="ORIGINAL_NUMBER_FOUND_NOT_INDEPENDENTLY_FROZEN"
    assert out["fixture_decisions"][0]["original_probability_source"]["sha256"]
    assert out["steps"]["step_3_manifest"]=="MISSING"
    assert out["production_p_matrix_authorized"] is False
    assert out["telegram_signal_authorized"] is False

def test_no_source_does_not_create_forecast(tmp_path):
    files=fixture(tmp_path,False)
    out=assess(tmp_path,files)
    assert out["fixture_decisions"][0]["status"]=="ORIGINAL_PREMATCH_PROBABILITY_NOT_VERIFIED"
    assert out["scientific_six_league_validation_passed"] is False

def test_corrupted_original_source_hash_fails_closed(tmp_path):
    files=fixture(tmp_path)
    target=tmp_path/REG
    target.write_text('{"tampered":true}',encoding="utf-8")
    try:assess(tmp_path,files)
    except ValueError as error:assert "SHA_MISMATCH" in str(error)
    else:raise AssertionError("tampered source passed")

def test_late_report_cannot_be_retroactively_frozen(tmp_path):
    files=fixture(tmp_path)
    p=tmp_path/SHADOW
    d=json.loads(p.read_text());d["generated_at_utc"]="2026-10-08T19:00:00Z"
    p.write_text(json.dumps(d))
    out=assess(tmp_path,files)
    assert out["counts"]["39"]["original_number_reported_pre_kickoff"]==0
    assert out["fixture_decisions"][0]["status"]=="ORIGINAL_PREMATCH_PROBABILITY_NOT_VERIFIED"

def test_filenames_do_not_prove_independent_snapshot(tmp_path):
    files=fixture(tmp_path)
    files.append("evidence/football_world_inventory/MATRIX_ALTERNATIVE_PRODUCER_FAKE.json")
    out=assess(tmp_path,files)
    assert out["alternative_named_source_file_count"]==1
    assert out["counts"]["39"]["alternative_genuine_prematch_pair"]==0
    assert out["counts"]["39"]["three_independent_source_pairs_verified"]==0

def test_same_fixture_conflicting_old_probabilities_are_not_selected(tmp_path):
    files=fixture(tmp_path)
    second=SHADOW.replace("probabilities.json","alternate.json")
    put(tmp_path,second,{"generated_at_utc":"2026-10-08T10:00:00Z",
        "all_rows":[{"fixture_id":"123","kickoff_utc":"2026-10-08T18:00:00Z",
                     "p_over_2_5":0.73,"league_id":"39"}]})
    out=assess(tmp_path,files+[second])
    assert out["fixture_decisions"][0]["status"]=="CONFLICTING_ORIGINAL_PROBABILITIES"
    assert out["counts"]["39"]["original_number_reported_pre_kickoff"]==0

def test_postmatch_raw_independent_source_not_promoted(tmp_path):
    files=fixture(tmp_path)
    raw="evidence/football_cohort_recovery/FOOTBALL_DATA_ORG_RAW_LAST.json"
    put(tmp_path,raw,{"matches":[{"id":100,"status":"FINISHED"}]})
    out=assess(tmp_path,files+[raw])
    assert out["alternative_raw_provenance_profile"]["completed_match_rows"]==1
    assert out["alternative_raw_provenance_profile"]["prospective_frozen_forecasts_certified"]==0
    assert out["counts"]["39"]["alternative_genuine_prematch_pair"]==0

def test_canonical_intake_empty_remains_telegram_blocked(tmp_path):
    files=fixture(tmp_path)
    name="evidence/notifications/telegram/MATRIX_BROWSER_GOVERNED_INTAKE_LAST.json"
    put(tmp_path,name,{"schema":"MATRIX_BROWSER_GOVERNED_INTAKE_SYNC_V1",
      "real_money":"BLOCKED","status":"NO_GOVERNED_CANONICAL_ROWS",
      "candidate_count":0,"telegram_signal_authorized":False})
    out=assess(tmp_path,files+[name])
    assert out["telegram_governed_intake_profile"]["governed_candidate_count"]==0
    assert out["steps"]["step_5_telegram"].startswith("BLOCKED")
    assert out["telegram_signal_authorized"] is False
