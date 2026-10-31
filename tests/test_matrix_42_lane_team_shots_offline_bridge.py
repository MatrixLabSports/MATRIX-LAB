from datetime import datetime, timezone
from tools.matrix_42_lane_team_shots_offline_bridge import build_rows


def _model(side,line):
    return {
      "prospective_eligible":True,"status":"FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION",
      "historical_evaluation_line":line,"odds_used_to_generate_probability":False,"real_money":"BLOCKED",
      "model_parameters_sha256":"a"*64,
      "model_parameters":{"weights":[2.5,0.1],"means":[12.0],"stds":[1.0]},
    }


def test_offline_team_shots_bridge_uses_only_prior_pit():
    pit=[]
    for i in range(6):
      pit.append({
        "fixture_id":str(100+i),"kickoff_utc":f"2026-10-{10+i:02d}T12:00:00+00:00",
        "league_id":"39","season":2026,"home_team_id":"1","away_team_id":"2",
        "target_home":14+i%2,"target_away":11+i%2,
      })
    source={"schema":"X","rows":[{
      "fixture_id":"999","kickoff_utc":"2026-10-26T12:00:00+00:00","freeze_at_utc":"2026-10-24T20:00:00+00:00",
      "competition_id":"39","season":2026,"home_team_id":"1","away_team_id":"2","outcome":None
    }]}
    rows,audit=build_rows(source=source,pit_rows=pit,home_model=_model("HOME",15.5),away_model=_model("AWAY",11.5),now_utc=datetime(2026,10,24,21,0,tzinfo=timezone.utc),existing_keys=set())
    assert len(rows)==2
    assert {x["market_lane"] for x in rows}=={"TEAM_TOTAL_SHOTS_HOME","TEAM_TOTAL_SHOTS_AWAY"}
    assert all(x["price_observed"] is False for x in rows)
    assert all(x["odds_used_to_generate_probability"] is False for x in rows)
    assert audit["protections"]["network_calls"]==0
    assert audit["protections"]["same_match_target_used_in_features"] is False
