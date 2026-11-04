"""Live Tennis must persist honest failures without bypassing free-provider reserves."""
import json,sys
from pathlib import Path
from unittest.mock import patch
from tools import live_tennis_bulk_collector as mod

D="2026-11-04"
GUARD=Path(f"evidence/live_tennis_lab/{D}/MATRIX_LIVE_TENNIS_QUOTA_GUARD_LAST.json")
LEDGER=Path(f"evidence/live_tennis_lab/{D}/MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json")

def run(monkeypatch,tmp_path,status,remaining=None,existing=False):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVE_TENNIS_API_KEY","private-test-key")
    monkeypatch.setattr(sys,"argv",["live_tennis_bulk_collector","--date",D,
                       "--cycles","6","--reserve-calls","20"])
    if existing:
        p=tmp_path/LEDGER;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('{"original":"immutable"}')
    def get_json(path,key,params=None):
        assert path=="/usage"
        if status==429:return {},{"http_status":429}
        return {"tier":"free","limits":{"per_day":100},
                "today":{"remaining_day":remaining}},{"http_status":status}
    monkeypatch.setattr(mod,"get_json",get_json)
    mod.main()
    return json.loads((tmp_path/GUARD).read_text())

def test_quota_11_never_spends_20_reserved_calls(monkeypatch,tmp_path):
    original=b'{"original":"immutable"}'
    guard=run(monkeypatch,tmp_path,200,11,existing=True)
    assert guard["status"]=="BLOCKED_BY_RESERVE"
    assert guard["executed_cycles"]==0
    assert guard["reserve_calls"]==20
    assert guard["protections"]["reserve_not_bypassed"] is True
    assert (tmp_path/LEDGER).read_bytes()==original

def test_http_429_persists_truth_and_no_ledger(monkeypatch,tmp_path):
    guard=run(monkeypatch,tmp_path,429)
    assert guard["status"]=="BLOCKED_PROVIDER_USAGE_HTTP_429"
    assert guard["executed_cycles"]==0
    assert not (tmp_path/LEDGER).exists()

def test_missing_api_key_is_durable_and_non_blocking(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIVE_TENNIS_API_KEY",raising=False)
    monkeypatch.setattr(sys,"argv",["collector","--date",D])
    with patch.object(mod,"get_json",side_effect=AssertionError("NO_NETWORK")):
        mod.main()
    guard=json.loads((tmp_path/GUARD).read_text())
    assert guard["status"]=="BLOCKED_MISSING_PROVIDER_KEY"
    assert guard["executed_cycles"]==0

def test_unknown_usage_is_not_interpreted_as_zero_or_spent(monkeypatch,tmp_path):
    guard=run(monkeypatch,tmp_path,200,None)
    assert guard["status"]=="BLOCKED_USAGE_REMAINING_UNVERIFIED"
    assert guard["executed_cycles"]==0
