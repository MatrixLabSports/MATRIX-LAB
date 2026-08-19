from datetime import datetime, timedelta, timezone

import pytest

from app.security.data_classification import DataAsset, DataClass
from app.security.data_inventory import DataInventoryRecord, DataInventorySnapshot
from app.security.purpose_governance import (
    PurposeAssessment,
    PurposeSpecification,
    PurposeStatus,
    PurposeUseRequest,
    evaluate_purpose_use,
)
from app.security.jurisdiction_evidence import (
    JurisdictionAssessment,
    JurisdictionEvidence,
    JurisdictionStatus,
    ReviewOutcome,
    evaluate_jurisdiction_evidence,
)
from app.security.transfer_governance import (
    TransferAssessment,
    TransferEvidence,
    TransferOutcome,
    TransferStatus,
    evaluate_transfer,
)
from app.security.compliance_evidence_gate import (
    ComplianceEvidenceGateInput,
    ComplianceEvidenceGateResult,
    ComplianceGateStatus,
    evaluate_compliance_evidence_gate,
)

NOW = datetime(2026, 8, 19, 1, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def asset(*, personal=True):
    return DataAsset(
        "asset-001",
        "analytics evidence",
        DataClass.CONFIDENTIAL if personal else DataClass.INTERNAL,
        personal,
        False,
        "sports-research",
        "data-team",
    )


def inventory(*, personal=True, jurisdictions=("CO", "EU"), purposes=("sports-research",)):
    return DataInventoryRecord(
        "inv-001",
        asset(personal=personal),
        ("historical-store", "feature-store"),
        ("provider:primary",),
        ("match-events", "model-evidence"),
        ("registered-user",) if personal else (),
        purposes,
        jurisdictions,
        ("provider:primary",),
        "retention-v1",
        "privacy-review-1" if personal else None,
        "data-owner",
        NOW - timedelta(days=2),
        NOW - timedelta(hours=1),
    )


def purpose(active=True):
    return PurposeSpecification(
        "sports-research",
        "Sports research and model evaluation",
        ("match-events", "model-evidence"),
        ("read", "feature-engineering"),
        "research-owner",
        "1.0",
        active,
    )


def request(**kwargs):
    values = dict(
        asset_id="asset-001",
        purpose_id="sports-research",
        operation="read",
        data_categories=("match-events",),
        requested_at=NOW,
    )
    values.update(kwargs)
    return PurposeUseRequest(**values)


def jurisdiction(code="CO", outcome=ReviewOutcome.APPROVED_FOR_GOVERNED_PROCESSING, **kwargs):
    values = dict(
        evidence_id=f"jur-{code}",
        jurisdiction=code,
        purpose_id="sports-research",
        framework_reference=f"external-review:{code}",
        basis_code="REVIEWED_BASIS",
        reviewer_role="legal-reviewer",
        reviewed_at=NOW - timedelta(days=2),
        valid_until=NOW + timedelta(days=30),
        evidence_sha256=SHA,
        outcome=outcome,
        revoked=False,
    )
    values.update(kwargs)
    return JurisdictionEvidence(**values)


def transfer(outcome=TransferOutcome.APPROVED_FOR_GOVERNED_TRANSFER, **kwargs):
    values = dict(
        transfer_id="xfer-1",
        asset_id="asset-001",
        purpose_id="sports-research",
        source_jurisdiction="CO",
        destination_jurisdiction="EU",
        mechanism_reference="reviewed-mechanism-1",
        assessment_reference="assessment-1",
        approved_by_role="legal-reviewer",
        assessed_at=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=30),
        evidence_sha256=SHA,
        outcome=outcome,
        revoked=False,
    )
    values.update(kwargs)
    return TransferEvidence(**values)


def test_inventory_personal_data_requires_subject_categories():
    with pytest.raises(ValueError):
        DataInventoryRecord(
            "i", asset(), ("s",), ("src",), ("d",), (), ("p",), ("CO",), (), "r", "review", "o", NOW, NOW
        )


def test_inventory_personal_data_requires_privacy_review_reference():
    with pytest.raises(ValueError):
        DataInventoryRecord(
            "i", asset(), ("s",), ("src",), ("d",), ("u",), ("p",), ("CO",), (), "r", None, "o", NOW, NOW
        )


