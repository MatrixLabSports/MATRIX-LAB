#!/usr/bin/env python3
"""Read-only governed cohort reconciliation; writes snapshot only when physical source SHA changes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evidence"
COHORT = BASE / "daily_selection/MATRIX_CALIBRATION_CANDIDATES_20261006_BOGOTA.json"
FOOTBALL = BASE / "api_football/calibration_v2/lanes/1x2/ledger.jsonl"
STATE = BASE / "api_football/calibration_v2/lanes/1x2/state.json"
TENNIS = BASE / "cor0203/settlement/MATRIX_COR0203_SETTLEMENT_LEDGER.jsonl"
UNIQUE = BASE / "cor0203/runtime/MATRIX_COR0203_SETTLEMENT_UNIQUENESS_LAST.json"
OUTPUT = BASE / "daily_selection/MATRIX_SETTLEMENT_PROGRESS_20261006_BOGOTA_AUTOMATED.json"

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def lines(p):
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]

def main():
    cohort = json.loads(COHORT.read_text())
    state = json.loads(STATE.read_text())
    unique = json.loads(UNIQUE.read_text())
    assert state["metrics_opened"] is False
    assert state["parameter_tuning_allowed"] is False
    assert state["real_money"] == "BLOCKED"
    assert unique["metrics_opened"] is False
    assert unique["real_money"] == "BLOCKED"
    assert unique["result"] == "PASS"
    assert unique["metrics"] == "SEALED_UNTIL_600"
    fids = [str(x["fixture_id"]) for x in cohort["football"]["matches"]]
    tids = [x["event_id"] for x in cohort["tennis"]["matches"]]
    assert len(fids) == len(set(fids)) == 116
    assert len(tids) == len(set(tids)) == 11
    flines, tlines = lines(FOOTBALL), lines(TENNIS)
    assert len(flines) == state["settlement_count"]
    assert len(tlines) == unique["ledger_records"]
    fset = {str(x["fixture_id"]) for x in flines if x.get("outcome") in ("H", "D", "A")}
    tset = {x["event_id"] for x in tlines if x.get("terminal_status") == "FINISHED"}
    fs = sorted(set(fids) & fset)
    ts = sorted(set(tids) & tset)
    snapshot = {
        "schema": "MATRIX_COHORT_SETTLEMENT_AUTOMATED_SNAPSHOT_V1",
        "cohort": "2026-10-06_BOGOTA",
        "sources_sha256": {str(p.relative_to(ROOT)): digest(p) for p in (COHORT, FOOTBALL, STATE, TENNIS, UNIQUE)},
        "football_cohort": {"total": 116, "settled_standard_in_ledger": len(fs), "pending": sorted(set(fids)-fset)},
        "tennis_cohort": {"total": 11, "settled_finished_in_ledger": len(ts), "pending": sorted(set(tids)-tset)},
        "football_v2": {"freezes": state["freeze_observation_count"], "settlements": state["settlement_count"], "pending": state["pending_settlement_count"]},
        "tennis_global": {"ledger_records": unique["ledger_records"], "unique_settled": unique["settled_unique_canonical_events"], "unique_pending": unique["unsettled_unique_canonical_events"], "duplicates_quarantined": unique["duplicate_observations_quarantined"]},
        "governance": {"metrics_opened": False, "tuning": False, "odds_to_p": False, "real_money": "BLOCKED"},
        "scope": "Ledger membership only; no provider result inferred; nonstandard statuses require separate evidence."
    }
    assert snapshot["football_v2"]["freezes"] == snapshot["football_v2"]["settlements"] + snapshot["football_v2"]["pending"]
    data = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if OUTPUT.exists() and OUTPUT.read_text() == data:
        print("NO_CHANGE: identical source evidence and counters")
    else:
        OUTPUT.write_text(data)
        print("SNAPSHOT_UPDATED:", OUTPUT, "football", len(fs), "/116 tennis", len(ts), "/11")

if __name__ == "__main__":
    main()
