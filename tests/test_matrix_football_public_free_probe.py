from tools.matrix_football_public_free_probe import classify

def test_empty_response_fails_closed():
    assert classify({}, "2026-11-01")["status"]=="NO_USABLE_EVENT_LIST_FAIL_CLOSED"

def test_three_event_cap_never_claims_worldwide_inventory():
    events=[{"idEvent":str(i),"dateEvent":"2026-11-01","strHomeTeam":"A","strAwayTeam":"B"} for i in range(20)]
    result=classify({"events":events},"2026-11-01")
    assert result["returned_count"]==3
    assert result["status"]=="PARTIAL_SAMPLE_ONLY_NOT_WORLD_INVENTORY"
