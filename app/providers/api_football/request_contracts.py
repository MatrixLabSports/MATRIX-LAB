from __future__ import annotations

from datetime import datetime
from typing import Mapping

from app.core.provider_request_contract import (
    ProviderRequestContract,
    RequestParameterRule,
    SQLiteProviderRequestContractRegistry,
    build_provider_request_contract,
)


API_FOOTBALL_PROVIDER_KEY = "api_football"
API_FOOTBALL_SPORT = "football"
API_FOOTBALL_AUTH_HEADER = "x-apisports-key"
API_FOOTBALL_CONTRACT_SET_VERSION = "2026-08-20.v1"


def _id_rule(
    name: str,
    *,
    required: bool = True,
) -> RequestParameterRule:
    return RequestParameterRule(
        name=name,
        value_type="POSITIVE_INT",
        required=required,
        minimum=1,
    )


def _season_rule(
    *,
    required: bool = True,
) -> RequestParameterRule:
    return RequestParameterRule(
        name="season",
        value_type="POSITIVE_INT",
        required=required,
        minimum=2000,
        maximum=2100,
    )


def build_api_football_request_contracts(
    *,
    secret_reference_fingerprint: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
) -> Mapping[str, ProviderRequestContract]:
    specifications = {
        "fixtures_by_date": (
            "/fixtures",
            (
                RequestParameterRule(
                    name="date",
                    value_type="DATE",
                    required=True,
                ),
                _id_rule(
                    "league",
                    required=False,
                ),
                _season_rule(
                    required=False,
                ),
                _id_rule(
                    "team",
                    required=False,
                ),
            ),
        ),
        "fixture_by_id": (
            "/fixtures",
            (
                _id_rule("id"),
            ),
        ),
        "fixture_events": (
            "/fixtures/events",
            (
                _id_rule("fixture"),
            ),
        ),
        "fixture_lineups": (
            "/fixtures/lineups",
            (
                _id_rule("fixture"),
            ),
        ),
        "fixture_statistics": (
            "/fixtures/statistics",
            (
                _id_rule("fixture"),
                _id_rule(
                    "team",
                    required=False,
                ),
            ),
        ),
        "fixture_players": (
            "/fixtures/players",
            (
                _id_rule("fixture"),
            ),
        ),
        "team_statistics": (
            "/teams/statistics",
            (
                _id_rule("league"),
                _season_rule(),
                _id_rule("team"),
            ),
        ),
        "players_by_team_season": (
            "/players",
            (
                _id_rule("team"),
                _season_rule(),
            ),
        ),
        "injuries_by_fixture": (
            "/injuries",
            (
                _id_rule("fixture"),
            ),
        ),
        "standings_by_league_season": (
            "/standings",
            (
                _id_rule("league"),
                _season_rule(),
            ),
        ),
        "odds_by_fixture": (
            "/odds",
            (
                _id_rule("fixture"),
            ),
        ),
        "live_odds_by_fixture": (
            "/odds/live",
            (
                _id_rule("fixture"),
            ),
        ),
    }

    contracts: dict[
        str,
        ProviderRequestContract,
    ] = {}

    for name, (
        path,
        rules,
    ) in specifications.items():
        contracts[name] = (
            build_provider_request_contract(
                provider_key=(
                    API_FOOTBALL_PROVIDER_KEY
                ),
                sport=API_FOOTBALL_SPORT,
                method="GET",
                path=path,
                parameter_rules=rules,
                auth_header_name=(
                    API_FOOTBALL_AUTH_HEADER
                ),
                secret_reference_fingerprint=(
                    secret_reference_fingerprint
                ),
                valid_from=valid_from,
                valid_until=valid_until,
            )
        )

    return contracts


def register_api_football_request_contracts(
    *,
    registry: SQLiteProviderRequestContractRegistry,
    secret_reference_fingerprint: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
) -> Mapping[str, ProviderRequestContract]:
    contracts = build_api_football_request_contracts(
        secret_reference_fingerprint=(
            secret_reference_fingerprint
        ),
        valid_from=valid_from,
        valid_until=valid_until,
    )

    for contract in contracts.values():
        registry.register(
            contract
        )

    return contracts

def register_api_football_contract_endpoint_bindings(
    *,
    contracts: Mapping[str, ProviderRequestContract],
    endpoint_manifest_ids: Mapping[str, str],
    registry,
    valid_from: datetime,
    valid_until: datetime | None = None,
):
    from app.core.provider_contract_endpoint_binding import (
        build_provider_contract_endpoint_binding,
    )

    if set(contracts) != set(endpoint_manifest_ids):
        raise ValueError(
            "API_FOOTBALL_ENDPOINT_MANIFEST_SET_MISMATCH"
        )

    bindings = {}

    for name in sorted(contracts):
        contract = contracts[name]

        binding = build_provider_contract_endpoint_binding(
            provider_key=contract.provider_key,
            sport=contract.sport,
            request_contract_id=contract.contract_id,
            endpoint_manifest_id=(
                endpoint_manifest_ids[name]
            ),
            path=contract.path,
            valid_from=valid_from,
            valid_until=valid_until,
        )

        registry.register(
            binding
        )

        bindings[name] = binding

    return bindings
