from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE = "https://api.odds-api.net/v1"
OUT = Path("evidence/notifications/telegram/MATRIX_ODDS_API_QUOTA_GUARD_LAST.json")

THRESHOLDS = (50.0, 75.0, 90.0, 95.0, 100.0)


def evaluate_usage(payload: dict[str, Any]) -> dict[str, Any]:
    used = float(payload.get("api_credits_used") or 0)
    limit = float(payload.get("api_credits_limit") or 0)
    exceeded = bool(payload.get("exceeded"))
    if limit <= 0:
        raise ValueError("ODDS_API_USAGE_LIMIT_INVALID")
    pct = 100.0 * used / limit
    remaining = max(0.0, limit - used)

    if exceeded or used >= limit:
        stage = "BLOCKED_EXHAUSTED"
        max_seconds = 0
        allow = False
    elif pct >= 95.0:
        stage = "RESERVE_T30_ONLY"
        max_seconds = 30 * 60
        allow = True
    elif pct >= 90.0:
        stage = "RESERVE_T60_ONLY"
        max_seconds = 60 * 60
        allow = True
    elif pct >= 75.0:
        stage = "CONSERVE_T90_ONLY"
        max_seconds = 90 * 60
        allow = True
    elif pct >= 50.0:
        stage = "WATCH_T120"
        max_seconds = 120 * 60
        allow = True
    else:
        stage = "NORMAL_T120"
        max_seconds = 120 * 60
        allow = True

    crossed = [x for x in THRESHOLDS if pct >= x]
    return {
        "stage": stage,
        "api_calls_allowed": allow,
        "max_seconds_to_kickoff_for_odds_api_call": max_seconds,
        "api_credits_used": used,
        "api_credits_limit": limit,
        "api_credits_remaining": remaining,
        "usage_pct": round(pct, 4),
        "exceeded": exceeded or used >= limit,
        "crossed_alert_thresholds_pct": crossed,
        "plan": payload.get("plan"),
        "pricing_model": payload.get("pricing_model"),
        "period_start_utc": payload.get("period_start_utc"),
        "period_end_utc": payload.get("period_end_utc"),
        "stream_hours_used": payload.get("stream_hours_used"),
        "stream_hours_limit": payload.get("stream_hours_limit"),
        "stream_concurrent_units_used": payload.get("stream_concurrent_units_used"),
        "stream_concurrent_units_limit": payload.get("stream_concurrent_units_limit"),
    }


def should_call_odds_api(decision: dict[str, Any], seconds_to_kickoff: float) -> bool:
    if not decision.get("api_calls_allowed"):
        return False
    max_seconds = float(decision.get("max_seconds_to_kickoff_for_odds_api_call") or 0)
    return 0 < float(seconds_to_kickoff) <= max_seconds


def _load_previous() -> dict[str, Any]:
    if not OUT.exists():
        return {}
    try:
        value = json.loads(OUT.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _notify(session: requests.Session, token: str, chat_id: str, current: dict[str, Any], previous: dict[str, Any]) -> None:
    old_stage = str((previous.get("decision") or {}).get("stage") or "")
    new_stage = str(current.get("stage") or "")
    if not token or not chat_id or new_stage == old_stage:
        return
    pct = current.get("usage_pct")
    remaining = current.get("api_credits_remaining")
    text = "\n".join([
        "⚠️ MATRIX — CUOTA ODDS-API",
        f"Estado: {new_stage}",
        f"Consumo mensual: {pct:.2f}%",
        f"Créditos restantes: {remaining:.0f}",
        "Política: reservar capacidad para candidatos cercanos al inicio.",
        "No se relajan P_MATRIX, EV, cuota mínima ni Pinnacle.",
        "DINERO REAL MATRIX: BLOQUEADO",
    ])
    r = session.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text},
        timeout=(10, 60),
    )
    if r.status_code >= 300:
        raise RuntimeError(f"TELEGRAM_QUOTA_ALERT_FAILED:{r.status_code}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("ODDS_API_NET_KEY", "").strip()
    if not key:
        raise SystemExit("ODDS_API_NET_KEY_NOT_CONFIGURED")

    previous = _load_previous()
    session = requests.Session()
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    request_id = f"matrix-quota-{checked_at.replace(':','').replace('+','_')[:40]}"
    response = session.get(
        f"{BASE}/usage",
        headers={"X-API-Key": key, "X-Request-ID": request_id},
        timeout=(10, 60),
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}

    if response.status_code >= 300 or not isinstance(payload, dict):
        prior_decision = previous.get("decision") if isinstance(previous.get("decision"), dict) else None
        decision = dict(prior_decision) if prior_decision else {
            "stage": "USAGE_UNAVAILABLE_T60_FAIL_CLOSED",
            "api_calls_allowed": True,
            "max_seconds_to_kickoff_for_odds_api_call": 60 * 60,
            "usage_pct": None,
            "api_credits_used": None,
            "api_credits_limit": None,
            "api_credits_remaining": None,
            "exceeded": None,
            "crossed_alert_thresholds_pct": [],
        }
        status = "USAGE_ENDPOINT_UNAVAILABLE_USING_LAST_SAFE_DECISION"
    else:
        decision = evaluate_usage(payload)
        status = "PASS"

    result = {
        "schema": "MATRIX_ODDS_API_QUOTA_GUARD_V1",
        "checked_at_utc": checked_at,
        "status": status,
        "provider": "odds-api.net",
        "endpoint": "/v1/usage",
        "http_status": int(response.status_code),
        "request_id_sent": request_id,
        "request_id_returned": response.headers.get("X-Request-ID"),
        "decision": decision,
        "policy": {
            "thresholds_pct": list(THRESHOLDS),
            "below_50": "NORMAL_T120",
            "50_to_75": "WATCH_T120",
            "75_to_90": "CONSERVE_T90_ONLY",
            "90_to_95": "RESERVE_T60_ONLY",
            "95_to_100": "RESERVE_T30_ONLY",
            "exhausted": "BLOCKED_EXHAUSTED_ZERO_ODDS_API_RETRIES",
            "usage_check_once_per_operational_workflow_cycle": True,
            "missing_is_not_zero": True,
            "no_silent_imputation": True,
            "no_gate_relaxation": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.notify:
        _notify(
            session,
            os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
            decision,
            previous,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
