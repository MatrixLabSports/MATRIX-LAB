from pathlib import Path

from tools.cor0203_apply_adjudications import apply_adjudications
from tools.cor0203_settlement_ledger import Cor0203SettlementLedger


def test_walkover_closes_without_metric_outcome(tmp_path: Path) -> None:
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    event_id = "COR0203-TEST-WALKOVER"
    queue = {
        "items": [{
            "event_id": event_id,
            "observation_index": 1,
            "observation_sha256": "a" * 64,
            "event_start_utc": "2026-10-03T11:30:00+00:00",
            "provider_match_key": "1346",
        }]
    }
    adjudications = {
        "created_at_utc": "2026-10-12T18:05:00+00:00",
        "entries": [{
            "event_id": event_id,
            "action": "APPEND_SETTLEMENT",
            "terminal_status": "WALKOVER",
            "event_final_result": "WALKOVER",
            "winner_canonical_name": "Henrique Rocha",
            "outcome_player_a": None,
            "metric_eligibility_at_open": "EXCLUDED_WALKOVER_NO_SPORTING_OUTCOME",
            "sources": ["source-a", "source-b"],
        }],
    }

    result = apply_adjudications(adjudications=adjudications, queue=queue, ledger=ledger)

    assert result["status"] == "PASS"
    assert result["appended_count"] == 1
    row = ledger.load()[0]
    assert row["terminal_status"] == "WALKOVER"
    assert row["outcome_player_a"] is None
    assert row["used_for_metrics"] is False
    assert row["metrics_opened"] is False
    assert row["real_money"] == "BLOCKED"


def test_walkover_rejects_binary_outcome(tmp_path: Path) -> None:
    ledger = Cor0203SettlementLedger(tmp_path / "ledger.jsonl")
    event_id = "COR0203-TEST-WALKOVER-BAD"
    queue = {
        "items": [{
            "event_id": event_id,
            "observation_index": 1,
            "observation_sha256": "b" * 64,
            "event_start_utc": "2026-10-03T11:30:00+00:00",
            "provider_match_key": "1346",
        }]
    }
    adjudications = {
        "created_at_utc": "2026-10-12T18:05:00+00:00",
        "entries": [{
            "event_id": event_id,
            "action": "APPEND_SETTLEMENT",
            "terminal_status": "WALKOVER",
            "event_final_result": "WALKOVER",
            "winner_canonical_name": "Henrique Rocha",
            "outcome_player_a": True,
            "sources": ["source-a", "source-b"],
        }],
    }

    result = apply_adjudications(adjudications=adjudications, queue=queue, ledger=ledger)

    assert result["status"] == "PASS_WITH_BLOCKERS"
    assert result["appended_count"] == 0
    assert result["blocked"][0]["reason"] == "WALKOVER_OUTCOME_MUST_BE_NULL"
