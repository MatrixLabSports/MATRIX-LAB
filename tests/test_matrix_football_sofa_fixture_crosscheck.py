from copy import deepcopy
import pytest
from tools.matrix_football_sofa_fixture_crosscheck import corroborate

def inputs():
    fixture={"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
             "target_date_bogota":"2026-11-02","real_money":"BLOCKED",
             "fixtures":[{"source_fixture_id":"558541","home":"US Sassuolo Calcio",
                          "away":"ACF Fiorentina","kickoff_utc":"2026-11-02T17:30:00+00:00"}]}
    browser={"schema":"MATRIX_SOFA_BROWSER_OBSERVATIONS_V1","source":"SOFASCORE",
             "real_money":"BLOCKED","target_date_bogota":"2026-11-02",
             "observed_at_utc":"2026-11-02T01:40:00Z",
             "matches":[{"provider_fixture_id":"558541","sofascore_event_id":"16285070",
                         "home":"Sassuolo","away":"Fiorentina","local_time_bogota":"12:30",
                         "url":"https://www.sofascore.com/es/football/match/sassuolo-fiorentina/TdbsTfb#id:16285070"}]}
    return fixture,browser

def test_real_browser_alias_identity_matches_and_signal_remains_off():
    f,b=inputs()
    result=corroborate(f,b)
    assert result["matched_count"]==1
    assert result["status"]=="PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL"
    assert result["flashscore_verified"] is False
    assert result["governed_model_parity_verified"] is False
    assert result["over25_exact_quote_verified"] is False
    assert result["signal_generation_authorized"] is False
    assert result["real_money"]=="BLOCKED"

def test_wrong_kickoff_blocks():
    f,b=inputs()
    b["matches"][0]["local_time_bogota"]="13:30"
    assert corroborate(f,b)["rejected"][0]["reason"]=="BROWSER_TIME_MISMATCH"

def test_swapped_team_blocks():
    f,b=inputs()
    b["matches"][0]["home"],b["matches"][0]["away"]="Fiorentina","Sassuolo"
    assert corroborate(f,b)["rejected"][0]["reason"]=="BROWSER_TEAM_IDENTITY_MISMATCH"

def test_wrong_provider_id_link_blocks():
    f,b=inputs()
    b["matches"][0]["url"]=b["matches"][0]["url"].replace("16285070","123456")
    assert corroborate(f,b)["rejected"][0]["reason"]=="BROWSER_PROVIDER_EVENT_URL_MISMATCH"

def test_duplicate_fixture_identity_fails_closed():
    f,b=inputs()
    b["matches"].append(deepcopy(b["matches"][0]))
    with pytest.raises(ValueError,match="DUPLICATE"):
        corroborate(f,b)

def test_nonprospective_capture_blocks():
    f,b=inputs()
    b["observed_at_utc"]="2026-11-02T18:00:00Z"
    assert corroborate(f,b)["rejected"][0]["reason"]=="BROWSER_OBSERVATION_NOT_PROSPECTIVE"

def test_missing_browser_capture_produces_blocked_not_green():
    f,_=inputs()
    result=corroborate(f,None)
    assert result["status"]=="BLOCKED_NO_CURRENT_BROWSER_CAPTURE"
    assert result["signal_generation_authorized"] is False

def test_wrong_date_hard_failure():
    f,b=inputs()
    b["target_date_bogota"]="2026-11-03"
    with pytest.raises(ValueError,match="MISMATCH"):
        corroborate(f,b)
