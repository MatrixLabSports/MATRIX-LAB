import json
import pytest
from tools.matrix_tennis_strict_review import SOURCE, check_option, review

def test_real_123_candidates_remain_uncertified():
    data=json.loads(SOURCE.read_text(encoding="utf-8"))
    report=review(data)
    assert report["candidate_events"]==123
    assert report["certified"]==0
    assert report["signals_authorized"]==0
    assert all(not r["certified"] and not r["date_verified"] and not r["tournament_verified"] for r in report["records"])
    assert all(not o["certified"] for r in report["records"] for o in r["options"])

def test_doubles_full_vs_partial():
    sofa="https://www.sofascore.com/es/tennis/match/adeshina-grammatikopoulou-paganetti-urgesi/x#id:1"
    assert check_option(sofa,"Paganetti V./Urgesi F. - Adeshina E./Grammatikopoulou V.")=="REVIEW_IDENTITY_ONLY"
    assert check_option(sofa,"Urgesi F. - Grammatikopoulou V.")=="REVIEW_IDENTITY_ONLY"
    # Even apparent surname matches are only review candidates, not certification.

def test_missing_second_side():
    assert check_option("https://www.sofascore.com/es/tennis/match/alpha-beta/x#id:1","Alpha vs Beta")=="UNPARSEABLE"

def test_pre_certified_rejected():
    with pytest.raises(ValueError):
        review({"review_only":True,"certified":1,"signals_authorized":0,"candidates":[]})
