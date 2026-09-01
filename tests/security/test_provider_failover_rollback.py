from dataclasses import replace
import pytest
from app.security.provider_failover_rollback import ProviderFailoverRollbackPlan, RollbackEvidence


def plan(**kw):
    d = dict(
        version="MATRIX-FAILOVER-ROLLBACK-R2/provider-a__provider-b__shadow",
        primary_provider="provider-a",
        secondary_provider="provider-b",
        environment="SHADOW",
        minimum_primary_stability_seconds=300,
        minimum_reconciliation_samples=5,
        primary_rights_profile_version="rights-a-v1",
        secondary_rights_profile_version="rights-b-v1",
        schema_compatibility_contract_version="schema-v1",
        identity_reconciliation_contract_version="identity-v1",
        human_approval_policy_version="approval-v1",
    )
    d.update(kw); return ProviderFailoverRollbackPlan(**d)


def evidence(**kw):
    d = dict(
        primary_rights_pass=True, secondary_rights_pass=True,
        schema_compatible=True, identity_reconciled=True,
        consecutive_reconciliation_samples=5, primary_stability_seconds=300,
        human_approval_pass=True, drill_pass=True, drill_evidence_sha256="a"*64,
        recovery_backfill_complete=True, primary_watermark_caught_up=True,
        unreconciled_gap_count=0, data_loss_events=0, open_incident_count=0,
    )
    d.update(kw); return RollbackEvidence(**d)


def test_complete_failback_barrier_passes_only_with_every_gate():
    ok, reasons = plan().evaluate(evidence())
    assert ok and reasons == ()


def test_recovery_backfill_watermark_and_gap_barrier_are_mandatory():
    ok, reasons = plan().evaluate(evidence(recovery_backfill_complete=False, primary_watermark_caught_up=False, unreconciled_gap_count=1))
    assert not ok
    assert {"RECOVERY_BACKFILL_INCOMPLETE", "PRIMARY_WATERMARK_NOT_CAUGHT_UP", "UNRECONCILED_GAPS_PRESENT"} <= set(reasons)


def test_rights_schema_identity_human_drill_data_loss_and_incidents_fail_closed():
    ok, reasons = plan().evaluate(evidence(primary_rights_pass=False, secondary_rights_pass=False, schema_compatible=False, identity_reconciled=False, human_approval_pass=False, drill_pass=False, data_loss_events=1, open_incident_count=1))
    assert not ok and len(reasons) >= 8


def test_reconciliation_and_primary_stability_windows_are_mandatory():
    ok, reasons = plan().evaluate(evidence(consecutive_reconciliation_samples=4, primary_stability_seconds=299))
    assert not ok
    assert "RECONCILIATION_WINDOW_INSUFFICIENT" in reasons
    assert "PRIMARY_STABILITY_WINDOW_INSUFFICIENT" in reasons


def test_production_and_automatic_provider_switch_are_forbidden():
    with pytest.raises(ValueError, match="ENVIRONMENT_MUST_BE_STAGING_OR_SHADOW"):
        plan(environment="PRODUCTION", version="MATRIX-FAILOVER-ROLLBACK-R2/provider-a__provider-b__production")
    with pytest.raises(ValueError, match="AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN"):
        plan(automatic_switch_allowed=True)


def test_ordered_provider_pair_is_bound_into_version():
    with pytest.raises(ValueError, match="ROLLBACK_VERSION_IDENTITY_MISMATCH"):
        plan(primary_provider="provider-b", secondary_provider="provider-a")
    with pytest.raises(ValueError, match="PROVIDERS_MUST_DIFFER"):
        plan(primary_provider="provider-a", secondary_provider="provider-a", version="MATRIX-FAILOVER-ROLLBACK-R2/provider-a__provider-a__shadow")
