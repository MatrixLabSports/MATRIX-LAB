from datetime import datetime, timedelta, timezone

import pytest

from app.security.provider_rights import (
    DataForm,
    DerivedDataRightsLineage,
    ProviderRightsAssessment,
    ProviderRightsBinding,
    ProviderRightsEvidence,
    ProviderRightsProfile,
    ProviderRightsReviewOutcome,
    ProviderRightsStatus,
    ProviderUseAction,
    ProviderUseRequest,
    RightsEvidenceStrength,
    TerminationTreatment,
    aggregate_provider_rights,
    evaluate_provider_rights,
)
from app.security.provider_rights_gate import (
    ProviderRightsGateInput,
    ProviderRightsGateResult,
    ProviderRightsGateStatus,
    evaluate_provider_rights_gate,
)
from app.security.provider_rights_inventory import (
    ProviderRightsInventoryRecord,
    ProviderRightsInventorySnapshot,
)
from app.security.provider_contract_monitor import (
    ContractMonitorStatus,
    monitor_provider_contract,
)

NOW = datetime(2026, 8, 19, 1, 30, tzinfo=timezone.utc)
SHA = "a" * 64
SHA2 = "b" * 64


def profile(**kwargs):
    values = dict(
        provider_id="provider-primary",
        profile_version="1.0",
        sports=("football", "tennis"),
        competition_scopes=("global-football", "atp"),
        territories=("CO", "US", "EU"),
        purpose_ids=("sports-research",),
        allow_ingest=True,
        allow_cache=True,
        allow_raw_storage=True,
        allow_historical_retention=True,
        allow_derived_data=True,
        allow_model_training=True,
        allow_internal_analytics=True,
        allow_internal_display=True,
        allow_customer_display=False,
        allow_public_redistribution=False,
        allow_customer_redistribution=False,
        allow_commercial_use=False,
        allow_backup=True,
        allow_export=False,
        allow_sublicense=False,
        max_raw_retention_days=365,
        max_cache_retention_minutes=60,
        attribution_required=True,
        attribution_reference="provider-attribution-v1",
        termination_treatment=TerminationTreatment.DELETE_RAW_RETAIN_DERIVED,
    )
    values.update(kwargs)
    return ProviderRightsProfile(**values)


def evidence(p=None, **kwargs):
    p = p or profile()
    values = dict(
        evidence_id="rights-001",
        provider_id=p.provider_id,
        profile_fingerprint=p.fingerprint,
        source_reference="contract:provider-primary:2026",
        terms_sha256=SHA,
        reviewer_role="legal-data-rights-reviewer",
        reviewed_at=NOW - timedelta(days=10),
        valid_from=NOW - timedelta(days=9),
        valid_until=NOW + timedelta(days=180),
        outcome=ProviderRightsReviewOutcome.APPROVED_FOR_GOVERNED_USE,
        evidence_strength=RightsEvidenceStrength.CONTRACTUAL,
        revoked=False,
        independent_review_reference="review-legal-001",
    )
    values.update(kwargs)
    return ProviderRightsEvidence(**values)


def request(**kwargs):
    values = dict(
        request_id="use-001",
        provider_id="provider-primary",
        purpose_id="sports-research",
        sport="football",
        competition_scope="global-football",
        territory="CO",
        action=ProviderUseAction.INTERNAL_ANALYTICS,
        data_form=DataForm.RAW,
        requested_raw_retention_days=None,
        requested_cache_retention_minutes=None,
        attribution_planned=True,
        requested_at=NOW,
        commercial_context=False,
    )
    values.update(kwargs)
    return ProviderUseRequest(**values)


def assessment(status=ProviderRightsStatus.PASS, reasons=()):
    return ProviderRightsAssessment(status, reasons, SHA, SHA2)


def test_profile_fingerprint_is_stable():
    assert profile().fingerprint == profile().fingerprint
    assert len(profile().fingerprint) == 64


def test_profile_requires_provider_id():
    with pytest.raises(ValueError):
        profile(provider_id=" ")


