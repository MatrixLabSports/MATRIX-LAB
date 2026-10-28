import pytest
from datetime import datetime,timedelta,timezone
from tools.matrix_quote_recovery_evidence import validate

def base():
    now=datetime.now(timezone.utc)
    return {
      "fixture_id":"X1","market":"OVER_2_5","bookmaker":"Betano","decimal_odds":1.70,
      "quote_observed_at_utc":now.isoformat(),"kickoff_utc":(now+timedelta(hours=1)).isoformat(),
      "p_matrix":0.65,"revalidated_ev":0.105,"source_evidence":"opera://physical-quote"
    }

def test_valid_recovery_evidence_passes():
    assert validate(base())["validated"] is True

def test_post_kickoff_is_rejected():
    x=base(); x["kickoff_utc"]=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    with pytest.raises(ValueError,match="QUOTE_NOT_PREMATCH"): validate(x)

def test_weak_ev_is_rejected():
    x=base(); x["revalidated_ev"]=0.01
    with pytest.raises(ValueError,match="EV_LT_0_05"): validate(x)


def test_unauthorized_bookmaker_is_rejected():
    x=base(); x["bookmaker"]="Pinnacle"
    with pytest.raises(ValueError,match="BOOKMAKER_NOT_AUTHORIZED_FOR_EXECUTION"): validate(x)
