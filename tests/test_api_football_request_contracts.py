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
    8,
    20,
    tzinfo=timezone.utc,
)


def test_api_football_canonical_contract_set_is_explicit():
    contracts = build_api_football_request_contracts(
        secret_reference_fingerprint="1" * 64,
        valid_from=NOW,
    )

    assert API_FOOTBALL_CONTRACT_SET_VERSION
    assert set(contracts) == {
        "status",
        "fixtures_by_date",
        "fixture_by_id",
        "fixture_events",
        "fixture_lineups",
        "fixture_statistics",
        "fixture_players",
        "team_statistics",
        "players_by_team_season",
        "injuries_by_fixture",
        "standings_by_league_season",
        "odds_by_fixture",
        "live_odds_by_fixture",
    }

    assert (
        contracts[
            "fixture_statistics"
        ].path
        == "/fixtures/statistics"
    )
    assert (
        contracts[
            "odds_by_fixture"
        ].path
        == "/odds"
    )
    assert all(
        contract.provider_key
        == "api_football"
        for contract
        in contracts.values()
    )
    assert all(
        contract.sport
        == "football"
        for contract
        in contracts.values()
    )


def test_contract_registration_and_authorization_bind_exact_values(
    tmp_path,
):
    registry = SQLiteProviderRequestContractRegistry(
        tmp_path / "contracts.db"
    )

    contracts = register_api_football_request_contracts(
        registry=registry,
        secret_reference_fingerprint="1" * 64,
        valid_from=NOW,
    )

    contract = contracts[
        "fixtures_by_date"
    ]

    first = registry.authorize(
        contract_id=contract.contract_id,
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/fixtures",
        params={
            "date": "2026-08-20",
            "league": 39,
            "season": 2026,
        },
        secret_reference_fingerprint="1" * 64,
        now=NOW,
    )

    second = registry.authorize(
        contract_id=contract.contract_id,
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/fixtures",
        params={
            "date": "2026-08-21",
            "league": 39,
            "season": 2026,
        },
        secret_reference_fingerprint="1" * 64,
        now=NOW,
    )

    assert (
        first.authorization_fingerprint
        != second.authorization_fingerprint
    )
    assert registry.audit_integrity() is True


def test_canonical_contract_rejects_unknown_parameter(
    tmp_path,
):
    registry = SQLiteProviderRequestContractRegistry(
        tmp_path / "contracts.db"
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
            contract_id=(
                contracts[
                    "fixture_by_id"
                ].contract_id
            ),
            provider_key="api_football",
            sport="football",
            method="GET",
            path="/fixtures",
            params={
                "id": 123,
                "unexpected": "x",
            },
            secret_reference_fingerprint="1" * 64,
            now=NOW,
        )
