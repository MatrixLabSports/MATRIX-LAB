import json
from pathlib import Path

from tools.football_4000_canonical_tracker import TARGET


def test_target_is_4000():
    assert TARGET == 4000


def test_current_sources_reconcile_physically():
    root=Path("evidence/api_football")
    settlement=json.loads((root/"prospective_market_freeze/settlement_sync_last.json").read_text())
    calibration=json.loads((root/"prospective_calibration/sync_last.json").read_text())
    frozen=int(settlement["frozen_event_count"])
    settled=int(settlement["ledger_final_count"])
    pending=len(settlement.get("pending") or [])
    blocked=len(settlement.get("blocked") or [])
    assert frozen == settled + pending + blocked
    assert settled == int(calibration["calibration_observation_count"])


def test_v2_lane_is_not_global_counter():
    root=Path("evidence/api_football")
    global_settled=json.loads((root/"prospective_market_freeze/settlement_sync_last.json").read_text())["ledger_final_count"]
    lane=json.loads((root/"calibration_v2/lanes/over_2_5/state.json").read_text())
    assert lane["cohort_id"] == "FOOTBALL_ALL_MARKETS_V2_20261004"
    assert int(lane["settlement_count"]) <= int(global_settled)
