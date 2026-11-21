"""Only SHA-valid prospectively-frozen and independently settled rows count."""
import json
from pathlib import Path
from tools.matrix_independent_over25_prematch_freeze import canonical,SCHEMA,digest
from tools.matrix_independent_over25_research_scorecard import evaluate

def sample(root):
    folder=root/"evidence/football_research_freezes/2026-11-04"
    (folder/"sources").mkdir(parents=True,exist_ok=True)
    forecast={"schema":SCHEMA,"provider_fixture_id":"555",
       "provider_competition_id":"2019",
       "research_probability_over25":0.6,
       "kickoff_utc":"2026-11-04T20:00:00+00:00",
       "sealed_at_utc":"2026-11-04T12:00:00+00:00"}
    p=folder/"555_sealed.json";p.write_bytes(canonical(forecast))
    raw=b'{"status":"FINISHED","id":555}'
    h=digest(raw)
    (folder/"sources"/(h+".json")).write_bytes(raw)
    settlement={"schema":"MATRIX_INDEPENDENT_OVER25_SETTLED_RESEARCH_V1",
        "fixture_id":"555","competition_id":"2019",
        "kickoff_utc":"2026-11-04T20:00:00+00:00",
        "forecast_frozen_at_utc":"2026-11-04T12:00:00+00:00",
        "result_observed_at_utc":"2026-11-04T23:00:00+00:00",
        "research_probability_over25":0.6,
        "forecast_sha256":digest(p.read_bytes()),"raw_result_sha256":h,
        "home_goals":2,"away_goals":1,"over25_outcome":1,
        "brier_loss":0.16,"telegram_signal_authorized":False,
        "real_money":"BLOCKED"}
    result=folder/"555_result_abc.json";result.write_bytes(canonical(settlement))
    return p,result

def test_true_out_of_sample_scorecard(tmp_path):
    sample(tmp_path)
    r=evaluate(tmp_path)
    assert r["total_verified_settled_rows"]==1
    assert r["provider_competitions"][0]["source_competition_id"]=="2019"
    assert r["provider_competitions"][0]["mean_brier"]==0.16
    assert r["provider_competitions"][0]["at_least_30_rows"] is False
    assert r["original_six_league_parity_certified"] is False
    assert r["telegram_signal_authorized"] is False

def test_changed_final_result_is_excluded(tmp_path):
    _,p=sample(tmp_path)
    r=json.loads(p.read_text());r["over25_outcome"]=0
    p.write_bytes(canonical(r))
    out=evaluate(tmp_path)
    assert out["total_verified_settled_rows"]==0
    assert len(out["rejected_settlements"])==1

def test_missing_exact_original_prediction_is_excluded(tmp_path):
    p,_=sample(tmp_path)
    p.write_text("{}")
    out=evaluate(tmp_path)
    assert out["total_verified_settled_rows"]==0
    assert len(out["rejected_settlements"])==1