def test_profile_rejects_duplicate_sport():
    with pytest.raises(ValueError):
        profile(sports=("football", "football"))


def test_profile_requires_territory():
    with pytest.raises(ValueError):
        profile(territories=())


def test_profile_requires_purpose():
    with pytest.raises(ValueError):
        profile(purpose_ids=())


def test_profile_rejects_negative_raw_retention():
    with pytest.raises(ValueError):
        profile(max_raw_retention_days=-1)


def test_profile_rejects_bool_as_retention_integer():
    with pytest.raises(TypeError):
        profile(max_raw_retention_days=True)


def test_historical_right_requires_raw_storage_right():
    with pytest.raises(ValueError):
        profile(allow_raw_storage=False, allow_historical_retention=True)


def test_model_training_requires_derivative_right():
    with pytest.raises(ValueError):
        profile(allow_derived_data=False, allow_model_training=True)


def test_customer_display_requires_internal_display():
    with pytest.raises(ValueError):
        profile(allow_internal_display=False, allow_customer_display=True)


def test_public_redistribution_requires_customer_display():
    with pytest.raises(ValueError):
        profile(allow_customer_display=False, allow_public_redistribution=True)


def test_sublicense_requires_customer_redistribution():
    with pytest.raises(ValueError):
        profile(allow_customer_display=True, allow_customer_redistribution=False, allow_sublicense=True)


def test_attribution_reference_required():
    with pytest.raises(ValueError):
        profile(attribution_required=True, attribution_reference=None)


def test_evidence_rejects_bad_sha():
    p = profile()
    with pytest.raises(ValueError):
        evidence(p, terms_sha256="bad")


def test_contractual_evidence_requires_independent_review_reference():
    p = profile()
    with pytest.raises(ValueError):
        evidence(p, independent_review_reference=None)


def test_evidence_rejects_non_aware_datetime():
    p = profile()
    with pytest.raises(ValueError):
        evidence(p, reviewed_at=datetime(2026, 8, 1))


def test_evidence_requires_positive_validity_window():
    p = profile()
    with pytest.raises(ValueError):
        evidence(p, valid_from=NOW, valid_until=NOW)


def test_request_rejects_negative_cache_retention():
    with pytest.raises(ValueError):
        request(requested_cache_retention_minutes=-1)


def test_exact_internal_use_passes():
    p = profile()
    result = evaluate_provider_rights(p, evidence(p), request(), now=NOW)
    assert result.status is ProviderRightsStatus.PASS
    assert result.legal_rights_certified is False


