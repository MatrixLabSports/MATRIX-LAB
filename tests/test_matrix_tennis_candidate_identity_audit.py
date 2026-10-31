import json
from tools.matrix_tennis_candidate_identity_audit import audit, INPUT

def test_real_46_leads_remain_unverified():
    raw=json.loads(INPUT.read_text(encoding="utf-8"))
    report=audit(raw)
    assert report["candidate_sofascore_events"] == 46
    assert report["unverified"] == 46
    assert report["individually_verified"] == 0
    assert report["signals_authorized"] == 0
    assert all(r["requires_two_sides"] for r in report["records"])
    assert all(not r["event_certified"] for r in report["records"])

def test_no_review_candidates_without_options():
    import pytest
    with pytest.raises(ValueError):
        audit({"target_date":"2026-10-31","cross_source_matches_certified":0,
               "signals_authorized":0,
               "candidates":[{"sofascore_url":"a","sofascore_name":"b","candidates":[]}]})

def test_previously_certified_input_rejected():
    import pytest
    with pytest.raises(ValueError):
        audit({"target_date":"2026-10-31","cross_source_matches_certified":1,
               "signals_authorized":0,"candidates":[]})
