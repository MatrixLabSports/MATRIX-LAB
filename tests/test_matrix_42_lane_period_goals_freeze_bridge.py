from datetime import datetime, timezone
from pathlib import Path
import json

from tools.matrix_42_lane_period_goals_freeze_bridge import build_rows


def _raw_history(path:Path):
    rows=[]
    for i in range(25):
        rows.append({
            "fixture":{"id":1000+i,"date":f"2026-09-{(i%20)+1:02d}T12:00:00+00:00","status":{"short":"FT"}},
            "teams":{"home":{"id":1 if i%2==0 else 2},"away":{"id":2 if i%2==0 else 1}},
            "score":{"halftime":{"home":1,"away":0},"fulltime":{"home":2,"away":1}},
        })
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({"response":rows}),encoding="utf-8")


def test_period_bridge_emits_six_lanes(tmp_path:Path):
    hist=tmp_path/"history.bin"; _raw_history(hist)
    source={
      "schema":"MATRIX_FOOTBALL_PROSPECTIVE_MARKET_FREEZE_V1",
      "protections":{
        "freeze_strictly_before_kickoff":True,
        "outcomes_read_at_freeze":False,
        "odds_used_to_generate_probability":False,
        "real_money":"BLOCKED",
      },
      "rows":[{
        "fixture_id":"7","home_team_id":"1","away_team_id":"2",
        "kickoff_utc":"2026-10-25T18:00:00+00:00",
        "freeze_at_utc":"2026-10-24T18:00:00+00:00",
        "historical_baseline_source":"history.bin",
        "outcome":None,
      }]
    }
    rows,audit=build_rows(source,repo_root=tmp_path,now_utc=datetime(2026,10,24,20,0,tzinfo=timezone.utc),existing_keys=set())
    assert len(rows)==8
    assert {x["market_lane"] for x in rows}=={
      "TEAM_TOTAL_GOALS_HOME","TEAM_TOTAL_GOALS_AWAY",
      "FIRST_HALF_TOTAL_GOALS_OVER_UNDER","SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
      "FIRST_HALF_TEAM_TOTAL_GOALS_HOME","FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
      "SECOND_HALF_TEAM_TOTAL_GOALS_HOME","SECOND_HALF_TEAM_TOTAL_GOALS_AWAY"
    }
    by={x["market_lane"]:x for x in rows}
    assert set(by["TEAM_TOTAL_GOALS_HOME"]["prediction"])=={"over_0_5","under_0_5","over_1_5","under_1_5","over_2_5","under_2_5"}
    assert set(by["TEAM_TOTAL_GOALS_AWAY"]["prediction"])=={"over_0_5","under_0_5","over_1_5","under_1_5","over_2_5","under_2_5"}
    assert all(x["target_outcome"] is None for x in rows)
    assert all(x["odds_used_to_generate_probability"] is False for x in rows)
    assert audit["blocked_count"]==0
