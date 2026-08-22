from pathlib import Path


NEW_RUNTIME_FILES = (
    "app/core/platform_scope.py",
    "app/providers/api_football/live_service.py",
    "app/application/football/live_snapshot.py",
    "app/application/football/live_odds_movement.py",
    "app/application/football/live_decision_timing.py",
    "app/application/football/live_evidence.py",
    "app/application/football/private_live_runtime.py",
)


def test_c2_live_modules_have_no_direct_network_stack():
    combined = "\n".join(
        Path(path).read_text(
            encoding="utf-8-sig"
        )
        for path in NEW_RUNTIME_FILES
    )
    for forbidden in (
        "import requests",
        "from requests",
        "urllib.request",
        "http.client",
        "socket.create_connection",
    ):
        assert forbidden not in combined


def test_live_service_binds_p133_response_validation():
    source = Path(
        "app/providers/api_football/live_service.py"
    ).read_text(
        encoding="utf-8-sig"
    )
    assert (
        "validate_api_football_response_envelope"
        in source
    )
    assert source.count(
        "_validated_items("
    ) >= 4
    assert "API_FOOTBALL_KEY" not in source
    assert "resolve_secret_runtime" not in source
    runtime = Path(
        "app/application/football/private_live_runtime.py"
    ).read_text(
        encoding="utf-8-sig"
    )
    assert "GovernedProviderRequestClient" in runtime
    assert "GOVERNED_PROVIDER_REQUEST_CLIENT_REQUIRED" in runtime


def test_c2_runtime_cannot_authorize_money_or_provider():
    combined = "\n".join(
        Path(path).read_text(
            encoding="utf-8-sig"
        )
        for path in NEW_RUNTIME_FILES
    )
    assert "automatic_wagering=True" not in combined
    assert "automatic_provider_switch=True" not in combined
    assert "automatic_model_promotion=True" not in combined
    assert (
        "real_provider_execution_authorized=True"
        not in combined
    )
