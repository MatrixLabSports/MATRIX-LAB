from datetime import datetime, timezone

from tools.api_football_extended_market_historical_bootstrap import (
    _player_rows,
    _stat_map,
    select_development_candidates,
)

def test_select_excludes_protected_prospective_and_post_cutoff():
    rows=[
        {"fixture_id":"1","kickoff_utc":"2026-09-01T00:00:00+00:00","league_id":"10"},
        {"fixture_id":"2","kickoff_utc":"2026-09-02T00:00:00+00:00","league_id":"10"},
        {"fixture_id":"3","kickoff_utc":"2026-09-03T00:00:00+00:00","league_id":"20"},
        {"fixture_id":"4","kickoff_utc":"2026-09-20T00:00:00+00:00","league_id":"20"},
    ]
    out=select_development_candidates(
        rows,
        protected_ids={"2"},
        prospective_ids={"3"},
        cutoff=datetime(2026,9,13,tzinfo=timezone.utc),
        limit=10,
    )
    assert [r["fixture_id"] for r in out]==["1"]

def test_select_round_robins_leagues():
    rows=[
        {"fixture_id":"1","kickoff_utc":"2026-09-01T00:00:00+00:00","league_id":"10"},
        {"fixture_id":"2","kickoff_utc":"2026-09-02T00:00:00+00:00","league_id":"10"},
        {"fixture_id":"3","kickoff_utc":"2026-09-03T00:00:00+00:00","league_id":"20"},
        {"fixture_id":"4","kickoff_utc":"2026-09-04T00:00:00+00:00","league_id":"20"},
    ]
    out=select_development_candidates(
        rows,set(),set(),datetime(2026,9,13,tzinfo=timezone.utc),limit=2
    )
    assert {r["league_id"] for r in out}=={"10","20"}

def test_stat_map_extracts_team_statistics():
    payload={"response":[
        {"team":{"id":1,"name":"A"},"statistics":[
            {"type":"Corner Kicks","value":7},
            {"type":"Shots on Goal","value":5},
            {"type":"Yellow Cards","value":2},
        ]}
    ]}
    d=_stat_map(payload)
    assert d["1"]["statistics"]["Corner Kicks"]==7
    assert d["1"]["statistics"]["Shots on Goal"]==5

def test_player_rows_extracts_extended_props():
    payload={"response":[
        {"team":{"id":1,"name":"A"},"players":[
            {"player":{"id":9,"name":"P"},"statistics":[{
                "games":{"minutes":90},
                "shots":{"total":4,"on":2},
                "goals":{"assists":1,"saves":None},
                "passes":{"total":33},
                "tackles":{"total":3},
                "fouls":{"committed":2},
            }]}
        ]}
    ]}
    rows=_player_rows(payload)
    assert len(rows)==1
    r=rows[0]
    assert r["shots_total"]==4
    assert r["shots_on_target"]==2
    assert r["assists"]==1
    assert r["passes_total"]==33
    assert r["tackles_total"]==3
    assert r["fouls_committed"]==2
