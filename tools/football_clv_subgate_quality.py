from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path("evidence/clv/football/over_2_5")
STATE_PATH = ROOT / "state.json"
LEDGER_PATH = ROOT / "prospective_clv_ledger.jsonl"
ATTEMPTS_PATH = ROOT / "closing_attempts.jsonl"
OUTPUT_PATH = ROOT / "quality" / "MATRIX_CLV_SUBGATE_30_QUALITY.json"
STRICT_FRESH_SECONDS = 120
SUBGATE_TARGET = 30
FINAL_TARGET = 300


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(float(x) for x in values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def _capture_path(source_reference: str | None) -> Path | None:
    if not source_reference:
        return None
    first = source_reference.split(";", 1)[0]
    path = Path(first)
    return path if path.is_file() else None


def _failure_bucket(outcome: str) -> str:
    u = (outcome or "").upper()
    if "STALE" in u:
        return "STALE"
    if "IDENTITY" in u:
        return "IDENTITY"
    if "INCOMPLETE" in u:
        return "MARKET_INCOMPLETE"
    if "TEMPORAL" in u:
        return "TEMPORAL"
    if "PROVIDER" in u or "HTTP" in u or "CREDENTIAL" in u:
        return "PROVIDER_OR_CREDENTIAL"
    if "CAPTURED_VALID" in u:
        return "CAPTURED_VALID"
    return "OTHER"


def build_report() -> dict:
    state = _read_json(STATE_PATH)
    ledger = _read_jsonl(LEDGER_PATH)
    attempts = _read_jsonl(ATTEMPTS_PATH)

    closing_events = [
        row.get("payload", {})
        for row in ledger
        if row.get("event_type") == "CLOSING_ODDS_RECORDED"
    ]

    captures = []
    missing_capture_files = 0
    for event in closing_events:
        path = _capture_path(event.get("source_reference"))
        if path is None:
            missing_capture_files += 1
            continue
        payload = _read_json(path)
        closing = payload.get("closing") or {}
        captures.append(
            {
                "fixture_id": str(payload.get("fixture_id") or event.get("fixture_id") or ""),
                "capture_path": str(path),
                "provider": closing.get("provider"),
                "transport": closing.get("transport"),
                "provider_quote_age_seconds": closing.get("provider_quote_age_seconds"),
                "capture_lead_seconds": closing.get("capture_lead_seconds"),
                "complete_market_snapshot": closing.get("complete_market_snapshot"),
                "gate_excess_seconds": closing.get("gate_excess_seconds"),
                "real_money": (payload.get("protections") or {}).get("real_money"),
                "post_kickoff_close_forbidden": (payload.get("protections") or {}).get("post_kickoff_close_forbidden"),
            }
        )

    valid = []
    invalid_reasons = Counter()
    for row in captures:
        age = row.get("provider_quote_age_seconds")
        lead = row.get("capture_lead_seconds")
        checks = {
            "provider_pinnacle": row.get("provider") == "Pinnacle",
            "fresh_le_120": isinstance(age, (int, float)) and age <= STRICT_FRESH_SECONDS,
            "prematch": isinstance(lead, (int, float)) and lead > 0,
            "complete_market_snapshot": row.get("complete_market_snapshot") is True,
            "real_money_blocked": row.get("real_money") == "BLOCKED",
        }
        if all(checks.values()):
            valid.append(row)
        else:
            for name, ok in checks.items():
                if not ok:
                    invalid_reasons[name] += 1

    ages = [float(x["provider_quote_age_seconds"]) for x in valid]
    leads = [float(x["capture_lead_seconds"]) for x in valid]

    attempt_outcomes = Counter(str(x.get("outcome") or "UNKNOWN") for x in attempts)
    attempt_buckets = Counter(_failure_bucket(str(x.get("outcome") or "")) for x in attempts)
    attempt_transports = Counter(str(x.get("transport") or "UNKNOWN") for x in attempts)
    valid_transports = Counter(str(x.get("transport") or "UNKNOWN") for x in valid)

    closing_count = int(state.get("closing_odds_count") or 0)
    decision_count = int(state.get("decision_count") or 0)
    remaining_to_30 = max(0, SUBGATE_TARGET - closing_count)
    remaining_to_300 = max(0, FINAL_TARGET - closing_count)

    return {
        "schema": "MATRIX_CLV_SUBGATE_30_QUALITY_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "market_key": "over_2_5",
        "status": {
            "decision_count": decision_count,
            "closing_odds_count": closing_count,
            "subgate_target": SUBGATE_TARGET,
            "remaining_to_subgate_30": remaining_to_30,
            "final_target": FINAL_TARGET,
            "remaining_to_300": remaining_to_300,
            "subgate_30_reached": closing_count >= SUBGATE_TARGET,
            "metrics_opened": bool(state.get("metrics_opened")),
            "state_status": state.get("status"),
        },
        "valid_closing_quality": {
            "closing_events": len(closing_events),
            "capture_files_read": len(captures),
            "valid_strict_fresh_captures": len(valid),
            "missing_capture_files": missing_capture_files,
            "invalid_capture_reason_counts": dict(sorted(invalid_reasons.items())),
            "valid_capture_rate_pct_of_closing_events": round((100.0 * len(valid) / len(closing_events)), 6) if closing_events else None,
            "quote_age_seconds": {
                "count": len(ages),
                "min": min(ages) if ages else None,
                "mean": mean(ages) if ages else None,
                "median": median(ages) if ages else None,
                "p95": _percentile(ages, 0.95),
                "max": max(ages) if ages else None,
                "all_within_120": all(x <= STRICT_FRESH_SECONDS for x in ages) if ages else None,
            },
            "capture_lead_seconds": {
                "count": len(leads),
                "min": min(leads) if leads else None,
                "mean": mean(leads) if leads else None,
                "median": median(leads) if leads else None,
                "p95": _percentile(leads, 0.95),
                "max": max(leads) if leads else None,
                "all_prematch": all(x > 0 for x in leads) if leads else None,
            },
            "valid_transport_breakdown": dict(sorted(valid_transports.items())),
        },
        "attempt_quality": {
            "attempt_count": len(attempts),
            "outcome_counts": dict(sorted(attempt_outcomes.items())),
            "failure_bucket_counts": dict(sorted(attempt_buckets.items())),
            "transport_attempt_counts": dict(sorted(attempt_transports.items())),
            "note": "Attempt counts include repeated watcher polls and are not an event-level capture-rate denominator.",
        },
        "subgate_30_policy": {
            "strict_fresh_gate_seconds": STRICT_FRESH_SECONDS,
            "required_provider": "Pinnacle",
            "require_complete_market_snapshot": True,
            "require_prematch_capture": True,
            "historical_backfill_without_physical_entry_timestamp": "FORBIDDEN",
            "post_kickoff_closing_line": "FORBIDDEN",
            "odds_used_to_generate_probability": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
            "metrics_remain_sealed_until": 300,
            "tuning_before_300": "FORBIDDEN",
        },
        "adjudication": (
            "SUBGATE_30_REACHED_AUDIT_STABILITY_BEFORE_ADVANCING"
            if closing_count >= SUBGATE_TARGET
            else "ACCUMULATING_TO_SUBGATE_30_WITHOUT_TUNING"
        ),
    }


def main() -> None:
    report = build_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_path": str(OUTPUT_PATH),
        "closing_odds_count": report["status"]["closing_odds_count"],
        "remaining_to_subgate_30": report["status"]["remaining_to_subgate_30"],
        "valid_strict_fresh_captures": report["valid_closing_quality"]["valid_strict_fresh_captures"],
        "subgate_30_reached": report["status"]["subgate_30_reached"],
        "real_money": report["subgate_30_policy"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
