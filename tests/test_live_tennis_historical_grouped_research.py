"""Group-split historical Live Tennis research has zero authority to send signals."""
import hashlib
import json
from pathlib import Path

import pytest

from tools.live_tennis_historical_grouped_research import (
    evidence,fit_research,metrics,score_state,SCHEMA,PROVIDER
)
from tools.live_tennis_model_gate import FEATURES_V0_1
from tools.live_tennis_presettlement_builder import fold_for_match

def sample(mid=100,label=1,**edits):
    row={
        "provider":PROVIDER,"match_id":mid,"tour":"itf","gender":"women",
        "surface":"hard","quality_state_valid":True,"origin":"observed",
        "stale":False,"corroborated":True,"sources_count":2,
        "sets_p1":1,"sets_p2":0,
        "set_diff_p1":1,"total_game_diff_p1":2,
        "current_set_game_diff_p1":1,"point_diff_p1":0,
        "server_is_p1":True,"ranking_advantage_p1":mid%30,
        "is_tiebreak":False,"age_seconds":30,"observed_age_seconds":3,
        "label_opened":True,"settlement_status":"FINAL_STANDARD",
        "p1_match_win":label,"captured_at_utc":"2026-11-17T12:05:00+00:00",
    }
    return {**row,**edits}

def write_research_inputs(tmp_path, *, flip_holdout=False):
    base=tmp_path/"evidence/live_tennis_lab"
    daily=base/"2026-11-17"
    daily.mkdir(parents=True,exist_ok=True)
    selected=[]
    dev=hold=0
    n=1000
    while dev<34 or hold<10:
        fold=fold_for_match(n)
        if fold==4 and hold<10:
            hold+=1
        elif fold!=4 and dev<34:
            dev+=1
        else:
            n+=1
            continue
        label=n%2
        if flip_holdout and fold==4:
            label=1-label
        selected.append(sample(mid=n,label=label))
        n+=1
    path=daily/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"
    data={"schema":"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1",
          "states":selected}
    path.write_text(json.dumps(data),encoding="utf-8")
    rel=path.relative_to(tmp_path).as_posix()
    src_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    cumulative={
        "schema":"MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1",
        "probability_output_status":"SEALED",
        "multi_lane_ambiguity_quarantined_from_all_gate_counts":True,
        "source_ledgers":[{"path":rel,"sha256":src_hash}],
    }
    cfile=base/"MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1.json"
    cfile.write_text(json.dumps(cumulative),encoding="utf-8")
    cumulative_hash=hashlib.sha256(cfile.read_bytes()).hexdigest()
    integrity={
        "schema":"MATRIX_LIVE_TENNIS_CUMULATIVE_INTEGRITY_RESEARCH_V1",
        "source_cumulative_sha256":cumulative_hash,
        "production_p_live_authorized":False,
        "real_money":"BLOCKED",
        "source_daily_ledgers":1,
        "source_daily_ledger_hashes":{rel:src_hash},
        "quarantined_physical_match_keys":[],
        "lane_research_counts":[
            {"lane":"itf|women|hard","research_integrity_clear":True,
             "research_count_threshold_30_met":True}
        ],
    }
    (base/"MATRIX_LIVE_TENNIS_CUMULATIVE_INTEGRITY_RESEARCH_LAST.json").write_text(json.dumps(integrity))
    return tmp_path

def test_missing_features_refused_not_filled():
    good=sample()
    assert len(score_state(good))==len(FEATURES_V0_1)
    assert score_state(sample(ranking_advantage_p1=None)) is None
    assert score_state(sample(observed_age_seconds=None)) is None
    assert score_state(sample(corroborated=False)) is None
    assert score_state(sample(sources_count=1)) is None
    assert score_state(sample(sets_p1=2)) is None
    assert score_state(sample(server_is_p1=None)) is None

def test_metrics_perfect_predictions_have_correct_direction():
    d=metrics([0,0,1,1],[0.01,0.1,0.9,0.99])
    assert d["auc"]==1.0
    assert d["brier"]<0.01
    assert d["log_loss"]<0.1

def test_model_requires_both_train_outcome_classes():
    x=[0.0]*len(FEATURES_V0_1)
    with pytest.raises(ValueError,match="DEVELOPMENT_REQUIRES_BOTH_OUTCOMES"):
        fit_research([(x,0)]*30)

def test_grouped_retrospective_research_is_not_production_or_prospective(tmp_path):
    report=evidence(write_research_inputs(tmp_path))
    assert report["schema"]==SCHEMA
    assert report["source_daily_ledgers_verified"]==1
    assert report["retrospective_research_lanes_with_metrics"]==1
    lane=report["per_lane"][0]
    assert lane["retrospective_grouped_research_training_executed"]
    assert lane["development_unique_matches"]==34
    assert lane["holdout_unique_matches"]==10
    assert lane["holdout_metrics"]["brier"] is not None
    assert lane["production_p_live_authorized"] is False
    assert report["production_p_live_authorized"] is False
    assert report["telegram_signal_authorized"] is False
    assert report["independently_pre_registered_prospective_holdout_complete"] is False
    assert report["real_money"]=="BLOCKED"

def test_changing_only_retrospective_heldout_labels_cannot_change_development_model(tmp_path):
    first=evidence(write_research_inputs(tmp_path))
    before=first["per_lane"][0]["fixed_research_model_sha256"]
    second=evidence(write_research_inputs(tmp_path,flip_holdout=True))
    after=second["per_lane"][0]["fixed_research_model_sha256"]
    assert before==after
    assert second["per_lane"][0]["holdout_unique_matches"]==10
    assert first["per_lane"][0]["holdout_metrics"]!=second["per_lane"][0]["holdout_metrics"]

def test_source_hash_drift_rejected_before_research_training(tmp_path):
    root=write_research_inputs(tmp_path)
    p=root/"evidence/live_tennis_lab/2026-11-17/MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"
    p.write_bytes(p.read_bytes()+b" ")
    with pytest.raises(ValueError,match="RESEARCH_LEDGER_SOURCE_SHA_CHANGED"):
        evidence(root)
