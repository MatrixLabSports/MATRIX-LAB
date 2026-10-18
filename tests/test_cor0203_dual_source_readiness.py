from tools.cor0203_dual_source_readiness import classify_dual_source_readiness


def _discovery(provider: str, *, calls: int = 3, status: str = "DISCOVERY_COMPLETED"):
    return {
        "provider": provider,
        "status": status,
        "network_calls": calls,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def _horizon(status: str = "PASS"):
    return {
        "status": status,
        "logical_horizon_days": 8,
        "real_money": "BLOCKED",
    }


def _reconciliation(status: str = "PASS"):
    return {
        "status": status,
        "rapidapi_provider_status": "DISCOVERY_COMPLETED",
        "api_tennis_provider_status": "DISCOVERY_COMPLETED",
        "real_money": "BLOCKED",
    }


def test_dual_readiness_requires_both_paid_providers_as_peers():
    result = classify_dual_source_readiness(
        rapidapi=_discovery("rapidapi_tennis", calls=4),
        api_tennis=_discovery("api_tennis", calls=2),
        horizon=_horizon(),
        reconciliation=_reconciliation(),
    )
    assert result["ready"] is True
    assert result["status"] == "DUAL_DISCOVERY_COMPLETED"
    assert result["provider"] == "dual_paid_tennis"
    assert result["required_providers"] == ["rapidapi_tennis", "api_tennis"]
    assert result["both_paid_providers_required"] is True
    assert result["symmetric_discovery"] is True
    assert result["provider_primary"] is None
    assert result["fallback_provider"] is None
    assert result["network_calls"] == 6
    assert result["real_money"] == "BLOCKED"


def test_dual_readiness_fails_closed_when_api_tennis_has_no_network_call():
    result = classify_dual_source_readiness(
        rapidapi=_discovery("rapidapi_tennis", calls=4),
        api_tennis=_discovery("api_tennis", calls=0),
        horizon=_horizon(),
        reconciliation=_reconciliation(),
    )
    assert result["ready"] is False
    assert result["status"] == "DUAL_DISCOVERY_BLOCKED"
    assert "api_tennis:DISCOVERY_COMPLETED_WITHOUT_NETWORK_CALL" in result["cause"]


def test_dual_readiness_fails_closed_when_rapidapi_is_not_ready():
    result = classify_dual_source_readiness(
        rapidapi=_discovery("rapidapi_tennis", calls=0),
        api_tennis=_discovery("api_tennis", calls=2),
        horizon=_horizon(),
        reconciliation=_reconciliation(),
    )
    assert result["ready"] is False
    assert "rapidapi_tennis:DISCOVERY_COMPLETED_WITHOUT_NETWORK_CALL" in result["cause"]


def test_dual_readiness_rejects_provider_identity_mismatch():
    result = classify_dual_source_readiness(
        rapidapi=_discovery("api_tennis", calls=2),
        api_tennis=_discovery("api_tennis", calls=2),
        horizon=_horizon(),
        reconciliation=_reconciliation(),
    )
    assert result["ready"] is False
    assert "rapidapi_tennis:PROVIDER_IDENTITY_MISMATCH" in result["cause"]


def test_dual_readiness_requires_passed_reconciliation_and_eight_day_horizon():
    bad_reconcile = classify_dual_source_readiness(
        rapidapi=_discovery("rapidapi_tennis"),
        api_tennis=_discovery("api_tennis"),
        horizon=_horizon(),
        reconciliation=_reconciliation("FAIL"),
    )
    assert bad_reconcile["ready"] is False
    assert bad_reconcile["cause"] == "DUAL_RECONCILIATION_NOT_READY"

    bad_horizon = classify_dual_source_readiness(
        rapidapi=_discovery("rapidapi_tennis"),
        api_tennis=_discovery("api_tennis"),
        horizon={**_horizon(), "logical_horizon_days": 4},
        reconciliation=_reconciliation(),
    )
    assert bad_horizon["ready"] is False
    assert bad_horizon["cause"] == "DUAL_HORIZON_NOT_READY"
