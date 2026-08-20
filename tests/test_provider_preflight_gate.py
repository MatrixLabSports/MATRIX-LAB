from datetime import datetime, timezone

from app.core.provider_bootstrap_probe import (
    build_bootstrap_probe_policy,
)
from app.core.provider_preflight_gate import (
    authorize_and_consume_provider_preflight,
)
from app.core.provider_run_permit import (
    SQLiteProviderRunPermitStore,
)
from app.core.provider_use_rights_registry import (
    SQLiteProviderUseRightsRegistry,
)


UTC = timezone.utc


def rights(tmp_path, sport="football"):
    registry = SQLiteProviderUseRightsRegistry(
        tmp_path / f"rights-{sport}.db"
    )
    manifest = registry.build_manifest(
        sport=sport,
        provider_key="provider-x",
        data_scope=("history",),
        allowed_purposes=("analysis",),
        jurisdiction_scope=("CO",),
        effective_at=datetime(2026, 8, 1, tzinfo=UTC),
        expires_at=None,
        terms_reference_sha256="a" * 64,
        manual_approval_id="LEGAL-1",
        status="APPROVED",
    )
    registry.register(manifest)
    return registry, manifest


def test_bootstrap_preflight_executes_once_and_quarantines_data(
    tmp_path,
):
    rights_registry, manifest = rights(tmp_path)
    policy = build_bootstrap_probe_policy(
        sport="football",
        provider_key="provider-x",
        manual_approval_id="OPS-BOOT-1",
        max_items=3,
        max_requests=5,
    )
    permits = SQLiteProviderRunPermitStore(
        tmp_path / "permit.db"
    )
    permit = permits.build_permit(
        run_id="run-boot-1",
        sport="football",
        provider_key="provider-x",
        mode="BOOTSTRAP_PROBE",
        queue_fingerprint="b" * 64,
        scheduling_evidence_fingerprint="c" * 64,
        rights_manifest_fingerprint=manifest.manifest_fingerprint,
        bootstrap_policy_fingerprint=policy.policy_fingerprint,
        max_items=3,
        max_requests=5,
    )
    permits.issue(permit)

    decision = authorize_and_consume_provider_preflight(
        run_id="run-boot-1",
        sport="football",
        provider_key="provider-x",
        mode="BOOTSTRAP_PROBE",
        queue_fingerprint="b" * 64,
        permit_id=permit.permit_id,
        rights_manifest_fingerprint=manifest.manifest_fingerprint,
        rights_registry=rights_registry,
        provider_health_status="REVIEW_REQUIRED",
        bootstrap_policy=policy,
        permit_store=permits,
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert decision.status == "EXECUTE"
    assert decision.executable is True
    assert decision.downstream_quarantine_required is True


def test_production_requires_eligible_health(tmp_path):
    rights_registry, manifest = rights(tmp_path)
    permits = SQLiteProviderRunPermitStore(
        tmp_path / "permit.db"
    )
    permit = permits.build_permit(
        run_id="run-prod-1",
        sport="football",
        provider_key="provider-x",
        mode="PRODUCTION",
        queue_fingerprint="d" * 64,
        scheduling_evidence_fingerprint="e" * 64,
        rights_manifest_fingerprint=manifest.manifest_fingerprint,
        bootstrap_policy_fingerprint=None,
        max_items=10,
        max_requests=20,
    )
    permits.issue(permit)

    decision = authorize_and_consume_provider_preflight(
        run_id="run-prod-1",
        sport="football",
        provider_key="provider-x",
        mode="PRODUCTION",
        queue_fingerprint="d" * 64,
        permit_id=permit.permit_id,
        rights_manifest_fingerprint=manifest.manifest_fingerprint,
        rights_registry=rights_registry,
        provider_health_status="REVIEW_REQUIRED",
        bootstrap_policy=None,
        permit_store=permits,
        as_of=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert decision.status == "QUARANTINE"
    assert decision.executable is False
    assert "PRODUCTION_PROVIDER_NOT_ELIGIBLE" in decision.reason_codes
