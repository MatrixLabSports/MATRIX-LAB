from datetime import datetime,timedelta,timezone
from tools.matrix_selfhosted_browser_quote_collector import book_from_url,candidate_rows,page_matches_candidate,betano_exact_over25_from_payload,betano_event_from_payload

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


def test_betano_exact_over25_binds_event_market_selection_chain():
    payload={
      "events":{"90298900":{"id":90298900,"url":"/cuotas-de-partido/nashville-sc-philadelphia-union/90298900/","participants":[{"name":"Nashville SC"},{"name":"Philadelphia Union"}],"marketIdList":[3030175141]}},
      "markets":{"3030175141":{"id":3030175141,"name":"Goles totales Más/Menos","type":"HCTG","handicap":2.5,"selectionIdList":[10691082472,10691082473]}},
      "selections":{"10691082472":{"id":10691082472,"name":"Más de 2.5","fullName":"Más de","handicap":2.5,"price":1.67},"10691082473":{"id":10691082473,"name":"Menos 2.5","fullName":"Menos","handicap":2.5,"price":2.22}}
    }
    q=betano_exact_over25_from_payload(payload,"Nashville SC","Philadelphia Union")
    assert q is not None
    assert q["event_id"]==90298900
    assert q["market_id"]==3030175141
    assert q["selection_id"]==10691082472
    assert q["price"]==1.67


def test_betano_exact_over25_rejects_unbound_global_selection():
    payload={
      "events":{"1":{"id":1,"participants":[{"name":"A"},{"name":"B"}],"marketIdList":[10]}},
      "markets":{"10":{"id":10,"name":"Resultado del partido","type":"1X2","selectionIdList":[100]}},
      "selections":{"100":{"id":100,"name":"Más de 2.5","handicap":2.5,"price":1.80}}
    }
    assert betano_exact_over25_from_payload(payload,"A","B") is None


def test_betano_event_lookup_requires_both_teams():
    payload={"data":{"events":{"90302907":{
      "id":90302907,
      "url":"/cuotas-de-partido/vancouver-whitecaps-fc-san-diego-fc/90302907/",
      "participants":[{"name":"Vancouver Whitecaps FC"},{"name":"San Diego FC"}],
      "marketIdList":[123]
    }}}}
    ev=betano_event_from_payload(payload,"Vancouver Whitecaps","San Diego")
    assert ev is not None
    assert ev["id"]==90302907
    assert betano_event_from_payload(payload,"Vancouver Whitecaps","Seattle Sounders") is None


def test_betano_structured_probe_does_not_require_visible_text():
    # Regression guard: Betano certified extraction is payload-driven, not gated by body text.
    c={"match":"Vancouver Whitecaps vs San Diego"}
    assert page_matches_candidate("Página Betano sin nombres visibles del partido",c) is False


def test_split_match_vancouver_san_diego_regression():
    from tools.matrix_selfhosted_browser_quote_collector import split_match
    assert split_match("Vancouver Whitecaps vs San Diego")==("vancouver whitecaps","san diego")


def test_betano_detail_probe_captures_network_json():
    import inspect
    from tools.matrix_selfhosted_browser_quote_collector import betano_detail_exact_over25
    source=inspect.getsource(betano_detail_exact_over25)
    assert '.on("response"' in source
    assert '"xhr","fetch"' in source
    assert "response.json()" in source


def test_betano_dom_exact_over25_binding_contract():
    import inspect
    from tools.matrix_selfhosted_browser_quote_collector import betano_dom_exact_over25
    source=inspect.getsource(betano_dom_exact_over25)
    assert 'Goles totales Más/Menos' in source
    assert 'Más de 2.5' in source
    assert 'EVENT_URL+PAGE_TITLE+MARKET_CONTAINER+SELECTION_ARIA' in source
    assert 'read_only' in source
