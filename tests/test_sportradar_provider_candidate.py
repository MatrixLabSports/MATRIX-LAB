from datetime import datetime, timezone

import pytest

from app.providers.sportradar.config import SportradarConfig
from app.providers.sportradar.request_contracts import (
    SPORTRADAR_AUTH_HEADER,
    SPORTRADAR_PROVIDER_KEY,
    build_sportradar_request_contracts,
    build_sportradar_concrete_dynamic_contract,
)
from app.providers.sportradar.response_validation import (
    SportradarProviderResponseError,
    validate_sportradar_collection,
)
from app.providers.sportradar.tennis_adapter import (
    adapt_sportradar_tennis_competition,
)
from app.providers.sportradar.soccer_adapter import (
    adapt_sportradar_soccer_competition,
)
from app.providers.sportradar.catalog_service import (
    ingest_sportradar_competitions,
)

NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)
FP = "a" * 64


def test_config_exact_versions_and_host():
    c = SportradarConfig()
    assert c.base_url == "https://api.sportradar.com"
    assert c.tennis_version == "v3"
    assert c.soccer_version == "v4"


@pytest.mark.parametrize("url", (
    "http://api.sportradar.com",
    "https://evil.example",
    "https://api.sportradar.com/path",
))
def test_config_rejects_wrong_base_url(url):
    with pytest.raises(ValueError, match="BASE_URL"):
        SportradarConfig(base_url=url)


def test_tennis_contracts_are_sport_scoped():
    c = SportradarConfig()
    contracts = build_sportradar_request_contracts(
        config=c,
        sport="tennis",
        secret_reference_fingerprint=FP,
        valid_from=NOW,
    )
    assert set(contracts) == {"competitions", "seasons", "live_schedule"}
    assert all(x.provider_key == SPORTRADAR_PROVIDER_KEY for x in contracts.values())
    assert all(x.sport == "tennis" for x in contracts.values())
    assert all(x.auth_header_name == SPORTRADAR_AUTH_HEADER for x in contracts.values())
    assert contracts["competitions"].path == "/tennis/trial/v3/en/competitions.json"


def test_soccer_contracts_are_football_scoped():
    c = SportradarConfig()
    contracts = build_sportradar_request_contracts(
        config=c,
        sport="football",
        secret_reference_fingerprint=FP,
        valid_from=NOW,
    )
    assert all(x.sport == "football" for x in contracts.values())
    assert contracts["competitions"].path == "/soccer/trial/v4/en/competitions.json"


def test_dynamic_tennis_season_summary_becomes_exact_contract():
    c = SportradarConfig()
    contract = build_sportradar_concrete_dynamic_contract(
        config=c,
        sport="tennis",
        feed="season_summaries",
        resource_id="sr:season:134885",
        secret_reference_fingerprint=FP,
        valid_from=NOW,
    )
    assert contract.path == (
        "/tennis/trial/v3/en/seasons/"
        "sr:season:134885/summaries.json"
    )
    assert contract.sport == "tennis"
    assert tuple(r.name for r in contract.parameter_rules) == ("limit", "start")
    limit_rule, start_rule = contract.parameter_rules
    assert start_rule.minimum == 1
    assert limit_rule.minimum == 1
    assert limit_rule.maximum == 200


def test_dynamic_soccer_daily_schedule_becomes_exact_contract():
    c = SportradarConfig()
    contract = build_sportradar_concrete_dynamic_contract(
        config=c,
        sport="football",
        feed="daily_schedule",
        date="2026-09-03",
        secret_reference_fingerprint=FP,
        valid_from=NOW,
    )
    assert contract.path == (
        "/soccer/trial/v4/en/schedules/"
        "2026-09-03/schedules.json"
    )


