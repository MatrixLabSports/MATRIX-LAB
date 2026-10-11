import json
from pathlib import Path

from tools.api_football_extended_market_coverage_probe import _players, _team, run

def test_team_fields():
    d=_team({"response":[{"statistics":[
        {"type":"Corner Kicks","value":4},{"type":"Shots on Goal","value":3},
        {"type":"Total Shots","value":10},{"type":"Yellow Cards","value":2},{"type":"Fouls","value":11}
    ]}]})
    assert d=={"corners":True,"team_shots_on_target":True,"team_total_shots":True,"cards":True,"team_fouls":True}

def test_player_fields():
    d=_players({"response":[{"players":[{"statistics":[{
        "shots":{"total":3,"on":2},"goals":{"assists":1,"saves":5},
        "passes":{"total":42},"tackles":{"total":4},"fouls":{"committed":2}
    }]}]}]})
    assert all(d.values())

class FakeClient:
    def get(self,endpoint,params):
        if endpoint=="/fixtures/statistics":
            return {"response":[{"statistics":[
                {"type":"Corner Kicks","value":5},{"type":"Shots on Goal","value":2},
                {"type":"Total Shots","value":8},{"type":"Yellow Cards","value":1},{"type":"Fouls","value":7}
            ]}]}
        return {"response":[{"players":[{"statistics":[{
            "shots":{"total":2,"on":1},"goals":{"assists":0,"saves":3},
            "passes":{"total":30},"tackles":{"total":2},"fouls":{"committed":1}
        }]}]}]}

def test_run_is_coverage_only(tmp_path:Path):
    r=run(tmp_path,client=FakeClient(),fixture_ids=["1","2"])
    assert r["status"]=="PASS"
    assert r["network_calls"]==4
    assert r["field_coverage_counts"]["corners"]==2
    assert r["field_coverage_counts"]["goalkeeper_saves"]==2
    assert r["market_state"]["CORNERS_OVER_UNDER"]["canonical_price_mapping"]=="EXISTS_R2"
    assert r["market_state"]["GOALKEEPER_SAVES"]["canonical_price_mapping"]=="MISSING_OR_REQUIRES_NEW_SCOPE"
    assert r["market_state"]["PLAYER_TACKLES"]["model_status"]=="NOT_YET_MODELED_PROSPECTIVELY"
    assert r["p_matrix_status"]=="NOT_GENERATED_FOR_EXTENDED_MARKETS"
    assert r["real_money"]=="BLOCKED"
    assert json.loads((tmp_path/"manifest.json").read_text())["status"]=="PASS"
