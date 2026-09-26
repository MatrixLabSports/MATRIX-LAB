import json
from pathlib import Path

from tools.cor0203_settlement_ledger import build_settlement_queue


def test_identity_overlay_unlocks_result_lookup_without_mutating_manifest():
    runtime = Path("evidence/cor0203/runtime")
    holdout = Path("evidence/cor0203/holdout")
    integrity = json.loads((runtime / "MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json").read_text())
    target_event = "COR0203-R718-STT-MAYOT-CASSONE"
    overlay = {
        target_event: {
            "event_id": target_event,
            "provider_match_key": "12345",
            "canonical_source_event_id": "api-tennis:event:12345",
            "provider_player_map": {
                "api-tennis:player:1": "Harold Mayot",
                "api-tennis:player:2": "Murphy Cassone",
            },
        }
    }
    queue = build_settlement_queue(
        runtime_dir=runtime,
        holdout_dir=holdout,
        integrity=integrity,
        ledger_records=[],
        identity_overlay=overlay,
    )
    row = next(item for item in queue["items"] if item["event_id"] == target_event)
    assert row["status"] == "READY_RESULT_LOOKUP"
    assert row["provider_match_key"] == "12345"
    assert row["canonical_source_event_id"] == "api-tennis:event:12345"
    assert row["identity_overlay_applied"] is True

    original = json.loads(
        (runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R718.json").read_text()
    )
    source = next(x for x in original["events"] if x["event_id"] == target_event)
    assert source["canonical_source_event_id"] == "STT-2026-SF-MAYOT-CASSONE"


def test_no_overlay_preserves_historical_blocker():
    runtime = Path("evidence/cor0203/runtime")
    holdout = Path("evidence/cor0203/holdout")
    integrity = json.loads((runtime / "MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json").read_text())
    queue = build_settlement_queue(
        runtime_dir=runtime,
        holdout_dir=holdout,
        integrity=integrity,
        ledger_records=[],
    )
    assert queue["identity_mapping_required"] == 10
    assert queue["ready_result_lookup"] == 0
