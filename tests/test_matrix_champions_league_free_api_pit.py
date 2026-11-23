"""CL 2001 provider-only proof; all external replies mocked, no network spending."""
from datetime import datetime,timezone
import json
from tools.matrix_champions_league_free_api_pit import inspect,COMPETITION_ID

NOW=datetime(2026,11,22,18,0,tzinfo=timezone.utc)
def intake(cl=True):
    fixtures=[{"source_competition_id":2001,"source_competition_code":"CL",
       "source_fixture_id":"575395","home_source_team_id":"11",
       "away_source_team_id":"22","kickoff_utc":"2026-11-24T17:45:00Z"}] if cl else []
    return {"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
       "target_date_bogota":"2026-11-24","source":"FOOTBALL_DATA_ORG",
       "signal_generation_authorized":False,"real_money":"BLOCKED",
       "fixtures":fixtures}
class Response:
    status=200
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return json.dumps(self.payload).encode()
def history(cid=2001,update="2026-11-21T23:10:00Z"):
    return {"competition":{"id":cid},"matches":[{
      "id":91,"status":"FINISHED","utcDate":"2026-11-21T19:00:00Z",
      "lastUpdated":update,"competition":{"id":cid},
      "homeTeam":{"id":11},"awayTeam":{"id":22},
      "score":{"fullTime":{"home":2,"away":1}}}]}

def test_authentic_cl_history_is_sha_bound_but_not_promoted():
    called=[]
    def opener(req,timeout):
        called.append(req.full_url)
        assert req.get_header("X-auth-token")=="free-key"
        assert timeout==25
        return Response(history())
    result,raw=inspect(intake(),"free-key",opener=opener,now=NOW)
    import hashlib
    assert called==["https://api.football-data.org/v4/competitions/CL/matches"]
    assert result["fixture_count"]==1
    assert result["history_network_calls"]==1
    assert result["history_sha256"]==hashlib.sha256(raw).hexdigest()
    assert result["provider_history_finished_pit_rows"]==1
    assert result["fixture_checks"][0]["prior_champions_only_home_rows"]==1
    assert result["fixture_checks"][0]["prior_champions_only_away_rows"]==1
    assert result["production_p_matrix_authorized"] is False
    assert result["telegram_signal_authorized"] is False
    assert result["original_six_leagues_scope_unchanged"] is True
    assert result["real_money"]=="BLOCKED"

def test_no_cl_no_provider_calls():
    def no(*a,**kw):raise AssertionError("NO_CL_API_CALL_ALLOWED")
    result,raw=inspect(intake(False),"free-key",opener=no,now=NOW)
    assert raw is None and result["history_network_calls"]==0

def test_no_key_no_calls_and_fail_closed():
    def no(*a,**kw):raise AssertionError("NO_API_WITHOUT_KEY")
    result,raw=inspect(intake(),"",opener=no,now=NOW)
    assert result["status"]=="MISSING_FOOTBALL_DATA_ORG_TOKEN"
    assert result["telegram_signal_authorized"] is False

def test_unverified_future_source_scores_excluded():
    result,raw=inspect(intake(),"free-key",
      opener=lambda *a,**kw:Response(history(update="2026-11-25T00:00:00Z")),now=NOW)
    assert result["provider_history_finished_pit_rows"]==0
    assert raw is not None
    assert result["research_probability_authorized"] is False

def test_other_competition_same_teams_must_not_pass():
    result,raw=inspect(intake(),"free-key",
      opener=lambda *a,**kw:Response(history(cid=2021)),now=NOW)
    assert raw is None
    assert result["status"]=="BLOCKED_HISTORY_COMPETITION_IDENTITY_MISMATCH"

def test_bad_event_kickoff_fails_closed():
    row=intake()
    row["fixtures"][0]["kickoff_utc"]="2026-11-21T17:45:00Z"
    import pytest
    with pytest.raises(ValueError,match="CHAMPIONS_FIXTURE_NOT_PROSPECTIVE"):
        inspect(row,"free-key",now=NOW)

def test_non_champions_fixture_cannot_be_misclassified():
    row=intake()
    row["fixtures"][0]["source_competition_code"]="PL"
    result,raw=inspect(row,"free-key",opener=lambda *a,**kw:(_ for _ in ()).throw(AssertionError()),now=NOW)
    assert result["fixture_count"]==0 and raw is None
