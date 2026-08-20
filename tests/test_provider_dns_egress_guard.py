from app.core.provider_dns_egress_guard import (
    resolve_and_validate_provider_egress,
)


def test_global_resolution_authorizes():
    decision = resolve_and_validate_provider_egress(
        host="api.example.test",
        port=443,
        resolver=lambda host, port: ("8.8.8.8", "1.1.1.1"),
    )
    assert decision.status == "AUTHORIZED"


def test_private_loopback_and_resolution_failure_quarantine():
    private = resolve_and_validate_provider_egress(
        host="api.example.test",
        port=443,
        resolver=lambda host, port: ("10.0.0.1",),
    )
    loopback = resolve_and_validate_provider_egress(
        host="127.0.0.1",
        port=443,
    )

    def fail(host, port):
        raise OSError("synthetic")

    failed = resolve_and_validate_provider_egress(
        host="api.example.test",
        port=443,
        resolver=fail,
    )

    assert private.status == "QUARANTINE"
    assert loopback.status == "QUARANTINE"
    assert failed.status == "QUARANTINE"
