from datetime import datetime,timedelta,timezone
from tools.matrix_selfhosted_browser_quote_collector import book_from_url,candidate_rows,page_matches_candidate

def test_bookmaker_domain_mapping():
    assert book_from_url("https://www.betano.co/sport/futbol/")=="betano"
    assert book_from_url("https://betplay.com.co/apuestas")=="betplay"
    assert book_from_url("https://example.com/") is None

def test_candidate_filter_is_final_window_only():
    now=datetime.now(timezone.utc)
    audit={"records":[
      {"fixture_id":"a","match":"Inter Miami vs FC Cincinnati","kickoff":(now+timedelta(minutes=90)).isoformat(),"p_matrix":0.70},
      {"fixture_id":"b","match":"A vs B","kickoff":(now+timedelta(minutes=150)).isoformat(),"p_matrix":0.80},
      {"fixture_id":"c","match":"A vs B","kickoff":(now+timedelta(minutes=30)).isoformat(),"p_matrix":0.59},
    ]}
    assert [x["fixture_id"] for x in candidate_rows(audit,now)]==["a"]

def test_candidate_match_requires_both_teams():
    c={"match":"Inter Miami vs FC Cincinnati"}
    assert page_matches_candidate("Inter Miami FC Cincinnati Más de 2.5",c) is True
    assert page_matches_candidate("Inter Miami solamente",c) is False
