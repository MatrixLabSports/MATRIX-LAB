"""Early market preflight must never promote independent research into signals."""
from datetime import datetime,timezone,timedelta
from copy import deepcopy
from tools.matrix_early_research_quote_intake import early_targets_from_docs

NOW=datetime(2026,11,3,23,30,tzinfo=timezone.utc)
def docs():
    intake={"source":"FOOTBALL_DATA_ORG","provider_status":"AUTHENTICATED_FIXTURE_CAPTURE",
        "target_date_bogota":"2026-11-04","generated_at_utc":"2026-11-03T23:00:00Z",
        "real_money":"BLOCKED","signal_generation_authorized":False,
        "fixtures":[{"source_fixture_id":"575387","source":"FOOTBALL_DATA_ORG",
         "home":"Fenerbahçe SK","away":"Liverpool FC","kickoff_utc":"2026-11-04T17:45:00Z"}]}
    sofa={"target_date_bogota":"2026-11-04","real_money":"BLOCKED","signal_generation_authorized":False,
        "sofascore_observed":True,"status":"PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL",
        "matched":[{"fixture_id":"575387","identity_time_and_teams_verified":True,
          "sofascore_event_id":"16938962","kickoff_utc":"2026-11-04T17:45:00Z"}]}
    flash={"target_date_bogota":"2026-11-04","real_money":"BLOCKED","signal_generation_authorized":False,
        "status":"PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS",
        "sofascore_verified":True,"flashscore_verified":True,
        "matched":[{"source_fixture_id":"575387","sofascore_event_id":"16938962",
         "flashscore_mid":"E3VsH66d","three_source_calendar_identity_verified":True,
         "kickoff_utc":"2026-11-04T17:45:00Z"}]}
    return intake,sofa,flash

def test_future_18h_research_target_without_probability():
    r=early_targets_from_docs(*docs(),NOW)
    assert len(r)==1
    assert r[0]["fixture_id"]=="FOOTBALL_DATA_ORG:575387"
    assert r[0]["research_only"] is True
    assert r[0]["p_matrix"] is None
    assert r[0]["production_probability_authorized"] is False
    assert r[0]["telegram_signal_authorized"] is False

def test_mismatch_and_betting_flags_fail_closed():
    import pytest
    x=list(docs());x[2]["matched"][0]["sofascore_event_id"]="WRONG"
    assert early_targets_from_docs(*x,NOW)==[]
    x=list(docs());x[0]["signal_generation_authorized"]=True
    with pytest.raises(ValueError,match="GOVERNANCE"):early_targets_from_docs(*x,NOW)
    x=list(docs());x[0]["generated_at_utc"]="2026-10-01T00:00:00Z"
    with pytest.raises(ValueError,match="STALE"):early_targets_from_docs(*x,NOW)

def test_no_old_or_far_future_target():
    assert early_targets_from_docs(*docs(),datetime(2026,11,4,18,tzinfo=timezone.utc))==[]
    x=list(docs())
    x[0]["fixtures"][0]["kickoff_utc"]="2026-11-05T23:45:00Z"
    assert early_targets_from_docs(*x,NOW)==[]
