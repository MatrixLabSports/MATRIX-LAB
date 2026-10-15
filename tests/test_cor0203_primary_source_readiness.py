from tools.cor0203_primary_source_readiness import classify


def test_primary_source_readiness_does_not_require_api_tennis():
    rapid={
        "provider":"rapidapi_tennis",
        "status":"DISCOVERY_COMPLETED",
        "network_calls":4,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    horizon={
        "status":"PASS",
        "logical_horizon_days":8,
        "real_money":"BLOCKED",
    }
    out=classify(rapidapi=rapid,horizon=horizon)
    assert out["ready"] is True
    assert out["status"] == "PRIMARY_PAID_DISCOVERY_COMPLETED"
    assert out["required_paid_providers"] == ["rapidapi_tennis"]
    assert out["two_paid_sources_required"] is False
    assert out["retired_paid_sources"]["api_tennis"]["status"] == "RETIRED_COST_UTILITY_DECISION"
    assert out["required_open_calendar_reconciliation"] == ["SofaScore","Flashscore"]
    assert out["metrics_opened"] is False
    assert out["automatic_wagering"] is False
    assert out["real_money"] == "BLOCKED"
