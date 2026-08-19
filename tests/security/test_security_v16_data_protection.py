from datetime import datetime, timedelta, timezone
import pytest

from app.security.data_classification import DataAsset, DataClass, classification_is_acceptable
from app.security.data_minimization import DataFieldUse, evaluate_minimization
from app.security.encryption_evidence import EncryptionEvidence
from app.security.retention import RetentionAction, RetentionPolicy, RetentionRecord, retention_action
from app.security.deletion_evidence import DeletionEvidence, DeletionStatus
from app.security.export_control import ExportDecision, ExportRequest, evaluate_export
from app.security.privacy_gate import PrivacyGateInput, PrivacyStatus, evaluate_privacy_gate
from app.security.backup_protection import BackupProtectionEvidence
from app.security.data_segregation import Environment, StorageZone, placement_allowed

NOW = datetime(2026, 8, 18, 19, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def asset(data_class=DataClass.CONFIDENTIAL, personal=True):
    return DataAsset("asset-001", "fixture evidence", data_class, personal, False, "model research", "data-team")


def enc(at_rest=True, in_transit=True, external=True, verified_at=NOW):
    return EncryptionEvidence("asset-001", at_rest, in_transit, "kms://key/1", external, verified_at, "security-ci", "crypto-policy-v1")


def backup(**overrides):
    values = dict(backup_id="backup-001", source_asset_id="asset-001", source_data_class=DataClass.CONFIDENTIAL, encrypted_at_rest=True, key_separated_from_backup=True, integrity_verified=True, restore_test_verified=True, immutable_or_write_protected=True, verified_at=NOW, verifier="backup-ci")
    values.update(overrides)
    return BackupProtectionEvidence(**values)


def test_credentials_require_restricted_class():
    with pytest.raises(ValueError):
        DataAsset("a", "secrets", DataClass.CONFIDENTIAL, False, True, "runtime", "security")


def test_personal_data_below_confidential_fails_classification():
    assert classification_is_acceptable(asset(DataClass.INTERNAL, personal=True)) is False


def test_non_personal_internal_data_can_pass_classification():
    assert classification_is_acceptable(asset(DataClass.INTERNAL, personal=False)) is True


def test_asset_fingerprint_is_stable():
    assert asset().fingerprint == asset().fingerprint


def test_minimization_passes_when_only_required_fields_collected():
    report = evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, True),))
    assert report.passed is True


def test_minimization_detects_unnecessary_collection():
    report = evaluate_minimization((DataFieldUse("phone", "analysis", False, True),))
    assert report.unnecessary_fields == ("phone",)


def test_minimization_detects_missing_required_field():
    report = evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, False),))
    assert report.missing_required_fields == ("fixture_id",)


def test_minimization_rejects_duplicate_declarations_casefolded():
    with pytest.raises(ValueError):
        evaluate_minimization((DataFieldUse("Email", "x", False, False), DataFieldUse("email", "x", False, False)))


def test_encryption_evidence_accepts_current_complete_evidence():
    assert enc().acceptable(now=NOW + timedelta(hours=1)) is True


def test_encryption_evidence_rejects_stale_evidence():
    assert enc(verified_at=NOW - timedelta(days=2)).acceptable(now=NOW) is False


def test_encryption_evidence_rejects_future_evidence():
    assert enc(verified_at=NOW + timedelta(hours=1)).acceptable(now=NOW) is False


def test_encryption_evidence_requires_external_key_management():
    assert enc(external=False).acceptable(now=NOW) is False


def test_encryption_evidence_requires_at_rest_when_required():
    assert enc(at_rest=False).acceptable(now=NOW) is False


def test_encryption_evidence_requires_in_transit_when_required():
    assert enc(in_transit=False).acceptable(now=NOW) is False


def test_retention_keep_review_delete_sequence():
    policy = RetentionPolicy("p1", retention_days=30, review_before_delete_days=7)
    record = RetentionRecord("a", NOW, "p1")
    assert retention_action(record, policy, now=NOW + timedelta(days=10)) is RetentionAction.KEEP
    assert retention_action(record, policy, now=NOW + timedelta(days=24)) is RetentionAction.REVIEW
    assert retention_action(record, policy, now=NOW + timedelta(days=31)) is RetentionAction.DELETE


def test_legal_hold_blocks_retention_deletion():
    policy = RetentionPolicy("p1", 30)
    record = RetentionRecord("a", NOW, "p1", legal_hold=True)
    assert retention_action(record, policy, now=NOW + timedelta(days=100)) is RetentionAction.LEGAL_HOLD