@pytest.mark.parametrize("bad_id", (
    "../etc/passwd",
    "sr:season:0",
    "sr:season:-1",
    "sr:season:123/summary",
    "sr:sport_event:1?x=1",
))
def test_dynamic_resource_ids_reject_path_injection(bad_id):
    c = SportradarConfig()
    with pytest.raises(ValueError, match="INVALID_SPORTRADAR"):
        build_sportradar_concrete_dynamic_contract(
            config=c,
            sport="tennis",
            feed="season_summaries",
            resource_id=bad_id,
            secret_reference_fingerprint=FP,
            valid_from=NOW,
        )


@pytest.mark.parametrize("bad_date", (
    "2026-9-3",
    "2026-02-30",
    "../2026-09-03",
    "2026-09-03?x=1",
))
def test_dynamic_dates_reject_noncanonical_or_injection(bad_date):
    c = SportradarConfig()
    with pytest.raises(ValueError, match="INVALID_SPORTRADAR_DATE"):
        build_sportradar_concrete_dynamic_contract(
            config=c,
            sport="football",
            feed="daily_schedule",
            date=bad_date,
            secret_reference_fingerprint=FP,
            valid_from=NOW,
        )


def test_response_validator_accepts_competitions():
    env = validate_sportradar_collection(
        {
            "generated_at": "2026-09-03T12:00:00+00:00",
            "competitions": [{"id": "sr:competition:1"}],
        },
        collection_name="competitions",
    )
    assert len(env.items) == 1
    assert len(env.payload_fingerprint) == 64


@pytest.mark.parametrize("payload", (
    [],
    {},
    {"generated_at": "", "competitions": []},
    {"generated_at": "x", "competitions": {}},
))
def test_response_validator_fails_closed(payload):
    with pytest.raises((ValueError, SportradarProviderResponseError)):
        validate_sportradar_collection(
            payload,
            collection_name="competitions",
        )


def test_tennis_adapter_is_strict():
    result = adapt_sportradar_tennis_competition(
        {
            "id": "sr:competition:2591",
            "name": "US Open Men Singles",
            "type": "singles",
            "gender": "men",
            "category": {"id": "sr:category:3", "name": "ATP"},
        }
    )
    assert result.sport == "tennis"
    assert result.competition_id == "sr:competition:2591"


def test_soccer_adapter_is_strict():
    result = adapt_sportradar_soccer_competition(
        {
            "id": "sr:competition:17",
            "name": "Premier League",
            "gender": "men",
            "category": {
                "id": "sr:category:1",
                "name": "England",
                "country_code": "ENG",
            },
        }
    )
    assert result.sport == "football"
    assert result.country_code == "ENG"


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, *, path, request_contract_id, params):
        self.calls.append((path, request_contract_id, params))
        return self.payload


def test_catalog_partial_ingestion_preserves_valid_records():
    client = FakeClient(
        {
            "generated_at": "2026-09-03T12:00:00+00:00",
            "competitions": [
                {
                    "id": "sr:competition:2591",
                    "name": "US Open Men Singles",
                    "type": "singles",
                    "gender": "men",
                    "category": {"id": "sr:category:3", "name": "ATP"},
                },
                {"id": "broken"},
            ],
        }
    )
    result = ingest_sportradar_competitions(
        client=client,
        sport="tennis",
        request_contract_id="f" * 64,
        path="/tennis/trial/v3/en/competitions.json",
    )
    assert result.received_count == 2
    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert len(client.calls) == 1


def test_concrete_dynamic_contract_preserves_core_exact_path_authorization(tmp_path):
    from app.core.provider_request_contract import (
        SQLiteProviderRequestContractRegistry,
    )

    c = SportradarConfig()
    registry = SQLiteProviderRequestContractRegistry(tmp_path / "contracts.sqlite3")
    contract = build_sportradar_concrete_dynamic_contract(
        config=c,
        sport="tennis",
        feed="season_summaries",
        resource_id="sr:season:134885",
        secret_reference_fingerprint=FP,
        valid_from=NOW,
    )
    registry.register(contract)

    decision = registry.authorize(
        contract_id=contract.contract_id,
        provider_key="sportradar",
        sport="tennis",
        method="GET",
        path=contract.path,
        params={"start": 200},
        secret_reference_fingerprint=FP,
        now=NOW,
    )
    assert decision.path == contract.path

    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        registry.authorize(
            contract_id=contract.contract_id,
            provider_key="sportradar",
            sport="tennis",
            method="GET",
            path=contract.path.replace("134885", "134881"),
            params={"start": 200},
            secret_reference_fingerprint=FP,
            now=NOW,
        )


