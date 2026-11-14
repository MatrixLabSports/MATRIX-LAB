import json

from tools.api_football_extended_team_models import _poisson_over, build_lane


def test_poisson_over_probability_is_bounded_and_line_sensitive():
    low=_poisson_over(9.0,7.5)
    high=_poisson_over(9.0,10.5)
    assert 0.0 < high < low < 1.0


def test_model_stays_sealed_below_minimum_train(tmp_path):
    path=tmp_path/"lane.jsonl"
    rows=[]
    for i in range(249):
        rows.append({
            "fixture_id":str(i),
            "split":"TRAIN" if i<199 else "VALIDATION",
            "target_total":10.0,
            "expected_total":9.0,
        })
    path.write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf-8")
    result=build_lane("CORNERS",path)
    assert result["status"]=="SEALED_INSUFFICIENT_HISTORICAL_OOS"
    assert result["metrics_opened"] is False
    assert result["prospective_eligible"] is False


def test_model_opens_only_with_200_train_and_50_validation(tmp_path):
    path=tmp_path/"lane.jsonl"
    rows=[]
    for i in range(250):
        rows.append({
            "fixture_id":str(i),
            "split":"TRAIN" if i<200 else "VALIDATION",
            "target_total":8.0 + (i%4),
            "expected_total":8.5 + ((i%3)-1)*0.5,
        })
    path.write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf-8")
    result=build_lane("CORNERS",path)
    assert result["metrics_opened"] is True
    assert result["validation"]["baseline"]["sample_size"]==50
    assert result["validation"]["challenger"]["sample_size"]==50
    assert result["validation_used_for_parameter_tuning"] is False
