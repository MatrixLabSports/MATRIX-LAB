import json
import pytest
from tools.matrix_tennis_structural_identity_guard import classify, INPUT, flash_sides

def test_real_review_snapshot_remains_uncertified():
    raw=json.loads(INPUT.read_text(encoding="utf-8"))
    result=classify(raw)
    assert result["candidate_events"]==123
    assert result["certified"]==0
    assert result["signals_authorized"]==0
    assert result["event_dates_verified"]==0
    assert result["tournaments_verified"]==0
    assert all(not row["event_certified"] for row in result["records"])
    assert all(not opt["event_certified"] for row in result["records"] for opt in row["options"])

def test_both_sides_overlap_and_partial_detected():
    data={"review_only":True,"certified":0,"signals_authorized":0,
          "target_date":"2026-10-31","candidates":[{
          "sofascore_url":"https://www.sofascore.com/es/tennis/match/adeshina-grammatikopoulou-paganetti-urgesi/abc#id:1",
          "sofascore_name":"31/10/26","candidates":[
          {"flashscore_url":"a","flashscore_name":"Paganetti V./Urgesi F. - Adeshina E./Grammatikopoulou V."},
          {"flashscore_url":"b","flashscore_name":"Paganetti V./Urgesi F. - Jialin T./Zaparyniuk A."}]}]}
    r=classify(data)
    assert r["options_both_sides_overlap"]==1
    assert r["options_partial_or_unparseable"]==1
    assert r["certified"]==0

def test_reject_certified_input():
    with pytest.raises(ValueError):
        classify({"review_only":True,"certified":1,"signals_authorized":0,"candidates":[]})

def test_missing_separator_is_not_two_sides():
    assert flash_sides("Player A vs Player B")==[]
