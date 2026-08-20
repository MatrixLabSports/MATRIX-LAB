from datetime import datetime, timezone
import sqlite3

from app.core.provider_bootstrap_probe import (
    SQLiteBootstrapProbePolicyRegistry,
    build_bootstrap_probe_policy,
)
from app.core.provider_preflight_gate import (
    SQLiteProviderPreflightEvidenceStore,
    authorize_and_consume_provider_preflight,
)
from app.core.provider_run_permit import (
    SQLiteProviderRunPermitStore,
)
from app.core.provider_use_rights_registry import (
    SQLiteProviderUseRightsRegistry,
)


UTC = timezone.utc


def setup_bootstrap(
    tmp_path,
):
    rights_registry = (
        SQLiteProviderUseRightsRegistry(
            tmp_path / "rights.db"
        )
    )

    rights = (
        rights_registry.build_manifest(
            sport="football",
            provider_key="provider-x",
            data_scope=(
                "history",
            ),
            allowed_purposes=(
                "analysis",
            ),
            jurisdiction_scope=(
                "CO",
            ),
            effective_at=datetime(
                2026,
                8,
                1,
                tzinfo=UTC,
            ),
            expires_at=None,
            terms_reference_sha256=(
                "a" * 64
            ),
            manual_approval_id=(
                "LEGAL-1"
            ),
            status="APPROVED",
        )
    )
    rights_registry.register(
        rights
    )

    policy_registry = (
        SQLiteBootstrapProbePolicyRegistry(
            tmp_path / "policy.db"
        )
    )
    policy = (
        build_bootstrap_probe_policy(
            sport="football",
            provider_key="provider-x",
            manual_approval_id=(
                "OPS-BOOT-1"
            ),
            max_items=3,
            max_requests=5,
        )
    )
    policy_registry.register(
        policy
    )

    permits = (
        SQLiteProviderRunPermitStore(
            tmp_path / "permit.db"
        )
    )

    permit = (
        permits.build_permit(
            run_id="run-boot-1",
            sport="football",
            provider_key="provider-x",
            mode="BOOTSTRAP_PROBE",
            queue_fingerprint=(
                "b" * 64
            ),
            scheduling_evidence_fingerprint=(
                "c" * 64
            ),
            rights_manifest_fingerprint=(
                rights
                .manifest_fingerprint
            ),
            bootstrap_policy_fingerprint=(
                policy
                .policy_fingerprint
            ),
            max_items=3,
            max_requests=5,
        )
    )
    permits.issue(
        permit
    )

    return (
        rights_registry,
        rights,
        policy_registry,
        policy,
        permits,
        permit,
    )


def test_bootstrap_preflight_executes_once_and_quarantines_data(
    tmp_path,
):
    (
        rights_registry,
        rights,
        policy_registry,
        policy,
        permits,
        permit,
    ) = setup_bootstrap(
        tmp_path
    )

    decision = (
        authorize_and_consume_provider_preflight(
            run_id="run-boot-1",
            sport="football",
            provider_key="provider-x",
            mode="BOOTSTRAP_PROBE",
            queue_fingerprint="b" * 64,
            permit_id=(
                permit.permit_id
            ),
            rights_manifest_fingerprint=(
                rights
                .manifest_fingerprint
            ),
            scheduling_evidence_fingerprint=(
                "c" * 64
            ),
            requested_data_scope=(
                "history",
            ),
            requested_purpose=(
                "analysis"
            ),
            requested_jurisdiction=(
                "CO"
            ),
            max_items=3,
            max_requests=5,
            rights_registry=(
                rights_registry
            ),
            provider_health_status=(
                "REVIEW_REQUIRED"
            ),
            bootstrap_policy_fingerprint=(
                policy
                .policy_fingerprint
            ),
            bootstrap_policy_registry=(
                policy_registry
            ),
            permit_store=permits,
            as_of=datetime(
                2026,
                8,
                2,
                tzinfo=UTC,
            ),
        )
    )

    assert (
        decision.status
        == "EXECUTE"
    )
    assert (
        decision.executable
        is True
    )
    assert (
        decision
        .downstream_quarantine_required
        is True
    )


def test_rights_scope_is_authoritative(
    tmp_path,
):
    (
        rights_registry,
        rights,
        policy_registry,
        policy,
        permits,
        permit,
    ) = setup_bootstrap(
        tmp_path
    )

    decision = (
        authorize_and_consume_provider_preflight(
            run_id="run-boot-1",
            sport="football",
            provider_key="provider-x",
            mode="BOOTSTRAP_PROBE",
            queue_fingerprint="b" * 64,
            permit_id=(
                permit.permit_id
            ),
            rights_manifest_fingerprint=(
                rights
                .manifest_fingerprint
            ),
            scheduling_evidence_fingerprint=(
                "c" * 64
            ),
            requested_data_scope=(
                "live_video",
            ),
            requested_purpose=(
                "analysis"
            ),
            requested_jurisdiction=(
                "CO"
            ),
            max_items=3,
            max_requests=5,
            rights_registry=(
                rights_registry
            ),
            provider_health_status=(
                "REVIEW_REQUIRED"
            ),
            bootstrap_policy_fingerprint=(
                policy
                .policy_fingerprint
            ),
            bootstrap_policy_registry=(
                policy_registry
            ),
            permit_store=permits,
            as_of=datetime(
                2026,
                8,
                2,
                tzinfo=UTC,
            ),
        )
    )

    assert (
        decision.status
        == "QUARANTINE"
    )
    assert any(
        reason.startswith(
            "RIGHTS:"
        )
        for reason
        in decision.reason_codes
    )


def test_preflight_evidence_rederives_and_audits(
    tmp_path,
):
    (
        rights_registry,
        rights,
        policy_registry,
        policy,
        permits,
        permit,
    ) = setup_bootstrap(
        tmp_path
    )

    decision = (
        authorize_and_consume_provider_preflight(
            run_id="run-boot-1",
            sport="football",
            provider_key="provider-x",
            mode="BOOTSTRAP_PROBE",
            queue_fingerprint="b" * 64,
            permit_id=(
                permit.permit_id
            ),
            rights_manifest_fingerprint=(
                rights
                .manifest_fingerprint
            ),
            scheduling_evidence_fingerprint=(
                "c" * 64
            ),
            requested_data_scope=(
                "history",
            ),
            requested_purpose=(
                "analysis"
            ),
            requested_jurisdiction=(
                "CO"
            ),
            max_items=3,
            max_requests=5,
            rights_registry=(
                rights_registry
            ),
            provider_health_status=(
                "REVIEW_REQUIRED"
            ),
            bootstrap_policy_fingerprint=(
                policy
                .policy_fingerprint
            ),
            bootstrap_policy_registry=(
                policy_registry
            ),
            permit_store=permits,
            as_of=datetime(
                2026,
                8,
                2,
                tzinfo=UTC,
            ),
        )
    )

    path = tmp_path / "preflight.db"
    store = (
        SQLiteProviderPreflightEvidenceStore(
            path
        )
    )

    store.record(
        decision
    )

    assert (
        store.audit_integrity().ok
        is True
    )

    with sqlite3.connect(
        path
    ) as connection:
        connection.execute(
            """
            UPDATE provider_preflight_evidence
            SET evidence_id = ?
            WHERE run_id = ?
            """,
            (
                "f" * 64,
                decision.run_id,
            ),
        )
        connection.commit()

    assert (
        store.audit_integrity().ok
        is False
    )
