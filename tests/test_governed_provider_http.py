from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.governed_provider_http import (
    GovernedProviderHttpSession,
    MatrixPinnedHttpsTransport,
    SQLiteProviderNetworkCallEvidenceStore,
)

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


class Authority:
    run_id = "run-1"
    mode = "PRODUCTION"

    def authorize(self, **kwargs):
        return SimpleNamespace(
            permit_id="1" * 64,
            provider_key="api_football",
            run_id="run-1",
            method="GET",
            endpoint_manifest_id="2" * 64,
            resolved_ips=("8.8.8.8",),
        )


class PermitStore:
    def __init__(self):
        self.used = []

    def consume(self, *, permit_id, consumed_at):
        self.used.append(permit_id)
        return {}


class Response:
    status_code = 200


class PinnedTransport(MatrixPinnedHttpsTransport):
    def __init__(self):
        self.calls = []

    def get_pinned(
        self,
        *,
        url,
        original_host,
        resolved_ips,
        allow_redirects,
        verify,
        **kwargs,
    ):
        assert original_host == "api.example.test"
        assert resolved_ips == ("8.8.8.8",)
        assert allow_redirects is False
        assert verify is True
        self.calls.append((url, resolved_ips, kwargs))
        return Response()


def _session(tmp_path):
    permits = PermitStore()
    transport = PinnedTransport()
    evidence = SQLiteProviderNetworkCallEvidenceStore(tmp_path / "calls.db")
    session = GovernedProviderHttpSession(
        authority=Authority(),
        network_permit_store=permits,
        call_evidence_store=evidence,
        pinned_transport=transport,
        clock=lambda: NOW,
    )
    return session, permits, transport, evidence


def test_exact_resolution_and_safe_flags_reach_pinned_transport(tmp_path):
    session, permits, transport, evidence = _session(tmp_path)
    response = session.get(
        "https://api.example.test/v3/fixtures",
        params={"date": "2026-08-20"},
    )
    assert response.status_code == 200
    assert permits.used == ["1" * 64]
    assert len(transport.calls) == 1
    assert evidence.audit_integrity()


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"allow_redirects": True}, "HTTP_REDIRECTS_FORBIDDEN"),
        ({"verify": False}, "TLS_VERIFICATION_MUST_REMAIN_ENABLED"),
        ({"proxies": {"https": "http://proxy.invalid"}}, "EXPLICIT_PROXY_FORBIDDEN"),
    ],
)
def test_redirect_tls_and_proxy_bypasses_fail_closed(tmp_path, kwargs, reason):
    session, _, _, _ = _session(tmp_path)
    with pytest.raises(ValueError, match=reason):
        session.get("https://api.example.test/v3/fixtures", **kwargs)


def test_non_pinned_transport_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="PINNED_HTTPS_TRANSPORT_REQUIRED"):
        GovernedProviderHttpSession(
            authority=Authority(),
            network_permit_store=PermitStore(),
            call_evidence_store=SQLiteProviderNetworkCallEvidenceStore(tmp_path / "calls.db"),
            pinned_transport=object(),
            clock=lambda: NOW,
        )
