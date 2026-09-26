import json
from pathlib import Path
import pytest

from tools.cor0203_settlement_ledger import (
    Cor0203SettlementLedger,
    build_settlement_queue,
    settlement_from_api_tennis,
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
    assert queue["admissible_observations"] == 10
    assert queue["settled"] == 0
    assert queue["ready_result_lookup"] == 0
    assert queue["identity_mapping_required"] == 10
    assert all(row["blocker"] == "PROVIDER_MATCH_KEY_MISSING" for row in queue["items"])
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
