from datetime import datetime, timezone
from pathlib import Path
import json

from tools.telegram_team_total_goals_picks import build_candidates, _event_pages, _message, _sim


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
