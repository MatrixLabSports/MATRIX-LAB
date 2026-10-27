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
    assert r["required_field_contract"]["all_rows_schema_validated"] is True
    assert "provider_event_id" in r["required_field_contract"]["identity_fields"]
    assert "run_token" in r["required_field_contract"]["top_level_fields"]
    assert r["reporting_scope_contract"]["LIVE_THIS_RUN"]["historical_terminal_states_included"] is False
    assert r["reporting_scope_contract"]["TERMINAL_HISTORICAL"]["may_not_overwrite_immutable_attempt_rows"] is True
    assert r["reporting_scope_contract"]["legacy_combined_counts_must_not_be_interpreted_as_live_coverage"] is True
