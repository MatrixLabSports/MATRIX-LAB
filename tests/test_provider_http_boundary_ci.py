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


def test_governed_client_may_construct_session_but_not_call_requests_verbs():
    source = Path(
        "app/providers/api_football/governed_client.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "requests.Session()" in source

    for forbidden in (
        "requests.get(",
        "requests.post(",
        "requests.put(",
        "requests.patch(",
        "requests.delete(",
        "requests.request(",
    ):
        assert forbidden not in source
