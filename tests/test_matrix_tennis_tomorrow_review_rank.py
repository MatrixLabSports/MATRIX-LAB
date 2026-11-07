import json
import pytest
from tools.matrix_tennis_tomorrow_review_rank import classify, INPUT

def test_real_review_candidates_remain_blocked():
    raw=json.loads(INPUT.read_text(encoding="utf-8"))
    result=classify(raw)
    assert result["candidate_events"] == 123
    assert result["with_multiple_options"] == 14
    assert result["certified"] == 0
    assert result["signals_authorized"] == 0
    assert all(r["status"] == "REVIEW_ONLY" and not r["certified"] for r in result["records"])

def test_equal_best_scores_remain_ambiguous():
    data={"review_only":True,"certified":0,"signals_authorized":0,
          "target_date":"2026-10-31","candidates":[{
          "sofascore_url":"s","sofascore_name":"players",
          "candidates":[{"shared_token_count":2,"flashscore_url":"f1"},
                        {"shared_token_count":2,"flashscore_url":"f2"}]}]}
    report=classify(data)
    assert report["ambiguous_best_score"] == 1
    assert report["certified"] == 0

def test_reject_pre_certified_input():
    with pytest.raises(ValueError):
        classify({"review_only":True,"certified":1,"signals_authorized":0,"candidates":[]})
