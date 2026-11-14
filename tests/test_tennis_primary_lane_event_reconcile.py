from datetime import datetime, timezone
import json

from tools.tennis_primary_lane_event_reconcile import MODE, run


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_primary_reconcile_accepts_future_clay_with_strong_provider_identity(tmp_path):
    rapid=_write(tmp_path/"rapid.json",{
        "target_date_bogota":"2026-10-16",
        "events":[{
            "circuit_detail":"ATP_CHALLENGER",
            "event_format":"SINGLES",
            "surface":"Clay",
            "source_event_id":"rapidapi-tennis:atp:match:1",
            "physical_event_key":"physical-1",
            "tournament_name":"Test Challenger",
            "event_start_utc":"2026-10-16T15:00:00+00:00",
            "player1":{"id":"11","name":"Player One"},
            "player2":{"id":"22","name":"Player Two"},
        }],
    })
    hold=_write(tmp_path/"hold.json",{"holdout_id":"ATP_CHALLENGER_CLAY_PROSPECTIVE_V1"})
    boot=_write(tmp_path/"boot.json",{"source":{"source_max_tourney_date":"20260914"}})
    out=tmp_path/"out.json"
    result=run(
        rapid,hold,boot,out,
        now=datetime(2026,10,15,23,0,tzinfo=timezone.utc),
    )
    assert result["source_mode"]==MODE
    assert result["api_tennis_status"]=="RETIRED_COST_UTILITY_DECISION"
    assert result["clay_bound_count"]==1
    assert result["bindings"][0]["identity_binding"]=="PASS_RAPIDAPI_PHYSICAL_KEY_PRIMARY"
    assert result["bindings"][0]["blockers"]==["PIT_HISTORY_NOT_CAUGHT_UP_TO_EVENT"]
    assert result["protections"]["required_open_calendar_reconciliation"]==["SofaScore","Flashscore"]
    assert result["protections"]["api_tennis_required"] is False


def test_primary_reconcile_rejects_incomplete_identity(tmp_path):
    rapid=_write(tmp_path/"rapid.json",{
        "target_date_bogota":"2026-10-16",
        "events":[{
            "circuit_detail":"ATP_CHALLENGER",
            "event_format":"SINGLES",
            "surface":"Clay",
            "source_event_id":"rapidapi-tennis:atp:match:2",
            "physical_event_key":"",
            "tournament_name":"Test Challenger",
            "event_start_utc":"2026-10-16T15:00:00+00:00",
            "player1":{"id":"11","name":"Player One"},
            "player2":{"id":"22","name":"Player Two"},
        }],
    })
    hold=_write(tmp_path/"hold.json",{"holdout_id":"ATP_CHALLENGER_CLAY_PROSPECTIVE_V1"})
    boot=_write(tmp_path/"boot.json",{"source":{"source_max_tourney_date":"20260914"}})
    result=run(
        rapid,hold,boot,tmp_path/"out.json",
        now=datetime(2026,10,15,23,0,tzinfo=timezone.utc),
    )
    assert result["clay_bound_count"]==0
    assert result["binding_blocked"][0]["reason"]=="RAPIDAPI_IDENTITY_INCOMPLETE"
    assert "PHYSICAL_EVENT_KEY_MISSING" in result["binding_blocked"][0]["blockers"]


def test_primary_reconcile_blocks_post_start(tmp_path):
    rapid=_write(tmp_path/"rapid.json",{
        "target_date_bogota":"2026-10-15",
        "events":[{
            "circuit_detail":"ATP_CHALLENGER",
            "event_format":"SINGLES",
            "surface":"Hard",
            "source_event_id":"rapidapi-tennis:atp:match:3",
            "physical_event_key":"physical-3",
            "tournament_name":"Test Challenger",
            "event_start_utc":"2026-10-15T20:00:00+00:00",
            "player1":{"id":"11","name":"Player One"},
            "player2":{"id":"22","name":"Player Two"},
        }],
    })
    hold=_write(tmp_path/"hold.json",{"holdout_id":"ATP_CHALLENGER_CLAY_PROSPECTIVE_V1"})
    boot=_write(tmp_path/"boot.json",{"source":{"source_max_tourney_date":"20260914"}})
    result=run(
        rapid,hold,boot,tmp_path/"out.json",
        now=datetime(2026,10,15,23,0,tzinfo=timezone.utc),
    )
    assert result["hard_bound_count"]==1
    assert result["bindings"][0]["blockers"]==["EVENT_NOT_FUTURE"]
