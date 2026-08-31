from datetime import datetime,timezone
import pytest
from matrix_elite.sre_governance import ErrorBudgetEvidence,ContinuityDrillEvidence,error_budget_gate,sre_continuity_gate
from matrix_elite.cicd_governance import CIRunEvidence,REQUIRED_GATES,ci_acceptance_gate
from matrix_elite.artifact_governance import ArtifactRecord,ActiveArtifactCatalog

UTC=timezone.utc;NOW=datetime(2026,8,29,tzinfo=UTC)
def continuity(**kw):
 d=dict(environment='staging',drill_completed_at=NOW,backup_manifest_sha256='a'*64,restore_evidence_sha256='b'*64,recovery_time_seconds=30,recovery_point_seconds=10,load_test_evidence_sha256='c'*64,chaos_test_evidence_sha256='d'*64,alerting_test_evidence_sha256='e'*64,telemetry_schema_sha256='f'*64,real_restore_executed=True,load_test_passed=True,chaos_test_passed=True,telemetry_validation_passed=True,real_alert_delivery_verified=True);d.update(kw);return ContinuityDrillEvidence(**d)
def ci(**kw):
 d=dict(commit_sha='a'*40,branch='main',completed_at=NOW,gates={g:True for g in REQUIRED_GATES},dependency_lock_sha256='a'*64,sbom_sha256='b'*64,build_artifact_sha256='c'*64,artifact_signature_evidence_sha256='d'*64,dependency_lock_verified=True,sbom_verified=True,artifact_signature_verified=True,main_protected=True,human_release_approved=True);d.update(kw);return CIRunEvidence(**d)


def test_error_budget_gate_requires_target_and_remaining_budget():
    good=ErrorBudgetEvidence('api','30d',10000,9995,.999)
    bad=ErrorBudgetEvidence('api','30d',10000,9980,.999)
    assert error_budget_gate(good) and not error_budget_gate(bad)


def test_sre_gate_requires_real_restore_and_alert_delivery():
    b=(ErrorBudgetEvidence('api','30d',10000,9995,.999),)
    assert sre_continuity_gate(continuity(),max_rto_seconds=60,max_rpo_seconds=30,error_budgets=b)['pass']
    assert not sre_continuity_gate(continuity(real_restore_executed=False),max_rto_seconds=60,max_rpo_seconds=30,error_budgets=b)['pass']
    assert not sre_continuity_gate(continuity(real_alert_delivery_verified=False),max_rto_seconds=60,max_rpo_seconds=30,error_budgets=b)['pass']


def test_sre_gate_blocks_rto_rpo_and_error_budget_breach():
    badb=(ErrorBudgetEvidence('api','30d',10000,9980,.999),)
    g=sre_continuity_gate(continuity(recovery_time_seconds=70,recovery_point_seconds=40),max_rto_seconds=60,max_rpo_seconds=30,error_budgets=badb)
    assert not g['pass'] and 'RTO_BREACH' in g['reasons'] and 'RPO_BREACH' in g['reasons'] and any(x.startswith('ERROR_BUDGET_EXHAUSTED') for x in g['reasons'])


def test_ci_gate_requires_every_declared_gate_on_exact_commit():
    e=ci();assert ci_acceptance_gate(e,expected_commit_sha='a'*40,production_release=True)['pass']
    badg={g:True for g in REQUIRED_GATES};del badg['sport_boundary']
    g=ci_acceptance_gate(ci(gates=badg),expected_commit_sha='a'*40,production_release=True)
    assert not g['pass'] and any(x.startswith('CI_GATES_MISSING') for x in g['reasons'])


def test_ci_gate_blocks_wrong_commit_or_failed_security():
    gates={g:True for g in REQUIRED_GATES};gates['security']=False
    g=ci_acceptance_gate(ci(gates=gates),expected_commit_sha='b'*40,production_release=False)
    assert not g['pass'] and 'CI_COMMIT_MISMATCH' in g['reasons'] and any('security' in x for x in g['reasons'])


def test_ci_gate_blocks_automatic_promotion_switch_and_wagering():
    g=ci_acceptance_gate(ci(automatic_model_promotion=True,automatic_provider_switch=True,automatic_wagering=True),expected_commit_sha='a'*40,production_release=False)
    assert not g['pass'] and len([x for x in g['reasons'] if 'AUTOMATIC_' in x])==3


def test_production_release_requires_human_approval():
    assert not ci_acceptance_gate(ci(human_release_approved=False),expected_commit_sha='a'*40,production_release=True)['pass']


def test_artifact_catalog_allows_only_one_active_artifact_per_role():
    c=ActiveArtifactCatalog();c.add_initial(ArtifactRecord('entry','r1.ps1','a'*64,'ACTIVE'))
    with pytest.raises(ValueError,match='ALREADY_EXISTS'):
        c.add_initial(ArtifactRecord('entry','r2.ps1','b'*64,'ACTIVE'))
    c.promote(ArtifactRecord('entry','r2.ps1','b'*64,'ACTIVE','a'*64))
    assert c.resolve_active('entry').sha256=='b'*64 and c.audit()['one_active_per_role']


def test_artifact_promotion_requires_exact_superseded_sha():
    c=ActiveArtifactCatalog();c.add_initial(ArtifactRecord('entry','r1','a'*64,'ACTIVE'))
    with pytest.raises(ValueError,match='SUPERSESSION_HASH_MISMATCH'):
        c.promote(ArtifactRecord('entry','r2','b'*64,'ACTIVE','c'*64))


def test_version_name_based_artifact_selection_is_forbidden():
    c=ActiveArtifactCatalog()
    with pytest.raises(ValueError,match='VERSION_NAME_BASED'):
        c.resolve_by_highest_version_name('entry')


def test_sre_gate_requires_load_chaos_and_telemetry_pass():
    b=(ErrorBudgetEvidence('api','30d',10000,9995,.999),)
    for field in ('load_test_passed','chaos_test_passed','telemetry_validation_passed'):
        g=sre_continuity_gate(continuity(**{field:False}),max_rto_seconds=60,max_rpo_seconds=30,error_budgets=b)
        assert not g['pass']


def test_ci_gate_requires_verified_lock_sbom_signature_and_main_protection():
    for field in ('dependency_lock_verified','sbom_verified','artifact_signature_verified','main_protected'):
        g=ci_acceptance_gate(ci(**{field:False}),expected_commit_sha='a'*40,production_release=False)
        assert not g['pass']
