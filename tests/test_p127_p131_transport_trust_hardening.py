import pytest

from app.core.pinned_https_transport import (
    StdlibPinnedHttpsTransport,
)
from app.core.provider_connector_trust import (
    assess_pinned_transport_connector_trust,
)


@pytest.mark.parametrize(
    "header, reason",
    [
        (
            "Content-Length",
            "CONTENT_LENGTH_HEADER_FORBIDDEN",
        ),
        (
            "Transfer-Encoding",
            "TRANSFER_ENCODING_HEADER_FORBIDDEN",
        ),
        (
            "Connection",
            "HOP_BY_HOP_HEADER_FORBIDDEN",
        ),
        (
            "Upgrade",
            "HOP_BY_HOP_HEADER_FORBIDDEN",
        ),
    ],
)
def test_request_framing_and_hop_by_hop_headers_are_forbidden(
    header,
    reason,
):
    transport = (
        StdlibPinnedHttpsTransport()
    )

    with pytest.raises(
        ValueError,
        match=reason,
    ):
        transport._headers(
            {
                header: "x",
            },
            original_host=(
                "api.example.test"
            ),
        )


class EvilTransport(
    StdlibPinnedHttpsTransport
):
    def get_pinned(
        self,
        **kwargs,
    ):
        raise RuntimeError(
            "EVIL_OVERRIDE"
        )


def test_subclassed_transport_is_not_trusted_for_production():
    decision = (
        assess_pinned_transport_connector_trust(
            EvilTransport()
        )
    )

    assert (
        decision.trusted_for_production
        is False
    )
    assert (
        "EXACT_STDLIB_PINNED_TRANSPORT_REQUIRED"
        in decision.blockers
    )
