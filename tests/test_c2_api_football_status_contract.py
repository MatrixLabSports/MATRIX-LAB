from datetime import UTC, datetime

import pytest

from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.providers.api_football.request_contracts import (
    API_FOOTBALL_AUTH_HEADER,
    register_api_football_request_contracts,
)


NOW = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)


def _registered(tmp_path):
    registry = SQLiteProviderRequestContractRegistry(
        tmp_path / "status-contracts.db"
    )
    contracts = register_api_football_request_contracts(
        registry=registry,
        secret_reference_fingerprint="1" * 64,
        valid_from=NOW,
    )
    return registry, contracts


def test_status_contract_is_exact_get_with_zero_parameters(tmp_path):
    registry, contracts = _registered(tmp_path)
    contract = contracts["status"]

    assert contract.provider_key == "api_football"
    assert contract.sport == "football"
    assert contract.method == "GET"
    assert contract.path == "/status"
    assert contract.parameter_rules == ()
    assert contract.auth_header_name == API_FOOTBALL_AUTH_HEADER

    authorization = registry.authorize(
        contract_id=contract.contract_id,
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/status",
        params=None,
        secret_reference_fingerprint="1" * 64,
        now=NOW,
    )

    assert authorization.path == "/status"
    assert authorization.parameter_names == ()
    assert registry.audit_integrity() is True


def test_status_contract_rejects_any_query_parameter(tmp_path):
    registry, contracts = _registered(tmp_path)
    contract = contracts["status"]

    with pytest.raises(
        ValueError,
        match="UNAUTHORIZED_REQUEST_PARAMETER",
    ):
        registry.authorize(
            contract_id=contract.contract_id,
            provider_key="api_football",
            sport="football",
            method="GET",
            path="/status",
            params={"unexpected": "x"},
            secret_reference_fingerprint="1" * 64,
            now=NOW,
        )


def test_status_contract_rejects_wrong_path(tmp_path):
    registry, contracts = _registered(tmp_path)
    contract = contracts["status"]

    with pytest.raises(
        ValueError,
        match="REQUEST_CONTRACT_BINDING_MISMATCH",
    ):
        registry.authorize(
            contract_id=contract.contract_id,
            provider_key="api_football",
            sport="football",
            method="GET",
            path="/fixtures",
            params=None,
            secret_reference_fingerprint="1" * 64,
            now=NOW,
        )
