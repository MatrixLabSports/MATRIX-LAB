from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INPUT = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json")
OUTPUT = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_FINAL_WINDOW_READINESS_LAST.json")
WINDOW_MINUTES = 120
SUPERVISOR_INTERVAL_MINUTES = 15

PROGRAMMATIC_LIVE_QUOTE_SOURCES = ["API-Football", "odds-api.net"]
PHYSICAL_EVIDENCE_RECOVERY_SOURCES = [
    "Betano", "BetPlay", "Betsson", "Bwin", "Codere", "Luckia", "MrYoker",
    "Rivalo", "Rushbet", "Sportium", "Stake", "Wplay", "YaJuego", "Zamba",
]


def parse_dt(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_DATETIME")
    return dt.astimezone(timezone.utc)


def next_quarter_hour(at: datetime) -> datetime:
    at = at.astimezone(timezone.utc).replace(second=0, microsecond=0)
    remainder = at.minute % SUPERVISOR_INTERVAL_MINUTES
    if remainder == 0:
        return at
    return at + timedelta(minutes=SUPERVISOR_INTERVAL_MINUTES - remainder)


def build(payload: dict[str, Any], generated_at: datetime | None = None) -> dict[str, Any]:
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rows = payload.get("records") or []
    waiting = [r for r in rows if isinstance(r, dict) and r.get("gate_state") == "WAITING_FINAL_REVALIDATION_WINDOW"]
    checks = []
    failures = []
    for row in waiting:
        kickoff = parse_dt(row.get("kickoff"))
        window_open = kickoff - timedelta(minutes=WINDOW_MINUTES)
        next_cycle = next_quarter_hour(window_open)
        delay = int((next_cycle - window_open).total_seconds())
        declared = list(row.get("sources_available_for_recovery") or [])
        live_programmatic = [x for x in PROGRAMMATIC_LIVE_QUOTE_SOURCES if x in declared]
        physical_declared = [x for x in PHYSICAL_EVIDENCE_RECOVERY_SOURCES if x in declared]
        covered = delay <= SUPERVISOR_INTERVAL_MINUTES * 60 and next_cycle < kickoff
        source_contract = set(PROGRAMMATIC_LIVE_QUOTE_SOURCES).issubset(set(declared))
        item = {
            "fixture_id": str(row.get("fixture_id") or ""),
            "match": row.get("match"),
            "kickoff_utc": kickoff.isoformat(),
            "window_opens_utc": window_open.isoformat(),
            "next_supervisor_cycle_utc": next_cycle.isoformat(),
            "seconds_after_window_open": delay,
            "window_covered_by_15m_supervisor": covered,
            "programmatic_live_quote_sources": live_programmatic,
            "physical_evidence_recovery_sources_declared": physical_declared,
            "source_contract_pass": source_contract,
            "real_money": "BLOCKED",
        }
        checks.append(item)
        if not covered:
            failures.append({"fixture_id": item["fixture_id"], "code": "FINAL_WINDOW_NOT_COVERED_BY_15M_CADENCE"})
        if not source_contract:
            failures.append({"fixture_id": item["fixture_id"], "code": "PROGRAMMATIC_QUOTE_SOURCE_CONTRACT_MISSING"})

    earliest = min((parse_dt(x["window_opens_utc"]) for x in checks), default=None)
    return {
        "schema": "MATRIX_TELEGRAM_FINAL_WINDOW_READINESS_V1",
        "generated_at_utc": generated_at.isoformat(),
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "contracts": {
            "final_prematch_window_minutes": WINDOW_MINUTES,
            "supervisor_interval_minutes": SUPERVISOR_INTERVAL_MINUTES,
            "no_backfill_after_kickoff": True,
            "odds_must_be_gt_1_50": True,
            "ev_must_be_positive": True,
            "p_matrix_must_preexist_before_odds": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "source_scope": {
            "programmatic_live_quote_sources": PROGRAMMATIC_LIVE_QUOTE_SOURCES,
            "physical_evidence_recovery_sources": PHYSICAL_EVIDENCE_RECOVERY_SOURCES,
            "physical_sources_are_not_claimed_as_live_api_queries": True,
        },
        "summary": {
            "waiting_candidates": len(waiting),
            "covered_by_15m_supervisor": sum(1 for x in checks if x["window_covered_by_15m_supervisor"]),
            "source_contract_passed": sum(1 for x in checks if x["source_contract_pass"]),
            "failures": len(failures),
            "earliest_window_open_utc": earliest.isoformat() if earliest else None,
        },
        "failures": failures,
        "candidates": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = build(payload)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], **report["summary"]}, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
