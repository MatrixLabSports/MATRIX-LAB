import pytest

from app.core.pinned_https_transport import (
    StdlibPinnedHttpsTransport,
)


class FakeRawSocket:
    def close(self):
        pass


class FakeTlsSocket:
    def sendall(self, value):
        pass

    def settimeout(self, value):
        pass

    def close(self):
        pass


class FakeContext:
    def __init__(self):
        self.minimum_version = None
        self.check_hostname = False
        self.verify_mode = None

    def wrap_socket(
        self,
        raw_socket,
        *,
        server_hostname,
    ):
        return FakeTlsSocket()


class Response:
    status = 200

    headers = []
    body = b"{}"

    def __init__(self, sock):
        self.sock = sock

    def begin(self):
        pass

    def read(self, limit):
        return self.body

    def getheaders(self):
        return list(
            self.headers
        )


def call(
    response_type,
    *,
    max_response_bytes=100,
):
    transport = (
        StdlibPinnedHttpsTransport(
            connector=(
                lambda *args: (
                    FakeRawSocket()
                )
            ),
            context_factory=(
                FakeContext
            ),
            response_factory=(
                response_type
            ),
            max_response_bytes=(
                max_response_bytes
            ),
        )
    )

    return transport.get_pinned(
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


def test_content_length_is_validated_exactly():
    class Exact(Response):
        headers = [
            (
                "Content-Length",
                "2",
            ),
        ]
        body = b"{}"

    result = call(
        Exact
    )

    assert (
        result.headers[
            "X-Matrix-Framing"
        ]
        == "content-length"
    )


def test_content_length_mismatch_fails_closed():
    class Mismatch(Response):
        headers = [
            (
                "Content-Length",
                "3",
            ),
        ]
        body = b"{}"

    with pytest.raises(
        ValueError,
        match="CONTENT_LENGTH_MISMATCH",
    ):
        call(
            Mismatch
        )


def test_content_length_and_transfer_encoding_conflict_is_rejected():
    class Conflict(Response):
        headers = [
            (
                "Content-Length",
                "2",
            ),
            (
                "Transfer-Encoding",
                "chunked",
            ),
        ]

    with pytest.raises(
        ValueError,
        match="HTTP_RESPONSE_FRAMING_CONFLICT",
    ):
        call(
            Conflict
        )


def test_unsupported_transfer_encoding_is_rejected():
    class Unsupported(Response):
        headers = [
            (
                "Transfer-Encoding",
                "gzip",
            ),
        ]

    with pytest.raises(
        ValueError,
        match="UNSUPPORTED_TRANSFER_ENCODING",
    ):
        call(
            Unsupported
        )


def test_chunked_framing_is_explicitly_allowed_and_bounded():
    class Chunked(Response):
        headers = [
            (
                "Transfer-Encoding",
                "chunked",
            ),
        ]
        body = b"{}"

    result = call(
        Chunked
    )

    assert (
        result.headers[
            "X-Matrix-Framing"
        ]
        == "chunked"
    )


def test_declared_oversized_content_length_is_rejected_before_acceptance():
    class Oversized(Response):
        headers = [
            (
                "Content-Length",
                "101",
            ),
        ]
        body = b"{}"

    with pytest.raises(
        ValueError,
        match="HTTP_RESPONSE_TOO_LARGE",
    ):
        call(
            Oversized,
            max_response_bytes=100,
        )
