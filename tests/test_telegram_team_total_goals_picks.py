from datetime import datetime, timezone
from pathlib import Path
import json

from tools.telegram_team_total_goals_picks import build_candidates, _event_pages, find_quote, physical_book_team_total_offer, _message, _sim


def _history(path:Path):
    rows=[]
    for i in range(8):
        rows.append({
          "fixture":{"id":100+i,"date":f"2026-10-{10+i:02d}T12:00:00+00:00","status":{"short":"FT"}},
          "teams":{"home":{"id":1 if i%2==0 else 2},"away":{"id":2 if i%2==0 else 1}},
          "score":{"halftime":{"home":0,"away":0},"fulltime":{"home":1,"away":0}},
        })
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({"response":rows}),encoding="utf-8")


def test_team_total_picks_build_from_strictly_prior_history(tmp_path:Path):
    hist=tmp_path/"h.bin"; _history(hist)
    source={"rows":[{
      "fixture_id":"999","kickoff_utc":"2026-10-25T18:00:00+00:00","freeze_at_utc":"2026-10-24T18:00:00+00:00",
      "home_team_id":"1","away_team_id":"2","historical_baseline_source":"h.bin","outcome":None
    }]}
    reg={"events":[{
      "provider_fixture_id":"999","event_start_utc":"2026-10-25T18:00:00+00:00",
      "home_team":"Alpha","away_team":"Beta","competition":"Test League","country":"Test"
    }]}
    rows,audit=build_candidates(source,reg,repo_root=tmp_path,now_utc=datetime(2026,10,24,20,0,tzinfo=timezone.utc))
    assert len(rows)==2
    assert all(x["p_matrix"]>=0.60 for x in rows)
    assert all(x["confidence"] in {"ALTA","MEDIA"} for x in rows)
    assert all(x["market_record"]["sample"]>=5 for x in rows)
    assert audit["protections"]["strictly_prior_history_only"] is True
    assert audit["protections"]["odds_used_to_generate_probability"] is False


def test_message_is_paper_only():
    c={"confidence":"MEDIA","p_matrix":0.64,"home_team":"A","away_team":"B","country":"X","competition":"Y",
       "event_start_utc":"2026-10-25T18:00:00+00:00","team_name":"A","selection_side":"under","line":1.5,
       "team_recent_goals_average":1.2,"opponent_recent_allowed_average":1.3,"market_record":{"wins":6,"sample":8}}
    q={"odds":1.65,"house":"Betano","ev":0.056}
    msg=_message(c,q)
    assert "PICKS NUEVOS MATRIX" in msg
    assert "CONFIANZA MEDIA" in msg
    assert "récord del mercado 6/8" in msg
    assert "1u = COP 25.000" in msg
    assert "DINERO REAL MATRIX: BLOQUEADO" in msg


def test_identity_similarity_reuses_governed_alias_and_club_designators():
    assert _sim("Manchester Utd FC","Manchester United") == 1.0
    assert _sim("Sporting Club de Braga","Braga") >= 0.85


class _FakeResponse:
    def __init__(self,payload):
        self._payload=payload
    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self,pages):
        self.pages=list(pages)
        self.calls=[]
    def get(self,url,headers=None,params=None,timeout=None):
        self.calls.append({"url":url,"params":dict(params or {})})
        return _FakeResponse(self.pages.pop(0))


def test_event_search_paginates_until_next_cursor_is_exhausted():
    session=_FakeSession([
        {"items":[{"event_id":"a","home_team":"Other A","away_team":"Other B"}],"next_cursor":"page-2"},
        {"items":[{"event_id":"b","home_team":"Alpha","away_team":"Beta"}],"next_cursor":None},
    ])
    diagnostic={}
    rows=_event_pages(session,"key",datetime(2026,10,25,18,0,tzinfo=timezone.utc),diagnostic)
    assert [row["event_id"] for row in rows] == ["a","b"]
    assert len(session.calls) == 2
    assert "cursor" not in session.calls[0]["params"]
    assert session.calls[1]["params"]["cursor"] == "page-2"
    assert diagnostic["event_search_pages"] == 2
    assert diagnostic["event_search_rows"] == 2
    assert diagnostic["event_search_pagination_exhausted"] is True


class _RouteSession:
    def __init__(self):
        self.calls=[]
    def get(self,url,headers=None,params=None,timeout=None):
        self.calls.append({"url":url,"params":dict(params or {})})
        if url.endswith("/events"):
            return _FakeResponse({
                "items":[{
                    "event_id":"evt-1",
                    "home_team":"Manchester United",
                    "away_team":"Arsenal",
                    "start_time":"2026-10-25T08:00:00Z",
                }],
                "next_cursor":None,
            })
        if url.endswith("/events/evt-1/odds/snapshot"):
            return _FakeResponse({
                "bookmaker_as_of_ts_ms":{},
                "items":[{
                    "bookmaker":"betano",
                    "market_key":"team_total",
                    "bet_type":"team total",
                    "period":"full time",
                    "team_subject":"Manchester United",
                    "selection_name":"Over 1.5",
                    "selection_key":"team_total:home:over:1.5",
                    "side":"over",
                    "line":"1.5",
                    "odds":1.80,
                    "is_available":True,
                }],
            })
        raise AssertionError(url)


