import json
from pathlib import Path
import pytest

from tools.cor0203_settlement_ledger import (
    Cor0203SettlementLedger,
    build_settlement_queue,
    settlement_from_api_tennis,
    settlement_from_rapidapi_tennis,
)


def test_current_holdout_queue_does_not_invent_provider_keys():
    runtime = Path("evidence/cor0203/runtime")
    holdout = Path("evidence/cor0203/holdout")
    integrity = json.loads((runtime / "MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json").read_text())
    queue = build_settlement_queue(
        runtime_dir=runtime,
        holdout_dir=holdout,
        integrity=integrity,
        ledger_records=[],
    )
    assert queue["admissible_observations"] == integrity["admissible_observations"]
    assert queue["settled"] == 0
    assert (
        queue["settled"]
        + queue["ready_result_lookup"]
        + queue["identity_mapping_required"]
        == queue["admissible_observations"]
    )
    for row in queue["items"]:
        if row["status"] == "READY_RESULT_LOOKUP":
            assert row["provider"] in {"api_tennis", "rapidapi_tennis"}
            assert str(row["provider_match_key"]).isdigit()
            assert len(row["provider_player_map"]) == 2
            assert row["blocker"] is None
        elif row["status"] == "IDENTITY_MAPPING_REQUIRED":
            assert row["blocker"] in {
                "PROVIDER_MATCH_KEY_MISSING",
                "PROVIDER_PLAYER_MAPPING_INCOMPLETE",
            }
    assert queue["metrics"] == "SEALED_UNTIL_600"
    assert queue["outcomes_used_for_metrics"] == 0


def ready_item():
    return {
        "status": "READY_RESULT_LOOKUP",
        "event_id": "COR0203-API-TENNIS-123",
        "observation_index": 11,
        "observation_sha256": "a" * 64,
        "alphabetical_player_a": "Alpha",
        "alphabetical_player_b": "Beta",
        "event_start_utc": "2026-09-27T10:00:00+00:00",
        "provider_match_key": "123",
        "provider_player_map": {
            "api-tennis:player:10": "Alpha",
            "api-tennis:player:20": "Beta",
        },
    }


def final_fixture():
    return {
        "event_key": "123",
        "first_player_key": "20",
        "second_player_key": "10",
        "event_status": "Finished",
        "event_winner": "Second Player",
        "event_final_result": "0 - 2",
    }


def test_standard_finished_result_maps_to_alphabetical_player_a():
    record = settlement_from_api_tennis(
        queue_item=ready_item(),
        fixture=final_fixture(),
        settled_at_utc="2026-09-27T12:00:00+00:00",
        source_reference="get_fixtures:match_key=123",
    )
    assert record["winner_canonical_name"] == "Alpha"
    assert record["outcome_player_a"] is True
    assert record["metrics_opened"] is False
    assert record["used_for_metrics"] is False


@pytest.mark.parametrize("status", ["Set 2", "Retired", "Walkover", "Cancelled", ""])
def test_nonstandard_or_nonfinal_status_never_auto_settles(status):
    fixture = final_fixture()
    fixture["event_status"] = status
    with pytest.raises(ValueError, match="SETTLEMENT_NOT_STANDARD_FINAL"):
        settlement_from_api_tennis(
            queue_item=ready_item(),
            fixture=fixture,
            settled_at_utc="2026-09-27T12:00:00+00:00",
            source_reference="get_fixtures:match_key=123",
        )


def test_append_only_settlement_ledger_hash_chain_and_metrics_seal(tmp_path):
    ledger = Cor0203SettlementLedger(tmp_path / "settlement.jsonl")
    record = settlement_from_api_tennis(
        queue_item=ready_item(),
        fixture=final_fixture(),
        settled_at_utc="2026-09-27T12:00:00+00:00",
        source_reference="get_fixtures:match_key=123",
    )
    stored = ledger.append(record)
    assert stored["previous_record_sha256"] is None
    audit = ledger.audit()
    assert audit.records == 1
    assert audit.unique_events == 1
    assert audit.hash_chain_verified is True
    assert audit.outcomes_used_for_metrics == 0
    with pytest.raises(ValueError, match="DUPLICATE_SETTLEMENT_EVENT"):
        ledger.append(record)


def rapid_ready_item():
    return {
        "status": "READY_RESULT_LOOKUP",
        "provider": "rapidapi_tennis",
        "event_id": "COR0203-RAPIDAPI-TENNIS-9001",
        "observation_index": 12,
        "observation_sha256": "b" * 64,
        "alphabetical_player_a": "Alpha",
        "alphabetical_player_b": "Beta",
        "event_start_utc": "2026-09-27T10:00:00+00:00",
        "provider_match_key": "9001",
        "provider_player_map": {
            "rapidapi-tennis:player:10": "Alpha",
            "rapidapi-tennis:player:20": "Beta",
        },
    }


def rapid_final_result(result_type="completed"):
    return {
        "id": 9001,
        "matchId": 9001,
        "result_type": result_type,
        "player1": {"id": 20, "name": "Beta"},
        "player2": {"id": 10, "name": "Alpha"},
        "result": "6-4 6-3",
    }


def test_rapidapi_completed_result_maps_documented_winner_without_opening_metrics():
    record = settlement_from_rapidapi_tennis(
        queue_item=rapid_ready_item(),
        result_row=rapid_final_result(),
        settled_at_utc="2026-09-27T12:00:00+00:00",
        source_reference="results:2026-09-27:matchId=9001",
    )
    assert record["winner_canonical_name"] == "Beta"
    assert record["outcome_player_a"] is False
    assert record["result_source_provider"] == "rapidapi_tennis"
    assert record["metrics_opened"] is False
    assert record["used_for_metrics"] is False


@pytest.mark.parametrize(
    "result_type",
    ["retired", "walkover", "cancelled", "", "live"],
)
def test_rapidapi_nonstandard_result_never_auto_settles(result_type):
    with pytest.raises(ValueError, match="SETTLEMENT_NOT_STANDARD_FINAL"):
        settlement_from_rapidapi_tennis(
            queue_item=rapid_ready_item(),
            result_row=rapid_final_result(result_type=result_type),
            settled_at_utc="2026-09-27T12:00:00+00:00",
            source_reference="results:2026-09-27:matchId=9001",
        )
