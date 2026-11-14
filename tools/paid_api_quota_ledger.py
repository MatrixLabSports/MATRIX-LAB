from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _quota_from_headers(headers: Mapping[str, Any] | None) -> dict[str, Any]:
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    limit = _int(
        h.get("x-ratelimit-requests-limit")
        or h.get("x-rapidapi-quota-limit")
    )
    remaining = _int(
        h.get("x-ratelimit-requests-remaining")
        or h.get("x-rapidapi-quota-remaining")
    )
    known = limit is not None and remaining is not None and limit > 0
    ratio = (remaining / limit) if known else None
    return {
        "quota_limit": limit,
        "quota_remaining": remaining,
        "quota_remaining_fraction": ratio,
        "quota_evidence_status": "VERIFIED_RESPONSE_HEADERS" if known else "UNKNOWN_NOT_EXPOSED_YET",
        "public_rate_headers": h,
    }


def build_ledger(
    *,
    tennis_inventory: Mapping[str, Any] | None,
    football_manifest: Mapping[str, Any] | None,
    previous_ledger: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tennis_inventory = tennis_inventory or {}
    football_manifest = football_manifest or {}
    previous_ledger = previous_ledger or {}

    tennis_headers = tennis_inventory.get("provider_public_rate_headers") or {}
    captures = football_manifest.get("captures") or []
    football_headers = {}
    if captures and isinstance(captures[0], Mapping):
        football_headers = captures[0].get("public_rate_headers") or {}

    tennis_quota = _quota_from_headers(tennis_headers)
    football_quota = _quota_from_headers(football_headers)

    prior_providers = previous_ledger.get("providers") or {}
    prior_tennis = prior_providers.get("rapidapi_tennis") or {}
    prior_football = prior_providers.get("api_football") or {}

    def preserve_verified_prior(current: dict[str, Any], prior: Mapping[str, Any]) -> dict[str, Any]:
        trusted = {
            "VERIFIED_RESPONSE_HEADERS",
            "VERIFIED_ACCOUNT_CONSOLE_PLUS_PROVIDER_DOCS",
        }
        if current.get("quota_evidence_status") == "VERIFIED_RESPONSE_HEADERS":
            return current
        if prior.get("quota_evidence_status") in trusted:
            out = dict(current)
            for key in (
                "quota_limit",
                "quota_remaining",
                "quota_remaining_fraction",
                "quota_evidence_status",
                "plan",
                "plan_price_usd_month",
                "quota_usage_percent",
                "bandwidth_quota_usage_percent",
                "account_console_status",
                "account_console_observed_at",
                "provider_docs_quota_basis",
                "quota_remaining_is_estimated_from_usage_percent",
                "subscription_start",
                "analytics_30d_api_calls_display",
                "analytics_30d_paid_api_calls_display",
                "analytics_30d_overage_spend_usd",
                "account_evidence",
                "analytics_evidence",
            ):
                if key in prior:
                    out[key] = prior[key]
            return out
        return current

    tennis_quota = preserve_verified_prior(tennis_quota, prior_tennis)
    football_quota = preserve_verified_prior(football_quota, prior_football)
    tennis_probe_count = int(prior_tennis.get("quota_probe_count") or 0)
    if "provider_public_rate_headers" in tennis_inventory:
        tennis_probe_count += 1

    reserve_fraction = 0.20

    def route(quota: Mapping[str, Any], *, unknown_probe_count: int = 0) -> dict[str, Any]:
        known = quota.get("quota_evidence_status") in {
            "VERIFIED_RESPONSE_HEADERS",
            "VERIFIED_ACCOUNT_CONSOLE_PLUS_PROVIDER_DOCS",
        }
        remaining_fraction = quota.get("quota_remaining_fraction")
        if known:
            low_value_allowed = bool(remaining_fraction is not None and remaining_fraction > reserve_fraction)
            reason = "QUOTA_ABOVE_INTERNAL_RESERVE" if low_value_allowed else "RESERVE_CRITICAL_CALLS_ONLY"
            quota_probe_allowed = False
        else:
            low_value_allowed = False
            quota_probe_allowed = unknown_probe_count < 1
            reason = "UNKNOWN_QUOTA_BLOCK_ROUTINE_CALLS"
        return {
            "routine_inventory_refresh_allowed": low_value_allowed,
            "critical_scientific_call_allowed": True,
            "quota_probe_allowed": quota_probe_allowed,
            "reason": reason,
            "internal_reserve_fraction": reserve_fraction,
        }

    return {
        "schema": "MATRIX_PAID_API_QUOTA_LEDGER_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "review_interval_minutes": 15,
        "network_refresh_floor_minutes": 60,
        "policy": {
            "unknown_quota_blocks_routine_calls": True,
            "critical_scientific_calls_are_separate": True,
            "internal_reserve_fraction": reserve_fraction,
            "real_money": "BLOCKED",
            "automatic_wagering": False,
        },
        "providers": {
            "rapidapi_tennis": {
                "network_calls_in_observation": int(tennis_inventory.get("provider_network_calls") or 0),
                "quota_probe_count": tennis_probe_count,
                **tennis_quota,
                "router": route(tennis_quota, unknown_probe_count=tennis_probe_count),
            },
            "api_football": {
                "network_calls_in_observation": int(football_manifest.get("network_calls") or 0),
                **football_quota,
                "router": route(football_quota),
            },
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tennis-inventory")
    p.add_argument("--football-manifest")
    p.add_argument("--previous-ledger")
    p.add_argument("--out", required=True)
    a = p.parse_args()

    def load(path: str | None) -> dict[str, Any]:
        if not path:
            return {}
        q = Path(path)
        if not q.exists():
            return {}
        return json.loads(q.read_text(encoding="utf-8"))

    ledger = build_ledger(
        tennis_inventory=load(a.tennis_inventory),
        football_manifest=load(a.football_manifest),
        previous_ledger=load(a.previous_ledger),
    )
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(ledger, sort_keys=True))


if __name__ == "__main__":
    main()
