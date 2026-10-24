from tools.paid_api_quota_ledger import build_ledger


def test_api_football_verified_headers_are_physical_quota_evidence():
    ledger = build_ledger(
        tennis_inventory={},
        football_manifest={
            "network_calls": 1,
            "captures": [{
                "public_rate_headers": {
                    "x-ratelimit-requests-limit": "7500",
                    "x-ratelimit-requests-remaining": "4169",
                }
            }],
        },
    )
    row = ledger["providers"]["api_football"]
    assert row["quota_evidence_status"] == "VERIFIED_RESPONSE_HEADERS"
    assert row["quota_limit"] == 7500
    assert row["quota_remaining"] == 4169
    assert row["router"]["routine_inventory_refresh_allowed"] is True


def test_unknown_tennis_quota_blocks_routine_calls_after_probe():
    ledger = build_ledger(
        tennis_inventory={"provider_network_calls": 2, "provider_public_rate_headers": {}},
        football_manifest={},
    )
    row = ledger["providers"]["rapidapi_tennis"]
    assert row["quota_evidence_status"] == "UNKNOWN_NOT_EXPOSED_YET"
    assert row["quota_probe_count"] == 1
    assert row["router"]["routine_inventory_refresh_allowed"] is False
    assert row["router"]["quota_probe_allowed"] is False
    assert row["router"]["critical_scientific_call_allowed"] is True


def test_tennis_verified_headers_enable_routine_only_above_internal_reserve():
    ledger = build_ledger(
        tennis_inventory={
            "provider_network_calls": 2,
            "provider_public_rate_headers": {
                "x-ratelimit-requests-limit": "1000",
                "x-ratelimit-requests-remaining": "500",
            },
        },
        football_manifest={},
    )
    row = ledger["providers"]["rapidapi_tennis"]
    assert row["quota_evidence_status"] == "VERIFIED_RESPONSE_HEADERS"
    assert row["router"]["routine_inventory_refresh_allowed"] is True

    low = build_ledger(
        tennis_inventory={
            "provider_network_calls": 2,
            "provider_public_rate_headers": {
                "x-ratelimit-requests-limit": "1000",
                "x-ratelimit-requests-remaining": "100",
            },
        },
        football_manifest={},
    )
    assert low["providers"]["rapidapi_tennis"]["router"]["routine_inventory_refresh_allowed"] is False


def test_verified_account_console_quota_survives_headerless_refresh():
    previous = {
        "providers": {
            "rapidapi_tennis": {
                "quota_evidence_status": "VERIFIED_ACCOUNT_CONSOLE_PLUS_PROVIDER_DOCS",
                "quota_limit": 1200000,
                "quota_remaining": 1151400,
                "quota_remaining_fraction": 0.9595,
                "plan": "Ultra",
                "plan_price_usd_month": 59.0,
                "quota_usage_percent": 4.05,
            }
        }
    }
    ledger = build_ledger(
        tennis_inventory={
            "provider_network_calls": 2,
            "provider_public_rate_headers": {},
        },
        football_manifest={},
        previous_ledger=previous,
    )
    row = ledger["providers"]["rapidapi_tennis"]
    assert row["quota_evidence_status"] == "VERIFIED_ACCOUNT_CONSOLE_PLUS_PROVIDER_DOCS"
    assert row["quota_limit"] == 1200000
    assert row["quota_remaining"] == 1151400
    assert row["router"]["routine_inventory_refresh_allowed"] is True
