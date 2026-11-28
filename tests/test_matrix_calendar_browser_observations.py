"""True fixture IDs and exact calendar labels, no prices or matrices."""
from datetime import datetime, timezone
from tools.matrix_calendar_browser_observations import extract_sofa, exact_label
from tools.matrix_football_sofa_fixture_crosscheck import corroborate

NOW=datetime(2026,11,3,22,57,tzinfo=timezone.utc)
def source():
    return {"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
        "source":"FOOTBALL_DATA_ORG","provider_status":"AUTHENTICATED_FIXTURE_CAPTURE",
        "target_date_bogota":"2026-11-04","real_money":"BLOCKED",
        "fixtures":[{"source_fixture_id":"575387","home":"Fenerbahçe SK",
                     "away":"Liverpool FC","kickoff_utc":"2026-11-04T17:45:00+00:00"}]}
def links(label="4/11/26 12:45 Fenerbahçe Fenerbahçe Liverpool FC Liverpool",
          url="https://www.sofascore.com/es/football/match/fenerbahce-liverpool-fc/Usclb#id:16938962"):
    return [{"name":label,"url":url}]

def test_real_observed_match_integrates_with_old_crosscheck():
    r=extract_sofa(source(),links(),NOW)
    assert len(r["matches"])==1
    assert r["matches"][0]["sofascore_event_id"]=="16938962"
    validated=corroborate(source(),r)
    assert validated["matched_count"]==1
    assert validated["rejected_count"]==0
    assert validated["signal_generation_authorized"] is False
    assert r["quotes_verified"] is False
    assert r["real_money"]=="BLOCKED"

def test_false_team_clock_or_url_cannot_pass():
    assert extract_sofa(source(),links(label="4/11/26 12:45 Fenerbahçe Chelsea"),NOW)["matches"]==[]
    assert extract_sofa(source(),links(label="4/11/26 12:46 Fenerbahçe Liverpool FC"),NOW)["matches"]==[]
    assert extract_sofa(source(),links(url="https://evil.invalid/es/football/match/a#id:16938962"),NOW)["matches"]==[]

def test_no_after_kickoff_and_no_false_authorization():
    future=datetime(2026,11,4,18,0,tzinfo=timezone.utc)
    assert extract_sofa(source(),links(),future)["matches"]==[]
    assert not exact_label("4/11/25 12:45 Fenerbahçe Liverpool FC","2026-11-04","12:45","fenerbahce","liverpool fc")
