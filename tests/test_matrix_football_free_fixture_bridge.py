from tools.matrix_football_free_fixture_bridge import bridge

def test_observed_fixtures_are_quarantined():
    source={"target_date":"2026-11-01","source":"TheSportsDB","events":[
        {"idEvent":"2398162","idAPIfootball":"1493213","home":"Belgrano","away":"Barracas Central","status":"NS"},
        {"idEvent":"2398163","home":"Boca Juniors","away":"River Plate","status":"NS"},
        {"idEvent":"2398166","home":"Estudiantes","away":"Instituto","status":"FT"}]}
    result=bridge(source,"2026-11-01")
    assert result["research_event_count"]==2
    assert result["canonical_producer_input_authorized"] is False
    assert result["telegram_signal_authorized"] is False
    assert result["real_money"]=="BLOCKED"
    assert all(e["p_matrix_status"]=="NOT_GENERATED" for e in result["research_events"])
    assert all(e["signal_generation_authorized"] is False for e in result["research_events"])

def test_empty_observation_stays_blocked():
    result=bridge({"target_date":"2026-11-01","source":"TheSportsDB","events":[]}, "2026-11-01")
    assert result["research_event_count"]==0
    assert result["telegram_signal_authorized"] is False


def test_wrong_date_rejected():
    import pytest
    with pytest.raises(ValueError, match="OBSERVATION_TARGET_DATE_MISMATCH"):
        bridge({"target_date":"2026-10-31","source":"TheSportsDB","events":[]}, "2026-11-01")

def test_wrong_provider_rejected():
    import pytest
    with pytest.raises(ValueError, match="OBSERVATION_PROVIDER_MISMATCH"):
        bridge({"target_date":"2026-11-01","source":"unknown","events":[]}, "2026-11-01")
