"""Strict free-provider independent probing and failure contracts."""
from datetime import datetime, timezone
import json
import requests
from tools.free_provider_authenticated_probe import probe

class Resp:
    def __init__(self,status,body):
        self.status_code=status
        self.content=json.dumps(body).encode()
        self.headers={"content-type":"application/json"}
        self._body=body
    def json(self):return self._body

class Network:
    def __init__(self,responses):
        self.responses=list(responses);self.calls=[]
    def get(self,url,headers,params,timeout):
        self.calls.append({"url":url,"headers":headers,"params":params})
        nextvalue=self.responses.pop(0)
        if isinstance(nextvalue,Exception):raise nextvalue
        return nextvalue

NOW=datetime(2026,11,14,12,0,tzinfo=timezone.utc)

def test_no_keys_is_zero_calls_and_no_false_success():
    net=Network([])
    d=probe("","",session=net,now=NOW)
    assert d["network_calls"]==0
    assert d["status"]=="NO_VERIFIED_LIVE_PROVIDER"
    assert d["providers"]["football_data_org"]["status"]=="KEY_NOT_CONFIGURED"
    assert d["providers"]["live_tennis_api"]["calls"]==0
    assert net.calls==[]

def test_one_working_football_provider_cannot_be_blocked_by_missing_tennis_key():
    net=Network([Resp(200,{"competitions":[{"id":2021}]}),Resp(200,{"matches":[{"id":12345,"utcDate":"2026-11-14T18:00:00Z",
"competition":{"id":2021},"homeTeam":{"name":"Alpha"},"awayTeam":{"name":"Beta"}}]})])
    d=probe("secret-123","",session=net,now=NOW)
    assert d["status"]=="PARTIAL_VERIFIED"
    assert d["providers"]["football_data_org"]["data_verified"] is True
    assert d["providers"]["live_tennis_api"]["data_verified"] is False
    assert d["network_calls"]==2
    assert d["football_current_day_fixture_proof"]["verified"] is True
    assert d["football_current_day_fixture_proof"]["candidate_count"]==1
    assert d["promotion_gate"]["production_feed_authorized"] is False
    assert "secret-123" not in json.dumps(d)
    assert net.calls[0]["headers"]=={"X-Auth-Token":"secret-123"}

def test_http200_empty_error_or_access_denied_never_certifies_source():
    for response in (Resp(200,{"competitions":[]}),Resp(200,{"errors":"denied"}),
                     Resp(401,{"error":"unauthorized"}),Resp(403,{"error":"suspended"}),
                     Resp(429,{"error":"quota"})):
        net=Network([response])
        d=probe("secret","",session=net,now=NOW)
        assert d["providers"]["football_data_org"]["data_verified"] is False
        assert d["status"]=="NO_VERIFIED_LIVE_PROVIDER"
        assert d["network_calls"]==1

def test_network_error_does_not_request_tennis_or_open_model():
    net=Network([requests.ConnectionError("private secrets must not be saved")])
    d=probe("foo","bar",session=net,now=NOW)
    assert d["network_calls"]==1
    assert d["providers"]["live_tennis_api"]["calls"]==0
    assert "private secrets must not be saved" not in json.dumps(d)
    assert d["protections"]["real_money"]=="BLOCKED"

def test_tennis_opt_in_still_cannot_promote_probability_engine():
    net=Network([Resp(200,{"competitions":[{"id":2021}]}),
                 Resp(200,{"matches":[{"id":12345,"utcDate":"2026-11-14T18:00:00Z",
"competition":{"id":2021},"homeTeam":{"name":"Alpha"},"awayTeam":{"name":"Beta"}}]}),
                 Resp(200,{"data":[{"id":"test"}]})])
    d=probe("football","tennis",tennis_opt_in=True,session=net,now=NOW)
    assert d["network_calls"]==3
    assert d["providers"]["live_tennis_api"]["data_verified"] is True
    assert d["promotion_gate"]["production_feed_authorized"] is False
    assert not d["protections"]["paid_api_subscription_authorized"]

def test_oversized_response_fails_closed_without_saving_body():
    response=Resp(200,{"competitions":[{"id":2021}]})
    response.content=b"x"*250001
    net=Network([response])
    d=probe("foo","",session=net,now=NOW)
    assert d["providers"]["football_data_org"]["data_verified"] is False
    assert d["providers"]["football_data_org"]["status"]=="NETWORK_OR_RESPONSE_BLOCK_ValueError"


