from app.core.governed_provider_http import MatrixPinnedHttpsTransport
from app.core.governed_provider_request import JitSecretPinnedHttpsTransport
from app.core.secret_reference import build_secret_reference


class Inner(MatrixPinnedHttpsTransport):
    def __init__(self):
        self.headers = None

    def get_pinned(self, *, headers=None, **kwargs):
        self.headers = dict(headers or {})
        return "ok"


def test_secret_resolution_happens_only_inside_transport_call():
    reference = build_secret_reference(
        provider_key="api_football",
        environment_variable="MATRIX_TEST_API_KEY",
        secret_type="API_KEY",
    )

    calls = []
    inner = Inner()

    transport = JitSecretPinnedHttpsTransport(
        inner=inner,
        secret_reference=reference,
        auth_header_name="x-apisports-key",
        resolver=lambda ref: (
            calls.append(ref.reference_fingerprint)
            or "secret-value"
        ),
    )

    assert calls == []

    result = transport.get_pinned(
        url="https://api.example.test/v3/fixtures",
        original_host="api.example.test",
        resolved_ips=("8.8.8.8",),
        allow_redirects=False,
        verify=True,
        matrix_request_secret_reference_fingerprint=(
            reference.reference_fingerprint
        ),
    )

    assert result == "ok"
    assert calls == [reference.reference_fingerprint]
    assert inner.headers["x-apisports-key"] == "secret-value"
