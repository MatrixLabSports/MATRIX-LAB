from copy import deepcopy
import pytest
from tools.matrix_football_flashscore_fixture_crosscheck import check

def inputs():
    intake={"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
            "target_date_bogota":"2026-11-02","real_money":"BLOCKED",
            "fixtures":[{"source_fixture_id":"558541","home":"US Sassuolo Calcio",
                         "away":"ACF Fiorentina","kickoff_utc":"2026-11-02T17:30:00+00:00"}]}
    sofa={"schema":"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK_V1",
          "target_date_bogota":"2026-11-02","status":"PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL",
          "rejected_count":0,"real_money":"BLOCKED",
          "matched":[{"fixture_id":"558541","sofascore_event_id":"16285070",
                      "kickoff_utc":"2026-11-02T17:30:00+00:00"}]}
    flash={"schema":"MATRIX_FLASH_BROWSER_OBSERVATIONS_V1",
           "target_date_bogota":"2026-11-02","source":"FLASHSCORE",
           "observed_at_utc":"2026-11-02T02:04:22+00:00",
           "automatic_wagering":False,"real_money":"BLOCKED",
           "matches":[{"provider_fixture_id":"558541","flashscore_mid":"YHemANS7",
                       "match":"Sassuolo - Fiorentina","local_time_bogota":"12:30",
                       "url":"https://www.flashscore.co/partido/futbol/fiorentina-X/sassuolo-Y/?mid=YHemANS7"}]}
    return intake,sofa,flash

def test_both_primary_calendars_verify_but_not_odds_or_signal():
    r=check(*inputs())
    assert r["status"]=="PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS"
    assert r["matched_count"]==1
    assert r["rejected_count"]==0
    assert r["sofascore_verified"] is True
    assert r["flashscore_verified"] is True
    assert r["odds_market_verified"] is False
    assert r["signal_generation_authorized"] is False
    assert r["real_money"]=="BLOCKED"

def test_changed_time_is_blocked():
    a,b,c=inputs();c["matches"][0]["local_time_bogota"]="12:45"
    assert check(a,b,c)["rejected"][0]["reason"]=="FLASH_KICKOFF_CONTRADICTION"

def test_swapped_teams_are_blocked():
    a,b,c=inputs();c["matches"][0]["match"]="Fiorentina - Sassuolo"
    assert check(a,b,c)["rejected"][0]["reason"]=="FLASH_TEAM_ORIENTATION_CONTRADICTION"

def test_wrong_url_mid_is_blocked():
    a,b,c=inputs();c["matches"][0]["url"]=c["matches"][0]["url"].replace("YHemANS7","AAAAXXXX")
    assert check(a,b,c)["rejected"][0]["reason"]=="FLASH_EVENT_URL_IDENTITY_INVALID"

def test_duplicate_flash_mid_blocks():
    a,b,c=inputs();c["matches"].append(deepcopy(c["matches"][0]))
    with pytest.raises(ValueError,match="DUPLICATE"):
        check(a,b,c)

def test_missing_evidence_is_blocked_not_promoted():
    a,b,c=inputs()
    r=check(a,b,None)
    assert r["status"]=="BLOCKED_MISSING_FLASH_BROWSER_EVIDENCE"
    assert r["signal_generation_authorized"] is False

def test_sofa_preregistration_rejection_blocks():
    a,b,c=inputs();b["rejected_count"]=1
    r=check(a,b,c)
    assert r["matched_count"]==0
    assert r["status"]=="BLOCKED_MISSING_FLASH_BROWSER_EVIDENCE"

def test_observation_after_kickoff_is_blocked():
    a,b,c=inputs();c["observed_at_utc"]="2026-11-02T18:00:00Z"
    assert check(a,b,c)["rejected"][0]["reason"]=="OBSERVATION_AFTER_KICKOFF"

def test_unauthorized_money_is_hard_error():
    a,b,c=inputs();c["real_money"]="ENABLED"
    with pytest.raises(ValueError,match="REAL_MONEY"):
        check(a,b,c)

def test_cross_calendar_target_mismatch_is_hard_error():
    a,b,c=inputs();c["target_date_bogota"]="2026-11-03"
    with pytest.raises(ValueError,match="DATE_MISMATCH"):
        check(a,b,c)