def test_inventory_rejects_duplicate_jurisdiction():
    with pytest.raises(ValueError):
        inventory(jurisdictions=("CO", "CO"))


def test_inventory_rejects_time_regression():
    i = inventory()
    with pytest.raises(ValueError):
        DataInventoryRecord(
            i.inventory_id, i.asset, i.systems, i.source_references, i.data_categories, i.data_subject_categories,
            i.purpose_ids, i.jurisdictions, i.processor_references, i.retention_policy_reference,
            i.privacy_review_reference, i.owner, NOW, NOW - timedelta(seconds=1)
        )


def test_inventory_fingerprint_is_stable():
    assert inventory().fingerprint == inventory().fingerprint


def test_inventory_snapshot_rejects_duplicate_asset():
    i = inventory()
    j = DataInventoryRecord(
        "inv-002", i.asset, i.systems, i.source_references, i.data_categories, i.data_subject_categories,
        i.purpose_ids, i.jurisdictions, i.processor_references, i.retention_policy_reference,
        i.privacy_review_reference, i.owner, i.created_at, i.updated_at
    )
    with pytest.raises(ValueError):
        DataInventorySnapshot("snap", (i, j), NOW, "v1")


def test_inventory_snapshot_rejects_future_record():
    i = inventory()
    future = DataInventoryRecord(
        i.inventory_id, i.asset, i.systems, i.source_references, i.data_categories, i.data_subject_categories,
        i.purpose_ids, i.jurisdictions, i.processor_references, i.retention_policy_reference,
        i.privacy_review_reference, i.owner, i.created_at, NOW + timedelta(seconds=1)
    )
    with pytest.raises(ValueError):
        DataInventorySnapshot("snap", (future,), NOW, "v1")


def test_inventory_snapshot_valid():
    snap = DataInventorySnapshot("snap", (inventory(),), NOW, "v1")
    assert len(snap.fingerprint) == 64


def test_purpose_use_passes_when_exactly_allowed():
    result = evaluate_purpose_use(inventory(), purpose(), request())
    assert result.status is PurposeStatus.PASS


@pytest.mark.parametrize(
    "req,reason",
    [
        (request(asset_id="other"), "ASSET_MISMATCH"),
        (request(purpose_id="marketing"), "PURPOSE_SPECIFICATION_MISMATCH"),
        (request(operation="delete"), "OPERATION_NOT_ALLOWED_FOR_PURPOSE"),
        (request(data_categories=("user-email",)), "REQUESTED_CATEGORY_NOT_IN_INVENTORY"),
    ],
)
def test_purpose_use_fail_closed(req, reason):
    result = evaluate_purpose_use(inventory(), purpose(), req)
    assert result.status is PurposeStatus.BLOCK
    assert reason in result.reasons


def test_purpose_inactive_blocks():
    result = evaluate_purpose_use(inventory(), purpose(False), request())
    assert result.status is PurposeStatus.BLOCK
    assert "PURPOSE_INACTIVE" in result.reasons


def test_secondary_purpose_not_in_inventory_blocks():
    spec = PurposeSpecification("marketing", "x", ("match-events",), ("read",), "o", "1")
    req = request(purpose_id="marketing")
    result = evaluate_purpose_use(inventory(), spec, req)
    assert "PURPOSE_NOT_IN_INVENTORY" in result.reasons


def test_jurisdiction_evidence_passes_when_all_covered():
    result = evaluate_jurisdiction_evidence(inventory(), purpose_id="sports-research", evidences=(jurisdiction("CO"), jurisdiction("EU")), now=NOW)
    assert result.status is JurisdictionStatus.PASS
    assert result.legal_compliance_certified is False


def test_missing_jurisdiction_evidence_blocks():
    result = evaluate_jurisdiction_evidence(inventory(), purpose_id="sports-research", evidences=(jurisdiction("CO"),), now=NOW)
    assert result.status is JurisdictionStatus.BLOCK
    assert "MISSING_JURISDICTION_EVIDENCE:EU" in result.reasons


