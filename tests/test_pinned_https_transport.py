import ssl

import pytest

from app.core.pinned_https_transport import StdlibPinnedHttpsTransport


class FakeRawSocket:
    def close(self):
        pass


class FakeTlsSocket:
    def __init__(self):
        self.sent = b""

    def sendall(self, value):
        self.sent += value

    def close(self):
        pass


class FakeContext:
    def __init__(self):
        self.check_hostname = False
        self.verify_mode = None
        self.server_hostname = None
        self.tls = FakeTlsSocket()

    def wrap_socket(self, raw_socket, *, server_hostname):
        self.server_hostname = server_hostname
        return self.tls


class FakeResponse:
    status = 200

    def __init__(self, sock):
        self.sock = sock

    def begin(self):
        pass

    def read(self, limit):
        return b'{"ok": true}'

    def getheaders(self):
        return [("Content-Type", "application/json")]


def test_pinned_transport_uses_ip_for_socket_and_hostname_for_tls():
    context = FakeContext()
    calls = []

    def connector(address, timeout):
        calls.append((address, timeout))
        return FakeRawSocket()

    transport = StdlibPinnedHttpsTransport(
        connector=connector,
        context_factory=lambda: context,
        response_factory=FakeResponse,
    )

    response = transport.get_pinned(
        url="https://api.example.test/v3/fixtures",
        original_host="api.example.test",
        resolved_ips=("8.8.8.8",),
        allow_redirects=False,
        verify=True,
        timeout=5,
        params={"date": "2026-08-20"},
    )

    assert calls == [(("8.8.8.8", 443), 5.0)]
    assert context.server_hostname == "api.example.test"
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert b"Host: api.example.test" in context.tls.sent
    assert response.json() == {"ok": True}


@pytest.mark.parametrize(
    "extra, reason",
    [
        (
            {"allow_redirects": True, "verify": True, "timeout": 5},
            "HTTP_REDIRECTS_FORBIDDEN",
        ),
        (
            {"allow_redirects": False, "verify": False, "timeout": 5},
            "TLS_VERIFICATION_MUST_REMAIN_ENABLED",
        ),
        (
            {"allow_redirects": False, "verify": True, "timeout": 31},
            "BOUNDED_TIMEOUT_REQUIRED",
        ),
        (
            {
                "allow_redirects": False,
                "verify": True,
                "timeout": 5,
                "proxies": {},
            },
            "EXPLICIT_PROXY_FORBIDDEN",
        ),
    ],
)
def test_pinned_transport_fails_closed(extra, reason):
    transport = StdlibPinnedHttpsTransport(
        connector=lambda *args: FakeRawSocket(),
        context_factory=FakeContext,
        response_factory=FakeResponse,
    )

    with pytest.raises(ValueError, match=reason):
        transport.get_pinned(
            url="https://api.example.test/v3/fixtures",
            original_host="api.example.test",
            resolved_ips=("8.8.8.8",),
            **extra,
        )
