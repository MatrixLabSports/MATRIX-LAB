"""Research-only source classification regression tests."""
import json
from tools.matrix_over25_noncanonical_probability_recovery import inspect, tracked_report_path

REG="evidence/api_football/governance/alternative_producer_original_six_league_registry.json"
BASE="evidence/api_football/daily_prematch_reports/2026-10-24/over25_shadow_ev/sample.json"

def fixture(tmp_path,rows):
    r=tmp_path/REG
    r.parent.mkdir(parents=True)
    r.write_text(json.dumps({"schema":"MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1",
      "scope_approved":True,"original_six_league_ids":["39","61","78","135","140","239"]}))
    p=tmp_path/BASE
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"all_rows":rows,"signal_generation_authorized":True,
      "probability_status":"FROZEN_GOVERNED_MARKET_SCOPED_SIGNAL_ONLY"}))
    return BASE

def test_only_expected_daily_lanes():
    assert tracked_report_path(BASE)
    assert not tracked_report_path("evidence/tennis_signals/2026-10-24/sample.json")
    assert not tracked_report_path("evidence/api_football/daily_prematch_reports/2026-10-24/other/sample.json")

def test_numeric_probability_not_equivalent_to_triplet(tmp_path):
    source=fixture(tmp_path,[{"fixture_id":"10","league_id":"39","p_matrix":0.65}])
    r=inspect(tmp_path,[source])
    assert r["tracked_report_file_count"]==1
    assert r["counts"]["numeric_probability_rows_unverified"]==1
    assert r["strict_original_alternative_result_triplet_certified"]==0
    assert r["production_p_matrix_authorized"] is False
    assert r["telegram_signal_authorized"] is False

def test_invalid_probability_is_not_counted(tmp_path):
    source=fixture(tmp_path,[{"p_matrix":True},{"p_matrix":1.05},{"p_matrix":-0.1}])
    r=inspect(tmp_path,[source])
    assert r["counts"]["rows_examined"]==3
    assert r["counts"].get("numeric_probability_rows_unverified",0)==0

def test_empty_report_fails_closed(tmp_path):
    source=fixture(tmp_path,[])
    (tmp_path/source).write_text("")
    r=inspect(tmp_path,[source])
    assert r["unreadable_report_count"]==1
    assert r["counts"].get("numeric_probability_rows_unverified",0)==0

def test_unrelated_source_not_promoted(tmp_path):
    fixture(tmp_path,[{"p_matrix":0.65}])
    r=inspect(tmp_path,["evidence/football_world_inventory/other.json"])
    assert r["tracked_report_file_count"]==0
    assert r["strict_original_alternative_result_triplet_certified"]==0

def test_original_shadow_probability_field_is_discovered_without_promotion(tmp_path):
    source=fixture(tmp_path,[{"fixture_id":"10","league_id":"39",
                              "p_over_2_5":0.61}])
    report=inspect(tmp_path,[source])
    assert report["counts"]["rows_with_numeric_p_over_2_5_field"]==1
    assert report["counts"].get("rows_with_numeric_p_matrix_field",0)==0
    assert report["six_original_leagues"]["39"]["rows_with_numeric_probability"]==1
    assert report["production_p_matrix_authorized"] is False

def test_conflicting_fields_not_silently_equated(tmp_path):
    source=fixture(tmp_path,[{"fixture_id":"20","league_id":"39",
                              "p_matrix":0.61,"p_over_2_5":0.70}])
    report=inspect(tmp_path,[source])
    assert report["counts"]["rows_with_conflicting_numeric_probability_fields"]==1
    assert report["numeric_probability_sample_without_values"][0]["two_numeric_fields_consistent"] is False
    assert report["strict_original_alternative_result_triplet_certified"]==0

def test_repeated_snapshots_are_not_unique_events(tmp_path):
    name=fixture(tmp_path,[{"fixture_id":"10","league_id":"39","p_over_2_5":0.61},
                           {"fixture_id":"10","league_id":"39","p_over_2_5":0.62},
                           {"fixture_id":"12","league_id":"39","p_over_2_5":0.63}])
    result=inspect(tmp_path,[name])
    assert result["six_original_leagues"]["39"]["rows_with_numeric_probability"]==3
    assert result["six_original_leagues"]["39"]["distinct_identified_fixture_ids_with_numeric_probability"]==2
    assert result["production_p_matrix_authorized"] is False