def test_expired_jurisdiction_evidence_blocks():
    expired = jurisdiction("EU", valid_until=NOW)
    result = evaluate_jurisdiction_evidence(inventory(), purpose_id="sports-research", evidences=(jurisdiction("CO"), expired), now=NOW)
    assert result.status is JurisdictionStatus.BLOCK
    assert "EXPIRED_JURISDICTION_EVIDENCE:EU" in result.reasons


def test_future_jurisdiction_evidence_blocks():
    future = jurisdiction("EU", reviewed_at=NOW + timedelta(seconds=1), valid_until=NOW + timedelta(days=30))
    result = evaluate_jurisdiction_evidence(inventory(), purpose_id="sports-research", evidences=(jurisdiction("CO"), future), now=NOW)
    assert result.status is JurisdictionStatus.BLOCK
    assert "FUTURE_JURISDICTION_EVIDENCE:EU" in result.reasons


def test_revoked_jurisdiction_evidence_blocks():
    revoked = jurisdiction("EU", revoked=True)
    result = evaluate_jurisdiction_evidence(inventory(), purpose_id="sports-research", evidences=(jurisdiction("CO"), revoked), now=NOW)
    assert result.status is JurisdictionStatus.BLOCK


def test_jurisdiction_review_required_is_watch():
    review = jurisdiction("EU", ReviewOutcome.REVIEW_REQUIRED)
    result = evaluate_jurisdiction_evidence(inventory(), purpose_id="sports-research", evidences=(jurisdiction("CO"), review), now=NOW)
    assert result.status is JurisdictionStatus.WATCH


def test_jurisdiction_rejected_blocks():
    rejected = jurisdiction("EU", ReviewOutcome.REJECTED)
    result = evaluate_jurisdiction_evidence(inventory(), purpose_id="sports-research", evidences=(jurisdiction("CO"), rejected), now=NOW)
    assert result.status is JurisdictionStatus.BLOCK


def test_duplicate_jurisdiction_evidence_blocks():
    result = evaluate_jurisdiction_evidence(inventory(jurisdictions=("CO",)), purpose_id="sports-research", evidences=(jurisdiction("CO"), jurisdiction("CO", evidence_id="x")), now=NOW)
    assert result.status is JurisdictionStatus.BLOCK
    assert "DUPLICATE_JURISDICTION_EVIDENCE:CO" in result.reasons


def test_jurisdiction_assessment_cannot_self_certify_law():
    with pytest.raises(ValueError):
        JurisdictionAssessment(JurisdictionStatus.PASS, (), True)


def test_same_jurisdiction_transfer_requires_no_crossborder_evidence():
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="CO", evidence=None, now=NOW)
    assert result.status is TransferStatus.NOT_REQUIRED


def test_crossborder_transfer_without_evidence_blocks():
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="EU", evidence=None, now=NOW)
    assert result.status is TransferStatus.BLOCK
    assert "MISSING_TRANSFER_EVIDENCE" in result.reasons


def test_valid_crossborder_transfer_passes():
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="EU", evidence=transfer(), now=NOW)
    assert result.status is TransferStatus.PASS
    assert result.legal_adequacy_certified is False


def test_transfer_route_mismatch_blocks():
    ev = transfer(destination_jurisdiction="US")
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="EU", evidence=ev, now=NOW)
    assert result.status is TransferStatus.BLOCK
    assert "TRANSFER_ROUTE_MISMATCH" in result.reasons


def test_transfer_asset_mismatch_blocks():
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="EU", evidence=transfer(asset_id="other"), now=NOW)
    assert "TRANSFER_ASSET_MISMATCH" in result.reasons


def test_transfer_expired_blocks():
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="EU", evidence=transfer(valid_until=NOW), now=NOW)
    assert result.status is TransferStatus.BLOCK


def test_transfer_future_evidence_blocks():
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="EU", evidence=transfer(assessed_at=NOW + timedelta(seconds=1)), now=NOW)
    assert result.status is TransferStatus.BLOCK


def test_transfer_revoked_blocks():
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="EU", evidence=transfer(revoked=True), now=NOW)
    assert result.status is TransferStatus.BLOCK


def test_transfer_review_required_is_watch():
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="EU", evidence=transfer(TransferOutcome.REVIEW_REQUIRED), now=NOW)
    assert result.status is TransferStatus.WATCH


