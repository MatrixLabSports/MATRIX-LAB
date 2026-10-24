from __future__ import annotations

from datetime import datetime, timezone

from tools.tennis_clay_prefeature_discovery import build_prefeature


def test_clay_prefeature_is_future_only_and_requires_exact_cut_rankings():
    inventory={
        "events":[
            {
                "source_event_id":"rapidapi-tennis:atp:match:1",
                "circuit_detail":"ATP_CHALLENGER",
                "event_format":"SINGLES",
                "surface":"Clay",
                "event_start_utc":"2026-10-12T18:00:00+00:00",
                "tournament_name":"Test Challenger",
                "tournament_id":"99",
                "round":"First",
                "physical_event_key":"a"*64,
                "player1":{"id":"11","name":"Player One","country":"USA"},
                "player2":{"id":"22","name":"Player Two","country":"ESP"},
            },
            {
                "source_event_id":"rapidapi-tennis:atp:match:2",
                "circuit_detail":"ATP_CHALLENGER",
                "event_format":"SINGLES",
                "surface":"Clay",
                "event_start_utc":"2026-10-12T06:00:00+00:00",
                "tournament_name":"Past Challenger",
                "tournament_id":"98",
                "round":"First",
                "physical_event_key":"b"*64,
                "player1":{"id":"33","name":"Past One","country":"FRA"},
                "player2":{"id":"44","name":"Past Two","country":"ITA"},
            },
        ]
    }
    rankings={
        "11":{"place":"100","points":"500","player":"Player One","country":"USA","snapshot_date":"2026-09-21"},
        "22":{"place":"200","points":"250","player":"Player Two","country":"ESP","snapshot_date":"2026-09-21"},
    }
    out=build_prefeature(
        inventory=inventory,
        inventory_sha256="c"*64,
        ranking_by_player=rankings,
        now_utc=datetime(2026,10,12,7,0,tzinfo=timezone.utc),
        starting_observation_count=0,
    )
    assert len(out["events"])==1
    assert out["events"][0]["surface"]=="Clay"
    assert out["events"][0]["identity_crosswalk_required"] is True
    assert out["events"][0]["features_loaded"] is False
    assert out["events"][0]["outcome"] is None
    assert out["events"][0]["player_identities"][0]["provider_ranking"]["snapshot_date"]=="2026-09-21"
    assert out["blocked_discovery"]==[
        {"source_event_id":"rapidapi-tennis:atp:match:2","reason":"EVENT_NOT_FUTURE"}
    ]
    assert out["metrics_opened"] is False
    assert out["real_money"]=="BLOCKED"
