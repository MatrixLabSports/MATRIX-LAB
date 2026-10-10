import json
from pathlib import Path

from tools.football_daily_governed_over25 import (
    _current_future_fixture_ids,
    select_probability_cycle,
)


def _cycle(root: Path, name: str, ready: int, fixture_ids: list[str]):
    c=root/"evidence"/"api_football"/"prospective_daily"/"2026-10-10"/name
    (c/"canonical_analysis").mkdir(parents=True)
    (c/"history"/"raw").mkdir(parents=True)
    (c/"fixtures").mkdir(parents=True)
    (c/"cycle_summary.json").write_text(json.dumps({
        "status":"PASS",
        "target_date_bogota":"2026-10-10",
        "canonical":{"ready_input_count":ready},
    }),encoding="utf-8")
    (c/"canonical_analysis"/"manifest.json").write_text(json.dumps({
        "status":"PASS",
        "real_money":"BLOCKED",
    }),encoding="utf-8")
    (c/"fixtures"/"future_fixture_registry.json").write_text(json.dumps({
        "events":[{"provider_fixture_id":x} for x in fixture_ids]
    }),encoding="utf-8")
    return c


def test_probability_cycle_reuses_wider_same_day_pit_when_latest_hits_quota(tmp_path):
    old=_cycle(tmp_path,"20261010T081232Z",326,["1575182"])
    latest=_cycle(tmp_path,"20261010T115258Z",5,["1575182"])
    chosen=select_probability_cycle(tmp_path,"2026-10-10",latest)
    assert chosen==old


def test_probability_cycle_prefers_newest_on_equal_coverage(tmp_path):
    _cycle(tmp_path,"20261010T080000Z",326,["1"])
    latest=_cycle(tmp_path,"20261010T090000Z",326,["1"])
    chosen=select_probability_cycle(tmp_path,"2026-10-10",latest)
    assert chosen==latest


def test_current_future_fixture_ids_uses_latest_inventory(tmp_path):
    latest=_cycle(tmp_path,"20261010T115258Z",5,["1575178","1575182"])
    assert _current_future_fixture_ids(latest)=={"1575178","1575182"}
