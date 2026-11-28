"""Bounded settlement never confuses a five-minute runner with API polling."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from tools.matrix_over25_settlement_due import execute, is_due
from tools.matrix_independent_over25_research_settlement import REPORT

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)

def write_report(tmp_path, checked_at):
    p = tmp_path / REPORT
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"checked_at_utc":checked_at.isoformat()}), encoding="utf-8")
    return p

def test_no_new_provider_calls_within_two_hour_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("REAL_MONEY", "BLOCKED")
    monkeypatch.setenv("AUTO_BETTING", "DISABLED")
    write_report(tmp_path, NOW - timedelta(minutes=5))
    assert is_due(tmp_path, NOW) is False
    assert execute(tmp_path, NOW, token="")["status"] == "RATE_GUARD_NOT_DUE"

def test_due_cycle_is_bounded_and_preserves_fail_closed_state(tmp_path, monkeypatch):
    import tools.matrix_over25_settlement_due as runner
    monkeypatch.setenv("REAL_MONEY", "BLOCKED")
    monkeypatch.setenv("AUTO_BETTING", "DISABLED")
    write_report(tmp_path, NOW - timedelta(hours=3))
    calls = []
    def fake(root, *, now, token, max_calls):
        calls.append((max_calls, token))
        return {"checked_at_utc":now.isoformat(),"http_calls":0,"settled_total":0,
                "unique_fixture_count":0,"telegram_signal_authorized":False,
                "real_money":"BLOCKED"}
    monkeypatch.setattr(runner, "settle", fake)
    result = execute(tmp_path, NOW, "secret-not-logged")
    assert calls == [(2,"secret-not-logged")]
    assert result["status"] == "VERIFIED_RESEARCH_SETTLEMENT_CYCLE"
    assert "secret" not in json.dumps(result)
    assert is_due(tmp_path, NOW + timedelta(minutes=5)) is False

def test_future_report_time_blocks_instead_of_backdating(tmp_path):
    write_report(tmp_path, NOW + timedelta(minutes=20))
    with pytest.raises(ValueError, match="FUTURE_TIME"):
        is_due(tmp_path, NOW)

def test_money_controls_cannot_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("REAL_MONEY", "ENABLED")
    monkeypatch.setenv("AUTO_BETTING", "DISABLED")
    with pytest.raises(ValueError, match="MONEY_GUARD"):
        execute(tmp_path, NOW, "token")


def test_verified_hash_recovery_allows_one_zero_http_retry(tmp_path):
    p = write_report(tmp_path, NOW - timedelta(minutes=6))
    doc = json.loads(p.read_text())
    doc.update({"http_calls":0,"decisions":[{"status":"BLOCKED_INVALID_SOURCE",
                                              "reason":"SOURCE_HASH_MISMATCH"}]})
    p.write_text(json.dumps(doc), encoding="utf-8")
    proof = tmp_path / "evidence/football_world_inventory/MATRIX_OVER25_MISSING_SOURCE_EXACT_RESTORE_LAST.json"
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text(json.dumps({"schema":"MATRIX_OVER25_MISSING_SOURCE_RESTORE_V1",
      "source_refs_checked":24,"already_verified":24,
      "unrecoverable_source_count":0}), encoding="utf-8")
    assert is_due(tmp_path, NOW) is True
    doc["http_calls"] = 1
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert is_due(tmp_path, NOW) is False


def test_missing_integrity_proof_cannot_override_rate_gate(tmp_path):
    p = write_report(tmp_path, NOW - timedelta(minutes=6))
    doc = {"checked_at_utc":(NOW - timedelta(minutes=6)).isoformat(),
           "http_calls":0,"decisions":[{"status":"BLOCKED_INVALID_SOURCE"}]}
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert is_due(tmp_path, NOW) is False
