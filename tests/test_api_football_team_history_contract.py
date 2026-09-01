from datetime import datetime, timezone

import pytest

from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.providers.api_football.request_contracts import (
    API_FOOTBALL_CONTRACT_SET_VERSION,
    build_api_football_request_contracts,
    register_api_football_request_contracts,
)


NOW = datetime(
    2026,
    9,
    1,
    16,
    0,
    tzinfo=timezone.utc,
)


def test_team_history_contract_is_exact_bounded_get():
    contracts = build_api_football_request_contracts(
        secret_reference_fingerprint="1" * 64,
        valid_from=NOW,
    )

    assert API_FOOTBALL_CONTRACT_SET_VERSION == "2026-09-01.v3"

    contract = contracts["fixtures_by_team_last"]
    assert contract.provider_key == "api_football"
    assert contract.sport == "football"
    assert contract.method == "GET"
    assert contract.path == "/fixtures"

    rules = {
        rule.name: rule
        for rule in contract.parameter_rules
    }
    assert set(rules) == {"team", "last"}

    assert rules["team"].value_type == "POSITIVE_INT"
    assert rules["team"].required is True
    assert rules["team"].minimum == 1

    assert rules["last"].value_type == "POSITIVE_INT"
    assert rules["last"].required is True
    assert rules["last"].minimum == 1
    assert rules["last"].maximum == 30


def _registered(tmp_path):
    registry = SQLiteProviderRequestContractRegistry(
        tmp_path / "team-history-contracts.db"
    )
    contracts = register_api_football_request_contracts(
        registry=registry,
        secret_reference_fingerprint="1" * 64,
        valid_from=NOW,
    )
    return registry, contracts["fixtures_by_team_last"]


def test_team_history_contract_authorizes_team_last30(tmp_path):
    registry, contract = _registered(tmp_path)

    decision = registry.authorize(
        contract_id=contract.contract_id,
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/fixtures",
        params={
            "team": 54,
            "last": 30,
        },
        secret_reference_fingerprint="1" * 64,
        now=NOW,
    )

    assert set(decision.parameter_names) == {
        "team",
        "last",
    }
    assert registry.audit_integrity() is True


@pytest.mark.parametrize(
    "params",
    [
        {"team": 54},
        {"last": 30},
        {"team": 54, "last": 0},
        {"team": 54, "last": 31},
        {"team": 0, "last": 30},
        {"team": 54, "last": 30, "date": "2026-09-01"},
    ],
)
def test_team_history_contract_fails_closed_outside_scope(
    tmp_path,
    params,
):
    registry, contract = _registered(tmp_path)

    with pytest.raises(ValueError):
        registry.authorize(
            contract_id=contract.contract_id,
            provider_key="api_football",
            sport="football",
            method="GET",
            path="/fixtures",
            params=params,
            secret_reference_fingerprint="1" * 64,
            now=NOW,
        )


def test_date_contract_still_rejects_last_parameter(tmp_path):
    registry = SQLiteProviderRequestContractRegistry(
        tmp_path / "date-contracts.db"
    )
    contracts = register_api_football_request_contracts(
        registry=registry,
        secret_reference_fingerprint="1" * 64,
        valid_from=NOW,
    )

    with pytest.raises(
        ValueError,
        match="UNAUTHORIZED_REQUEST_PARAMETER",
    ):
        registry.authorize(
            contract_id=contracts["fixtures_by_date"].contract_id,
            provider_key="api_football",
            sport="football",
            method="GET",
            path="/fixtures",
            params={
                "date": "2026-09-01",
                "team": 54,
                "last": 30,
            },
            secret_reference_fingerprint="1" * 64,
            now=NOW,
        )
