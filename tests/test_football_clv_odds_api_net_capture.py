import json
from datetime import datetime, timezone
from pathlib import Path

from app.research.football.prospective_ledger import (
    FootballProspectiveEvidenceLedger,
    FrozenProspectiveDecision,
)
from tools.football_clv_odds_api_net_capture import capture_due_via_odds_api_net


UTC = timezone.utc


class Resp:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class RoutedSession:
    def __init__(self, capture_at, quote_age_seconds=60):
        self.capture_at = capture_at
        self.quote_age_seconds = quote_age_seconds
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, params or {}))
        if url.endswith("/fixtures"):
            return Resp({
                "response": [{
                    "teams": {
                        "home": {"name": "Alpha FC"},
                        "away": {"name": "Beta United"},
                    }
                }]
            })
        if url.endswith("/events"):
            return Resp({
                "items": [{
                    "event_id": "oa-123",
                    "home_team": "Alpha FC",
                    "away_team": "Beta United",
                }]
            })
        if "/odds/snapshot" in url:
            ts_ms = int((self.capture_at.timestamp() - self.quote_age_seconds) * 1000)
            return Resp({
                "bookmaker_as_of_ts_ms": {"pinnacle": ts_ms},
                "items": [
                    {
                        "bookmaker": "pinnacle",
                        "market_key": "total",
                        "bet_type": "total",
                        "side": "over",
                        "selection_name": "Over 2.5",
                        "line": 2.5,
                        "odds": 1.91,
                        "is_available": True,
                    },
                    {
                        "bookmaker": "pinnacle",
                        "market_key": "total",
                        "bet_type": "total",
                        "side": "under",
                        "selection_name": "Under 2.5",
                        "line": 2.5,
                        "odds": 1.93,
                        "is_available": True,
                    },
                ],
            })
        raise AssertionError(url)



class IncompleteRoutedSession(RoutedSession):
    def get(self, url, headers=None, params=None, timeout=None):
        if "/odds/snapshot" in url:
            self.calls.append((url, params or {}))
            ts_ms = int((self.capture_at.timestamp() - 60) * 1000)
            return Resp({
                "bookmaker_as_of_ts_ms": {"pinnacle": ts_ms},
                "items": [
                    {
                        "bookmaker": "pinnacle",
                        "market_key": "total",
                        "bet_type": "total",
                        "side": "over",
                        "selection_name": "Over 3.0",
                        "line": 3.0,
                        "odds": 1.91,
                        "is_available": True,
                    },
                    {
                        "bookmaker": "pinnacle",
                        "market_key": "total",
                        "bet_type": "total",
                        "side": "under",
                        "selection_name": "Under 3.0",
                        "line": 3.0,
                        "odds": 1.93,
                        "is_available": True,
                    },
                ],
            })
        return super().get(url, headers=headers, params=params, timeout=timeout)


def _ledger(tmp_path: Path) -> FootballProspectiveEvidenceLedger:
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.append_decision(FrozenProspectiveDecision(
        decision_id="clv-over25-test",
        fixture_id="fx-1",
        market_key="over_2_5",
        selection_key="over",
        model_version="calibrated_log_pool_v1_over_2_5",
        model_probability=0.61,
        decision_at_utc="2026-10-15T14:00:00+00:00",
        fixture_kickoff_utc="2026-10-15T15:00:00+00:00",
        block_id="2026-10-15",
        odds_snapshot_sha256="a"*64,
        odds_observed_at_utc="2026-10-15T14:00:00+00:00",
        decimal_odds=1.95,
        odds_source_provider="Betano",
        odds_source_reference="test",
        odds_source_authorized=True,
        model_input_sha256s=("b"*64,),
    ))
    return ledger


def test_missing_odds_api_credential_fails_closed_without_touching_ledger(tmp_path):
    ledger = _ledger(tmp_path)
    now = datetime(2026, 10, 15, 14, 50, tzinfo=UTC)
    result = capture_due_via_odds_api_net(
        ledger_path=ledger.path,
        capture_dir=tmp_path / "captures",
        attempt_log_path=tmp_path / "attempts.jsonl",
        api_football_key="af",
        odds_api_key="",
        now=now,
    )
    assert result["due_count"] == 1
    assert result["blocked_credential"] == 1
    assert result["captured_new"] == 0
    assert ledger.audit().closing_odds_count == 0


