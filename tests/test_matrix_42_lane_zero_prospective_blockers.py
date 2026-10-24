from datetime import datetime, timezone
import json
from pathlib import Path
import tools.matrix_42_lane_zero_prospective_blockers as m

def test_blocker_report_classifies_zero_lanes(tmp_path:Path, monkeypatch):
    reg=tmp_path/"reg.json"; pri=tmp_path/"pri.json"; pro=tmp_path/"pro.json"; pla=tmp_path/"pla.json"; ser=tmp_path/"ser.json"
    lanes={
      "ACES":{"sport":"tennis","operational_state":"LAB","prospective_unique_count":0},
      "PLAYER_SHOTS":{"sport":"football","operational_state":"LAB","prospective_unique_count":0},
      "MATCH_WINNER":{"sport":"tennis","operational_state":"ACTIVE","prospective_unique_count":2},
    }
    reg.write_text(json.dumps({"status":"PASS","total_lanes":42,"lanes":lanes}),encoding="utf-8")
    pri.write_text(json.dumps({"status":"PASS","rows":[]}),encoding="utf-8")
    pro.write_text(json.dumps({"offer_audit":{"zero_freeze_reason":"NO_CANONICAL_TARGET_MARKET_OFFERS_IN_CHECKED_EVENTS"}}),encoding="utf-8")
    pla.write_text(json.dumps({"future_events_checked":20,"blockers":[{"reason":"PREMATCH_LINEUP_NOT_AVAILABLE"}]}),encoding="utf-8")
    ser.write_text(json.dumps({"status":"PASS_SOURCE_LAB"}),encoding="utf-8")
    monkeypatch.setattr(m,"REGISTRY",reg); monkeypatch.setattr(m,"PRIORITY",pri); monkeypatch.setattr(m,"PROMOTED",pro); monkeypatch.setattr(m,"PLAYER",pla); monkeypatch.setattr(m,"SERVE",ser)
    out=m.build(datetime(2026,10,24,21,0,tzinfo=timezone.utc))
    assert out["zero_prospective_lane_count"]==2
    by={x["market_lane"]:x["blocker"] for x in out["rows"]}
    assert by["ACES"]=="INPLAY_SOURCE_COVERAGE_ONLY_NO_PREMATCH_PREDICTIVE_FREEZE"
    assert by["PLAYER_SHOTS"]=="PREMATCH_LINEUP_NOT_AVAILABLE_IN_CHECKED_EVENTS"
