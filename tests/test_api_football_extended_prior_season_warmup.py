from tools.api_football_extended_prior_season_warmup import _select


def test_prior_season_selection_round_robins_statsrich_leagues():
    by={
        "72":[
            {"fixture_id":"1","kickoff_utc":"2025-12-01T00:00:00+00:00","current_2026_team_overlap":2},
            {"fixture_id":"2","kickoff_utc":"2025-11-01T00:00:00+00:00","current_2026_team_overlap":1},
        ],
        "252":[
            {"fixture_id":"3","kickoff_utc":"2025-12-02T00:00:00+00:00","current_2026_team_overlap":2},
            {"fixture_id":"4","kickoff_utc":"2025-11-02T00:00:00+00:00","current_2026_team_overlap":1},
        ],
    }
    out=_select(by,3)
    assert len(out)==3
    assert {r["fixture_id"] for r in out}=={"1","2","3"}