def test_retention_policy_mismatch_fails_closed():
    with pytest.raises(ValueError):
        retention_action(RetentionRecord("a", NOW, "p1"), RetentionPolicy("p2", 30), now=NOW)


def test_retention_rejects_clock_before_creation():
    with pytest.raises(ValueError):
        retention_action(RetentionRecord("a", NOW, "p1"), RetentionPolicy("p1", 30), now=NOW - timedelta(seconds=1))


def test_completed_deletion_requires_tombstone():
    with pytest.raises(ValueError):
        DeletionEvidence("d1", "a", NOW, NOW, "actor", "crypto-erase", DeletionStatus.COMPLETED, SHA, None, True)


def test_non_completed_deletion_cannot_claim_tombstone():
    with pytest.raises(ValueError):
        DeletionEvidence("d1", "a", NOW, None, "actor", "crypto-erase", DeletionStatus.REQUESTED, SHA, SHA, False)


def test_completed_deletion_has_stable_fingerprint():
    d = DeletionEvidence("d1", "a", NOW, NOW + timedelta(seconds=1), "actor", "crypto-erase", DeletionStatus.COMPLETED, SHA, "b"*64, True)
    assert len(d.fingerprint) == 64


def test_public_export_can_be_allowed_without_review():
    req = ExportRequest("r1", "a", DataClass.PUBLIC, "public-report", "publish", "u", NOW, False, False)
    assert evaluate_export(req) is ExportDecision.ALLOW


def test_internal_export_requires_recipient_and_transport_controls():
    req = ExportRequest("r1", "a", DataClass.INTERNAL, "partner", "ops", "u", NOW, False, True)
    assert evaluate_export(req) is ExportDecision.BLOCK


def test_internal_export_can_pass_with_controls():
    req = ExportRequest("r1", "a", DataClass.INTERNAL, "partner", "ops", "u", NOW, True, True)
    assert evaluate_export(req) is ExportDecision.ALLOW


def test_confidential_export_requires_review_reference():
    req = ExportRequest("r1", "a", DataClass.CONFIDENTIAL, "partner", "ops", "u", NOW, True, True)
    assert evaluate_export(req) is ExportDecision.BLOCK


def test_confidential_export_with_reference_requires_review_not_auto_allow():
    req = ExportRequest("r1", "a", DataClass.CONFIDENTIAL, "partner", "ops", "u", NOW, True, True, "approval-123")
    assert evaluate_export(req) is ExportDecision.REQUIRE_REVIEW


def test_privacy_gate_passes_when_all_required_evidence_is_present():
    data = PrivacyGateInput(asset(), evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, True),)), enc(), True, True, backup(), True, True)
    result = evaluate_privacy_gate(data, now=NOW)
    assert result.status is PrivacyStatus.PASS
    assert result.automatic_model_promotion_enabled is False
    assert result.automatic_wager_execution_enabled is False


def test_privacy_gate_blocks_low_classification():
    data = PrivacyGateInput(asset(DataClass.INTERNAL, True), evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, True),)), enc(), True, True, backup(source_data_class=DataClass.INTERNAL), True, True)
    assert evaluate_privacy_gate(data, now=NOW).status is PrivacyStatus.BLOCK


def test_privacy_gate_blocks_minimization_failure():
    data = PrivacyGateInput(asset(), evaluate_minimization((DataFieldUse("phone", "analysis", False, True),)), enc(), True, True, backup(), True, True)
    assert "DATA_MINIMIZATION_FAILURE" in evaluate_privacy_gate(data, now=NOW).reasons


def test_privacy_gate_blocks_missing_encryption_for_confidential_data():
    data = PrivacyGateInput(asset(), evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, True),)), None, True, True, backup(), True, True)
    assert "MISSING_ENCRYPTION_EVIDENCE" in evaluate_privacy_gate(data, now=NOW).reasons


def test_privacy_gate_blocks_wrong_asset_encryption_evidence():
    wrong = EncryptionEvidence("other", True, True, "kms://key/1", True, NOW, "security-ci", "crypto-policy-v1")
    data = PrivacyGateInput(asset(), evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, True),)), wrong, True, True, backup(), True, True)
    assert "ENCRYPTION_EVIDENCE_NOT_ACCEPTABLE" in evaluate_privacy_gate(data, now=NOW).reasons


