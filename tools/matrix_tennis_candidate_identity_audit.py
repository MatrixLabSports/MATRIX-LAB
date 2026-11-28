"""Audit saved tennis cross-source review leads without certifying fixtures.

A token overlap is insufficient for identity, especially in doubles.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "evidence/calendar/MATRIX_TENNIS_CROSS_SOURCE_REVIEW_20261031.json"

def audit(raw: dict) -> dict:
    rows = raw["candidates"]
    if raw.get("cross_source_matches_certified") != 0 or raw.get("signals_authorized") != 0:
        raise ValueError("Input review evidence must not contain certified signals")
    out = []
    for row in rows:
        candidates = row.get("candidates", [])
        if not candidates:
            raise ValueError("Review entry without candidates")
        out.append({
            "sofascore_url": row["sofascore_url"],
            "sofascore_name": row["sofascore_name"],
            "flashscore_options": candidates,
            "review_status": "UNVERIFIED_PARTICIPANTS_AND_DATE",
            "requires_two_sides": True,
            "event_certified": False,
            "signal_authorized": False,
        })
    return {"target_date": raw["target_date"],
            "candidate_sofascore_events": len(out),
            "individually_verified": 0,
            "unverified": len(out),
            "signals_authorized": 0,
            "records": out}

def main() -> None:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    report = audit(data)
    print(json.dumps({k:v for k,v in report.items() if k != "records"}, indent=2))

if __name__ == "__main__":
    main()
