from datetime import datetime, timezone

import pytest

from app.core.provider_request_contract import (
    RequestParameterRule,
    SQLiteProviderRequestContractRegistry,
    build_provider_request_contract,
)


NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def _setup(tmp_path):
    registry = SQLiteProviderRequestContractRegistry(
        tmp_path / "contracts.db"
    )

    contract = build_provider_request_contract(
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/v3/fixtures",
        parameter_rules=(
            RequestParameterRule(
                name="date",
                value_type="DATE",
                required=True,
            ),
            RequestParameterRule(
                name="league",
                value_type="POSITIVE_INT",
                minimum=1,
                maximum=999999,
            ),
        ),
        auth_header_name="x-apisports-key",
        secret_reference_fingerprint="a" * 64,
        valid_from=NOW,
    )

    registry.register(contract)
    return registry, contract


def test_request_contract_authorizes_exact_typed_params(tmp_path):
    registry, contract = _setup(tmp_path)

    decision = registry.authorize(
        contract_id=contract.contract_id,
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/v3/fixtures",
        params={"date": "2026-08-20", "league": 39},
        secret_reference_fingerprint="a" * 64,
        now=NOW,
    )

    assert decision.parameter_names == ("date", "league")
    assert registry.audit_integrity() is True


def test_request_contract_rejects_unknown_params(tmp_path):
    registry, contract = _setup(tmp_path)

    with pytest.raises(
        ValueError,
        match="UNAUTHORIZED_REQUEST_PARAMETER",
    ):
        registry.authorize(
            contract_id=contract.contract_id,
            provider_key="api_football",
            sport="football",
            method="GET",
            path="/v3/fixtures",
            params={"date": "2026-08-20", "evil": "x"},
            secret_reference_fingerprint="a" * 64,
            now=NOW,
        )
