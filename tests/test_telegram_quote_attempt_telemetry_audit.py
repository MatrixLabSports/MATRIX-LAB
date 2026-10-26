from pathlib import Path
import json

import tools.telegram_quote_attempt_telemetry_audit as mod


def test_audit_keeps_recommendation_closed_below_50(tmp_path,monkeypatch):
    ledger=tmp_path/"attempts.jsonl"
    ledger.write_text("",encoding="utf-8")
    monkeypatch.setattr(mod,"LEDGER",ledger)
    r=mod.build()
    assert r["status"]=="PASS"
    assert r["sample"]["real_quote_attempts_total"]==0
    assert r["sample"]["remaining_to_minimum"]==50
    assert r["recommendation_gate"]["recommendation_authorized"] is False
    assert r["exact_line_policy"]["nearby_lines_never_substitute_for_2_5"] is True
    assert r["protections"]["historical_terminal_state_cannot_overwrite_attempt"] is True