def test_find_quote_requests_exact_team_total_full_time_market():
    session=_RouteSession()
    diagnostic={}
    candidate={
        "fixture_id":"999",
        "event_start_utc":"2026-10-25T08:00:00+00:00",
        "home_team":"Manchester Utd FC",
        "away_team":"Arsenal",
        "team_name":"Manchester Utd FC",
        "market_lane":"TEAM_TOTAL_GOALS_HOME",
        "selection_side":"over",
        "line":1.5,
        "p_matrix":0.62,
    }
    quote=find_quote(session,"key",candidate,diagnostic,{})
    assert quote is not None
    assert quote["house_key"]=="betano"
    assert quote["odds"]==1.80
    snap=[x for x in session.calls if x["url"].endswith("/odds/snapshot")][0]
    assert snap["params"]["types"]=="team total"
    assert snap["params"]["periods"]=="full time"
    assert diagnostic["status"]=="PASS_EXACT_TEAM_TOTAL_QUOTE"


def test_find_quote_rejects_wrong_team_subject():
    session=_RouteSession()
    original_get=session.get
    def wrong_subject(url,headers=None,params=None,timeout=None):
        if url.endswith("/events/evt-1/odds/snapshot"):
            session.calls.append({"url":url,"params":dict(params or {})})
            return _FakeResponse({
                "bookmaker_as_of_ts_ms":{},
                "items":[{
                    "bookmaker":"betano",
                    "market_key":"team_total",
                    "bet_type":"team total",
                    "period":"full time",
                    "team_subject":"Arsenal",
                    "selection_name":"Over 1.5",
                    "selection_key":"team_total:away:over:1.5",
                    "side":"over",
                    "line":"1.5",
                    "odds":2.10,
                    "is_available":True,
                }],
            })
        return original_get(url,headers=headers,params=params,timeout=timeout)
    session.get=wrong_subject
    diagnostic={}
    candidate={
        "fixture_id":"999",
        "event_start_utc":"2026-10-25T08:00:00+00:00",
        "home_team":"Manchester United",
        "away_team":"Arsenal",
        "team_name":"Manchester United",
        "market_lane":"TEAM_TOTAL_GOALS_HOME",
        "selection_side":"over",
        "line":1.5,
        "p_matrix":0.62,
    }
    assert find_quote(session,"key",candidate,diagnostic,{}) is None
    assert diagnostic["status"]=="BLOCKED_NO_EXACT_TEAM_TOTAL_QUOTE"


def test_physical_browser_team_total_offer_requires_exact_identity_and_freshness(tmp_path:Path):
    root=tmp_path/"physical"/"2026-10-25"
    root.mkdir(parents=True)
    quote_path=root/"MATRIX_BETANO_QUOTE_999.json"
    quote_path.write_text(json.dumps({
        "schema":"MATRIX_PHYSICAL_BOOK_QUOTE_V1",
        "fixture_id":"999",
        "market_key":"TEAM_TOTAL_GOALS_HOME",
        "market":"Team Total Goals",
        "team_name":"Manchester United",
        "selection_side":"over",
        "line":1.5,
        "decimal_odds":1.80,
        "house":"Betano",
        "captured_at_utc":"2026-10-25T07:40:00+00:00",
        "kickoff_utc":"2026-10-25T08:00:00+00:00"
    }),encoding="utf-8")
    candidate={
        "fixture_id":"999",
        "event_start_utc":"2026-10-25T08:00:00+00:00",
        "team_name":"Manchester Utd FC",
        "market_lane":"TEAM_TOTAL_GOALS_HOME",
        "selection_side":"over",
        "line":1.5,
        "p_matrix":0.62,
    }
    q=physical_book_team_total_offer(candidate,datetime(2026,10,25,7,50,tzinfo=timezone.utc),root=tmp_path/"physical")
    assert q is not None
    assert q["provider"]=="physical-browser-evidence"
    assert q["house_key"]=="betano"
    assert q["quote_age_seconds"]==600
    assert q["ev"] > 0.05


def test_find_quote_uses_physical_fallback_when_provider_event_missing(tmp_path:Path):
    root=tmp_path/"physical"/"2026-10-25"
    root.mkdir(parents=True)
    (root/"MATRIX_BETANO_QUOTE_999.json").write_text(json.dumps({
        "schema":"MATRIX_PHYSICAL_BOOK_QUOTE_V1",
        "fixture_id":"999",
        "market_key":"TEAM_TOTAL_GOALS_HOME",
        "market":"Team Total Goals",
        "team_name":"Manchester United",
        "selection_side":"over",
        "line":1.5,
        "decimal_odds":1.80,
        "house":"Betano",
        "captured_at_utc":"2026-10-25T07:40:00+00:00",
        "kickoff_utc":"2026-10-25T08:00:00+00:00"
    }),encoding="utf-8")
    class EmptyEventsSession:
        def get(self,url,headers=None,params=None,timeout=None):
            return _FakeResponse({"items":[],"next_cursor":None})
    diagnostic={}
    candidate={
        "fixture_id":"999",
        "event_start_utc":"2026-10-25T08:00:00+00:00",
        "home_team":"Manchester United",
        "away_team":"Arsenal",
        "team_name":"Manchester United",
        "market_lane":"TEAM_TOTAL_GOALS_HOME",
        "selection_side":"over",
        "line":1.5,
        "p_matrix":0.62,
    }
    import tools.telegram_team_total_goals_picks as mod
    real_datetime=mod.datetime
    class FixedDateTime(real_datetime):
        @classmethod
        def now(cls,tz=None):
            return cls(2026,10,25,7,50,tzinfo=timezone.utc)
    mod.datetime=FixedDateTime
    try:
        q=find_quote(EmptyEventsSession(),"key",candidate,diagnostic,{},tmp_path/"physical")
    finally:
        mod.datetime=real_datetime
    assert q is not None
    assert q["provider"]=="physical-browser-evidence"
    assert diagnostic["status"]=="PASS_PHYSICAL_BROWSER_TEAM_TOTAL_QUOTE"
    assert diagnostic["physical_fallback_used"] is True
