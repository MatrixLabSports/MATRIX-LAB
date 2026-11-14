"""MATRIX: fail-closed, no-network readiness of source entitlement evidence.

This is NOT an API entitlement verifier. It checks recorded evidence only.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

PROVIDERS = ("api_football_free", "rapidapi_tennis", "api_tennis", "odds_api_net")
REQUIRED = ("account_plan_verified", "current_season_coverage_verified", "endpoint_entitlement_verified", "quota_verified", "successful_response_verified")

def audit(evidence: dict) -> dict:
    providers = {}
    for name in PROVIDERS:
        row = evidence.get(name, {})
        valid = isinstance(row, dict) and all(row.get(k) is True for k in REQUIRED)
        valid = valid and bool(row.get("verification_artifact")) and bool(row.get("verified_at_utc"))
        providers[name] = {"status": "EVIDENCE_RECORDED_NOT_RUNTIME_AUTHORIZATION" if valid else "UNVERIFIED_FAIL_CLOSED",
                           "missing": [k for k in REQUIRED if row.get(k) is not True] if isinstance(row, dict) else list(REQUIRED)}
    return {"schema": "MATRIX_PROVIDER_READINESS_OFFLINE_V1",
            "status": "OFFLINE_EVIDENCE_INVENTORY_ONLY",
            "provider_authorization_granted_by_this_tool": False,
            "signal_generation_authorized_by_this_tool": False,
            "network_calls_performed": 0,
            "providers": providers,
            "real_money": "BLOCKED", "automatic_wagering": False}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path("evidence/governance/MATRIX_PROVIDER_ENTITLEMENTS_VERIFIED.json"))
    parser.add_argument("--out", type=Path, default=Path("evidence/governance/MATRIX_PROVIDER_READINESS_OFFLINE_LAST.json"))
    args = parser.parse_args()
    try:
        evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        evidence = {}
    result = audit(evidence)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
