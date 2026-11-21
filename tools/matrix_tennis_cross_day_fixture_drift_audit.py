"""Cross-day Challenger fixture clock drift audit; no market, holdout or model writes.

A single source event appearing with different UTC kickoffs across immutable
capture days is quarantined, not double-counted or silently rescheduled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path("evidence/tennis_calendar_reconciliation")
SCHEMA = "MATRIX_TENNIS_CROSS_DAY_FIXTURE_DRIFT_V1"

def stamp(s: str) -> datetime:
    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if dt.utcoffset() is None:
        raise ValueError("CROSS_DAY_KICKOFF_TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)

def verified_snapshot(root: Path, day: str) -> tuple[dict, dict]:
    report_path = root / BASE / day / "MATRIX_TENNIS_FREE_PROFILE_SOURCE_BINDING_AUDIT_LAST.json"
    report = json.loads(report_path.read_bytes())
    if (report.get("schema") != "MATRIX_TENNIS_FREE_PROFILE_SOURCE_BINDING_AUDIT_V1"
        or report.get("date_bogota") != day
        or report.get("real_money") != "BLOCKED"
        or report.get("new_hard_holdout_observations") != 0
        or report.get("new_clay_holdout_observations") != 0):
        raise ValueError("CROSS_DAY_UNTRUSTED_PROFILE_AUDIT")
    source = root / report["source_detail_path"]
    raw = source.read_bytes()
    if len(raw) > 7_000_000 or hashlib.sha256(raw).hexdigest() != (
        report.get("source_sha256") or {}).get("verified_match_details"):
        raise ValueError("CROSS_DAY_SOURCE_DETAIL_SHA_MISMATCH")
    doc = json.loads(raw)
    if (doc.get("schema") != "MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1"
        or doc.get("target_date_bogota") != day or doc.get("real_money") != "BLOCKED"
        or doc.get("provider_identity_equivalence_certified") is not False):
        raise ValueError("CROSS_DAY_UNTRUSTED_MATCH_DETAIL")
    return report, doc

def audit(root: Path, days: tuple[str, ...]) -> dict:
    if len(set(days)) != len(days) or len(days) < 2:
        raise ValueError("CROSS_DAY_REQUIRES_DISTINCT_DAYS")
    occurrences = {}
    all_profiles = set()
    all_day_instances = 0
    for day in days:
        date.fromisoformat(day)
        report, detail = verified_snapshot(root, day)
        profile_ids = {str(r["sofascore_player_id"]) for r in report["rows"]}
        all_profiles.update(profile_ids)
        events = {str(r["sofascore_event_id"]) for r in report["rows"]}
        original_events = detail.get("events") or []
        if len({str(e["sofascore_event_id"]) for e in original_events}) != len(original_events):
            raise ValueError("CROSS_DAY_DUPLICATE_IN_SOURCE_DAY")
        for e in original_events:
            event_id = str(e["sofascore_event_id"])
            if event_id not in events:
                continue
            names = tuple(sorted(str(p["name"]) for p in e.get("players") or []))
            if len(names) != 2:
                raise ValueError("CROSS_DAY_INCOMPLETE_PLAYER_PAIR")
            occurrence = {
                "source_day": day,
                "captured_kickoff_utc": stamp(e["kickoff_utc"]).isoformat(),
                "players": list(names),
                "surface": e["surface"],
                "detail_sha256": report["source_sha256"]["verified_match_details"],
            }
            occurrences.setdefault(event_id, []).append(occurrence)
            all_day_instances += 1
    conflicts = []
    unique_stable = 0
    for event_id, versions in sorted(occurrences.items()):
        start_times = {x["captured_kickoff_utc"] for x in versions}
        player_pairs = {tuple(x["players"]) for x in versions}
        surfaces = {x["surface"] for x in versions}
        if len(start_times) > 1 or len(player_pairs) > 1 or len(surfaces) > 1:
            conflicts.append({
                "sofascore_event_id": event_id,
                "reason": "MULTI_DAY_SOURCE_KICKOFF_OR_IDENTITY_DRIFT",
                "versions": versions,
                "model_holdout_admission_authorized": False,
            })
        else:
            unique_stable += 1
    return {
        "schema": SCHEMA,
        "source_days": list(days),
        "status": "CROSS_DAY_SOURCE_DRIFT_QUARANTINED_RESEARCH_ONLY" if conflicts
                  else "CROSS_DAY_NO_CONFLICT_DETECTED_RESEARCH_ONLY",
        "source_day_event_instances": all_day_instances,
        "unique_source_event_ids": len(occurrences),
        "unique_visible_player_ids_across_days": len(all_profiles),
        "conflicting_source_event_ids": len(conflicts),
        "unique_nonconflicting_event_ids_research_only": unique_stable,
        "original_model_pit_equivalence_certified": False,
        "new_hard_holdout_observations": 0,
        "new_clay_holdout_observations": 0,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "conflicts": conflicts,
    }

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--day", action="append", required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    args = p.parse_args()
    result = audit(args.root, tuple(args.day))
    outfile = args.root / BASE / args.day[-1] / "MATRIX_TENNIS_CROSS_DAY_FIXTURE_DRIFT_LAST.json"
    outfile.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+"\n",
                       encoding="utf-8")
    print(json.dumps({"source_day_instances": result["source_day_event_instances"],
                      "unique_events": result["unique_source_event_ids"],
                      "drift_quarantined": result["conflicting_source_event_ids"],
                      "holdout_admitted": 0}, sort_keys=True))

if __name__ == "__main__":
    main()
