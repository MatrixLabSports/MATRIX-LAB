import socket

import pytest

from app.core.pinned_https_transport import (
    StdlibPinnedHttpsTransport,
)
from app.core.provider_connector_trust import (
    assess_pinned_transport_connector_trust,
    require_trusted_production_connector,
)


def test_default_stdlib_transport_is_the_only_trusted_production_connector():
    transport = (
        StdlibPinnedHttpsTransport()
    )

    decision = (
        require_trusted_production_connector(
            transport
        )
    )

    assert (
        decision.trusted_for_production
        is True
    )
    assert (
        decision.minimum_tls_version
        == "TLSv1_2"
    )


def test_injected_connector_is_not_trusted_for_production():
    transport = (
        StdlibPinnedHttpsTransport(
            connector=(
                lambda *args: (
                    socket.socket()
                )
            ),
        )
    )

    decision = (
        assess_pinned_transport_connector_trust(
            transport
        )
    )

    assert (
        decision.trusted_for_production
        is False
    )
    assert (
        "DEFAULT_SOCKET_CONNECTOR_REQUIRED"
        in decision.blockers
    )

    with pytest.raises(
        ValueError,
        match="UNTRUSTED_PRODUCTION_CONNECTOR",
    ):
        require_trusted_production_connector(
            transport
        )
