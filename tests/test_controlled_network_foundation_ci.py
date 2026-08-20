from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_controlled_network_foundation_remains_fail_closed():
    transport = (
        ROOT
        / "app"
        / "core"
        / "pinned_https_transport.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    request_contract = (
        ROOT
        / "app"
        / "core"
        / "provider_request_contract.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    governed_request = (
        ROOT
        / "app"
        / "core"
        / "governed_provider_request.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    network_binding = (
        ROOT
        / "app"
        / "core"
        / "provider_network_binding.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    certification = (
        ROOT
        / "app"
        / "core"
        / "controlled_network_certification.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "socket.create_connection" in transport
    assert "server_hostname=original_host" in transport
    assert "ssl.CERT_REQUIRED" in transport
    assert "EXPLICIT_PROXY_FORBIDDEN" in transport
    assert "HTTP_REDIRECTS_FORBIDDEN" in transport

    assert (
        "SQLiteProviderRequestContractRegistry"
        in request_contract
    )
    assert (
        "UNAUTHORIZED_REQUEST_PARAMETER"
        in request_contract
    )

    assert (
        "JitSecretPinnedHttpsTransport"
        in governed_request
    )
    assert (
        "GovernedProviderHttpSession"
        not in governed_request
    )
    assert (
        "resolve_secret_runtime"
        in governed_request
    )

    assert (
        "BindingAuditPinnedHttpsTransport"
        in network_binding
    )
    assert (
        "network_binding_evidence_ids"
        in network_binding
    )

    assert (
        "TECHNICALLY_CERTIFIED_FAIL_CLOSED"
        in certification
    )
    assert (
        "real_provider_execution_authorized=False"
        in certification
    )
