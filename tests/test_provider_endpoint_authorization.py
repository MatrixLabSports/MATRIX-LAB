from datetime import datetime, timedelta, timezone

from app.core.provider_endpoint_authorization import (
    SQLiteProviderEndpointAuthorizationRegistry,
    build_provider_endpoint_manifest,
)


NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def _registry(tmp_path):
    registry = SQLiteProviderEndpointAuthorizationRegistry(
        tmp_path / "endpoint.db"
    )
    manifest = build_provider_endpoint_manifest(
        provider_key="api_football",
        sport="football",
        method="GET",
        endpoint_url="https://api.example.test/v3/fixtures",
        allowed_query_keys=("date", "league"),
        secret_reference_fingerprint="a" * 64,
        valid_from=NOW - timedelta(seconds=1),
    )
    registry.register(manifest)
    return registry, manifest


def test_exact_endpoint_contract_authorizes(tmp_path):
    registry, manifest = _registry(tmp_path)
    decision = registry.authorize_request(
        provider_key="api_football",
        sport="football",
        method="GET",
        endpoint_url="https://api.example.test/v3/fixtures",
        query_keys=("date",),
        secret_reference_fingerprint="a" * 64,
        as_of=NOW,
    )
    assert decision.status == "AUTHORIZED"
    assert decision.manifest_id == manifest.manifest_id
    assert registry.audit_integrity()


def test_wrong_path_sensitive_query_and_revocation_fail_closed(tmp_path):
    registry, manifest = _registry(tmp_path)

    wrong = registry.authorize_request(
        provider_key="api_football",
        sport="football",
        method="GET",
        endpoint_url="https://api.example.test/v3/teams",
        query_keys=(),
        secret_reference_fingerprint="a" * 64,
        as_of=NOW,
    )
    assert wrong.status == "QUARANTINE"

    sensitive = registry.authorize_request(
        provider_key="api_football",
        sport="football",
        method="GET",
        endpoint_url="https://api.example.test/v3/fixtures",
        query_keys=("token",),
        secret_reference_fingerprint="a" * 64,
        as_of=NOW,
    )
    assert sensitive.status == "QUARANTINE"

    registry.revoke(
        manifest_id=manifest.manifest_id,
        revoked_at=NOW,
        reason_code="manual_revoke",
    )

    revoked = registry.authorize_request(
        provider_key="api_football",
        sport="football",
        method="GET",
        endpoint_url="https://api.example.test/v3/fixtures",
        query_keys=("date",),
        secret_reference_fingerprint="a" * 64,
        as_of=NOW + timedelta(seconds=1),
    )
    assert revoked.status == "QUARANTINE"
    assert registry.audit_integrity()