def test_fresh_odds_api_pinnacle_close_is_persisted_automatically(tmp_path):
    ledger = _ledger(tmp_path)
    capture_at = datetime(2026, 10, 15, 14, 50, tzinfo=UTC)
    session = RoutedSession(capture_at)
    attempts = tmp_path / "attempts.jsonl"
    result = capture_due_via_odds_api_net(
        ledger_path=ledger.path,
        capture_dir=tmp_path / "captures",
        attempt_log_path=attempts,
        api_football_key="af",
        odds_api_key="oa",
        now=capture_at,
        session=session,
        capture_clock=lambda: capture_at,
    )
    assert result["due_count"] == 1
    assert result["captured_new"] == 1
    assert result["blocked_stale_provider_quote"] == 0
    assert result["network_calls"] == 3
    assert ledger.audit().closing_odds_count == 1
    captures = list((tmp_path / "captures").glob("*.json"))
    assert len(captures) == 1
    evidence = json.loads(captures[0].read_text(encoding="utf-8"))
    assert evidence["closing"]["transport"] == "odds-api.net"
    assert evidence["closing"]["provider_quote_age_seconds"] == 60
    assert evidence["closing"]["source_quality_flag"] == "SHARP_PINNACLE_VIA_ODDS_API_NET_STRICT_120S_AUTO"
    assert evidence["protections"]["real_money"] == "BLOCKED"
    rows = [json.loads(x) for x in attempts.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["outcome"] == "ODDS_API_CAPTURED_VALID"
    assert rows[-1]["attempted_at_utc"] == capture_at.isoformat()
    assert rows[-1]["provider_quote_updated_at_utc"] == "2026-10-15T14:49:00+00:00"
    assert rows[-1]["provider_quote_age_seconds"] == 60
    assert rows[-1]["gate_excess_seconds"] == 0

def test_stale_odds_api_attempt_persists_exact_gate_excess(tmp_path):
    ledger = _ledger(tmp_path)
    capture_at = datetime(2026, 10, 15, 14, 50, tzinfo=UTC)
    session = RoutedSession(capture_at, quote_age_seconds=121)
    attempts = tmp_path / "attempts.jsonl"
    result = capture_due_via_odds_api_net(
        ledger_path=ledger.path,
        capture_dir=tmp_path / "captures",
        attempt_log_path=attempts,
        api_football_key="af",
        odds_api_key="oa",
        now=capture_at,
        session=session,
        capture_clock=lambda: capture_at,
    )
    assert result["captured_new"] == 0
    assert result["blocked_stale_provider_quote"] == 1
    rows = [json.loads(x) for x in attempts.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["outcome"] == "ODDS_API_BLOCKED_STALE_PROVIDER_QUOTE"
    assert rows[-1]["attempted_at_utc"] == capture_at.isoformat()
    assert rows[-1]["provider_quote_updated_at_utc"] == "2026-10-15T14:47:59+00:00"
    assert rows[-1]["provider_quote_age_seconds"] == 121
    assert rows[-1]["gate_excess_seconds"] == 1


def test_incomplete_odds_api_market_persists_total_25_missing(tmp_path):
    ledger = _ledger(tmp_path)
    capture_at = datetime(2026, 10, 15, 14, 50, tzinfo=UTC)
    attempts = tmp_path / "attempts.jsonl"
    result = capture_due_via_odds_api_net(
        ledger_path=ledger.path,
        capture_dir=tmp_path / "captures",
        attempt_log_path=attempts,
        api_football_key="af",
        odds_api_key="oa",
        now=capture_at,
        session=IncompleteRoutedSession(capture_at),
        capture_clock=lambda: capture_at,
    )
    assert result["captured_new"] == 0
    assert result["blocked_market_incomplete"] == 1
    row = json.loads(attempts.read_text(encoding="utf-8").splitlines()[-1])
    assert row["outcome"] == "ODDS_API_BLOCKED_MARKET_INCOMPLETE"
    assert row["market_diagnostic"]["provider_timestamp_present"] is True
    assert row["market_diagnostic"]["pinnacle_item_count"] == 2
    assert row["market_diagnostic"]["total_market_item_count"] == 2
    assert row["market_diagnostic"]["available_total_lines"] == [3.0]
    assert row["market_diagnostic"]["incomplete_reason"] == "TOTAL_2_5_LINE_MISSING"


class LabelOnlyLineSession(RoutedSession):
    def get(self, url, headers=None, params=None, timeout=None):
        if "/odds/snapshot" in url:
            self.calls.append((url, params or {}))
            ts_ms = int((self.capture_at.timestamp() - 60) * 1000)
            return Resp({
                "bookmaker_as_of_ts_ms": {"pinnacle": ts_ms},
                "items": [
                    {
                        "bookmaker": "pinnacle",
                        "market_key": "total",
                        "bet_type": "total",
                        "side": "over",
                        "selection_name": "Over 2.5",
                        "line": None,
                        "odds": 1.91,
                        "is_available": True,
                    },
                    {
                        "bookmaker": "pinnacle",
                        "market_key": "total",
                        "bet_type": "total",
                        "side": "under",
                        "selection_name": "Under 2.5",
                        "line": None,
                        "odds": 1.93,
                        "is_available": True,
                    },
                ],
            })
        return super().get(url, headers=headers, params=params, timeout=timeout)


def test_exact_total_25_can_be_recovered_from_explicit_selection_label(tmp_path):
    ledger = _ledger(tmp_path)
    capture_at = datetime(2026, 10, 15, 14, 50, tzinfo=UTC)
    attempts = tmp_path / "attempts.jsonl"
    result = capture_due_via_odds_api_net(
        ledger_path=ledger.path,
        capture_dir=tmp_path / "captures",
        attempt_log_path=attempts,
        api_football_key="af",
        odds_api_key="oa",
        now=capture_at,
        session=LabelOnlyLineSession(capture_at),
        capture_clock=lambda: capture_at,
    )
    assert result["captured_new"] == 1
    assert ledger.audit().closing_odds_count == 1
    rows = [json.loads(x) for x in attempts.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["outcome"] == "ODDS_API_CAPTURED_VALID"


class CurrentOddsApiLineContractSession(RoutedSession):
    def get(self, url, headers=None, params=None, timeout=None):
        if "/odds/snapshot" in url:
            self.calls.append((url, params or {}))
            ts_ms = int((self.capture_at.timestamp() - 60) * 1000)
            return Resp({
                "bookmaker_as_of_ts_ms": {"pinnacle": ts_ms},
                "items": [
                    {
                        "bookmaker": "pinnacle",
                        "market_key": "total/cards/over 2.5 (full time)",
                        "bet_type": "total",
                        "metric": "cards",
                        "period": "full time",
                        "selection_name": "over",
                        "side": None,
                        "line": "over 2.5",
                        "odds": 1.40,
                        "is_available": True,
                    },
                    {
                        "bookmaker": "pinnacle",
                        "market_key": "total/over 2.5 (full time)",
                        "bet_type": "total",
                        "metric": "standard",
                        "period": "full time",
                        "selection_name": "over",
                        "side": None,
                        "line": "over 2.5",
                        "odds": 1.91,
                        "is_available": True,
                    },
                    {
                        "bookmaker": "pinnacle",
                        "market_key": "total/under 2.5 (full time)",
                        "bet_type": "total",
                        "metric": "standard",
                        "period": "full time",
                        "selection_name": "under",
                        "side": None,
                        "line": "under 2.5",
                        "odds": 1.93,
                        "is_available": True,
                    },
                ],
            })
        return super().get(url, headers=headers, params=params, timeout=timeout)


def test_current_odds_api_side_prefixed_line_contract_is_parsed_strictly(tmp_path):
    ledger = _ledger(tmp_path)
    capture_at = datetime(2026, 10, 15, 14, 50, tzinfo=UTC)
    attempts = tmp_path / "attempts.jsonl"
    result = capture_due_via_odds_api_net(
        ledger_path=ledger.path,
        capture_dir=tmp_path / "captures",
        attempt_log_path=attempts,
        api_football_key="af",
        odds_api_key="oa",
        now=capture_at,
        session=CurrentOddsApiLineContractSession(capture_at),
        capture_clock=lambda: capture_at,
    )
    assert result["captured_new"] == 1
    captures = list((tmp_path / "captures").glob("*.json"))
    assert len(captures) == 1
    evidence = json.loads(captures[0].read_text(encoding="utf-8"))
    assert evidence["closing"]["over_2_5_decimal_odds"] == 1.91
    assert evidence["closing"]["under_2_5_decimal_odds"] == 1.93
