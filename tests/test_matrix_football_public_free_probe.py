from tools.matrix_football_public_free_probe import classify

def test_empty_response_fails_closed():
    assert classify({}, "2026-11-01")["status"]=="NO_USABLE_EVENT_LIST_FAIL_CLOSED"

def test_three_event_cap_never_claims_worldwide_inventory():
    events=[{"idEvent":str(i),"dateEvent":"2026-11-01","strHomeTeam":"A","strAwayTeam":"B"} for i in range(20)]
    result=classify({"events":events},"2026-11-01")
    assert result["returned_count"]==3
    assert result["status"]=="PARTIAL_SAMPLE_ONLY_NOT_WORLD_INVENTORY"


def test_bounded_public_response_verifies_only_current_day_identified_fixtures():
    from datetime import datetime,timezone
    import json
    from tools.matrix_football_public_free_probe import one_call
    class FakeResponse:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,n):
            assert n==250001
            return json.dumps({"events":[
              {"idEvent":"12345","dateEvent":"2026-11-14","strLeague":"Premier League",
               "strHomeTeam":"Alpha","strAwayTeam":"Beta"},
              {"idEvent":"12346","dateEvent":"2026-11-15","strLeague":"Premier League",
               "strHomeTeam":"C","strAwayTeam":"D"},
              {"idEvent":"12347","dateEvent":"2026-11-14","strLeague":"",
               "strHomeTeam":"C","strAwayTeam":"D"}]}).encode()
    calls=[]
    def opener(request,timeout):
        calls.append(request.full_url)
        assert timeout==15
        return FakeResponse()
    data=one_call("2026-11-14",opener=opener,
                  clock=datetime(2026,11,14,12,0,tzinfo=timezone.utc))
    assert len(calls)==1
    assert data["network_calls"]==1
    assert data["http_status"]==200
    assert data["current_day_fixture_ids_verified"]==1
    assert data["current_day_sample_ids"]==["12345"]
    assert data["canonical_candidate_generation_authorized"] is False
    assert data["real_money"]=="BLOCKED"

def test_explicit_http_denial_remains_available_as_failure_evidence():
    from urllib.error import HTTPError
    from tools.matrix_football_public_free_probe import one_call
    def denied(*args,**kwargs):
        raise HTTPError("https://www.thesportsdb.com/",429,"rate limit",{},None)
    data=one_call("2026-11-14",opener=denied)
    assert data["status"]=="PROVIDER_HTTP_429"
    assert data["http_status"]==429
    assert data["current_day_fixture_ids_verified"]==0
    assert data["network_calls"]==1
    assert data["signal_generation_authorized"] is False

def test_source_has_no_permitted_global_or_model_promotion():
    from tools.matrix_football_public_free_probe import strict_daily_fixture_rows
    assert strict_daily_fixture_rows({"events":[
      {"idEvent":"123","dateEvent":"2026-11-14","strLeague":"League",
       "strHomeTeam":"Same","strAwayTeam":"Same"}
    ]},"2026-11-14")==[]
