from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

FOOTBALL_EVIDENCE = Path("evidence/api_football/period_goals_lab/MATRIX_PERIOD_GOALS_LAB_LAST.json")
TENNIS_EVIDENCE = Path("evidence/tennis_serve_stats_lab/MATRIX_TENNIS_SERVE_STATS_LAB_LAST.json")
DEFAULT_STATE = Path("evidence/lab_gates/MATRIX_NINE_LAB_GATE_REGISTRY_LAST.json")
DEFAULT_LEDGER = Path("evidence/lab_gates/MATRIX_NINE_LAB_OBSERVATION_LEDGER.jsonl")
GATES = (100, 300, 600)

FOOTBALL_LANES = (
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
    "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
)
TENNIS_LANES = ("ACES", "DOUBLE_FAULTS", "BREAKS_OF_SERVE")
ALL_LANES = FOOTBALL_LANES + TENNIS_LANES


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append_unique(path: Path, rows: list[dict[str, Any]]) -> tuple[int, int]:
    existing = _read_ledger(path)
    keys = {str(x.get("observation_key") or "") for x in existing}
    new_rows = [x for x in rows if str(x.get("observation_key") or "") not in keys]
    path.parent.mkdir(parents=True, exist_ok=True)
    if new_rows:
        with path.open("a", encoding="utf-8") as f:
            for row in new_rows:
                f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return len(existing), len(new_rows)



