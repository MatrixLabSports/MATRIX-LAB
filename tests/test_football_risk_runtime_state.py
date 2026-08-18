from datetime import datetime, timedelta, timezone
import json

import pytest

from app.application.football.risk_runtime_state import (
    FootballRiskStateEvent,
    FootballRiskStateLedger,
)

UTC = timezone.utc
BASE = datetime(2026, 8, 18, 14, 0, tzinfo=UTC)


def event(kind, minutes=0, **payload):
    return FootballRiskStateEvent(kind, BASE + timedelta(minutes=minutes), payload)


def initialized():
    return event("INITIALIZED", bankroll=100000, business_date="2026-08-18")


def test_runtime_state_rebuilds_across_restart(tmp_path):
    path = tmp_path / "risk.jsonl"
    ledger = FootballRiskStateLedger(path)
    ledger.append(initialized())
    ledger.append(event("EXPOSURE_OPENED", 1, market_key="h2h", amount=500))
    ledger.append(event("APPROVAL_CONSUMED", 2, approval_id="ap-1"))
    state = FootballRiskStateLedger(path).rebuild_state()
    assert state.bankroll == 100000
    assert state.daily_exposure == 500
    assert state.total_open_exposure == 500
    assert state.market_amount("h2h") == 500
    assert "ap-1" in state.consumed_approval_ids


def test_runtime_state_rejects_settlement_above_open_exposure(tmp_path):
    ledger = FootballRiskStateLedger(tmp_path / "risk.jsonl")
    ledger.append(initialized())
    ledger.append(event("EXPOSURE_OPENED", 1, market_key="totals", amount=300))
    ledger.append(event("EXPOSURE_SETTLED", 2, market_key="totals", amount=400))
    with pytest.raises(ValueError, match="settle more"):
        ledger.rebuild_state()


def test_runtime_state_rejects_approval_replay(tmp_path):
    ledger = FootballRiskStateLedger(tmp_path / "risk.jsonl")
    ledger.append(initialized())
    ledger.append(event("APPROVAL_CONSUMED", 1, approval_id="ap-1"))
    ledger.append(event("APPROVAL_CONSUMED", 2, approval_id="ap-1"))
    with pytest.raises(ValueError, match="already consumed"):
        ledger.rebuild_state()


def test_runtime_state_rollover_requires_no_open_exposure(tmp_path):
    ledger = FootballRiskStateLedger(tmp_path / "risk.jsonl")
    ledger.append(initialized())
    ledger.append(event("EXPOSURE_OPENED", 1, market_key="h2h", amount=100))
    ledger.append(event("DAY_ROLLOVER", 2, business_date="2026-08-19"))
    with pytest.raises(ValueError, match="open exposure"):
        ledger.rebuild_state()


def test_runtime_state_rollover_resets_daily_exposure_after_settlement(tmp_path):
    ledger = FootballRiskStateLedger(tmp_path / "risk.jsonl")
    ledger.append(initialized())
    ledger.append(event("EXPOSURE_OPENED", 1, market_key="h2h", amount=100))
    ledger.append(event("EXPOSURE_SETTLED", 2, market_key="h2h", amount=100))
    ledger.append(event("DAY_ROLLOVER", 3, business_date="2026-08-19"))
    state = ledger.rebuild_state()
    assert state.daily_exposure == 0
    assert state.total_open_exposure == 0
    assert state.business_date.isoformat() == "2026-08-19"


def test_runtime_state_kill_switch_persists(tmp_path):
    path = tmp_path / "risk.jsonl"
    ledger = FootballRiskStateLedger(path)
    ledger.append(initialized())
    ledger.append(event("KILL_SWITCH_SET", 1, active=True))
    assert FootballRiskStateLedger(path).rebuild_state().manual_kill_switch_active is True


def test_runtime_state_peak_bankroll_is_monotonic(tmp_path):
    ledger = FootballRiskStateLedger(tmp_path / "risk.jsonl")
    ledger.append(initialized())
    ledger.append(event("BANKROLL_MARKED", 1, bankroll=105000))
    ledger.append(event("BANKROLL_MARKED", 2, bankroll=99000))
    state = ledger.rebuild_state()
    assert state.bankroll == 99000
    assert state.peak_bankroll == 105000


def test_runtime_state_detects_tampering(tmp_path):
    path = tmp_path / "risk.jsonl"
    ledger = FootballRiskStateLedger(path)
    ledger.append(initialized())
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["event"]["payload"]["bankroll"] = 999999
    path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        ledger.load()


def test_runtime_state_rejects_time_reversal(tmp_path):
    ledger = FootballRiskStateLedger(tmp_path / "risk.jsonl")
    ledger.append(initialized())
    with pytest.raises(ValueError, match="backwards"):
        ledger.append(FootballRiskStateEvent("KILL_SWITCH_SET", BASE - timedelta(seconds=1), {"active": True}))
