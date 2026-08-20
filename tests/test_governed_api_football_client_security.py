from pathlib import Path


def test_official_governed_client_has_no_requests_or_default_session():
    source = Path("app/providers/api_football/governed_client.py").read_text(encoding="utf-8-sig")
    assert "import requests" not in source
    assert "requests.Session" not in source
    assert "underlying_session" not in source
    assert "pinned_transport" in source


def test_governed_http_has_no_requests_dependency():
    source = Path("app/core/governed_provider_http.py").read_text(encoding="utf-8-sig")
    assert "import requests" not in source
    assert "requests." not in source