@pytest.mark.parametrize("url", (
    "https://user:pass@api.sportradar.com",
    "https://api.sportradar.com:443",
    "https://api.sportradar.com:444",
    "https://api.sportradar.com?api_key=secret",
))
def test_config_rejects_noncanonical_authority_or_query(url):
    with pytest.raises(ValueError, match="BASE_URL"):
        SportradarConfig(base_url=url)


@pytest.mark.parametrize("timeout", (
    True,
    float("nan"),
    float("inf"),
    0,
    30.0001,
))
def test_config_rejects_unsafe_timeout(timeout):
    with pytest.raises(ValueError, match="TIMEOUT"):
        SportradarConfig(timeout_seconds=timeout)


def test_tennis_en_us_is_supported_official_language():
    c = SportradarConfig(language_code="en_us")
    assert c.static_path(
        sport="tennis",
        feed="competitions",
    ) == "/tennis/trial/v3/en_us/competitions.json"


def test_soccer_sr1_is_supported_official_language():
    c = SportradarConfig(language_code="sr1")
    assert c.static_path(
        sport="football",
        feed="competitions",
    ) == "/soccer/trial/v4/sr1/competitions.json"


@pytest.mark.parametrize(("language", "sport"), (
    ("da", "tennis"),
    ("en_us", "football"),
))
def test_language_is_fail_closed_per_sport(language, sport):
    c = SportradarConfig(language_code=language)
    with pytest.raises(
        ValueError,
        match="UNSUPPORTED_SPORTRADAR_LANGUAGE_FOR_SPORT",
    ):
        c.static_path(sport=sport, feed="competitions")


@pytest.mark.parametrize("language", ("zz", "EN", "en-us", ""))
def test_config_rejects_unknown_or_noncanonical_language(language):
    with pytest.raises(ValueError, match="LANGUAGE"):
        SportradarConfig(language_code=language)


@pytest.mark.parametrize("generated_at", (
    "x",
    "2026-09-03",
    "2026-09-03T12:00:00",
))
def test_response_validator_rejects_invalid_or_naive_generated_at(generated_at):
    with pytest.raises(SportradarProviderResponseError):
        validate_sportradar_collection(
            {
                "generated_at": generated_at,
                "competitions": [],
            },
            collection_name="competitions",
        )


def test_response_validator_accepts_zulu_generated_at():
    env = validate_sportradar_collection(
        {
            "generated_at": "2026-09-03T12:00:00Z",
            "competitions": [],
        },
        collection_name="competitions",
    )
    assert env.generated_at == "2026-09-03T12:00:00Z"


@pytest.mark.parametrize("bad_id", (
    "sr:competition:evil",
    "sr:competition:0",
    "sr:competition:1/../../x",
))
def test_tennis_adapter_rejects_malformed_competition_id(bad_id):
    with pytest.raises(ValueError, match="COMPETITION_ID"):
        adapt_sportradar_tennis_competition(
            {
                "id": bad_id,
                "name": "X",
                "type": "singles",
                "gender": "men",
                "category": {
                    "id": "sr:category:3",
                    "name": "ATP",
                },
            }
        )


def test_tennis_adapter_rejects_malformed_category_id():
    with pytest.raises(ValueError, match="CATEGORY_ID"):
        adapt_sportradar_tennis_competition(
            {
                "id": "sr:competition:2591",
                "name": "X",
                "type": "singles",
                "gender": "men",
                "category": {
                    "id": "sr:category:evil",
                    "name": "ATP",
                },
            }
        )


