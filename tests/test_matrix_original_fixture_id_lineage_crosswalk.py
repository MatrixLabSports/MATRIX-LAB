"""Frozen original fixture IDs must have noncontradictory pre-kickoff source."""
import json
from pathlib import Path
from tools.matrix_original_fixture_id_lineage_crosswalk import examine

RID="evidence/api_football/governance/alternative_producer_original_six_league_registry.json"
BASE="evidence/api_football/prospective_daily/2026-10-08/20261008T080000Z"
FIX=BASE+"/fixtures/future_fixture_registry.json"
CAP=BASE+"/fixtures/capture_manifest.json"
SHADOW="evidence/api_football/daily_prematch_reports/2026-10-08/over25_shadow_ev/sample.json"

def put(root,name,data):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data),encoding="utf-8")
    return name

def setup(root,league="39",at="2026-10-08T08:00:00Z",kickoff="2026-10-08T18:00:00Z"):
    put(root,RID,{"schema":"MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1",
        "scope_approved":True,"original_six_league_ids":["39","61","78","135","140","239"]})
    put(root,FIX,{"provider":"api_football","future_only":True,"captured_at_utc":at,
        "events":[{"provider_fixture_id":"123456","provider_league_id":league,
           "provider_home_team_id":"55","provider_away_team_id":"66",
           "event_start_utc":kickoff}]})
    put(root,CAP,{"provider":"api_football","status":"PASS",
        "verified_successful_provider_response":True,"captured_at_utc":at})
    put(root,SHADOW,{"generated_at_utc":"2026-10-08T09:00:00Z",
        "all_rows":[{"fixture_id":"123456","kickoff_utc":kickoff,
                     "p_over_2_5":0.65}]})
    return [FIX,SHADOW]

def test_verified_unique_original_identity_never_promotes(tmp_path):
    x=examine(tmp_path,setup(tmp_path))
    assert x["identity_status_counts"]["ORIGINAL_FIXTURE_IDENTITY_RECOVERED"]==1
    assert x["selected_league_identity_counts"]["39"]["recovered_unique_fixture_ids"]==1
    assert x["identity_rows"][0]["evidence_registry_sha256"]
    assert x["strict_original_alternative_result_triplets_certified"]==0
    assert x["telegram_signal_authorized"] is False

def test_conflicting_league_claim_fails_closed(tmp_path):
    paths=setup(tmp_path)
    p=tmp_path/SHADOW
    d=json.loads(p.read_text());d["all_rows"][0]["league_id"]="61"
    p.write_text(json.dumps(d))
    x=examine(tmp_path,paths)
    assert x["identity_status_counts"]["ORIGINAL_LEAGUE_ID_CONFLICT"]==1
    assert x["identity_rows"][0]["league_id"] is None

def test_original_calendar_after_kickoff_is_rejected(tmp_path):
    paths=setup(tmp_path,at="2026-10-08T19:00:00Z")
    x=examine(tmp_path,paths)
    assert x["identity_status_counts"]["NO_ORIGINAL_FIXTURE_REGISTRY_MATCH"]==1

def test_missing_original_registry_not_backfilled(tmp_path):
    paths=setup(tmp_path)
    x=examine(tmp_path,[SHADOW])
    assert x["identity_status_counts"]["NO_ORIGINAL_FIXTURE_REGISTRY_MATCH"]==1
    assert x["identity_rows"][0]["league_id"] is None

def test_report_after_kickoff_is_excluded(tmp_path):
    paths=setup(tmp_path)
    p=tmp_path/SHADOW
    d=json.loads(p.read_text());d["generated_at_utc"]="2026-10-08T20:00:00Z"
    p.write_text(json.dumps(d))
    x=examine(tmp_path,paths)
    assert x["original_probability_distinct_fixture_ids_with_known_prematch_report_time"]==0
    assert x["probability_rows_excluded_from_identity_recovery"]["probability_generated_at_or_after_kickoff"]==1