def test_no_fixture_data_is_not_false_production_readiness():
    net=Network([Resp(200,{"competitions":[{"id":2021}]}),Resp(200,{"matches":[]}),
                 Resp(200,{"matches":[]})])
    d=probe("foo","",session=net,now=NOW)
    assert d["providers"]["football_data_org"]["data_verified"] is True
    assert d["football_current_day_fixture_proof"]["verified"] is False
    assert d["football_current_day_fixture_proof"]["candidate_count"]==0
    assert d["promotion_gate"]["production_feed_authorized"] is False

def test_cross_day_fixture_or_missing_team_does_not_pass():
    net=Network([Resp(200,{"competitions":[{"id":2021}]}),
        Resp(200,{"matches":[{"id":12345,"utcDate":"2026-11-15T18:00:00Z",
        "competition":{"id":2021},"homeTeam":{"name":"Alpha"},"awayTeam":{"name":"Beta"}},
        {"id":12346,"utcDate":"2026-11-14T18:00:00Z",
        "competition":{"id":2021},"homeTeam":{},"awayTeam":{"name":"Beta"}}]}),
        Resp(200,{"matches":[]})])
    d=probe("foo","",session=net,now=NOW)
    assert d["football_current_day_fixture_proof"]["candidate_count"]==0
    assert d["football_current_day_fixture_proof"]["verified"] is False


def test_weekly_fallback_source_fixture_verified_only_with_real_identity():
    net=Network([Resp(200,{"competitions":[{"id":2021}]}),
                 Resp(200,{"matches":[]}),
                 Resp(200,{"matches":[{
                    "id":44567,"utcDate":"2026-11-21T15:00:00Z",
                    "competition":{"id":2021,"code":"PL"},
                    "homeTeam":{"name":"Alpha"},"awayTeam":{"name":"Beta"}
                 }]})])
    d=probe("key","",session=net,now=NOW)
    assert d["network_calls"]==3
    assert d["football_current_day_fixture_proof"]["verified"] is False
    assert d["football_named_competition_week_proof"]["verified"] is True
    assert d["football_named_competition_week_proof"]["sample_ids"]==[44567]
    source=d["football_named_competition_week_proof"]["source_fixtures_research_only"]
    assert source==[{"provider_fixture_id":44567,"kickoff_utc":"2026-11-21T15:00:00Z",
       "competition_id":2021,"competition_code":"PL","home":"Alpha","away":"Beta"}]
    assert d["football_named_competition_week_proof"]["historic_provider_id_equivalence_certified"] is False
    assert d["promotion_gate"]["production_feed_authorized"] is False

def test_weekly_fallback_403_never_claims_live_fixtures():
    net=Network([Resp(200,{"competitions":[{"id":2021}]}),
                 Resp(200,{"matches":[]}),Resp(403,{"message":"denied"})])
    d=probe("key","",session=net,now=NOW)
    assert d["football_named_competition_week_proof"]["verified"] is False
    assert d["providers"]["football_data_org"]["data_verified"] is True
    assert d["promotion_gate"]["production_feed_authorized"] is False


def test_pl_week_fixtures_wrong_league_and_duplicate_id_cannot_be_ingested():
    net=Network([Resp(200,{"competitions":[{"id":2021}]}),
                 Resp(200,{"matches":[]}),
                 Resp(200,{"matches":[
                    {"id":44567,"utcDate":"2026-11-21T15:00:00Z",
                     "competition":{"id":2021,"code":"PL"},
                     "homeTeam":{"name":"Alpha"},"awayTeam":{"name":"Beta"}},
                    {"id":44567,"utcDate":"2026-11-21T15:00:00Z",
                     "competition":{"id":2021,"code":"PL"},
                     "homeTeam":{"name":"Alpha"},"awayTeam":{"name":"Beta"}},
                    {"id":44568,"utcDate":"2026-11-21T18:00:00Z",
                     "competition":{"id":2014,"code":"PD"},
                     "homeTeam":{"name":"Gamma"},"awayTeam":{"name":"Delta"}}
                 ]})])
    report=probe("test","",session=net,now=NOW)
    proof=report["football_named_competition_week_proof"]
    assert proof["verified"] is True
    assert proof["match_count"]==1
    assert len(proof["source_fixtures_research_only"])==1
    assert proof["source_name_crossmatch_certified"] is False
    assert report["promotion_gate"]["production_feed_authorized"] is False
