from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import json
import socket
from typing import Any, Callable, Iterable, Mapping


Resolver = Callable[[str, int], Iterable[object]]


def _json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(_json(value).encode()).hexdigest()


def _default_resolver(host: str, port: int):
    return socket.getaddrinfo(
        host,
        port,
        type=socket.SOCK_STREAM,
    )


def _extract_ip(item: object) -> str:
    if isinstance(item, str):
        return item
    if (
        isinstance(item, tuple)
        and len(item) >= 5
        and isinstance(item[4], tuple)
        and item[4]
    ):
        return str(item[4][0])
    raise ValueError("UNSUPPORTED_RESOLVER_RESULT")


@dataclass(frozen=True)
class DnsEgressDecision:
    status: str
    executable: bool
    host: str
    port: int
    resolved_ips: tuple[str, ...]
    reason_codes: tuple[str, ...]
    resolution_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-dns-egress-decision/1",
            "status": self.status,
            "executable": self.executable,
            "host": self.host,
            "port": self.port,
            "resolved_ips": list(self.resolved_ips),
            "reason_codes": list(self.reason_codes),
            "resolution_fingerprint": self.resolution_fingerprint,
            "checked_immediately_before_network_call": True,
            "connection_dns_pinning": False,
        }


def resolve_and_validate_provider_egress(
    *,
    host: str,
    port: int,
    resolver: Resolver | None = None,
    max_addresses: int = 16,
) -> DnsEgressDecision:
    if not isinstance(host, str) or not host.strip():
        raise ValueError("INVALID_HOST")
    if port != 443:
        raise ValueError("TLS_443_REQUIRED")
    if max_addresses < 1 or max_addresses > 64:
        raise ValueError("INVALID_MAX_ADDRESSES")

    host = host.strip().lower()
    resolver = resolver or _default_resolver
    reasons: list[str] = []

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        items: Iterable[object] = (host,)
    else:
        try:
            items = resolver(host, port)
        except Exception:
            items = ()
            reasons.append("DNS_RESOLUTION_FAILED")

    ips: list[str] = []

    for item in items:
        if len(ips) >= max_addresses:
            reasons.append("DNS_ADDRESS_LIMIT_EXCEEDED")
            break
        try:
            address = ipaddress.ip_address(_extract_ip(item))
        except Exception:
            reasons.append("INVALID_RESOLVED_ADDRESS")
            continue

        value = str(address)
        if value not in ips:
            ips.append(value)
        if not address.is_global:
            reasons.append("NON_GLOBAL_EGRESS_ADDRESS")

    if not ips:
        reasons.append("NO_RESOLVED_ADDRESSES")

    ips_tuple = tuple(sorted(ips))
    reasons_tuple = tuple(sorted(set(reasons)))
    status = "AUTHORIZED" if not reasons_tuple else "QUARANTINE"

    base = {
        "schema": "matrix.provider-dns-egress-decision/1",
        "status": status,
        "executable": status == "AUTHORIZED",
        "host": host,
        "port": port,
        "resolved_ips": list(ips_tuple),
        "reason_codes": list(reasons_tuple),
        "checked_immediately_before_network_call": True,
        "connection_dns_pinning": False,
    }

    return DnsEgressDecision(
        status=status,
        executable=status == "AUTHORIZED",
        host=host,
        port=port,
        resolved_ips=ips_tuple,
        reason_codes=reasons_tuple,
        resolution_fingerprint=_sha(base),
    )
