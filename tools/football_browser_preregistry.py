from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

DEFAULT_WATCHLIST = Path("evidence/calendar_reconciliation/MATRIX_FOOTBALL_WORLD_WATCHLIST_LAST.json")


def _parse_dt(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _event_key(row: Mapping[str, Any]) -> str:
    basis = "|".join([
        str(row.get("sofascore_observation") or ""),
        str(row.get("flashscore_observation") or ""),
        str(row.get("event_identity") or ""),
        str(row.get("status") or ""),
    ])
    return "browser:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def build_browser_preregistry(watchlist: Mapping[str, Any], *, target_date: str) -> dict[str, Any]:
    if watchlist.get("status") != "PASS_MONITORING_ONLY":
        raise ValueError("WATCHLIST_NOT_PASS_MONITORING_ONLY")
    if str(watchlist.get("target_date_bogota") or "") != target_date:
        raise ValueError("WATCHLIST_TARGET_DATE_MISMATCH")
    policy = watchlist.get("policy")
    if not isinstance(policy, Mapping):
        raise ValueError("WATCHLIST_POLICY_MISSING")
    if policy.get("source_order") != ["SOFASCORE", "FLASHSCORE", "APIS"]:
        raise ValueError("BROWSER_FIRST_SOURCE_ORDER_REQUIRED")
    if policy.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")

    observed_at = _parse_dt(str(watchlist.get("generated_at_utc") or ""))
    if observed_at is None:
        raise ValueError("WATCHLIST_GENERATED_AT_REQUIRED")

    rows: list[dict[str, Any]] = []
    for bucket in ("confirmed_both", "sofascore_only", "flashscore_only", "ambiguous"):
        source_rows = watchlist.get(bucket) or []
        if not isinstance(source_rows, list):
            raise ValueError("WATCHLIST_BUCKET_MUST_BE_LIST:" + bucket)
        for raw in source_rows:
            if not isinstance(raw, Mapping):
                raise ValueError("WATCHLIST_EVENT_MUST_BE_OBJECT")
            kickoff = _parse_dt(str(raw.get("kickoff_display_bogota") or ""))
            if kickoff is None:
                temporal_status = "KICKOFF_NOT_CERTIFIED"
                prospective = False
            elif observed_at < kickoff:
                temporal_status = "OBSERVED_BEFORE_DISPLAYED_KICKOFF"
                prospective = True
            else:
                temporal_status = "NOT_PROSPECTIVE_AT_PREREGISTRATION"
                prospective = False
            rows.append({
                "browser_event_key": _event_key(raw),
                "bucket": bucket,
                "event_identity": raw.get("event_identity"),
                "sofascore_observation": raw.get("sofascore_observation"),
                "flashscore_observation": raw.get("flashscore_observation"),
                "source_count": raw.get("source_count"),
                "identity_status": raw.get("status"),
                "kickoff_display_bogota": raw.get("kickoff_display_bogota"),
                "preregistered_at_utc": observed_at.isoformat(),
                "prospective_observation": prospective,
                "temporal_status": temporal_status,
                "eligible_for_monitoring": True,
                "eligible_for_freeze": False,
                "freeze_blocker": raw.get("freeze_blocker") or "INDEPENDENT_TIME_CERTIFICATION_REQUIRED",
            })

    keys=[row["browser_event_key"] for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_BROWSER_EVENT_KEY")

    return {
        "schema": "MATRIX_FOOTBALL_BROWSER_FIRST_PREREGISTRY_V1",
        "target_date_bogota": target_date,
        "generated_from_watchlist_at_utc": observed_at.isoformat(),
        "status": "PASS_BROWSER_FIRST_PREREGISTRATION",
        "counts": {
            "total_monitoring_events": len(rows),
            "prospective_before_displayed_kickoff": sum(1 for row in rows if row["prospective_observation"]),
            "kickoff_not_certified": sum(1 for row in rows if row["temporal_status"]=="KICKOFF_NOT_CERTIFIED"),
            "not_prospective_at_preregistration": sum(1 for row in rows if row["temporal_status"]=="NOT_PROSPECTIVE_AT_PREREGISTRATION"),
        },
        "events": rows,
        "policy": {
            "source_order": ["SOFASCORE", "FLASHSCORE", "APIS"],
            "browser_event_survives_api_absence": True,
            "missing_not_zero": True,
            "no_silent_imputation": True,
            "post_start_backfill_forbidden": True,
            "preregistration_does_not_equal_freeze": True,
            "preregistration_does_not_create_p_matrix": True,
            "odds_used": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }


def load_and_build(path: Path, *, target_date: str) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("WATCHLIST_ROOT_MUST_BE_OBJECT")
    return build_browser_preregistry(value, target_date=target_date)


def main() -> None:
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--out", default="evidence/calendar_reconciliation/MATRIX_FOOTBALL_BROWSER_PREREGISTRY_LAST.json")
    parser.add_argument("--target-date", default="")
    args=parser.parse_args()
    watch_path=Path(args.watchlist)
    raw=json.loads(watch_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("WATCHLIST_ROOT_MUST_BE_OBJECT")
    target=str(args.target_date or raw.get("target_date_bogota") or "").strip()
    if not target:
        raise ValueError("TARGET_DATE_REQUIRED")
    result=build_browser_preregistry(raw,target_date=target)
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"target_date_bogota":target,"counts":result["counts"],"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
