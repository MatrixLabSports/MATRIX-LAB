import json
from datetime import datetime, timezone
from pathlib import Path

from app.research.football.prospective_ledger import FootballProspectiveEvidenceLedger
from tools.football_clv_tracking_cycle import (
    capture_due_closing_lines,
    freeze_new_decisions,
    run_cycle,
)


UTC = timezone.utc


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload, status_code=200):
        self.response = FakeResponse(payload, status_code=status_code)
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({
            "url": url,
            "headers": headers,
            "params": params,
            "timeout": timeout,
        })
        return self.response


def _report(path: Path, *, with_timestamp=True):
    offer = {
        "bookmaker_id": 32,
        "bookmaker_name": "Betano",
        "bet_id": 5,
        "bet_name": "Goals Over/Under",
        "label": "Over 2.5",
        "decimal_odds": 2.00,
        "ev": 0.20,
    }
    row = {
        "fixture_id": "fx-1",
        "kickoff_utc": "2026-10-13T12:10:00+00:00",
        "p_over_2_5": 0.60,
        "raw_sha256": "b" * 64,
        "best_policy_offer": offer,
    }
    if with_timestamp:
        row["odds_captured_at_utc"] = "2026-10-13T10:00:00+00:00"
        offer["odds_captured_at_utc"] = "2026-10-13T10:00:00+00:00"
        offer["provider_quote_updated_at_utc"] = "2026-10-13T09:59:00+00:00"
        offer["raw_sha256"] = "b" * 64
        offer["quote_evidence_sha256"] = "a" * 64

    payload = {
        "schema": "MATRIX_FOOTBALL_DAILY_OVER25_GOVERNED_SHADOW_EV_V2",
        "target_date_bogota": "2026-10-13",
        "market": "OVER_2_5",
        "sha256_without_self": "c" * 64,
        "bet_shadow": [row],
        "protections": {
            "odds_used_to_generate_probability": False,
            "real_money": "BLOCKED",
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _pinnacle_payload(update="2026-10-13T11:59:00+00:00"):
    return {
        "errors": {},
        "response": [{
            "fixture": {"id": "fx-1"},
            "update": update,
            "bookmakers": [{
                "id": 4,
                "name": "Pinnacle",
                "bets": [{
                    "id": 5,
                    "name": "Goals Over/Under",
                    "values": [
                        {"value": "Over 2.5", "odd": "1.90"},
                        {"value": "Under 2.5", "odd": "1.90"},
                    ],
                }],
            }],
        }],
    }


def test_legacy_report_without_physical_entry_timestamp_is_not_backfilled(tmp_path):
    report = _report(tmp_path / "report.json", with_timestamp=False)
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")

    result = freeze_new_decisions(report, ledger)

    assert result["frozen_new"] == 0
    assert result["blocked_missing_entry_timestamp"] == 1
    assert ledger.audit().decision_count == 0


def test_timestamped_entry_freezes_once_and_hash_chain_verifies(tmp_path):
    report = _report(tmp_path / "report.json", with_timestamp=True)
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")

    first = freeze_new_decisions(report, ledger)
    second = freeze_new_decisions(report, ledger)
    audit = ledger.audit()

    assert first["frozen_new"] == 1
    assert second["frozen_new"] == 0
    assert second["skipped_existing"] == 1
    assert audit.decision_count == 1
    assert audit.closing_odds_count == 0
    assert audit.timestamp_integrity_verified is True
    assert len(audit.ledger_sha256) == 64


def test_due_pinnacle_close_requires_complete_market_and_writes_devigged_clv(tmp_path):
    report = _report(tmp_path / "report.json", with_timestamp=True)
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    freeze_new_decisions(report, ledger)
    session = FakeSession(_pinnacle_payload())
    capture_at = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)

    attempts = tmp_path / "attempts.jsonl"
    result = capture_due_closing_lines(
        ledger,
        tmp_path / "captures",
        api_key="test-key",
        now=capture_at,
        session=session,
        capture_clock=lambda: capture_at,
        attempt_log_path=attempts,
    )

    assert result["due_count"] == 1
    assert result["network_calls"] == 1
    assert result["captured_new"] == 1
    assert ledger.audit().closing_odds_count == 1
    captures = list((tmp_path / "captures").glob("*.json"))
    assert len(captures) == 1
    evidence = json.loads(captures[0].read_text(encoding="utf-8"))
    assert evidence["closing"]["provider"] == "Pinnacle"
    assert evidence["closing"]["source_quality_flag"] == "SHARP_PINNACLE_VIA_API_FOOTBALL_STRICT_120S"
    assert evidence["closing"]["complete_market_snapshot"] is True
    assert evidence["closing"]["devig_method"] == "MULTIPLICATIVE"
    assert evidence["closing"]["fair_over_2_5_probability_devigged"] == 0.5
    assert evidence["clv"]["probability_clv_vs_devigged_close"] == 0.0
    assert evidence["protections"]["real_money"] == "BLOCKED"
    attempt_rows = [json.loads(x) for x in attempts.read_text(encoding="utf-8").splitlines()]
    assert len(attempt_rows) == 1
    assert attempt_rows[0]["outcome"] == "CAPTURED_VALID"
    assert attempt_rows[0]["provider_quote_age_seconds"] == 60
    assert attempt_rows[0]["gate_excess_seconds"] == 0
    assert attempt_rows[0]["strict_fresh_gate_seconds"] == 120
    assert len(attempt_rows[0]["attempt_sha256"]) == 64


def test_stale_pinnacle_provider_update_fails_closed(tmp_path):
    report = _report(tmp_path / "report.json", with_timestamp=True)
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    freeze_new_decisions(report, ledger)
    session = FakeSession(_pinnacle_payload(update="2026-10-13T08:00:00+00:00"))
    capture_at = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)

    attempts = tmp_path / "attempts.jsonl"
    result = capture_due_closing_lines(
        ledger,
        tmp_path / "captures",
        api_key="test-key",
        now=capture_at,
        session=session,
        capture_clock=lambda: capture_at,
        attempt_log_path=attempts,
    )

    assert result["captured_new"] == 0
    assert result["blocked_stale_provider_quote"] == 1
    assert ledger.audit().closing_odds_count == 0
    rows = [json.loads(x) for x in attempts.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["outcome"] == "BLOCKED_STALE_PROVIDER_QUOTE"
    assert rows[-1]["provider_quote_age_seconds"] == 14400
    assert rows[-1]["gate_excess_seconds"] == 14280




def test_incomplete_api_football_market_persists_subreason(tmp_path):
    report = _report(tmp_path / "report.json", with_timestamp=True)
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    freeze_new_decisions(report, ledger)
    payload = _pinnacle_payload()
    payload["response"][0]["bookmakers"][0]["bets"][0]["values"] = [
        {"value": "Over 2.5", "odd": "1.90"},
    ]
    capture_at = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    attempts = tmp_path / "attempts.jsonl"
    result = capture_due_closing_lines(
        ledger,
        tmp_path / "captures",
        api_key="test-key",
        now=capture_at,
        session=FakeSession(payload),
        capture_clock=lambda: capture_at,
        attempt_log_path=attempts,
    )
    assert result["captured_new"] == 0
    assert result["blocked_market_incomplete"] == 1
    row = json.loads(attempts.read_text(encoding="utf-8").splitlines()[-1])
    assert row["outcome"] == "BLOCKED_MARKET_INCOMPLETE"
    assert row["market_diagnostic"]["pinnacle_bookmaker_present"] is True
    assert row["market_diagnostic"]["goals_over_under_market_present"] is True
    assert row["market_diagnostic"]["over_2_5_present"] is True
    assert row["market_diagnostic"]["under_2_5_present"] is False
    assert row["market_diagnostic"]["incomplete_reason"] == "UNDER_2_5_MISSING"


def test_pinnacle_quote_older_than_strict_120_seconds_is_not_closing_line(tmp_path):
    report = _report(tmp_path / "report.json", with_timestamp=True)
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    freeze_new_decisions(report, ledger)
    # Capture is 12:00 UTC; provider quote is 2m01s old.
    session = FakeSession(_pinnacle_payload(update="2026-10-13T11:57:59+00:00"))
    capture_at = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)

    attempts = tmp_path / "attempts.jsonl"
    result = capture_due_closing_lines(
        ledger,
        tmp_path / "captures",
        api_key="test-key",
        now=capture_at,
        session=session,
        capture_clock=lambda: capture_at,
        attempt_log_path=attempts,
    )

    assert result["captured_new"] == 0
    assert result["blocked_stale_provider_quote"] == 1
    assert ledger.audit().closing_odds_count == 0
    rows = [json.loads(x) for x in attempts.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["provider_quote_age_seconds"] == 121
    assert rows[-1]["gate_excess_seconds"] == 1

def test_cycle_keeps_clv_metrics_sealed_below_300(tmp_path):
    report = _report(tmp_path / "report.json", with_timestamp=True)
    session = FakeSession(_pinnacle_payload())
    capture_at = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)

    state = run_cycle(
        report_path=report,
        ledger_path=tmp_path / "ledger.jsonl",
        capture_dir=tmp_path / "captures",
        state_path=tmp_path / "state.json",
        attempt_log_path=tmp_path / "attempts.jsonl",
        api_key="test-key",
        now=capture_at,
        session=session,
        capture_clock=lambda: capture_at,
    )

    assert state["decision_count"] == 1
    assert state["closing_odds_count"] == 1
    assert state["minimum_clv_closing_observations"] == 300
    assert state["remaining_to_open_metrics"] == 299
    assert state["metrics_opened"] is False
    assert state["metrics"] is None
    assert state["status"] == "ACCUMULATING_SEALED_UNTIL_300"
    assert state["protections"]["automatic_wagering"] is False
    assert state["protections"]["real_money"] == "BLOCKED"
