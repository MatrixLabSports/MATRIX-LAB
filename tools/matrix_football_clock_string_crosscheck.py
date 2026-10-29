"""Read-only comparison of Opera Flashscore and SofaScore displayed clock strings.

Does not certify timezone, event kickoff or eligibility for wagering.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def normalize_clock(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}:\d{2}", value):
        return None
    hour, minute = map(int, value.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def compare(recon: dict, capture: dict) -> dict:
    if recon.get("target_date_bogota") != capture.get("target_date_bogota"):
        raise ValueError("TARGET_DATE_MISMATCH")
    if recon.get("status") != "PASS_OPEN_RECONCILIATION":
        raise ValueError("RECONCILIATION_NOT_PASS")
    times = {}
    conflicts = set()
    for row in capture.get("rows", []):
        name = row.get("link", {}).get("name")
        if not name:
            continue
        clock = normalize_clock(row.get("time"))
        if name in times and times[name] != clock:
            conflicts.add(name)
        times[name] = clock
    for name in conflicts:
        times.pop(name, None)
    records = []
    for event in recon.get("confirmed_both", []):
        name = event["flashscore"]
        sofa = event["sofascore"]
        match = re.match(r"^\d{1,2}/\d{1,2}/\d{2}\s+(\d{1,2}:\d{2})\s+", sofa)
        st = normalize_clock(match.group(1)) if match else None
        ft = times.get(name)
        status = ("CLOCK_STRING_MATCH" if st == ft else "CLOCK_STRING_MISMATCH") if st and ft else "NOT_COMPARABLE"
        records.append({"flashscore": name, "sofascore": sofa, "sofascore_normalized_clock": st,
                        "flashscore_normalized_clock": ft, "display_clock_comparison": status,
                        "timezone_certified": False})
    counts = Counter(row["display_clock_comparison"] for row in records)
    return {"schema": "MATRIX_FOOTBALL_CLOCK_STRING_CROSSCHECK_V2",
            "target_date_bogota": recon["target_date_bogota"],
            "identity_confirmed": len(records), "clock_comparison_counts": dict(counts),
            "rows": records,
            "policy": {"clock_string_match_is_not_timezone_certification": True,
                       "no_freeze_from_uncertified_clock": True,
                       "automatic_wagering": False, "real_money": "BLOCKED"}}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--reconciliation", default="evidence/calendar_reconciliation/MATRIX_FOOTBALL_WORLD_CALENDAR_RECONCILIATION_LAST.json")
    p.add_argument("--temporal-rows", default="evidence/calendar_physical/2026-10-29/football_flashscore_opera_calendar_rows_with_time.json")
    p.add_argument("--out", default="evidence/calendar_reconciliation/MATRIX_FOOTBALL_OCT29_CLOCK_STRING_CROSSCHECK_V2.json")
    a = p.parse_args()
    recon = json.loads(Path(a.reconciliation).read_text(encoding="utf-8"))
    rows = json.loads(Path(a.temporal_rows).read_text(encoding="utf-8"))
    result = compare(recon, rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"identity_confirmed": result["identity_confirmed"],
                      "clock_comparison_counts": result["clock_comparison_counts"],
                      "timezone_certified": False}, sort_keys=True))


if __name__ == "__main__":
    main()
