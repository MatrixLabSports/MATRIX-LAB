from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

POLICY_PATH = Path("config/MATRIX_FOOTBALL_SUBSCRIPTION_DEADLINE.json")
BOGOTA = ZoneInfo("America/Bogota")


def load_policy(path: Path = POLICY_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["paid_primary"]["provider"] == "api_football"
    assert data["paid_primary"]["renewal_authorized"] is False
    return data


def evaluate(as_of_bogota: date, *, require_paid_use: bool = False, require_key: bool = False) -> dict:
    policy = load_policy()
    cutoff = date.fromisoformat(policy["paid_primary"]["paid_through_bogota_date"])
    active = as_of_bogota <= cutoff
    override = os.environ.get("MATRIX_API_FOOTBALL_POST_CUTOFF_AUTHORIZED", "").strip().lower() == "true"
    authorized = active or override
    days_remaining_inclusive = (cutoff - as_of_bogota).days + 1 if active else 0
    status = "PAID_WINDOW_ACTIVE_MAXIMIZE_EVIDENCE" if active else (
        "POST_CUTOFF_EXPLICITLY_AUTHORIZED" if override else "PAID_WINDOW_CLOSED_NO_RENEWAL"
    )
    if require_paid_use and not authorized:
        raise SystemExit("API_FOOTBALL_PAID_WINDOW_EXPIRED_NO_RENEWAL_AUTHORIZED")
    if require_key and authorized and not os.environ.get("API_FOOTBALL_KEY", "").strip():
        raise SystemExit("API_FOOTBALL_KEY_REQUIRED_DURING_AUTHORIZED_WINDOW")
    return {
        "schema":"MATRIX_FOOTBALL_SUBSCRIPTION_DEADLINE_GUARD_V1",
        "as_of_bogota_date":as_of_bogota.isoformat(),
        "paid_through_bogota_date":cutoff.isoformat(),
        "paid_window_active":active,
        "days_remaining_inclusive":days_remaining_inclusive,
        "status":status,
        "provider":"api_football",
        "renewal_authorized":False,
        "post_cutoff_override":override,
        "odds_api_net_covered_by_this_expiry_rule":False,
        "source_order":policy["source_order"],
        "real_money":"BLOCKED",
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--as-of-bogota-date")
    p.add_argument("--require-paid-use",action="store_true")
    p.add_argument("--require-key",action="store_true")
    p.add_argument("--out")
    a=p.parse_args()
    d=date.fromisoformat(a.as_of_bogota_date) if a.as_of_bogota_date else datetime.now(BOGOTA).date()
    result=evaluate(d,require_paid_use=a.require_paid_use,require_key=a.require_key)
    raw=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.out:
        out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(raw,encoding="utf-8")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
