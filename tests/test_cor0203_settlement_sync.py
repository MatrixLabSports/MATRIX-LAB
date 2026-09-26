from pathlib import Path

from tools.cor0203_settlement_ledger import Cor0203SettlementLedger
from tools.cor0203_settlement_sync import sync_settlements


class FakeClient:
    def __init__(self, payloads):
        self.payloads = dict(payloads)
        self.request_count = 0

    def fixture_by_match_key(self, match_key):
        self.request_count += 1
        return self.payloads[match_key]


def item(start="2026-09-27T10:00:00+00:00"):
    return {
        "status": "READY_RESULT_LOOKUP",
        "event_id": "COR0203-API-TENNIS-123",
        "observation_index": 11,
        "observation_sha256": "a" * 64,
        "alphabetical_player_a": "Alpha",
        "alphabetical_player_b": "Beta",
        "event_start_utc": start,
        "provider_match_key": "123",
        "provider_player_map": {
            "api-tennis:player:10": "Alpha",
            "api-tennis:player:20": "Beta",
        },
    }


def payload(status="Finished", winner="First Player"):
    return {
        "success": 1,
        "result": [{
            "event_key": "123",
            "first_player_key": "10",
            "second_player_key": "20",
            "event_status": status,
            "event_winner": winner,
            "event_final_result": "2 - 0",
        }],
    }


def queue(row):
    return {"items": [row]}


def test_future_event_is_not_polled(tmp_path):
    client = FakeClient({"123": payload()})
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    result = sync_settlements(
        queue=queue(item(start="2026-09-28T10:00:00+00:00")),
        ledger=ledger,
        client=client,
        now_utc="2026-09-27T09:00:00+00:00",
    )
    assert result["new_settlements"] == 0
    assert result["network_calls"] == 0
    assert result["pending"][0]["reason"] == "WAITING_EVENT_START"


def test_finished_event_is_appended_without_opening_metrics(tmp_path):
    client = FakeClient({"123": payload()})
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    result = sync_settlements(
        queue=queue(item()),
        ledger=ledger,
        client=client,
        now_utc="2026-09-27T12:00:00+00:00",
    )
    assert result["new_settlements"] == 1
    assert result["network_calls"] == 1
    assert result["outcomes_used_for_metrics"] == 0
    assert result["metrics"] == "SEALED_UNTIL_600"
    records = ledger.load()
    assert records[0]["outcome_player_a"] is True
    assert records[0]["used_for_metrics"] is False


def test_live_event_stays_pending(tmp_path):
    client = FakeClient({"123": payload(status="Set 2", winner="")})
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    result = sync_settlements(
        queue=queue(item()),
        ledger=ledger,
        client=client,
        now_utc="2026-09-27T12:00:00+00:00",
    )
    assert result["new_settlements"] == 0
    assert result["pending"][0]["reason"] == "RESULT_NOT_FINAL"
    assert ledger.audit().records == 0


def test_nonstandard_terminal_requires_adjudication(tmp_path):
    client = FakeClient({"123": payload(status="Retired")})
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    result = sync_settlements(
        queue=queue(item()),
        ledger=ledger,
        client=client,
        now_utc="2026-09-27T12:00:00+00:00",
    )
    assert result["new_settlements"] == 0
    assert result["blocked"][0]["reason"].startswith(
        "NONSTANDARD_TERMINAL_REQUIRES_ADJUDICATION"
    )
    assert ledger.audit().records == 0


def test_request_budget_is_bounded(tmp_path):
    client = FakeClient({"123": payload()})
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    result = sync_settlements(
        queue=queue(item()),
        ledger=ledger,
        client=client,
        now_utc="2026-09-27T12:00:00+00:00",
        max_requests=1,
    )
    assert result["network_calls"] == 1
    assert result["new_settlements"] == 1
