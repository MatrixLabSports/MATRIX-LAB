import json
from pathlib import Path


ROOT = Path("evidence/api_football/match_total_shots_lab/2026-10-10")


def _jsonl(path: Path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_match_total_shots_gate30_freeze_cohort_is_unique_and_fail_closed():
    state = json.loads((ROOT / "state.json").read_text(encoding="utf-8"))
    rows = _jsonl(ROOT / "freeze_ledger.jsonl")
    fixture_ids = [str(x["fixture_id"]) for x in rows]

    assert state["cumulative_unique_research_freeze_count"] == 30
    assert state["gate_30"]["freeze_count"] == 30
    assert state["gate_30"]["remaining_freezes_to_target"] == 0
    assert state["gate_30"]["status"] == "FREEZE_TARGET_REACHED_AWAIT_FINALS"
    assert state["gate_30"]["final_settlement_count"] == 0
    assert state["gate_30"]["metrics_opened"] is False

    assert len(rows) == 30
    assert len(set(fixture_ids)) == 30
    assert all(x["market"] == "MATCH_TOTAL_SHOTS" for x in rows)
    assert all(x["p_matrix"] is None for x in rows)
    assert all(x.get("p_research_over") is not None for x in rows)
    assert all(x["odds_used_to_generate_probability"] is False for x in rows)
    assert all(x["telegram_signal_authorized"] is False for x in rows)
    assert all(x["paper_bankroll_authorized"] is False for x in rows)
    assert all(x["automatic_wagering"] is False for x in rows)
    assert all(x["real_money"] == "BLOCKED" for x in rows)
