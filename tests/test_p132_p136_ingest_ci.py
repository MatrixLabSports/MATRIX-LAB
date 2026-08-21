
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_p132_p136_semantic_ci_boundary_is_wired():
    source = (
        ROOT
        / "scripts"
        / "matrix_ci_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "def _provider_response_ingest_boundary("
        in source
    )
    assert (
        "_provider_response_ingest_boundary(ROOT)"
        in source
    )


def test_p133_validation_precedes_fixture_domain_mapping():
    source = (
        ROOT
        / "app"
        / "providers"
        / "api_football"
        / "fixture_service.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    validation = source.index(
        "validate_api_football_response_envelope("
    )
    mapping = source.index(
        "adapt_api_football_fixture("
    )

    assert validation < mapping


def test_p136_offline_certification_has_no_network_client_surface():
    source = (
        ROOT
        / "app"
        / "providers"
        / "api_football"
        / "offline_ingest_certification.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for forbidden in (
        "socket.create_connection",
        "requests.",
        "urllib.",
        "get_pinned(",
        "build_governed_api_football_client(",
    ):
        assert forbidden not in source

    for required in (
        "OFFLINE_REPLAY",
        "zero_network_calls",
        "real_provider_execution_authorized=False",
        "automatic_provider_switch=False",
        "automatic_wagering=False",
    ):
        assert required in source
