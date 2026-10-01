from pathlib import Path

from tools.cor0203_settlement_ledger import Cor0203SettlementLedger
from tools.cor0203_settlement_sync import sync_settlements, sync_mixed_settlements


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


class FakeRapidClient:
    def __init__(self, payload):
        self.payload = payload
        self.request_count = 0
        self.ranges = []

    def results_for_date(self, target_date):
        self.request_count += 1
        return self.payload

    def results_for_range(self, start, stop):
        self.request_count += 1
        self.ranges.append((start, stop))
        return self.payload


def rapid_item(start="2026-09-27T10:00:00+00:00"):
    return {
        "status": "READY_RESULT_LOOKUP",
        "provider": "rapidapi_tennis",
        "event_id": "COR0203-RAPIDAPI-TENNIS-9001",
        "observation_index": 12,
        "observation_sha256": "b" * 64,
        "alphabetical_player_a": "Alpha",
        "alphabetical_player_b": "Beta",
        "event_start_utc": start,
        "provider_match_key": "9001",
        "provider_tournament_id": "22037",
        "provider_player_map": {
            "rapidapi-tennis:player:10": "Alpha",
            "rapidapi-tennis:player:20": "Beta",
        },
    }


def rapid_payload(result_type="completed"):
    return {
        "data": [
            {
                "id": 9001,
                "matchId": 9001,
                "result_type": result_type,
                "date": "2026-09-27T10:15:00Z",
                "tournamentId": 22037,
                "player1": {"id": 20, "name": "Beta"},
                "player2": {"id": 10, "name": "Alpha"},
                "result": "6-4 6-3",
            }
        ]
    }


def test_mixed_sync_can_settle_rapidapi_without_api_tennis_key(tmp_path):
    rapid = FakeRapidClient(rapid_payload())
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    result = sync_mixed_settlements(
        queue=queue(rapid_item()),
        ledger=ledger,
        api_tennis_client=None,
        rapidapi_client=rapid,
        now_utc="2026-09-27T12:00:00+00:00",
    )
    assert result["new_settlements"] == 1
    assert result["network_calls"] == 1
    assert result["outcomes_used_for_metrics"] == 0
    record = ledger.load()[0]
    assert record["result_source_provider"] == "rapidapi_tennis"
    assert record["winner_canonical_name"] == "Beta"


def test_mixed_sync_blocks_nonstandard_rapidapi_terminal(tmp_path):
    rapid = FakeRapidClient(rapid_payload("retired"))
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    result = sync_mixed_settlements(
        queue=queue(rapid_item()),
        ledger=ledger,
        api_tennis_client=None,
        rapidapi_client=rapid,
        now_utc="2026-09-27T12:00:00+00:00",
    )
    assert result["new_settlements"] == 0
    assert result["blocked"][0]["reason"].startswith(
        "NONSTANDARD_TERMINAL_REQUIRES_ADJUDICATION"
    )
    assert ledger.audit().records == 0


def test_mixed_sync_bulk_fetches_once_for_many_rapidapi_items(tmp_path):
    rows = rapid_payload()["data"]
    payload = {"data": rows}
    rapid = FakeRapidClient(payload)
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    first = rapid_item()
    second = dict(rapid_item())
    second["event_id"] = "COR0203-RAPIDAPI-TENNIS-9002"
    second["observation_index"] = 13
    second["observation_sha256"] = "c" * 64
    second["provider_match_key"] = "9002"
    second["provider_player_map"] = {
        "rapidapi-tennis:player:30": "Gamma",
        "rapidapi-tennis:player:40": "Delta",
    }
    payload["data"].append({
        "id": 9002,
        "matchId": 9002,
        "result_type": "completed",
        "date": "2026-09-27T11:15:00Z",
        "tournamentId": 22037,
        "player1": {"id": 30, "name": "Gamma"},
        "player2": {"id": 40, "name": "Delta"},
        "result": "6-2 6-2",
    })
    second["alphabetical_player_a"] = "Delta"
    second["alphabetical_player_b"] = "Gamma"
    result = sync_mixed_settlements(
        queue={"items": [first, second]},
        ledger=ledger,
        api_tennis_client=None,
        rapidapi_client=rapid,
        now_utc="2026-09-27T14:00:00+00:00",
    )
    assert result["new_settlements"] == 2
    assert result["network_calls"] == 1
    assert len(rapid.ranges) == 1


def test_mixed_sync_resolves_changed_archive_id_by_exact_pair_and_tournament(tmp_path):
    payload = rapid_payload()
    payload["data"][0]["id"] = 99001
    payload["data"][0]["matchId"] = 99001
    rapid = FakeRapidClient(payload)
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    result = sync_mixed_settlements(
        queue=queue(rapid_item()),
        ledger=ledger,
        api_tennis_client=None,
        rapidapi_client=rapid,
        now_utc="2026-09-27T12:00:00+00:00",
    )
    assert result["new_settlements"] == 1
    record = ledger.load()[0]
    assert record["provider_match_key"] == "9001"
    assert record["provider_result_match_key"] == "99001"
    assert record["settlement_resolution"] == "EXACT_TOURNAMENT_UNORDERED_PLAYER_PAIR_UNIQUE"


def test_mixed_sync_blocks_ambiguous_pair_fallback(tmp_path):
    payload = rapid_payload()
    payload["data"][0]["id"] = 99001
    payload["data"][0]["matchId"] = 99001
    duplicate = dict(payload["data"][0])
    duplicate["id"] = 99002
    duplicate["matchId"] = 99002
    payload["data"].append(duplicate)
    rapid = FakeRapidClient(payload)
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    result = sync_mixed_settlements(
        queue=queue(rapid_item()),
        ledger=ledger,
        api_tennis_client=None,
        rapidapi_client=rapid,
        now_utc="2026-09-27T12:00:00+00:00",
    )
    assert result["new_settlements"] == 0
    assert result["blocked"][0]["reason"] == "AMBIGUOUS_EXACT_PLAYER_PAIR"
    assert ledger.audit().records == 0