@pytest.mark.parametrize("bad_id", (
    "sr:competition:evil",
    "sr:competition:0",
    "sr:competition:17?x=1",
))
def test_soccer_adapter_rejects_malformed_competition_id(bad_id):
    with pytest.raises(ValueError, match="COMPETITION_ID"):
        adapt_sportradar_soccer_competition(
            {
                "id": bad_id,
                "name": "X",
                "category": {
                    "id": "sr:category:1",
                    "name": "England",
                    "country_code": "ENG",
                },
            }
        )


def test_soccer_adapter_rejects_malformed_category_id():
    with pytest.raises(ValueError, match="CATEGORY_ID"):
        adapt_sportradar_soccer_competition(
            {
                "id": "sr:competition:17",
                "name": "X",
                "category": {
                    "id": "sr:category:evil",
                    "name": "England",
                    "country_code": "ENG",
                },
            }
        )


@pytest.mark.parametrize("contract_id", (
    "",
    "f" * 63,
    "g" * 64,
))
def test_catalog_rejects_invalid_contract_id_before_client_call(contract_id):
    client = FakeClient(
        {
            "generated_at": "2026-09-03T12:00:00+00:00",
            "competitions": [],
        }
    )
    with pytest.raises(ValueError, match="CONTRACT_ID"):
        ingest_sportradar_competitions(
            client=client,
            sport="tennis",
            request_contract_id=contract_id,
            path="/tennis/trial/v3/en/competitions.json",
        )
    assert client.calls == []


@pytest.mark.parametrize("path", (
    "/soccer/trial/v4/en/competitions.json",
    "/tennis/trial/v3/en/seasons.json",
    "/tennis/trial/v3/en/competitions.json?api_key=x",
))
def test_catalog_rejects_cross_sport_or_noncatalog_path_before_client_call(path):
    client = FakeClient(
        {
            "generated_at": "2026-09-03T12:00:00+00:00",
            "competitions": [],
        }
    )
    with pytest.raises(ValueError, match="PATH"):
        ingest_sportradar_competitions(
            client=client,
            sport="tennis",
            request_contract_id="f" * 64,
            path=path,
        )
    assert client.calls == []


def test_catalog_rejects_cross_sport_path_before_client_call():
    from unittest.mock import Mock
    client = Mock()
    with pytest.raises(ValueError, match="SPORT_PATH"):
        ingest_sportradar_competitions(
            client=client,
            sport="tennis",
            path="/soccer/trial/v4/en/competitions.json",
            request_contract_id="a" * 64,
        )
    client.get.assert_not_called()


@pytest.mark.parametrize("path", (
    "/tennis/trial/v3/en/competitions.json?api_key=x",
    "/tennis/trial/v3/en/seasons.json",
    "tennis/trial/v3/en/competitions.json",
))
def test_catalog_rejects_noncanonical_catalog_path_before_client_call(path):
    from unittest.mock import Mock
    client = Mock()
    with pytest.raises(ValueError, match="PATH"):
        ingest_sportradar_competitions(
            client=client,
            sport="tennis",
            path=path,
            request_contract_id="a" * 64,
        )
    client.get.assert_not_called()


@pytest.mark.parametrize("contract_id", (
    "",
    "x" * 64,
    "a" * 63,
    "a" * 65,
))
def test_catalog_rejects_invalid_contract_id_with_mock_before_client_call(contract_id):
    from unittest.mock import Mock
    client = Mock()
    with pytest.raises(ValueError, match="CONTRACT_ID"):
        ingest_sportradar_competitions(
            client=client,
            sport="tennis",
            path="/tennis/trial/v3/en/competitions.json",
            request_contract_id=contract_id,
        )
    client.get.assert_not_called()
