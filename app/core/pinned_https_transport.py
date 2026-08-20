from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import json
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
        return json.loads(self.body.decode("utf-8"))


class StdlibPinnedHttpsTransport(MatrixPinnedHttpsTransport):
    matrix_dns_pinning_capable = True
    matrix_environment_proxy_disabled = True
    matrix_tls_verification_required = True
    matrix_redirects_disabled = True

    def __init__(
        self,
        *,
        connector: Callable[..., Any] = socket.create_connection,
        context_factory: Callable[[], ssl.SSLContext] = ssl.create_default_context,
        response_factory: Callable[[Any], Any] = http.client.HTTPResponse,
        max_response_bytes: int = 10_000_000,
    ) -> None:
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or max_response_bytes <= 0
        ):
            raise ValueError("INVALID_MAX_RESPONSE_BYTES")

        self._connector = connector
        self._context_factory = context_factory
        self._response_factory = response_factory
        self.max_response_bytes = max_response_bytes
        self.production_default_transport = (
            connector is socket.create_connection
            and context_factory is ssl.create_default_context
            and response_factory is http.client.HTTPResponse
        )

    @staticmethod
    def _timeout(value: object) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
            or value > 30
        ):
            raise ValueError("BOUNDED_TIMEOUT_REQUIRED")
        return float(value)

    @staticmethod
    def _headers(
        headers: object,
        *,
        original_host: str,
    ) -> dict[str, str]:
        if headers is None:
            result: dict[str, str] = {}
        elif isinstance(headers, Mapping):
            result = {}
            for key, value in headers.items():
                key_text = str(key)
                value_text = str(value)
                if (
                    "\r" in key_text
                    or "\n" in key_text
                    or "\r" in value_text
                    or "\n" in value_text
                ):
                    raise ValueError("INVALID_HTTP_HEADER")
                if key_text.lower() == "host":
                    raise ValueError("HOST_HEADER_OVERRIDE_FORBIDDEN")
                result[key_text] = value_text
        else:
            raise ValueError("INVALID_HTTP_HEADERS")

        result["Host"] = original_host
        result.setdefault("Accept", "application/json")
        result["Connection"] = "close"
        return result

    @staticmethod
    def _ip(resolved_ips: tuple[str, ...]) -> str:
        if not resolved_ips:
            raise ValueError("PINNED_RESOLUTION_REQUIRED")

        values: list[str] = []

        for raw in resolved_ips:
            try:
                address = ipaddress.ip_address(raw)
            except ValueError as error:
                raise ValueError("INVALID_PINNED_IP") from error

            if not address.is_global:
                raise ValueError("NON_GLOBAL_PINNED_IP_FORBIDDEN")

            values.append(str(address))

        return sorted(values)[0]

    @staticmethod
    def _target(
        *,
        url: str,
        params: object,
        original_host: str,
    ) -> str:
        parsed = urlsplit(url)

        if parsed.scheme.lower() != "https":
            raise ValueError("PINNED_HTTPS_REQUIRED")

        if (
            parsed.hostname is None
            or parsed.hostname.lower() != original_host.lower()
        ):
            raise ValueError("ORIGINAL_HOST_MISMATCH")

        if parsed.port not in {None, 443}:
            raise ValueError("HTTPS_PORT_443_REQUIRED")

        if parsed.username or parsed.password:
            raise ValueError("URL_USERINFO_FORBIDDEN")

        if parsed.fragment:
            raise ValueError("URL_FRAGMENT_FORBIDDEN")

        if parsed.query:
            raise ValueError("RAW_URL_QUERY_FORBIDDEN")

        path = parsed.path or "/"

        if params is None:
            return path

        if isinstance(params, Mapping):
            items = list(params.items())
        else:
            try:
                items = list(params)
            except Exception as error:
                raise ValueError("INVALID_QUERY_PARAMS") from error

        query = urlencode(items, doseq=True, safe="")
        return path if not query else f"{path}?{query}"

    def get_pinned(
        self,
        *,
        url: str,
        original_host: str,
        resolved_ips: tuple[str, ...],
        allow_redirects: bool,
        verify: bool,
        **kwargs: Any,
    ) -> PinnedHttpResponse:
        if allow_redirects is not False:
            raise ValueError("HTTP_REDIRECTS_FORBIDDEN")

        if verify is not True:
            raise ValueError("TLS_VERIFICATION_MUST_REMAIN_ENABLED")

        if "proxies" in kwargs or "proxy" in kwargs:
            raise ValueError("EXPLICIT_PROXY_FORBIDDEN")

        timeout = self._timeout(kwargs.pop("timeout", None))
        headers = self._headers(
            kwargs.pop("headers", None),
            original_host=original_host,
        )
        params = kwargs.pop("params", None)

        kwargs.pop("matrix_permit", None)
        kwargs.pop("matrix_request_contract_fingerprint", None)
        kwargs.pop("matrix_request_secret_reference_fingerprint", None)

        if kwargs:
            raise ValueError("UNSUPPORTED_PINNED_HTTP_OPTIONS")

        target = self._target(
            url=url,
            params=params,
            original_host=original_host,
        )
        pinned_ip = self._ip(tuple(resolved_ips))

        raw_socket = None
        tls_socket = None

        try:
            raw_socket = self._connector((pinned_ip, 443), timeout)

            context = self._context_factory()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED

            tls_socket = context.wrap_socket(
                raw_socket,
                server_hostname=original_host,
            )
            raw_socket = None

            lines = [f"GET {target} HTTP/1.1"]
            for key, value in headers.items():
                lines.append(f"{key}: {value}")
            lines.extend(["", ""])

            tls_socket.sendall(
                "\r\n".join(lines).encode("utf-8")
            )

            response = self._response_factory(tls_socket)
            response.begin()

            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise ValueError("HTTP_RESPONSE_TOO_LARGE")

            response_headers = {
                str(key): str(value)
                for key, value in response.getheaders()
            }

            encoding = (
                response_headers.get("Content-Encoding")
                or response_headers.get("content-encoding")
            )

            if encoding and encoding.lower() != "identity":
                raise ValueError("UNSUPPORTED_CONTENT_ENCODING")

            return PinnedHttpResponse(
                status_code=int(response.status),
                headers=response_headers,
                body=bytes(body),
            )
        finally:
            if tls_socket is not None:
                try:
                    tls_socket.close()
                except Exception:
                    pass

            if raw_socket is not None:
                try:
                    raw_socket.close()
                except Exception:
                    pass
