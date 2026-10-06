from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIN_ODDS_EXCLUSIVE = 1.50
BLOCKING_ADJUDICATION_PREFIXES = ("NO_BET", "WATCHLIST", "RESEARCH_SIGNAL")


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def adjudicate(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    model = payload.get("model_status", {})
    protections = payload.get("protections", {})

    if model.get("daily_p_matrix") != "GENERATED":
        reasons.append("P_MATRIX_NOT_GENERATED")
    if model.get("real_money") != "BLOCKED":
        reasons.append("REAL_MONEY_NOT_BLOCKED")
    if protections.get("automatic_wagering") is not False:
        reasons.append("AUTOMATIC_WAGERING_NOT_DISABLED")
    if protections.get("real_money") != "BLOCKED":
        reasons.append("PROTECTION_REAL_MONEY_NOT_BLOCKED")

    eligible: list[dict[str, Any]] = []
    for c in payload.get("candidates", []):
        local: list[str] = []
        adjudication = str(c.get("adjudication", ""))
        if adjudication.startswith(BLOCKING_ADJUDICATION_PREFIXES):
            local.append("CANDIDATE_NOT_AUTHORIZED")
        p = c.get("p_matrix")
        odds = c.get("observed_decimal_odds")
        freeze = c.get("freeze_timestamp_utc")
        start = c.get("event_start_utc")
        if not isinstance(p, (int, float)) or not (0 < p < 1):
            local.append("P_MATRIX_MISSING_OR_INVALID")
        if not isinstance(odds, (int, float)) or odds <= MIN_ODDS_EXCLUSIVE:
            local.append("ODDS_MISSING_OR_BELOW_FLOOR")
        if not freeze or not start:
            local.append("FREEZE_OR_START_MISSING")
        else:
            try:
                f, s = _utc(freeze), _utc(start)
                if f >= s:
                    local.append("FREEZE_NOT_PREMATCH")
                if now >= s:
                    local.append("EVENT_ALREADY_STARTED")
            except ValueError:
                local.append("TIMESTAMP_INVALID")
        if not local and not reasons:
            ev = float(p) * float(odds) - 1.0
            if ev <= 0:
                local.append("EV_NOT_POSITIVE")
            else:
                row = dict(c)
                row["computed_ev"] = ev
                eligible.append(row)
        c["telegram_bridge_reasons"] = local

    status = "ELIGIBLE" if eligible else "BLOCKED"
    result = {
        "schema": "MATRIX_TELEGRAM_SHADOW_BRIDGE_V1",
        "status": status,
        "mode": "SHADOW",
        "real_money": "BLOCKED",
        "automatic_wagering": False,
        "source_target_date_bogota": payload.get("target_date_bogota"),
        "global_block_reasons": reasons,
        "eligible_count": len(eligible),
        "eligible": eligible,
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    result["record_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    payload = json.loads(Path(args.source).read_text(encoding="utf-8"))
    result = adjudicate(payload)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("MATRIX_TELEGRAM_SHADOW_BRIDGE=" + result["status"])
    print("ELIGIBLE_COUNT=" + str(result["eligible_count"]))
    print("RECORD_SHA256=" + result["record_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