def test_transfer_rejected_blocks():
    result = evaluate_transfer(inventory(), purpose_id="sports-research", source_jurisdiction="CO", destination_jurisdiction="EU", evidence=transfer(TransferOutcome.REJECTED), now=NOW)
    assert result.status is TransferStatus.BLOCK


def test_transfer_assessment_cannot_self_certify_legal_adequacy():
    with pytest.raises(ValueError):
        TransferAssessment(TransferStatus.PASS, (), True)


def good_gate(*, legal_review="legal-review-ticket-1"):
    return ComplianceEvidenceGateInput(
        True,
        PurposeAssessment(PurposeStatus.PASS, ()),
        JurisdictionAssessment(JurisdictionStatus.PASS, ()),
        (TransferAssessment(TransferStatus.PASS, ()),),
        True, True, True, True,
        legal_review,
    )


def test_compliance_gate_passes_evidence_but_does_not_certify_law():
    result = evaluate_compliance_evidence_gate(good_gate())
    assert result.status is ComplianceGateStatus.PASS
    assert result.eligible_for_legal_review is True
    assert result.legal_compliance_certified is False
    assert result.automatic_model_promotion_enabled is False
    assert result.automatic_wager_execution_enabled is False


def test_compliance_gate_without_independent_legal_review_is_watch():
    result = evaluate_compliance_evidence_gate(good_gate(legal_review=None))
    assert result.status is ComplianceGateStatus.WATCH
    assert "INDEPENDENT_LEGAL_REVIEW_NOT_RECORDED" in result.reasons


@pytest.mark.parametrize(
    "field,reason",
    [
        ("inventory_verified", "DATA_INVENTORY_NOT_VERIFIED"),
        ("access_control_verified", "ACCESS_CONTROL_NOT_VERIFIED"),
        ("retention_control_verified", "RETENTION_CONTROL_NOT_VERIFIED"),
        ("deletion_control_verified", "DELETION_CONTROL_NOT_VERIFIED"),
        ("incident_response_verified", "INCIDENT_RESPONSE_NOT_VERIFIED"),
    ],
)
def test_compliance_gate_core_control_failures_block(field, reason):
    base = good_gate().__dict__.copy()
    base[field] = False
    result = evaluate_compliance_evidence_gate(ComplianceEvidenceGateInput(**base))
    assert result.status is ComplianceGateStatus.BLOCK
    assert reason in result.reasons
    assert result.eligible_for_legal_review is False


def test_compliance_gate_purpose_block_propagates():
    base = good_gate().__dict__.copy()
    base["purpose_assessment"] = PurposeAssessment(PurposeStatus.BLOCK, ("PURPOSE_INACTIVE",))
    result = evaluate_compliance_evidence_gate(ComplianceEvidenceGateInput(**base))
    assert result.status is ComplianceGateStatus.BLOCK
    assert "PURPOSE_INACTIVE" in result.reasons


def test_compliance_gate_jurisdiction_watch_propagates():
    base = good_gate().__dict__.copy()
    base["jurisdiction_assessment"] = JurisdictionAssessment(JurisdictionStatus.WATCH, ("JURISDICTION_REVIEW_REQUIRED:EU",))
    result = evaluate_compliance_evidence_gate(ComplianceEvidenceGateInput(**base))
    assert result.status is ComplianceGateStatus.WATCH


def test_compliance_gate_transfer_block_propagates():
    base = good_gate().__dict__.copy()
    base["transfer_assessments"] = (TransferAssessment(TransferStatus.BLOCK, ("TRANSFER_REJECTED",)),)
    result = evaluate_compliance_evidence_gate(ComplianceEvidenceGateInput(**base))
    assert result.status is ComplianceGateStatus.BLOCK


def test_compliance_gate_cannot_enable_automatic_wagering_or_promotion():
    with pytest.raises(ValueError):
        ComplianceEvidenceGateResult(ComplianceGateStatus.PASS, (), True, False, True, False)
    with pytest.raises(ValueError):
        ComplianceEvidenceGateResult(ComplianceGateStatus.PASS, (), True, False, False, True)


def test_compliance_gate_cannot_self_certify_legal_compliance():
    with pytest.raises(ValueError):
        ComplianceEvidenceGateResult(ComplianceGateStatus.PASS, (), True, True)
