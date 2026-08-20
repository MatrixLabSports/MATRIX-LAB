from pathlib import Path


def test_ci_forbids_direct_legacy_http_boundary():
    source = Path(
        "scripts/matrix_ci_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "PROVIDER_HTTP_BOUNDARY_VIOLATION" in source
    assert "_provider_http_boundary(ROOT)" in source
    assert "governed_client.py" in source
    assert "DIRECT_REQUESTS_CALL" in source
    assert "UNAUTHORIZED_REQUESTS_SESSION" in source


def test_governed_client_requires_pinned_transport_and_has_no_requests_session():
    source = Path(
        "app/providers/api_football/governed_client.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "requests.Session()" not in source
    assert "import requests" not in source
    assert "pinned_transport" in source
    assert "MatrixPinnedHttpsTransport" in source
    assert "PINNED_HTTPS_TRANSPORT_REQUIRED" in source

    for forbidden in (
        "requests.get(",
        "requests.post(",
        "requests.put(",
        "requests.patch(",
        "requests.delete(",
        "requests.request(",
    ):
        assert forbidden not in source
