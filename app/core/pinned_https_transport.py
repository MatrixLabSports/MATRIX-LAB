from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import json
import re
import socket
import ssl
from typing import Any, Callable, Mapping
from urllib.parse import urlencode, urlsplit

from app.core.governed_provider_http import MatrixPinnedHttpsTransport


class PinnedHttpStatusError(RuntimeError):
    pass


@dataclass(frozen=True)
class PinnedHttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes

    def raise_for_status(self) -> None:
        if self.status_code >= 300:
            raise PinnedHttpStatusError(
                f"HTTP_STATUS_{self.status_code}"
            )

    def json(self) -> Any:
        return json.loads(
            self.body.decode("utf-8")
        )


class StdlibPinnedHttpsTransport(
    MatrixPinnedHttpsTransport
):
    matrix_dns_pinning_capable = True
    matrix_environment_proxy_disabled = True
    matrix_tls_verification_required = True
    matrix_redirects_disabled = True
    matrix_minimum_tls_version = "TLSv1_2"
    matrix_header_canonicalization = True
    matrix_path_canonicalization = True

    def __init__(
        self,
        *,
        connector: Callable[
            ...,
            Any,
        ] = socket.create_connection,
        context_factory: Callable[
            [],
            ssl.SSLContext,
        ] = ssl.create_default_context,
        response_factory: Callable[
            [Any],
            Any,
        ] = http.client.HTTPResponse,
        max_response_bytes: int = 10_000_000,
    ) -> None:
        if (
            isinstance(
                max_response_bytes,
                bool,
            )
            or not isinstance(
                max_response_bytes,
                int,
            )
            or max_response_bytes <= 0
        ):
            raise ValueError(
                "INVALID_MAX_RESPONSE_BYTES"
            )

        self._connector = connector
        self._context_factory = (
            context_factory
        )
        self._response_factory = (
            response_factory
        )
        self.max_response_bytes = (
            max_response_bytes
        )
        self.production_default_transport = (
            connector
            is socket.create_connection
            and context_factory
            is ssl.create_default_context
            and response_factory
            is http.client.HTTPResponse
        )

    @staticmethod
    def _timeout(
        value: object,
    ) -> float:
        if (
            isinstance(
                value,
                bool,
            )
            or not isinstance(
                value,
                (
                    int,
                    float,
                ),
            )
            or value <= 0
            or value > 30
        ):
            raise ValueError(
                "BOUNDED_TIMEOUT_REQUIRED"
            )

        return float(
            value
        )

    @staticmethod
    def _headers(
        headers: object,
        *,
        original_host: str,
    ) -> dict[str, str]:
        token = re.compile(
            r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$"
        )

        if headers is None:
            items = ()
        elif isinstance(
            headers,
            Mapping,
        ):
            items = tuple(
                headers.items()
            )
        else:
            raise ValueError(
                "INVALID_HTTP_HEADERS"
            )

        result: dict[
            str,
            str,
        ] = {}
        seen: set[
            str
        ] = set()

        for (
            raw_key,
            raw_value,
        ) in items:
            if not isinstance(
                raw_key,
                str,
            ):
                raise ValueError(
                    "INVALID_HTTP_HEADER_NAME"
                )

            if not token.fullmatch(
                raw_key
            ):
                raise ValueError(
                    "INVALID_HTTP_HEADER_NAME"
                )

            lowered = (
                raw_key.lower()
            )

            if lowered == "host":
                raise ValueError(
                    "HOST_HEADER_OVERRIDE_FORBIDDEN"
                )

            if lowered in seen:
                raise ValueError(
                    "DUPLICATE_HTTP_HEADER"
                )

            if not isinstance(
                raw_value,
                str,
            ):
                raise ValueError(
                    "INVALID_HTTP_HEADER_VALUE"
                )

            if any(
                ord(char) < 32
                or ord(char) == 127
                for char
                in raw_value
            ):
                raise ValueError(
                    "INVALID_HTTP_HEADER_VALUE"
                )

            try:
                raw_value.encode(
                    "latin-1"
                )
            except UnicodeEncodeError as error:
                raise ValueError(
                    "INVALID_HTTP_HEADER_VALUE"
                ) from error

            canonical_name = "-".join(
                part[:1].upper()
                + part[1:].lower()
                for part
                in raw_key.split("-")
            )

            result[
                canonical_name
            ] = raw_value
            seen.add(
                lowered
            )

        result[
            "Host"
        ] = original_host
        result.setdefault(
            "Accept",
            "application/json",
        )
        result[
            "Connection"
        ] = "close"

        return result

    @staticmethod
    def _ip(
        resolved_ips: tuple[
            str,
            ...,
        ],
    ) -> str:
        if not resolved_ips:
            raise ValueError(
                "PINNED_RESOLUTION_REQUIRED"
            )

        values: list[
            str
        ] = []

        for raw in resolved_ips:
            try:
                address = (
                    ipaddress.ip_address(
                        raw
                    )
                )
            except ValueError as error:
                raise ValueError(
                    "INVALID_PINNED_IP"
                ) from error

            if not address.is_global:
                raise ValueError(
                    "NON_GLOBAL_PINNED_IP_FORBIDDEN"
                )

            values.append(
                str(
                    address
                )
            )

        return sorted(
            values
        )[0]

    @staticmethod
    def _target(
        *,
        url: str,
        params: object,
        original_host: str,
    ) -> str:
        parsed = urlsplit(
            url
        )

        if (
            parsed.scheme.lower()
            != "https"
        ):
            raise ValueError(
                "PINNED_HTTPS_REQUIRED"
            )

        if (
            parsed.hostname is None
            or parsed.hostname.lower()
            != original_host.lower()
        ):
            raise ValueError(
                "ORIGINAL_HOST_MISMATCH"
            )

        if parsed.port not in {
            None,
            443,
        }:
            raise ValueError(
                "HTTPS_PORT_443_REQUIRED"
            )

        if (
            parsed.username
            or parsed.password
        ):
            raise ValueError(
                "URL_USERINFO_FORBIDDEN"
            )

        if parsed.fragment:
            raise ValueError(
                "URL_FRAGMENT_FORBIDDEN"
            )

        if parsed.query:
            raise ValueError(
                "RAW_URL_QUERY_FORBIDDEN"
            )

        path = (
            parsed.path
            or "/"
        )

        try:
            path.encode(
                "ascii"
            )
        except UnicodeEncodeError as error:
            raise ValueError(
                "NON_CANONICAL_HTTP_PATH"
            ) from error

        if (
            not path.startswith("/")
            or "\\" in path
            or "%" in path
            or "//" in path
            or "?" in path
            or "#" in path
            or any(
                ord(char) < 32
                or ord(char) == 127
                for char
                in path
            )
        ):
            raise ValueError(
                "NON_CANONICAL_HTTP_PATH"
            )

        segments = (
            path.split(
                "/"
            )[1:]
        )

        if any(
            segment
            in {
                ".",
                "..",
            }
            for segment
            in segments
        ):
            raise ValueError(
                "NON_CANONICAL_HTTP_PATH"
            )

        if params is None:
            return path

        if isinstance(
            params,
            Mapping,
        ):
            items = list(
                params.items()
            )
        else:
            try:
                items = list(
                    params
                )
            except Exception as error:
                raise ValueError(
                    "INVALID_QUERY_PARAMS"
                ) from error

        query = urlencode(
            items,
            doseq=True,
            safe="",
        )

        return (
            path
            if not query
            else f"{path}?{query}"
        )

    def get_pinned(
        self,
        *,
        url: str,
        original_host: str,
        resolved_ips: tuple[
            str,
            ...,
        ],
        allow_redirects: bool,
        verify: bool,
        **kwargs: Any,
    ) -> PinnedHttpResponse:
        if allow_redirects is not False:
            raise ValueError(
                "HTTP_REDIRECTS_FORBIDDEN"
            )

        if verify is not True:
            raise ValueError(
                "TLS_VERIFICATION_MUST_REMAIN_ENABLED"
            )

        if (
            "proxies" in kwargs
            or "proxy" in kwargs
        ):
            raise ValueError(
                "EXPLICIT_PROXY_FORBIDDEN"
            )

        timeout = self._timeout(
            kwargs.pop(
                "timeout",
                None,
            )
        )
        headers = self._headers(
            kwargs.pop(
                "headers",
                None,
            ),
            original_host=(
                original_host
            ),
        )
        params = kwargs.pop(
            "params",
            None,
        )

        for internal_key in (
            "matrix_permit",
            "matrix_request_contract_id",
            "matrix_request_contract_fingerprint",
            "matrix_request_path",
            "matrix_request_parameter_names",
            "matrix_request_parameter_values_fingerprint",
            "matrix_request_secret_reference_fingerprint",
        ):
            kwargs.pop(
                internal_key,
                None,
            )

        if kwargs:
            raise ValueError(
                "UNSUPPORTED_PINNED_HTTP_OPTIONS"
            )

        target = self._target(
            url=url,
            params=params,
            original_host=(
                original_host
            ),
        )
        pinned_ip = self._ip(
            tuple(
                resolved_ips
            )
        )

        raw_socket = None
        tls_socket = None

        try:
            raw_socket = self._connector(
                (
                    pinned_ip,
                    443,
                ),
                timeout,
            )

            context = (
                self._context_factory()
            )
            context.minimum_version = (
                ssl.TLSVersion.TLSv1_2
            )
            context.check_hostname = True
            context.verify_mode = (
                ssl.CERT_REQUIRED
            )

            tls_socket = (
                context.wrap_socket(
                    raw_socket,
                    server_hostname=(
                        original_host
                    ),
                )
            )
            raw_socket = None

            setter = getattr(
                tls_socket,
                "settimeout",
                None,
            )

            if callable(
                setter
            ):
                setter(
                    timeout
                )
            elif (
                self.production_default_transport
            ):
                raise ValueError(
                    "READ_TIMEOUT_ENFORCEMENT_UNAVAILABLE"
                )

            lines = [
                f"GET {target} HTTP/1.1"
            ]

            for (
                key,
                value,
            ) in headers.items():
                lines.append(
                    f"{key}: {value}"
                )

            lines.extend(
                [
                    "",
                    "",
                ]
            )

            tls_socket.sendall(
                "\r\n".join(
                    lines
                ).encode(
                    "latin-1"
                )
            )

            response = (
                self._response_factory(
                    tls_socket
                )
            )
            response.begin()

            body = response.read(
                self.max_response_bytes
                + 1
            )

            if (
                len(body)
                > self.max_response_bytes
            ):
                raise ValueError(
                    "HTTP_RESPONSE_TOO_LARGE"
                )

            response_headers = {
                str(key): str(value)
                for (
                    key,
                    value,
                )
                in response.getheaders()
            }

            encoding = (
                response_headers.get(
                    "Content-Encoding"
                )
                or response_headers.get(
                    "content-encoding"
                )
            )

            if (
                encoding
                and encoding.lower()
                != "identity"
            ):
                raise ValueError(
                    "UNSUPPORTED_CONTENT_ENCODING"
                )

            return PinnedHttpResponse(
                status_code=int(
                    response.status
                ),
                headers=(
                    response_headers
                ),
                body=bytes(
                    body
                ),
            )
        finally:
            if (
                tls_socket
                is not None
            ):
                try:
                    tls_socket.close()
                except Exception:
                    pass

            if (
                raw_socket
                is not None
            ):
                try:
                    raw_socket.close()
                except Exception:
                    pass
