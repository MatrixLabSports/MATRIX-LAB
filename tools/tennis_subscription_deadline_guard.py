from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

POLICY_PATH = Path("config/MATRIX_TENNIS_SUBSCRIPTION_DEADLINE.json")
BOGOTA = ZoneInfo("America/Bogota")


def load_policy(path: Path = POLICY_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["paid_primary"]["provider"] == "rapidapi_tennis"
    assert data["paid_primary"]["renewal_authorized"] is False
    assert data["retired_sources"]["api_tennis"]["allowed_for_network_calls"] is False
    return data


def evaluate(as_of_bogota: date, *, require_paid_use: bool = False, require_key: bool = False) -> dict:
    policy = load_policy()
    cutoff = date.fromisoformat(policy["paid_primary"]["paid_through_bogota_date"])
    active = as_of_bogota <= cutoff
    days_remaining_inclusive = (cutoff - as_of_bogota).days + 1 if active else 0
    status = "PAID_WINDOW_ACTIVE_MAXIMIZE_EVIDENCE" if active else "PAID_WINDOW_CLOSED_NO_RENEWAL"
    if require_paid_use and not active:
        raise SystemExit("PAID_API_WINDOW_EXPIRED_NO_RENEWAL_AUTHORIZED")
    if require_key and active and not os.environ.get("RAPIDAPI_TENNIS_KEY", "").strip():
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED_DURING_ACTIVE_PAID_WINDOW")
    return {
        "schema": "MATRIX_TENNIS_SUBSCRIPTION_DEADLINE_GUARD_V1",
        "as_of_bogota_date": as_of_bogota.isoformat(),
        "paid_through_bogota_date": cutoff.isoformat(),
        "paid_window_active": active,
        "days_remaining_inclusive": days_remaining_inclusive,
        "status": status,
        "provider": "rapidapi_tennis",
        "renewal_authorized": False,
        "api_tennis_network_calls_allowed": False,
        "source_order": policy["source_order"],
        "free50_auto_activation_allowed": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--as-of-bogota-date")
    p.add_argument("--require-paid-use", action="store_true")
    p.add_argument("--require-key", action="store_true")
    p.add_argument("--out")
    args = p.parse_args()
    d = date.fromisoformat(args.as_of_bogota_date) if args.as_of_bogota_date else datetime.now(BOGOTA).date()
    result = evaluate(d, require_paid_use=args.require_paid_use, require_key=args.require_key)
    raw = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(raw, encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
