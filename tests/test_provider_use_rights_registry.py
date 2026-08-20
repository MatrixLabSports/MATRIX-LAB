from datetime import datetime, timezone

from app.core.provider_use_rights_registry import (
    SQLiteProviderUseRightsRegistry,
)


UTC = timezone.utc


def test_use_rights_manifest_is_manual_and_immutable(tmp_path):
    registry = SQLiteProviderUseRightsRegistry(
        tmp_path / "rights.db"
    )
    manifest = registry.build_manifest(
        sport="tennis",
        provider_key="provider-x",
        data_scope=("fixtures", "history"),
        allowed_purposes=("analysis",),
        jurisdiction_scope=("CO",),
        effective_at=datetime(2026, 8, 1, tzinfo=UTC),
        expires_at=None,
        terms_reference_sha256="a" * 64,
        manual_approval_id="LEGAL-001",
        status="APPROVED",
    )

    registry.register(manifest)
    replay = registry.register(manifest)

    assert replay.manifest_id == manifest.manifest_id
    assert registry.audit_integrity().ok is True


def test_cross_sport_rights_are_distinct(tmp_path):
    registry = SQLiteProviderUseRightsRegistry(
        tmp_path / "rights.db"
    )
    tennis = registry.build_manifest(
        sport="tennis",
        provider_key="provider-x",
        data_scope=("history",),
        allowed_purposes=("analysis",),
        jurisdiction_scope=("CO",),
        effective_at=datetime(2026, 8, 1, tzinfo=UTC),
        expires_at=None,
        terms_reference_sha256="a" * 64,
        manual_approval_id="LEGAL-T",
        status="APPROVED",
    )
    football = registry.build_manifest(
        sport="football",
        provider_key="provider-x",
        data_scope=("history",),
        allowed_purposes=("analysis",),
        jurisdiction_scope=("CO",),
        effective_at=datetime(2026, 8, 1, tzinfo=UTC),
        expires_at=None,
        terms_reference_sha256="a" * 64,
        manual_approval_id="LEGAL-F",
        status="APPROVED",
    )

    assert (
        tennis.manifest_fingerprint
        != football.manifest_fingerprint
    )
