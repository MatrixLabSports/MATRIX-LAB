from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from app.market.matrix_market_portfolio import ALL_MARKETS

GATES = (100, 300, 600)
DEFAULT_SUPERVISOR = Path("evidence/market_portfolio/MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json")
DEFAULT_INBOX = Path("evidence/market_portfolio/MATRIX_42_LANE_FREEZE_INBOX.jsonl")
DEFAULT_LEDGER = Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl")
DEFAULT_STATE = Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json")
FOOTBALL_FIXTURES = Path("evidence/api_football/fixtures/future_fixture_registry.json")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"EXPECTED_OBJECT_JSONL:{path}:{n}")
        rows.append(value)
    return rows


def _aware(value: object, field: str) -> datetime:
    token = str(value or "").strip()
    if not token:
        raise ValueError(f"{field}_MISSING")
    dt = datetime.fromisoformat(token.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field}_NOT_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)


def validate_freeze(row: Mapping[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    lane = str(row.get("market_lane") or "")
    allowed = {m.key for m in ALL_MARKETS}
    if row.get("record_type") != "PROSPECTIVE_PREMATCH_FREEZE":
        errors.append("RECORD_TYPE_INVALID")
    if lane not in allowed:
        errors.append("UNKNOWN_MARKET_LANE")
    event_id = str(row.get("event_id") or row.get("fixture_id") or "").strip()
    if not event_id:
        errors.append("EVENT_ID_MISSING")
    key = str(row.get("observation_key") or "").strip()
    if not key:
        errors.append("OBSERVATION_KEY_MISSING")

    try:
        freeze = _aware(row.get("freeze_timestamp_utc"), "FREEZE_TIMESTAMP")
        start = _aware(row.get("event_start_utc"), "EVENT_START")
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
    if row.get("prospective_admitted") is not True:
        errors.append("PROSPECTIVE_ADMITTED_NOT_TRUE")
    if row.get("counts_toward_100_300_600") is not True:
        errors.append("COUNTS_TOWARD_GATES_NOT_TRUE")
    return (not errors), errors


def _append_valid_unique(inbox: Path, ledger: Path) -> dict[str, Any]:
    incoming = _read_jsonl(inbox)
    existing = _read_jsonl(ledger)
    existing_keys = {str(x.get("observation_key") or "") for x in existing}
    seen_batch: set[str] = set()
    admitted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in incoming:
        ok, errors = validate_freeze(row)
        key = str(row.get("observation_key") or "")
        if key in existing_keys or key in seen_batch:
            ok = False
            errors = list(errors) + ["DUPLICATE_OBSERVATION_KEY"]
        if ok:
            admitted.append(dict(row))
            seen_batch.add(key)
        else:
            rejected.append({
                "observation_key": key or None,
                "market_lane": row.get("market_lane"),
                "errors": sorted(set(errors)),
            })

    ledger.parent.mkdir(parents=True, exist_ok=True)
    if admitted:
        with ledger.open("a", encoding="utf-8") as handle:
            for row in admitted:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return {
        "incoming_rows": len(incoming),
        "existing_rows_before": len(existing),
        "admitted_this_run": len(admitted),
        "rejected_this_run": len(rejected),
        "rejections": rejected[:100],
    }


def _gate(count: int) -> dict[str, Any]:
    return {
        str(g): {
            "threshold": g,
            "count": min(count, g),
            "remaining": max(0, g - count),
            "status": "OPEN" if count >= g else "SEALED",
        }
        for g in GATES
    }


def _football_inventory(now_utc: datetime) -> dict[str, Any]:
    if not FOOTBALL_FIXTURES.exists():
        return {"available": False, "event_count": 0, "future_event_count_now": 0, "captured_at_utc": None}
    data = _load_json(FOOTBALL_FIXTURES)
    events = [x for x in (data.get("events") or []) if isinstance(x, Mapping)]
    future_now = 0
    latest_start = None
    for row in events:
        try:
            start = _aware(row.get("event_start_utc"), "EVENT_START")
        except (TypeError, ValueError):
            continue
        if latest_start is None or start > latest_start:
            latest_start = start
        if start > now_utc:
            future_now += 1
    captured = data.get("captured_at_utc")
    captured_age_hours = None
    try:
        captured_dt = _aware(captured, "CAPTURED_AT")
        captured_age_hours = round((now_utc - captured_dt).total_seconds() / 3600.0, 3)
    except (TypeError, ValueError):
        pass
    return {
        "available": True,
        "event_count": len(events),
        "future_event_count_now": future_now,
        "captured_at_utc": captured,
        "captured_age_hours": captured_age_hours,
        "latest_event_start_utc": latest_start.isoformat() if latest_start else None,
        "source_usable_for_new_freeze_now": future_now > 0,
        "blocker": None if future_now > 0 else "NO_FUTURE_EVENTS_IN_PERSISTED_FOOTBALL_INVENTORY",
    }


def _tennis_day_audit(day: str) -> dict[str, Any]:
    path = Path("evidence/tennis_world_inventory") / day / "world_exact_day_dual_audit.json"
    if not path.exists():
        return {"available": False, "day": day, "open_reconciliation_required": True}
    data = _load_json(path)
    primary = data.get("primary_world_inventory") or {}
    return {
        "available": True,
        "day": day,
        "status": data.get("status"),
        "primary_paid_unique_match_count": data.get("primary_worldwide_registered_match_count"),
        "provider_inventory_complete": primary.get("provider_inventory_complete"),
        "world_inventory_complete": data.get("world_inventory_complete"),
        "open_reconciliation_required": data.get("open_reconciliation_required"),
        "authoritative_count_policy": data.get("authoritative_count_policy"),
        "required_open_calendar_reconciliation": (data.get("source_architecture") or {}).get("required_open_calendar_reconciliation"),
    }


def _tennis_inventory(now_utc: datetime) -> dict[str, Any]:
    root = Path("evidence/tennis_world_inventory")
    bogota = ZoneInfo("America/Bogota")
    local_day = now_utc.astimezone(bogota).date()
    today = local_day.isoformat()
    tomorrow = (local_day + timedelta(days=1)).isoformat()
    if not root.exists():
        return {"available": False, "today": _tennis_day_audit(today), "tomorrow": _tennis_day_audit(tomorrow)}
    days = sorted([p.name for p in root.iterdir() if p.is_dir()])
    return {
        "available": bool(days),
        "latest_day": days[-1] if days else None,
        "today": _tennis_day_audit(today),
        "tomorrow": _tennis_day_audit(tomorrow),
    }


def build(
    *,
    supervisor_path: Path = DEFAULT_SUPERVISOR,
    inbox_path: Path = DEFAULT_INBOX,
    ledger_path: Path = DEFAULT_LEDGER,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    supervisor = _load_json(supervisor_path)
    if supervisor.get("status") != "PASS" or supervisor.get("total_required_lanes") != 42:
        raise ValueError("CANONICAL_42_LANE_SUPERVISOR_NOT_PASS")

    append = _append_valid_unique(inbox_path, ledger_path)
    ledger = _read_jsonl(ledger_path)
    lane_map = {m.key: m for m in ALL_MARKETS}
    counts = {k: 0 for k in lane_map}
    for row in ledger:
        ok, _ = validate_freeze(row)
        lane = str(row.get("market_lane") or "")
        if ok and lane in counts:
            counts[lane] += 1

    supervisor_rows = {str(x.get("market_key")): x for x in supervisor.get("rows") or [] if isinstance(x, dict)}
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0).isoformat()
    lanes: dict[str, Any] = {}
    for key, market in lane_map.items():
        sup = supervisor_rows.get(key, {})
        blockers: list[str] = []
        if not sup:
            blockers.append("LANE_MISSING_FROM_SUPERVISOR")
        if not sup.get("implementation_present"):
            blockers.append("IMPLEMENTATION_NOT_PRESENT")
        if counts[key] == 0:
            blockers.append("AWAITING_VALID_PROSPECTIVE_PREMATCH_FREEZE")
        lanes[key] = {
            "sport": market.sport,
            "display_name": market.display_name,
            "operational_state": sup.get("operational_state"),
            "implementation_present": bool(sup.get("implementation_present")),
            "must_continue_collecting": bool(sup.get("must_continue_collecting")),
            "prospective_unique_count": counts[key],
            "gates": _gate(counts[key]),
            "blockers": blockers,
            "production_authorized_by_registry": False,
        }

    result = {
        "schema": "MATRIX_42_LANE_PROSPECTIVE_REGISTRY_V1",
        "generated_at_utc": now,
        "status": "PASS",
        "total_lanes": 42,
        "football_lanes": 30,
        "tennis_lanes": 12,
        "gate_thresholds": list(GATES),
        "lanes": lanes,
        "counts": {
            "lanes_with_any_valid_prospective": sum(1 for v in counts.values() if v > 0),
            "lanes_at_100": sum(1 for v in counts.values() if v >= 100),
            "lanes_at_300": sum(1 for v in counts.values() if v >= 300),
            "lanes_at_600": sum(1 for v in counts.values() if v >= 600),
            "ledger_rows_total": len(ledger),
        },
        "source_inventory": {
            "football": _football_inventory(datetime.fromisoformat(now)),
            "tennis": _tennis_inventory(datetime.fromisoformat(now)),
        },
        "append_result": append,
        "admission_contract": {
            "record_type": "PROSPECTIVE_PREMATCH_FREEZE",
            "freeze_strictly_before_event_start": True,
            "event_identity_required": True,
            "prediction_or_feature_snapshot_required": True,
            "target_outcome_forbidden_at_freeze": True,
            "duplicate_observation_key_forbidden": True,
            "post_start_backfill_forbidden": True,
            "missing_not_zero": True,
            "silent_imputation": False,
        },
        "protections": {
            "odds_used_to_generate_probability": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
            "production_authorized": False,
        },
    }
    result["registry_sha256"] = _sha(result)
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--supervisor", default=str(DEFAULT_SUPERVISOR))
    p.add_argument("--inbox", default=str(DEFAULT_INBOX))
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    p.add_argument("--out", default=str(DEFAULT_STATE))
    args = p.parse_args()
    result = build(
        supervisor_path=Path(args.supervisor),
        inbox_path=Path(args.inbox),
        ledger_path=Path(args.ledger),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "total_lanes": result["total_lanes"],
        "counts": result["counts"],
        "admitted_this_run": result["append_result"]["admitted_this_run"],
        "rejected_this_run": result["append_result"]["rejected_this_run"],
        "real_money": result["protections"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