@pytest.mark.parametrize("field,reason", [
    ("retention_policy_assigned", "RETENTION_POLICY_MISSING"),
    ("deletion_procedure_verified", "DELETION_PROCEDURE_NOT_VERIFIED"),
        ("access_control_verified", "ACCESS_CONTROL_NOT_VERIFIED"),
    ("export_controls_verified", "EXPORT_CONTROLS_NOT_VERIFIED"),
])
def test_privacy_gate_blocks_missing_controls(field, reason):
    kwargs = dict(asset=asset(), minimization=evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, True),)), encryption=enc(), retention_policy_assigned=True, deletion_procedure_verified=True, backup_protection=backup(), access_control_verified=True, export_controls_verified=True)
    kwargs[field] = False
    result = evaluate_privacy_gate(PrivacyGateInput(**kwargs), now=NOW)
    assert result.status is PrivacyStatus.BLOCK
    assert reason in result.reasons


def test_lower_class_data_without_encryption_is_watch_not_pass():
    data = PrivacyGateInput(asset(DataClass.INTERNAL, False), evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, True),)), None, True, True, backup(source_data_class=DataClass.INTERNAL), True, True)
    assert evaluate_privacy_gate(data, now=NOW).status is PrivacyStatus.WATCH


def test_privacy_gate_cannot_enable_promotion_or_wagering():
    from app.security.privacy_gate import PrivacyGateResult
    with pytest.raises(ValueError):
        PrivacyGateResult(PrivacyStatus.PASS, (), automatic_model_promotion_enabled=True)
    with pytest.raises(ValueError):
        PrivacyGateResult(PrivacyStatus.PASS, (), automatic_wager_execution_enabled=True)


def test_completed_deletion_requires_complete_scope():
    with pytest.raises(ValueError):
        DeletionEvidence("d2", "a", NOW, NOW, "actor", "crypto-erase", DeletionStatus.COMPLETED, SHA, "b"*64, False)


def test_backup_protection_accepts_complete_evidence():
    assert backup().acceptable(now=NOW) is True


def test_backup_protection_rejects_stale_evidence():
    assert backup(verified_at=NOW - timedelta(days=8)).acceptable(now=NOW) is False


def test_restricted_backup_requires_immutability_or_write_protection():
    b = backup(source_data_class=DataClass.RESTRICTED, immutable_or_write_protected=False)
    assert b.acceptable(now=NOW) is False


def test_privacy_gate_blocks_missing_backup_evidence():
    data = PrivacyGateInput(asset(), evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, True),)), enc(), True, True, None, True, True)
    result = evaluate_privacy_gate(data, now=NOW)
    assert result.status is PrivacyStatus.BLOCK
    assert "BACKUP_PROTECTION_NOT_VERIFIED" in result.reasons


def test_privacy_gate_blocks_backup_for_wrong_asset():
    data = PrivacyGateInput(asset(), evaluate_minimization((DataFieldUse("fixture_id", "analysis", True, True),)), enc(), True, True, backup(source_asset_id="other"), True, True)
    assert "BACKUP_PROTECTION_NOT_ACCEPTABLE" in evaluate_privacy_gate(data, now=NOW).reasons


def test_confidential_asset_cannot_be_placed_in_internal_zone():
    z = StorageZone("z1", Environment.PRODUCTION, DataClass.INTERNAL, True, False)
    assert placement_allowed(asset(), z) is False


def test_personal_data_rejected_from_zone_that_disallows_personal_data():
    z = StorageZone("z1", Environment.PRODUCTION, DataClass.RESTRICTED, False, False)
    assert placement_allowed(asset(), z) is False


def test_restricted_data_rejected_from_external_shared_zone():
    a = DataAsset("cred", "credentials", DataClass.RESTRICTED, False, True, "runtime", "security")
    z = StorageZone("z1", Environment.PRODUCTION, DataClass.RESTRICTED, True, True, externally_shared=True)
    assert placement_allowed(a, z) is False


def test_credentials_rejected_from_development_even_when_zone_allows_credentials():
    a = DataAsset("cred", "credentials", DataClass.RESTRICTED, False, True, "runtime", "security")
    z = StorageZone("z1", Environment.DEVELOPMENT, DataClass.RESTRICTED, True, True)
    assert placement_allowed(a, z) is False


def test_confidential_noncredential_data_allowed_in_suitable_production_zone():
    z = StorageZone("z1", Environment.PRODUCTION, DataClass.RESTRICTED, True, False)
    assert placement_allowed(asset(), z) is True