@pytest.mark.parametrize(
    "req,reason",
    [
        (request(provider_id="other"), "PROVIDER_PROFILE_MISMATCH"),
        (request(purpose_id="marketing"), "PURPOSE_NOT_AUTHORIZED_BY_PROVIDER_RIGHTS"),
        (request(sport="basketball"), "SPORT_NOT_AUTHORIZED_BY_PROVIDER_RIGHTS"),
        (request(competition_scope="serie-a"), "COMPETITION_NOT_AUTHORIZED_BY_PROVIDER_RIGHTS"),
        (request(territory="BR"), "TERRITORY_NOT_AUTHORIZED_BY_PROVIDER_RIGHTS"),
    ],
)
def test_scope_mismatches_fail_closed(req, reason):
    p = profile()
    result = evaluate_provider_rights(p, evidence(p), req, now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert reason in result.reasons


def test_unauthorized_action_blocks():
    p = profile(allow_export=False)
    result = evaluate_provider_rights(p, evidence(p), request(action=ProviderUseAction.EXPORT), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert "ACTION_NOT_AUTHORIZED:EXPORT" in result.reasons


def test_commercial_context_requires_commercial_right():
    p = profile(allow_commercial_use=False)
    result = evaluate_provider_rights(p, evidence(p), request(commercial_context=True), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert "COMMERCIAL_CONTEXT_NOT_AUTHORIZED" in result.reasons


def test_raw_retention_limit_enforced():
    p = profile(max_raw_retention_days=30)
    result = evaluate_provider_rights(p, evidence(p), request(requested_raw_retention_days=31), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert "RAW_RETENTION_EXCEEDS_PROVIDER_LIMIT" in result.reasons


def test_cache_retention_limit_enforced():
    p = profile(max_cache_retention_minutes=10)
    result = evaluate_provider_rights(p, evidence(p), request(requested_cache_retention_minutes=11), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert "CACHE_RETENTION_EXCEEDS_PROVIDER_LIMIT" in result.reasons


def test_required_attribution_is_enforced():
    p = profile(attribution_required=True)
    result = evaluate_provider_rights(p, evidence(p), request(attribution_planned=False), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert "REQUIRED_ATTRIBUTION_NOT_PLANNED" in result.reasons


def test_missing_evidence_blocks():
    p = profile()
    result = evaluate_provider_rights(p, None, request(), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert "MISSING_PROVIDER_RIGHTS_EVIDENCE" in result.reasons


def test_evidence_provider_mismatch_blocks():
    p = profile()
    ev = evidence(p, provider_id="other")
    result = evaluate_provider_rights(p, ev, request(), now=NOW)
    assert "RIGHTS_EVIDENCE_PROVIDER_MISMATCH" in result.reasons


def test_evidence_profile_mismatch_blocks():
    p = profile()
    other = profile(profile_version="2.0")
    ev = evidence(p, profile_fingerprint=other.fingerprint)
    result = evaluate_provider_rights(p, ev, request(), now=NOW)
    assert "RIGHTS_EVIDENCE_PROFILE_MISMATCH" in result.reasons


def test_future_evidence_blocks():
    p = profile()
    ev = evidence(p, valid_from=NOW + timedelta(days=1), valid_until=NOW + timedelta(days=30))
    result = evaluate_provider_rights(p, ev, request(), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert "FUTURE_OR_NOT_YET_VALID_RIGHTS_EVIDENCE" in result.reasons


def test_expired_evidence_blocks():
    p = profile()
    ev = evidence(
        p,
        reviewed_at=NOW - timedelta(days=40),
        valid_from=NOW - timedelta(days=30),
        valid_until=NOW,
    )
    result = evaluate_provider_rights(p, ev, request(), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert "EXPIRED_PROVIDER_RIGHTS_EVIDENCE" in result.reasons


def test_revoked_evidence_blocks():
    p = profile()
    result = evaluate_provider_rights(p, evidence(p, revoked=True), request(), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK
    assert "REVOKED_PROVIDER_RIGHTS_EVIDENCE" in result.reasons


def test_rejected_evidence_blocks():
    p = profile()
    result = evaluate_provider_rights(
        p,
        evidence(p, outcome=ProviderRightsReviewOutcome.REJECTED),
        request(),
        now=NOW,
    )
    assert result.status is ProviderRightsStatus.BLOCK


def test_review_required_is_watch():
    p = profile()
    result = evaluate_provider_rights(
        p,
        evidence(p, outcome=ProviderRightsReviewOutcome.REVIEW_REQUIRED),
        request(),
        now=NOW,
    )
    assert result.status is ProviderRightsStatus.WATCH
    assert "PROVIDER_RIGHTS_REVIEW_REQUIRED" in result.reasons


def test_unknown_evidence_strength_blocks():
    p = profile()
    ev = evidence(
        p,
        evidence_strength=RightsEvidenceStrength.UNKNOWN,
        independent_review_reference=None,
    )
    result = evaluate_provider_rights(p, ev, request(), now=NOW)
    assert result.status is ProviderRightsStatus.BLOCK


def test_expiring_rights_is_watch():
    p = profile()
    ev = evidence(p, valid_until=NOW + timedelta(days=5))
    result = evaluate_provider_rights(p, ev, request(), now=NOW, contract_warning_days=30)
    assert result.status is ProviderRightsStatus.WATCH
    assert "PROVIDER_RIGHTS_EXPIRING_SOON" in result.reasons


def test_public_terms_for_customer_display_requires_review_and_is_watch():
    p = profile(allow_customer_display=True)
    ev = evidence(
        p,
        evidence_strength=RightsEvidenceStrength.PUBLIC_TERMS_REVIEWED,
        independent_review_reference="legal-review-public-terms",
    )
    result = evaluate_provider_rights(
        p,
        ev,
        request(action=ProviderUseAction.DISPLAY_CUSTOMER),
        now=NOW,
    )
    assert result.status is ProviderRightsStatus.WATCH
    assert "HIGH_RISK_USE_REQUIRES_CONTRACTUAL_EVIDENCE_REVIEW" in result.reasons


def test_contractual_customer_display_can_pass_when_explicitly_allowed():
    p = profile(allow_customer_display=True)
    result = evaluate_provider_rights(
        p,
        evidence(p),
        request(action=ProviderUseAction.DISPLAY_CUSTOMER),
        now=NOW,
    )
    assert result.status is ProviderRightsStatus.PASS


def test_public_redistribution_blocks_without_explicit_right():
    p = profile(allow_customer_display=True, allow_public_redistribution=False)
    result = evaluate_provider_rights(
        p,
        evidence(p),
        request(action=ProviderUseAction.REDISTRIBUTE_PUBLIC),
        now=NOW,
    )
    assert result.status is ProviderRightsStatus.BLOCK


def test_training_blocks_without_model_training_right():
    p = profile(allow_model_training=False)
    result = evaluate_provider_rights(
        p,
        evidence(p),
        request(action=ProviderUseAction.TRAIN_MODEL),
        now=NOW,
    )
    assert result.status is ProviderRightsStatus.BLOCK


def test_assessment_cannot_self_certify_legal_rights():
    with pytest.raises(ValueError):
        ProviderRightsAssessment(ProviderRightsStatus.PASS, (), SHA, SHA2, True)


def binding(provider="provider-primary", source="raw-asset-1", bound_at=NOW - timedelta(hours=2)):
    return ProviderRightsBinding(provider, source, SHA, SHA2, bound_at)


def test_rights_binding_fingerprint_is_stable():
    assert binding().fingerprint == binding().fingerprint


def test_rights_binding_requires_sha():
    with pytest.raises(ValueError):
        ProviderRightsBinding("p", "a", "bad", SHA2, NOW)


def test_derived_lineage_requires_source_binding():
    with pytest.raises(ValueError):
        DerivedDataRightsLineage("derived", (), "transform-v1", NOW)


def test_derived_lineage_rejects_duplicate_provider_source_binding():
    b = binding()
    with pytest.raises(ValueError):
        DerivedDataRightsLineage("derived", (b, b), "transform-v1", NOW)


def test_derived_lineage_rejects_future_binding():
    with pytest.raises(ValueError):
        DerivedDataRightsLineage("derived", (binding(bound_at=NOW + timedelta(seconds=1)),), "transform-v1", NOW)


def test_derived_lineage_multi_provider_is_hashable_and_stable():
    lineage = DerivedDataRightsLineage(
        "derived",
        (binding(), binding(provider="provider-secondary", source="raw-asset-2")),
        "feature-pipeline-v19",
        NOW,
    )
    assert len(lineage.fingerprint) == 64


def test_multi_provider_aggregate_uses_weakest_status_block():
    result = aggregate_provider_rights((assessment(), assessment(ProviderRightsStatus.BLOCK, ("NO_RIGHT",))))
    assert result.status is ProviderRightsStatus.BLOCK
    assert any("NO_RIGHT" in reason for reason in result.reasons)


def test_multi_provider_aggregate_uses_weakest_status_watch():
    result = aggregate_provider_rights((assessment(), assessment(ProviderRightsStatus.WATCH, ("EXPIRING",))))
    assert result.status is ProviderRightsStatus.WATCH


def test_multi_provider_aggregate_passes_only_if_all_pass():
    result = aggregate_provider_rights((assessment(), assessment()))
    assert result.status is ProviderRightsStatus.PASS


def test_multi_provider_aggregate_rejects_empty_input():
    with pytest.raises(ValueError):
        aggregate_provider_rights(())


def inventory_record(**kwargs):
    p = kwargs.pop("p", profile())
    ev = kwargs.pop("ev", evidence(p))
    values = dict(
        provider_id=p.provider_id,
        profile=p,
        evidence=ev,
        dataset_references=("fixtures", "odds"),
        owner="data-governance",
        recorded_at=NOW,
    )
    values.update(kwargs)
    return ProviderRightsInventoryRecord(**values)


def test_inventory_record_binds_exact_profile():
    rec = inventory_record()
    assert len(rec.fingerprint) == 64


def test_inventory_record_rejects_provider_mismatch():
    with pytest.raises(ValueError):
        inventory_record(provider_id="other")


def test_inventory_record_rejects_profile_evidence_mismatch():
    p = profile()
    p2 = profile(profile_version="2.0")
    ev = evidence(p, profile_fingerprint=p2.fingerprint)
    with pytest.raises(ValueError):
        inventory_record(p=p, ev=ev)


def test_inventory_record_rejects_duplicate_dataset_reference():
    with pytest.raises(ValueError):
        inventory_record(dataset_references=("fixtures", "fixtures"))


def test_inventory_snapshot_rejects_duplicate_provider_version():
    rec = inventory_record()
    rec2 = ProviderRightsInventoryRecord(
        rec.provider_id,
        rec.profile,
        ProviderRightsEvidence(
            "rights-002",
            rec.evidence.provider_id,
            rec.evidence.profile_fingerprint,
            rec.evidence.source_reference,
            rec.evidence.terms_sha256,
            rec.evidence.reviewer_role,
            rec.evidence.reviewed_at,
            rec.evidence.valid_from,
            rec.evidence.valid_until,
            rec.evidence.outcome,
            rec.evidence.evidence_strength,
            rec.evidence.revoked,
            rec.evidence.independent_review_reference,
        ),
        ("other",),
        "owner",
        NOW,
    )
    with pytest.raises(ValueError):
        ProviderRightsInventorySnapshot("snap", (rec, rec2), NOW, "v19")


def test_inventory_snapshot_valid():
    snap = ProviderRightsInventorySnapshot("snap", (inventory_record(),), NOW, "v19")
    assert len(snap.fingerprint) == 64


def test_contract_monitor_healthy():
    p = profile()
    result = monitor_provider_contract(evidence(p), now=NOW, warning_days=30)
    assert result.status is ContractMonitorStatus.HEALTHY


def test_contract_monitor_warns_before_expiry_without_renewal():
    p = profile()
    ev = evidence(p, valid_until=NOW + timedelta(days=10))
    result = monitor_provider_contract(ev, now=NOW, warning_days=30)
    assert result.status is ContractMonitorStatus.WATCH


def test_contract_monitor_allows_verified_renewal_to_remove_expiry_warning():
    p = profile()
    ev = evidence(p, valid_until=NOW + timedelta(days=10))
    result = monitor_provider_contract(ev, now=NOW, warning_days=30, renewal_verified=True)
    assert result.status is ContractMonitorStatus.HEALTHY


def test_contract_monitor_expired_blocks():
    p = profile()
    ev = evidence(
        p,
        reviewed_at=NOW - timedelta(days=30),
        valid_from=NOW - timedelta(days=20),
        valid_until=NOW - timedelta(seconds=1),
    )
    result = monitor_provider_contract(ev, now=NOW, warning_days=30)
    assert result.status is ContractMonitorStatus.BLOCK


def test_contract_monitor_revoked_blocks():
    p = profile()
    result = monitor_provider_contract(evidence(p, revoked=True), now=NOW, warning_days=30)
    assert result.status is ContractMonitorStatus.BLOCK


def gate_input(**kwargs):
    values = dict(
        acquisition=assessment(),
        storage=assessment(),
        analytics_or_training=assessment(),
        display_or_distribution=assessment(),
        termination_plan_verified=True,
        attribution_control_verified=True,
        provider_inventory_verified=True,
        independent_legal_review_reference="provider-rights-review-001",
    )
    values.update(kwargs)
    return ProviderRightsGateInput(**values)


def test_provider_rights_gate_passes_complete_evidence():
    result = evaluate_provider_rights_gate(gate_input())
    assert result.status is ProviderRightsGateStatus.PASS
    assert result.eligible_for_provider_integration_review is True
    assert result.legal_rights_certified is False


def test_provider_rights_gate_blocks_any_stage_block():
    result = evaluate_provider_rights_gate(
        gate_input(storage=assessment(ProviderRightsStatus.BLOCK, ("RAW_STORAGE_NOT_ALLOWED",)))
    )
    assert result.status is ProviderRightsGateStatus.BLOCK
    assert "STORAGE:RAW_STORAGE_NOT_ALLOWED" in result.reasons


def test_provider_rights_gate_watch_propagates():
    result = evaluate_provider_rights_gate(
        gate_input(display_or_distribution=assessment(ProviderRightsStatus.WATCH, ("REVIEW",)))
    )
    assert result.status is ProviderRightsGateStatus.WATCH


def test_provider_rights_gate_requires_termination_plan():
    result = evaluate_provider_rights_gate(gate_input(termination_plan_verified=False))
    assert result.status is ProviderRightsGateStatus.BLOCK
    assert "PROVIDER_TERMINATION_PLAN_NOT_VERIFIED" in result.reasons


def test_provider_rights_gate_requires_attribution_control():
    result = evaluate_provider_rights_gate(gate_input(attribution_control_verified=False))
    assert result.status is ProviderRightsGateStatus.BLOCK


def test_provider_rights_gate_requires_provider_inventory():
    result = evaluate_provider_rights_gate(gate_input(provider_inventory_verified=False))
    assert result.status is ProviderRightsGateStatus.BLOCK


def test_provider_rights_gate_without_independent_review_is_watch():
    result = evaluate_provider_rights_gate(gate_input(independent_legal_review_reference=None))
    assert result.status is ProviderRightsGateStatus.WATCH
    assert result.eligible_for_provider_integration_review is True


def test_provider_rights_gate_cannot_certify_legal_rights():
    with pytest.raises(ValueError):
        ProviderRightsGateResult(ProviderRightsGateStatus.PASS, (), True, True)


def test_provider_rights_gate_cannot_enable_wagering():
    with pytest.raises(ValueError):
        ProviderRightsGateResult(
            ProviderRightsGateStatus.PASS,
            (),
            True,
            False,
            False,
            True,
        )

from app.security.provider_terms_versioning import TermsTransitionStatus, evaluate_terms_transition
from app.security.provider_termination import DataDispositionStatus, evaluate_post_termination_disposition


def test_terms_transition_passes_unchanged_evidence():
    p = profile()
    ev = evidence(p)
    result = evaluate_terms_transition(p, ev, p, ev)
    assert result.status is TermsTransitionStatus.PASS


def test_terms_change_requires_version_bump():
    p = profile()
    old = evidence(p)
    new = evidence(p, evidence_id="rights-002", terms_sha256=SHA2, reviewed_at=NOW - timedelta(days=1))
    result = evaluate_terms_transition(p, old, p, new)
    assert result.status is TermsTransitionStatus.BLOCK
    assert "TERMS_CHANGED_WITHOUT_PROFILE_VERSION_BUMP" in result.reasons


def test_profile_change_requires_version_bump():
    p = profile()
    old = evidence(p)
    changed = profile(allow_export=True)
    new = evidence(changed, evidence_id="rights-002", reviewed_at=NOW - timedelta(days=1))
    result = evaluate_terms_transition(p, old, changed, new)
    assert result.status is TermsTransitionStatus.BLOCK
    assert "RIGHTS_PROFILE_CHANGED_WITHOUT_VERSION_BUMP" in result.reasons


def test_terms_and_profile_change_with_version_bump_are_allowed_but_same_source_warns():
    p = profile()
    old = evidence(p)
    changed = profile(profile_version="2.0", allow_export=True)
    new = evidence(
        changed,
        evidence_id="rights-002",
        terms_sha256=SHA2,
        reviewed_at=NOW - timedelta(days=1),
    )
    result = evaluate_terms_transition(p, old, changed, new)
    assert result.status is TermsTransitionStatus.WATCH
    assert "TERMS_HASH_CHANGED_WITH_SAME_SOURCE_REFERENCE" in result.reasons


def test_evidence_id_reuse_with_changed_content_blocks():
    p = profile()
    old = evidence(p)
    new = evidence(p, valid_until=NOW + timedelta(days=200), reviewed_at=NOW - timedelta(days=1))
    result = evaluate_terms_transition(p, old, p, new)
    assert result.status is TermsTransitionStatus.BLOCK
    assert "RIGHTS_EVIDENCE_ID_REUSED_FOR_CHANGED_CONTENT" in result.reasons


def test_review_time_regression_blocks():
    p = profile()
    old = evidence(p, reviewed_at=NOW - timedelta(days=2))
    new = evidence(p, evidence_id="rights-002", reviewed_at=NOW - timedelta(days=3))
    result = evaluate_terms_transition(p, old, p, new)
    assert result.status is TermsTransitionStatus.BLOCK


def test_future_termination_is_not_applicable():
    result = evaluate_post_termination_disposition(
        profile(),
        data_form=DataForm.RAW,
        termination_at=NOW + timedelta(days=1),
        now=NOW,
        deletion_evidence_verified=False,
    )
    assert result.status is DataDispositionStatus.NOT_APPLICABLE


def test_delete_all_requires_deletion_evidence():
    p = profile(termination_treatment=TerminationTreatment.DELETE_ALL_PROVIDER_DATA)
    result = evaluate_post_termination_disposition(
        p,
        data_form=DataForm.DERIVED,
        termination_at=NOW,
        now=NOW,
        deletion_evidence_verified=False,
    )
    assert result.status is DataDispositionStatus.BLOCK
    assert result.deletion_required is True


def test_delete_all_passes_once_deletion_verified():
    p = profile(termination_treatment=TerminationTreatment.DELETE_ALL_PROVIDER_DATA)
    result = evaluate_post_termination_disposition(
        p,
        data_form=DataForm.MODEL_ARTIFACT,
        termination_at=NOW,
        now=NOW,
        deletion_evidence_verified=True,
    )
    assert result.status is DataDispositionStatus.PASS
    assert result.retention_permitted is False


def test_delete_raw_retain_derived_requires_raw_deletion():
    p = profile(termination_treatment=TerminationTreatment.DELETE_RAW_RETAIN_DERIVED)
    result = evaluate_post_termination_disposition(
        p,
        data_form=DataForm.RAW,
        termination_at=NOW,
        now=NOW,
        deletion_evidence_verified=False,
    )
    assert result.status is DataDispositionStatus.BLOCK


def test_delete_raw_retain_derived_allows_derived_retention():
    p = profile(termination_treatment=TerminationTreatment.DELETE_RAW_RETAIN_DERIVED)
    result = evaluate_post_termination_disposition(
        p,
        data_form=DataForm.DERIVED,
        termination_at=NOW,
        now=NOW,
        deletion_evidence_verified=False,
    )
    assert result.status is DataDispositionStatus.PASS
    assert result.retention_permitted is True


def test_retain_governed_data_allows_retention():
    p = profile(termination_treatment=TerminationTreatment.RETAIN_GOVERNED_DATA)
    result = evaluate_post_termination_disposition(
        p,
        data_form=DataForm.RAW,
        termination_at=NOW,
        now=NOW,
        deletion_evidence_verified=False,
    )
    assert result.status is DataDispositionStatus.PASS


def test_external_review_termination_is_watch_not_pass():
    p = profile(termination_treatment=TerminationTreatment.EXTERNAL_REVIEW_REQUIRED)
    result = evaluate_post_termination_disposition(
        p,
        data_form=DataForm.AGGREGATED,
        termination_at=NOW,
        now=NOW,
        deletion_evidence_verified=False,
    )
    assert result.status is DataDispositionStatus.WATCH
    assert result.retention_permitted is False
