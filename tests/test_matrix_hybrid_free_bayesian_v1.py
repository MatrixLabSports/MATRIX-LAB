"""Physical source evidence tests for isolated hybrid Bayesian research.

All real fixtures are from the frozen 2026-11-21 prospective cohort. No
outcome from that day is read to generate the Bayesian forecast.
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from tools import matrix_hybrid_free_bayesian_v1 as engine

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT/"evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json"
NOW = datetime(2026,11,19,9,45,tzinfo=timezone.utc)


def load():
    return json.loads(MANIFEST.read_bytes())


def test_real_37_research_only_bayesian_forecasts_from_authenticated_raw_history():
    result = engine.build(ROOT,load(),NOW)
    assert result["scored_count"] == 37, result["blocked"]
    assert result["blocked_count"] == 0
    assert len({r["physical_event_id"] for r in result["scored"]}) == 37
    assert len({r["provider_competition_id"] for r in result["scored"]}) == 6
    assert all(r["certified_before_prediction_historical_pool_count"] >= 30 for r in result["scored"])
    assert all(0 < r["p_bayesian_research_over25"] < 1 for r in result["scored"])
    assert all(r["forecast_frozen_at_utc"] < r["event_start_at_utc"] for r in result["scored"])
    assert all(r["target_outcome_not_used"] is True for r in result["scored"])
    assert all(r["original_official_p_matrix_parity_certified"] is False for r in result["scored"])
    assert all(r["telegram_signal_authorized"] is False for r in result["scored"])
    assert result["original_calibrated_parameters_modified"] is False


def test_bayesian_is_not_relabelled_original_matrix_probability():
    result=engine.build(ROOT,load(),NOW)
    assert result["formal_original_matrix_p_comparison_allowed"] is False
    assert result["automatic_model_promotion"] is False
    assert result["real_money"] == "BLOCKED"
    # This is genuinely a distinct model, not a copy of free-source Poisson.
    source=load()
    p={r["physical_event_id"]:r["independent_free_poisson_p"] for r in source["prelabel_research_pairs"]}
    assert any(abs(row["p_bayesian_research_over25"]-p[row["physical_event_id"]])>0.001
               for row in result["scored"])


def test_bad_source_sha_rejected_with_no_fabricated_result():
    doc=load()
    doc["prelabel_research_pairs"]=doc["prelabel_research_pairs"][:1]
    doc["recovered_research_pair_count"]=1
    doc["prelabel_research_pairs"][0]["original_freeze_sha256"]="0"*64
    result=engine.build(ROOT,doc,NOW)
    assert result["scored_count"]==0
    assert result["blocked_count"]==1
    assert "HYBRID_PAIR_RECEIPT_DOES_NOT_MATCH_PHYSICAL_BYTES" in result["blocked"][0]["reason"]


def test_after_kickoff_no_new_bayesian_probability():
    result=engine.build(ROOT,load(),datetime(2026,11,22,20,tzinfo=timezone.utc))
    assert result["scored_count"]==0
    assert result["blocked_count"]==37
    assert result["real_money"]=="BLOCKED"


def test_manifest_cannot_claim_official_hybrid_gate_open():
    doc=load()
    doc["formal_hybrid_elite_lab_rows_admitted"]=1
    try:
        engine.build(ROOT,doc,NOW)
        assert False,"should have refused model promotion"
    except ValueError as err:
        assert "HYBRID_RESEARCH_PAIR_MANIFEST_UNTRUSTED" in str(err)


def test_empty_manifest_never_creates_fake_observations():
    doc=load()
    doc["prelabel_research_pairs"]=[]
    doc["recovered_research_pair_count"]=0
    result=engine.build(ROOT,doc,NOW)
    assert result["scored_count"]==0
    assert result["blocked_count"]==0
    assert result["telegram_signal_authorized"] is False


def test_select_new_first_time_and_expired_never_backfills(tmp_path):
    doc=load()
    doc["prelabel_research_pairs"]=doc["prelabel_research_pairs"][:1]
    doc["recovered_research_pair_count"]=1
    scoped, already, expired=engine.select_new_prospective(tmp_path,doc,NOW)
    assert len(scoped["prelabel_research_pairs"])==1
    assert (already,expired)==(0,0)
    after=datetime(2026,11,23,tzinfo=timezone.utc)
    scoped, already, expired=engine.select_new_prospective(tmp_path,doc,after)
    assert len(scoped["prelabel_research_pairs"])==0
    assert (already,expired)==(0,1)


def test_dynamic_bogota_date_for_future_cohorts(tmp_path):
    entry={"physical_event_id":"999001","event_start_at_utc":"2026-12-05T02:00:00Z"}
    path=engine.freeze_path(tmp_path,entry)
    assert "2026-12-04" in str(path)
    assert path.name=="999001.json"


def test_conflicting_existing_bayesian_file_never_overwritten(tmp_path):
    doc=load()
    doc["prelabel_research_pairs"]=doc["prelabel_research_pairs"][:1]
    doc["recovered_research_pair_count"]=1
    entry=doc["prelabel_research_pairs"][0]
    path=engine.freeze_path(tmp_path,entry)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({"schema":"bogus","real_money":"BLOCKED"}))
    try:
        engine.select_new_prospective(tmp_path,doc,NOW)
        assert False,"failed to block immutable overwrite"
    except (ValueError,KeyError) as e:
        assert str(e) in ("BAYESIAN_PRIOR_IMMUTABLE_FILE_CONFLICT", "'forecast_frozen_at_utc'")
