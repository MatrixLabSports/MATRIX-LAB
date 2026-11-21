"""Offline football source-recovery audit; never authorizes expired provider use or bets."""
from __future__ import annotations
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
SOURCE_ORDER = ["SOFASCORE", "FLASHSCORE", "APIS"]
SOURCES = ("sofascore", "flashscore", "odds_api_net", "api_football_free")

def inspect(policy: dict, preregistry: dict | None, entitlements: dict | None, target_date: str) -> dict:
    paid = policy["paid_primary"]
    paid_usable = target_date <= paid["paid_through_bogota_date"]
    prereg = preregistry if isinstance(preregistry, dict) else {}
    browser_current = (prereg.get("status") == "PASS_BROWSER_FIRST_PREREGISTRATION"
                       and prereg.get("target_date_bogota") == target_date
                       and prereg.get("policy", {}).get("source_order") == SOURCE_ORDER)
    ent = entitlements if isinstance(entitlements, dict) else {}
    source_states = {}
    for name in SOURCES:
        row = ent.get(name, {})
        complete = isinstance(row, dict) and all(row.get(k) is True for k in (
            "account_plan_verified", "current_season_coverage_verified",
            "endpoint_entitlement_verified", "quota_verified", "successful_response_verified"))
        complete = complete and bool(row.get("verification_artifact")) and bool(row.get("verified_at_utc"))
        source_states[name] = "EVIDENCE_RECORDED_NOT_RUNTIME_AUTHORIZATION" if complete else "UNVERIFIED_FAIL_CLOSED"
    return {
        "schema": "MATRIX_FOOTBALL_SOURCE_RECOVERY_OFFLINE_V1",
        "target_date_bogota": target_date,
        "paid_api_football_window_active": paid_usable,
        "paid_api_football_renewal_authorized": paid["renewal_authorized"],
        "browser_preregistry_current": browser_current,
        "browser_source_order": SOURCE_ORDER,
        "sources": source_states,
        "network_calls_performed": 0,
        "canonical_candidate_generation_verified": False,
        "telegram_delivery_verified": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "RECOVERY_EVIDENCE_INCOMPLETE_FAIL_CLOSED",
    }

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(BOGOTA).date().isoformat())
    parser.add_argument("--policy", type=Path, default=Path("config/MATRIX_FOOTBALL_SUBSCRIPTION_DEADLINE.json"))
    parser.add_argument("--preregistry", type=Path, default=Path("evidence/calendar_reconciliation/MATRIX_FOOTBALL_BROWSER_PREREGISTRY_LAST.json"))
    parser.add_argument("--entitlements", type=Path, default=Path("evidence/governance/MATRIX_PROVIDER_ENTITLEMENTS_VERIFIED.json"))
    parser.add_argument("--out", type=Path, default=Path("evidence/governance/MATRIX_FOOTBALL_SOURCE_RECOVERY_LAST.json"))
    args = parser.parse_args()
    policy = read_json(args.policy)
    if not isinstance(policy, dict):
        raise SystemExit("FOOTBALL_POLICY_MISSING_FAIL_CLOSED")
    result = inspect(policy, read_json(args.preregistry), read_json(args.entitlements), args.date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
