from datetime import datetime, timezone
from pathlib import Path

from tools.cor10_genuine_future_shadow_execution import adjudicate, build


def test_cor10_future_shadow_execution_passes_literal_gate_before_kickoff():
    record=build(Path("."),datetime(2026,9,28,10,30,tzinfo=timezone.utc))
    adjudication=adjudicate(record)
    assert record["fixture_id"]=="1528902"
    assert record["bookmaker"]=="Pinnacle"
    assert record["decimal_odds"]==2.20
    assert record["stake"]["amount"]==1000
    assert record["stake"]["currency"]=="COP"
    assert record["stake"]["funds_transferred"] is False
    assert record["execution_mode"]=="SHADOW_PAPER_EXECUTION_NO_FUNDS_SENT"
    assert record["future_at_execution"] is True
    assert record["freeze_precedes_execution"] is True
    assert record["quote_precedes_execution"] is True
    assert record["odds_used_to_generate_probability"] is False
    assert record["automatic_wagering"] is False
    assert record["real_money"]=="BLOCKED"
    assert adjudication["pass"] is True
    assert adjudication["status"]=="RESOLVED"
    assert adjudication["future_execution_rate"]==1.0


def test_cor10_rejects_execution_after_kickoff():
    try:
        build(Path("."),datetime(2026,9,28,16,1,tzinfo=timezone.utc))
    except ValueError as exc:
        assert "TEMPORAL_ORDER_INVALID" in str(exc)
    else:
        raise AssertionError("post-kickoff execution must fail")
