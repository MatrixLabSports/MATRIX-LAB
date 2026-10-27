import json
from pathlib import Path
import tools.matrix_football_signal_market_eligibility as m

def dump(path:Path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj),encoding="utf-8")

def test_registry_only_promotes_physically_authorized_market(tmp_path,monkeypatch):
    root=tmp_path/"evidence/api_football"; monkeypatch.setattr(m,"ROOT",root)
    dump(root/"governance/over_2_5_p_matrix_promotion.json",{"promotion_status":"PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"})
    dump(root/"calibration_v2/OOS_4001_5000_STATE.json",{"current_oos_observations":796,"remaining_to_1000":204})
    dump(root/"calibration_v2/lanes/double_chance_12/state.json",{"status":"BLOCKED_NOT_PROMOTED","blocker":"x"})
    dump(root/"calibration_v2/lanes/btts/state.json",{"status":"BLOCKED_NEW_CHALLENGER_REQUIRED","blocker":"y"})
    for name,n in [("team_total_shots_home",2),("team_total_shots_away",2),("team_fouls_total",1)]:
        dump(root/f"promoted_team_markets/{name}/state.json",{"freeze_observation_count":n,"gates":{"30":{"remaining":30-n}}})
    dump(root/"player_shots_v3_prospective/state.json",{"freeze_observation_count":0,"gates":{"30":{"remaining":30}}})
    dump(root/"market_expansion/failed_team_markets_v3/summary.json",{"lanes":{}})
    out=m.build()
    assert out["signal_eligible_markets"]==["OVER_2_5"]
    assert out["markets"]["1X2"]["status"]=="BLOCKED_UNTIL_OOS1000_ADJUDICATION"
    assert out["markets"]["1X2"]["oos_progress"]==796
    assert out["markets"]["UNDER_2_5"]["oos_remaining"]==204
    assert out["markets"]["BTTS"]["signal_eligible"] is False
    assert out["markets"]["FIRST_HALF_GOALS"]["status"]=="NOT_IMPLEMENTED_NO_CALIBRATED_LANE_FOUND"
    assert out["markets"]["SECOND_HALF_GOALS"]["status"]=="NOT_IMPLEMENTED_NO_CALIBRATED_LANE_FOUND"
    assert out["protections"]["real_money"]=="BLOCKED"