def _aware_iso(value: object, field: str) -> datetime:
    token = str(value or "").strip()
    if not token:
        raise ValueError(f"{field}_MISSING")
    parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field}_NOT_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _validate_prospective_row(row: Mapping[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if row.get("record_type") != "PROSPECTIVE_PREMATCH_FREEZE":
        errors.append("RECORD_TYPE_INVALID")
    if str(row.get("market_lane") or "") not in ALL_LANES:
        errors.append("UNKNOWN_MARKET_LANE")
    if not str(row.get("event_id") or row.get("fixture_id") or "").strip():
        errors.append("EVENT_ID_MISSING")
    if not str(row.get("observation_key") or "").strip():
        errors.append("OBSERVATION_KEY_MISSING")
    try:
        freeze = _aware_iso(row.get("freeze_timestamp_utc"), "FREEZE_TIMESTAMP")
        start = _aware_iso(row.get("event_start_utc"), "EVENT_START")
        if freeze >= start:
            errors.append("FREEZE_NOT_BEFORE_EVENT_START")
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    if not row.get("prediction_snapshot_sha256") and not row.get("feature_snapshot_sha256"):
        errors.append("PREDICTION_OR_FEATURE_SNAPSHOT_MISSING")
    if row.get("target_outcome") is not None or row.get("settlement") is not None:
        errors.append("OUTCOME_PRESENT_AT_FREEZE")
    if row.get("odds_used_to_generate_probability") is not False:
        errors.append("ODDS_TO_P_MATRIX_NOT_EXPLICITLY_FALSE")
    if row.get("missing_not_zero") is not True:
        errors.append("MISSING_NOT_ZERO_NOT_ASSERTED")
    if row.get("silent_imputation") is not False:
        errors.append("SILENT_IMPUTATION_NOT_FALSE")
    if row.get("automatic_wagering") is not False:
        errors.append("AUTOMATIC_WAGERING_NOT_FALSE")
    if row.get("real_money") != "BLOCKED":
        errors.append("REAL_MONEY_NOT_BLOCKED")
    return (not errors), errors


def _gate_state(count: int) -> dict[str, Any]:
    return {
        str(g): {
            "threshold": g,
            "count": min(count, g),
            "remaining": max(0, g - count),
            "status": "OPEN" if count >= g else "SEALED",
        }
        for g in GATES
    }


def _baseline_rows(football: Mapping[str, Any], tennis: Mapping[str, Any], now: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    football_sha = str(football.get("payload_sha256") or "")
    historical = int(football.get("eligible_walk_forward_rows") or 0)
    for lane in FOOTBALL_LANES:
        key = f"BASELINE|football|{lane}|{football_sha}"
        rows.append({
            "observation_key": key,
            "record_type": "BASELINE_AUDIT",
            "sport": "football",
            "market_lane": lane,
            "captured_at_utc": now,
            "source_evidence_sha256": football_sha,
            "historical_walk_forward_rows": historical,
            "prospective_admitted": False,
            "prospective_blocker": "HISTORICAL_WALK_FORWARD_NOT_PROSPECTIVE",
            "counts_toward_100_300_600": False,
        })

    tennis_sha = str(tennis.get("payload_sha256") or "")
    captures = tennis.get("captures") or []
    for capture in captures:
        if not isinstance(capture, Mapping):
            continue
        event_id = str(capture.get("event_id") or "")
        for lane in TENNIS_LANES:
            key = f"SOURCE|tennis|{lane}|{event_id}|{tennis_sha}"
            rows.append({
                "observation_key": key,
                "record_type": "SOURCE_COVERAGE",
                "sport": "tennis",
                "market_lane": lane,
                "event_id": event_id,
                "captured_at_utc": now,
                "source_evidence_sha256": tennis_sha,
                "provider_status": capture.get("status"),
                "prospective_admitted": False,
                "prospective_blocker": "INPLAY_SOURCE_COVERAGE_NOT_PREMATCH_FREEZE",
                "counts_toward_100_300_600": False,
            })
    return rows


def build_registry(
    *,
    football_path: Path = FOOTBALL_EVIDENCE,
    tennis_path: Path = TENNIS_EVIDENCE,
    ledger_path: Path = DEFAULT_LEDGER,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    football = _load(football_path)
    tennis = _load(tennis_path)
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0).isoformat()

    if football.get("status") != "PASS_LAB":
        raise ValueError("FOOTBALL_PERIOD_LAB_NOT_PASS")
    if tennis.get("status") != "PASS_SOURCE_LAB":
        raise ValueError("TENNIS_SERVE_STATS_LAB_NOT_PASS")

    before, appended = _append_unique(ledger_path, _baseline_rows(football, tennis, now))
    ledger = _read_ledger(ledger_path)

    prospective_counts = {lane: 0 for lane in ALL_LANES}
    source_coverage_counts = {lane: 0 for lane in ALL_LANES}
    for row in ledger:
        lane = str(row.get("market_lane") or "")
        if lane not in prospective_counts:
            continue
        if row.get("record_type") == "SOURCE_COVERAGE":
            source_coverage_counts[lane] += 1
        if row.get("prospective_admitted") is True and row.get("counts_toward_100_300_600") is True:
            valid, _ = _validate_prospective_row(row)
            if valid:
                prospective_counts[lane] += 1

    lanes = {}
    for lane in ALL_LANES:
        lanes[lane] = {
            "sport": "football" if lane in FOOTBALL_LANES else "tennis",
            "prospective_unique_count": prospective_counts[lane],
            "source_coverage_count": source_coverage_counts[lane],
            "gates": _gate_state(prospective_counts[lane]),
            "metrics_status": "SEALED_UNTIL_GATE",
            "production_authorized": False,
        }

    result = {
        "schema": "MATRIX_NINE_LAB_GATE_REGISTRY_V1",
        "generated_at_utc": now,
        "gate_thresholds": list(GATES),
        "lane_count": len(ALL_LANES),
        "lanes": lanes,
        "ledger_path": ledger_path.as_posix(),
        "ledger_rows_before_run": before,
        "ledger_rows_appended_this_run": appended,
        "ledger_rows_total": len(ledger),
        "baseline": {
            "football_historical_walk_forward_rows": int(football.get("eligible_walk_forward_rows") or 0),
            "football_baseline_counts_as_prospective": False,
            "tennis_live_source_events": int(tennis.get("events_probed") or 0),
            "tennis_inplay_counts_as_prospective": False,
        },
        "admission_contract": {
            "required_record_type": "PROSPECTIVE_PREMATCH_FREEZE",
            "event_identity_required": True,
            "freeze_timestamp_required": True,
            "freeze_strictly_before_event_start": True,
            "prediction_or_feature_snapshot_required": True,
            "duplicate_observation_key_forbidden": True,
            "post_start_backfill_forbidden": True,
            "missing_not_zero": True,
            "silent_imputation": False,
        },
        "protections": {
            "metrics_open_only_at_declared_gate": True,
            "odds_used_to_generate_probability": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "status": "PASS",
    }
    result["registry_sha256"] = _sha(result)
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--football-evidence", default=str(FOOTBALL_EVIDENCE))
    p.add_argument("--tennis-evidence", default=str(TENNIS_EVIDENCE))
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    p.add_argument("--out", default=str(DEFAULT_STATE))
    args = p.parse_args()
    result = build_registry(
        football_path=Path(args.football_evidence),
        tennis_path=Path(args.tennis_evidence),
        ledger_path=Path(args.ledger),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "lane_count": result["lane_count"],
        "ledger_rows_total": result["ledger_rows_total"],
        "ledger_rows_appended_this_run": result["ledger_rows_appended_this_run"],
        "prospective_counts": {k:v["prospective_unique_count"] for k,v in result["lanes"].items()},
        "real_money": result["protections"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
