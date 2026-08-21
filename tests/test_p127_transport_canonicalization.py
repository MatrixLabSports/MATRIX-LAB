import ssl

import pytest

from app.core.pinned_https_transport import (
    StdlibPinnedHttpsTransport,
)


class FakeRawSocket:
    def close(self):
        pass


class FakeTlsSocket:
    def __init__(self):
        self.sent = b""
        self.timeout = None

    def sendall(self, value):
        self.sent += value

    def settimeout(self, value):
        self.timeout = value

    def close(self):
        pass


class FakeContext:
    def __init__(self):
        self.minimum_version = None
        self.check_hostname = False
        self.verify_mode = None
        self.server_hostname = None
        self.tls = FakeTlsSocket()

    def wrap_socket(
        self,
        raw_socket,
        *,
        server_hostname,
    ):
        self.server_hostname = server_hostname
        return self.tls


class FakeResponse:
    status = 200

    def __init__(self, sock):
        self.sock = sock

    def begin(self):
        pass

    def read(self, limit):
        return b"{}"

    def getheaders(self):
        return [
            (
                "Content-Type",
                "application/json",
            ),
        ]


def build_transport():
    context = FakeContext()

    return (
        StdlibPinnedHttpsTransport(
            connector=(
                lambda *args: (
                    FakeRawSocket()
                )
            ),
            context_factory=(
                lambda: context
            ),
            response_factory=(
                FakeResponse
            ),
        ),
        context,
    )


def test_tls_12_minimum_and_read_timeout_are_explicit():
    transport, context = build_transport()

    transport.get_pinned(
        url=(
            "https://api.example.test/v3/fixtures"
        ),
        original_host=(
            "api.example.test"
        ),
        resolved_ips=(
            "8.8.8.8",
        ),
        allow_redirects=False,
        verify=True,
        timeout=5,
    )

    assert (
        context.minimum_version
        == ssl.TLSVersion.TLSv1_2
    )
    assert (
        context.tls.timeout
        == 5.0
    )


@pytest.mark.parametrize(
    "headers, reason",
    [
        (
            {
                "Bad Header": "x",
            },
            "INVALID_HTTP_HEADER_NAME",
        ),
        (
            {
                "X-Test": "ok",
                "x-test": "dup",
            },
            "DUPLICATE_HTTP_HEADER",
        ),
        (
            {
                "X-Test": "bad\nvalue",
            },
            "INVALID_HTTP_HEADER_VALUE",
        ),
        (
            {
                "host": "evil.test",
            },
            "HOST_HEADER_OVERRIDE_FORBIDDEN",
        ),
    ],
)
def test_header_canonicalization_fails_closed(
    headers,
    reason,
):
    transport, _ = build_transport()

    with pytest.raises(
        ValueError,
        match=reason,
    ):
        transport.get_pinned(
            url=(
                "https://api.example.test/v3/fixtures"
            ),
            original_host=(
                "api.example.test"
            ),
            resolved_ips=(
                "8.8.8.8",
            ),
            allow_redirects=False,
            verify=True,
            timeout=5,
            headers=headers,
        )


@pytest.mark.parametrize(
    "path",
    [
        "/v3//fixtures",
        "/v3/./fixtures",
        "/v3/../fixtures",
        "/v3/%2e/fixtures",
        "/v3\\fixtures",
    ],
)
def test_noncanonical_paths_are_rejected(
    path,
):
    transport, _ = build_transport()

    with pytest.raises(
        ValueError,
        match="NON_CANONICAL_HTTP_PATH",
    ):
        transport.get_pinned(
            url=(
                "https://api.example.test"
                + path
            ),
            original_host=(
                "api.example.test"
            ),
            resolved_ips=(
                "8.8.8.8",
            ),
            allow_redirects=False,
            verify=True,
            timeout=5,
        )
