from datetime import datetime, timedelta, timezone
import json

import pytest

from app.security.data_classification import DataAsset, DataClass
from app.security.deletion_evidence import DeletionEvidence, DeletionStatus
from app.security.data_lifecycle import (
    LifecycleStage,
    initial_lifecycle_record,
    transition_lifecycle,
    verify_lifecycle_chain,
)
from app.security.privacy_gate import PrivacyGateResult, PrivacyStatus
from app.security.privacy_incident import (
    PrivacyIncident,
    PrivacyIncidentCategory,
    PrivacyIncidentSeverity,
    PrivacyIncidentState,
    assess_technical_severity,
    transition_incident,
    verify_incident_chain,
)
from app.security.privacy_policy_monitor import (
    MonitorStatus,
    PrivacyControlObservation,
    PrivacyMonitoringReport,
    evaluate_privacy_observations,
    observation_from_privacy_gate,
)
from app.security.privacy_evidence_automation import (
    EvidenceAutomationResult,
    EvidenceAutomationStatus,
    build_privacy_evidence_snapshot,
)
from app.security.privacy_evidence_ledger import PrivacyEvidenceLedger, verify_privacy_evidence_ledger

NOW = datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def asset(data_class=DataClass.CONFIDENTIAL, personal=True, credentials=False):
    return DataAsset("asset-001", "match evidence", data_class, personal, credentials, "research", "data-team")


def deletion(a: DataAsset, completed_at=NOW + timedelta(minutes=5)):
    return DeletionEvidence(
        "del-1", a.asset_id, NOW, completed_at, "privacy-operator", "crypto-erase",
        DeletionStatus.COMPLETED, a.fingerprint, "b" * 64, True,
    )


def full_lifecycle(a: DataAsset):
    i = initial_lifecycle_record(a, occurred_at=NOW, actor_id="ingest")
    v = transition_lifecycle(i, LifecycleStage.VALIDATED, occurred_at=NOW + timedelta(minutes=1), actor_id="validator", reason="validated")
    ac = transition_lifecycle(v, LifecycleStage.ACTIVE, occurred_at=NOW + timedelta(minutes=2), actor_id="engine", reason="active")
    ar = transition_lifecycle(ac, LifecycleStage.ARCHIVED, occurred_at=NOW + timedelta(minutes=3), actor_id="archive", reason="archive")
    return i, v, ac, ar


def test_lifecycle_begins_ingested_with_asset_binding():
    a = asset()
    record = initial_lifecycle_record(a, occurred_at=NOW, actor_id="u")
    assert record.stage is LifecycleStage.INGESTED
    assert record.asset_fingerprint == a.fingerprint
    assert record.previous_record_fingerprint is None


def test_lifecycle_rejects_invalid_jump():
    i = initial_lifecycle_record(asset(), occurred_at=NOW, actor_id="u")
    with pytest.raises(ValueError):
        transition_lifecycle(i, LifecycleStage.ACTIVE, occurred_at=NOW, actor_id="u", reason="skip")


def test_lifecycle_rejects_time_regression():
    i = initial_lifecycle_record(asset(), occurred_at=NOW, actor_id="u")
    with pytest.raises(ValueError):
        transition_lifecycle(i, LifecycleStage.VALIDATED, occurred_at=NOW - timedelta(seconds=1), actor_id="u", reason="bad")


def test_lifecycle_chain_verifies_valid_sequence():
    chain = full_lifecycle(asset())
    assert verify_lifecycle_chain(chain) == (True, ())


def test_lifecycle_chain_detects_broken_hash():
    i, v, ac, ar = full_lifecycle(asset())
    broken = type(ar)(ar.asset_id, ar.asset_fingerprint, ar.stage, ar.occurred_at, ar.actor_id, ar.reason, SHA, ar.legal_hold)
    ok, reasons = verify_lifecycle_chain((i, v, ac, broken))
    assert ok is False
    assert any(reason.startswith("LIFECYCLE_CHAIN_BROKEN") for reason in reasons)


def test_legal_hold_blocks_deletion_pending():
    i, v, ac, ar = full_lifecycle(asset())
    held = transition_lifecycle(ac, LifecycleStage.QUARANTINED, occurred_at=NOW + timedelta(minutes=4), actor_id="legal", reason="hold", legal_hold=True)
    with pytest.raises(ValueError):
        transition_lifecycle(held, LifecycleStage.DELETION_PENDING, occurred_at=NOW + timedelta(minutes=5), actor_id="u", reason="delete")


def test_legal_hold_cannot_be_removed_by_lifecycle_transition():
    i, v, ac, _ = full_lifecycle(asset())
    held = transition_lifecycle(ac, LifecycleStage.QUARANTINED, occurred_at=NOW + timedelta(minutes=4), actor_id="legal", reason="hold", legal_hold=True)
    with pytest.raises(ValueError):
        transition_lifecycle(held, LifecycleStage.ARCHIVED, occurred_at=NOW + timedelta(minutes=5), actor_id="u", reason="release", legal_hold=False)


def test_deleted_requires_completed_matching_deletion_evidence():
    a = asset()
    i, v, ac, ar = full_lifecycle(a)
    dp = transition_lifecycle(ar, LifecycleStage.DELETION_PENDING, occurred_at=NOW + timedelta(minutes=4), actor_id="u", reason="retention")
    with pytest.raises(ValueError):
        transition_lifecycle(dp, LifecycleStage.DELETED, occurred_at=NOW + timedelta(minutes=6), actor_id="u", reason="done")
    wrong = deletion(DataAsset("other", "x", DataClass.CONFIDENTIAL, True, False, "r", "o"))
    with pytest.raises(ValueError):
        transition_lifecycle(dp, LifecycleStage.DELETED, occurred_at=NOW + timedelta(minutes=6), actor_id="u", reason="done", deletion_evidence=wrong)


def test_deleted_accepts_completed_evidence():
    a = asset()
    i, v, ac, ar = full_lifecycle(a)
    dp = transition_lifecycle(ar, LifecycleStage.DELETION_PENDING, occurred_at=NOW + timedelta(minutes=4), actor_id="u", reason="retention")
    d = transition_lifecycle(dp, LifecycleStage.DELETED, occurred_at=NOW + timedelta(minutes=6), actor_id="u", reason="done", deletion_evidence=deletion(a))
    assert d.stage is LifecycleStage.DELETED


def test_deleted_is_terminal():
    a = asset()
    i, v, ac, ar = full_lifecycle(a)
    dp = transition_lifecycle(ar, LifecycleStage.DELETION_PENDING, occurred_at=NOW + timedelta(minutes=4), actor_id="u", reason="retention")
    d = transition_lifecycle(dp, LifecycleStage.DELETED, occurred_at=NOW + timedelta(minutes=6), actor_id="u", reason="done", deletion_evidence=deletion(a))
    with pytest.raises(ValueError):
        transition_lifecycle(d, LifecycleStage.ARCHIVED, occurred_at=NOW + timedelta(minutes=7), actor_id="u", reason="resurrect")


@pytest.mark.parametrize(
    "data_class,external,integrity,credentials,expected",
    [
        (DataClass.PUBLIC, False, False, False, PrivacyIncidentSeverity.LOW),
        (DataClass.CONFIDENTIAL, False, False, False, PrivacyIncidentSeverity.MEDIUM),
        (DataClass.CONFIDENTIAL, True, False, False, PrivacyIncidentSeverity.HIGH),
        (DataClass.RESTRICTED, True, False, False, PrivacyIncidentSeverity.CRITICAL),
        (DataClass.CONFIDENTIAL, False, True, False, PrivacyIncidentSeverity.HIGH),
        (DataClass.RESTRICTED, False, False, True, PrivacyIncidentSeverity.CRITICAL),
    ],
)
def test_technical_incident_severity(data_class, external, integrity, credentials, expected):
    a = asset(data_class=data_class, personal=(data_class is DataClass.CONFIDENTIAL), credentials=(data_class is DataClass.RESTRICTED and credentials))
    assert assess_technical_severity((a,), confirmed_external_exposure=external, integrity_compromised=integrity, credentials_exposed=credentials) is expected


def incident(severity=PrivacyIncidentSeverity.HIGH, legal=True):
    return PrivacyIncident(
        "inc-1", PrivacyIncidentCategory.CONFIDENTIALITY, severity, PrivacyIncidentState.DETECTED,
        NOW, NOW, "monitor", "detected", ("asset-001",), True, False, (SHA,),
        legal_assessment_required=legal,
    )


def test_incident_transition_sequence_and_chain():
    d = incident(PrivacyIncidentSeverity.MEDIUM, legal=False)
    t = transition_incident(d, PrivacyIncidentState.TRIAGED, updated_at=NOW + timedelta(minutes=1))
    c = transition_incident(t, PrivacyIncidentState.CONTAINED, updated_at=NOW + timedelta(minutes=2))
    r = transition_incident(c, PrivacyIncidentState.REMEDIATED, updated_at=NOW + timedelta(minutes=3), root_cause="policy gap", remediation_reference="fix-1")
    closed = transition_incident(r, PrivacyIncidentState.CLOSED, updated_at=NOW + timedelta(minutes=4))
    assert closed.state is PrivacyIncidentState.CLOSED
    assert verify_incident_chain((d, t, c, r, closed)) == (True, ())


def test_incident_cannot_skip_states():
    with pytest.raises(ValueError):
        transition_incident(incident(), PrivacyIncidentState.CONTAINED, updated_at=NOW + timedelta(minutes=1))


def test_high_incident_cannot_close_without_independent_review():
    d = incident()
    t = transition_incident(d, PrivacyIncidentState.TRIAGED, updated_at=NOW + timedelta(minutes=1))
    c = transition_incident(t, PrivacyIncidentState.CONTAINED, updated_at=NOW + timedelta(minutes=2))
    r = transition_incident(c, PrivacyIncidentState.REMEDIATED, updated_at=NOW + timedelta(minutes=3), root_cause="x", remediation_reference="r")
    with pytest.raises(ValueError):
        transition_incident(r, PrivacyIncidentState.CLOSED, updated_at=NOW + timedelta(minutes=4), legal_notification_status="NOT_REQUIRED")


def test_legal_assessment_required_before_close():
    d = incident(PrivacyIncidentSeverity.MEDIUM, legal=True)
    t = transition_incident(d, PrivacyIncidentState.TRIAGED, updated_at=NOW + timedelta(minutes=1))
    c = transition_incident(t, PrivacyIncidentState.CONTAINED, updated_at=NOW + timedelta(minutes=2))
    r = transition_incident(c, PrivacyIncidentState.REMEDIATED, updated_at=NOW + timedelta(minutes=3), root_cause="x", remediation_reference="r")
    with pytest.raises(ValueError):
        transition_incident(r, PrivacyIncidentState.CLOSED, updated_at=NOW + timedelta(minutes=4))


def test_high_incident_can_close_with_review_and_legal_assessment():
    d = incident()
    t = transition_incident(d, PrivacyIncidentState.TRIAGED, updated_at=NOW + timedelta(minutes=1))
    c = transition_incident(t, PrivacyIncidentState.CONTAINED, updated_at=NOW + timedelta(minutes=2))
    r = transition_incident(c, PrivacyIncidentState.REMEDIATED, updated_at=NOW + timedelta(minutes=3), root_cause="x", remediation_reference="r")
    closed = transition_incident(r, PrivacyIncidentState.CLOSED, updated_at=NOW + timedelta(minutes=4), independent_review_reference="review-1", legal_notification_status="ASSESSED_NO_NOTIFICATION")
    assert closed.state is PrivacyIncidentState.CLOSED


def test_monitor_builds_observation_from_gate():
    a = asset()
    obs = observation_from_privacy_gate(a, PrivacyGateResult(PrivacyStatus.WATCH, ("X",)), observed_at=NOW, evidence_sha256=SHA, observation_id="o1")
    assert obs.status is PrivacyStatus.WATCH
    assert obs.asset_id == a.asset_id


def test_monitor_no_observations_is_unknown():
    result = evaluate_privacy_observations(asset(), (), now=NOW)
    assert result.status is MonitorStatus.UNKNOWN


def test_monitor_pass_is_healthy():
    obs = PrivacyControlObservation("o1", "asset-001", "PRIVACY_GATE", PrivacyStatus.PASS, NOW, SHA, ())
    result = evaluate_privacy_observations(asset(), (obs,), now=NOW)
    assert result.status is MonitorStatus.HEALTHY
    assert result.incident_candidate is None


def test_monitor_watch_remains_watch_without_incident():
    obs = PrivacyControlObservation("o1", "asset-001", "PRIVACY_GATE", PrivacyStatus.WATCH, NOW, SHA, ("LOWER_CLASS_NO_ENCRYPTION",))
    result = evaluate_privacy_observations(asset(DataClass.INTERNAL, personal=False), (obs,), now=NOW)
    assert result.status is MonitorStatus.WATCH
    assert result.incident_candidate is None


def test_monitor_block_creates_technical_incident_candidate_not_legal_notification():
    obs = PrivacyControlObservation("o1", "asset-001", "PRIVACY_GATE", PrivacyStatus.BLOCK, NOW, SHA, ("MISSING_ENCRYPTION_EVIDENCE",))
    result = evaluate_privacy_observations(asset(), (obs,), now=NOW)
    assert result.status is MonitorStatus.INCIDENT_CANDIDATE
    assert result.incident_candidate is not None
    assert result.incident_candidate.legal_assessment_required is True
    assert result.automatic_legal_notification_enabled is False


def test_monitor_restricted_export_or_access_failure_is_critical_candidate():
    a = asset(DataClass.RESTRICTED, personal=False, credentials=True)
    obs = PrivacyControlObservation("o1", a.asset_id, "EXPORT", PrivacyStatus.BLOCK, NOW, SHA, ("EXPORT_CONTROLS_NOT_VERIFIED",))
    result = evaluate_privacy_observations(a, (obs,), now=NOW)
    assert result.incident_candidate.severity is PrivacyIncidentSeverity.CRITICAL


def test_monitor_rejects_stale_observation_into_incident_candidate():
    obs = PrivacyControlObservation("o1", "asset-001", "PRIVACY_GATE", PrivacyStatus.PASS, NOW - timedelta(days=2), SHA, ())
    result = evaluate_privacy_observations(asset(), (obs,), now=NOW)
    assert result.status is MonitorStatus.INCIDENT_CANDIDATE
    assert "STALE_PRIVACY_OBSERVATION" in result.reasons


def test_monitor_rejects_future_observation():
    obs = PrivacyControlObservation("o1", "asset-001", "PRIVACY_GATE", PrivacyStatus.PASS, NOW + timedelta(minutes=6), SHA, ())
    result = evaluate_privacy_observations(asset(), (obs,), now=NOW)
    assert result.status is MonitorStatus.INCIDENT_CANDIDATE
    assert "OBSERVATION_FROM_FUTURE" in result.reasons


def test_monitor_detects_duplicate_control_observations():
    o1 = PrivacyControlObservation("o1", "asset-001", "X", PrivacyStatus.PASS, NOW, SHA, ())
    o2 = PrivacyControlObservation("o2", "asset-001", "x", PrivacyStatus.PASS, NOW, "b" * 64, ())
    result = evaluate_privacy_observations(asset(), (o1, o2), now=NOW)
    assert result.status is MonitorStatus.INCIDENT_CANDIDATE
    assert any(reason.startswith("DUPLICATE_CONTROL_OBSERVATION") for reason in result.reasons)


def test_monitor_detects_asset_mismatch():
    obs = PrivacyControlObservation("o1", "other", "X", PrivacyStatus.PASS, NOW, SHA, ())
    assert evaluate_privacy_observations(asset(), (obs,), now=NOW).status is MonitorStatus.INCIDENT_CANDIDATE


def healthy_monitor():
    return PrivacyMonitoringReport(MonitorStatus.HEALTHY, (), None)


def test_evidence_snapshot_complete_when_bound_and_monitored():
    a = asset()
    lifecycle = initial_lifecycle_record(a, occurred_at=NOW, actor_id="u")
    result = build_privacy_evidence_snapshot(a, lifecycle, healthy_monitor(), generated_at=NOW, source_evidence_sha256=(SHA,), policy_version="privacy-v17", snapshot_id="s1")
    assert result.status is EvidenceAutomationStatus.COMPLETE
    assert result.snapshot is not None
    assert len(result.snapshot.fingerprint) == 64


def test_evidence_snapshot_blocks_unknown_monitoring():
    a = asset()
    lifecycle = initial_lifecycle_record(a, occurred_at=NOW, actor_id="u")
    result = build_privacy_evidence_snapshot(a, lifecycle, PrivacyMonitoringReport(MonitorStatus.UNKNOWN, ("x",), None), generated_at=NOW, source_evidence_sha256=(SHA,), policy_version="v", snapshot_id="s")
    assert result.status is EvidenceAutomationStatus.BLOCK
    assert result.snapshot is None


def test_evidence_snapshot_blocks_incident_candidate():
    a = asset()
    lifecycle = initial_lifecycle_record(a, occurred_at=NOW, actor_id="u")
    candidate = incident(PrivacyIncidentSeverity.MEDIUM, legal=False)
    monitor = PrivacyMonitoringReport(MonitorStatus.INCIDENT_CANDIDATE, ("x",), candidate)
    result = build_privacy_evidence_snapshot(a, lifecycle, monitor, generated_at=NOW, source_evidence_sha256=(SHA,), policy_version="v", snapshot_id="s")
    assert "OPEN_PRIVACY_INCIDENT_CANDIDATE" in result.reasons


def test_evidence_snapshot_blocks_wrong_lifecycle_binding():
    a = asset()
    other = asset(DataClass.INTERNAL, personal=False)
    # same asset id but fingerprint differs, which must be caught
    lifecycle = initial_lifecycle_record(other, occurred_at=NOW, actor_id="u")
    result = build_privacy_evidence_snapshot(a, lifecycle, healthy_monitor(), generated_at=NOW, source_evidence_sha256=(SHA,), policy_version="v", snapshot_id="s")
    assert result.status is EvidenceAutomationStatus.BLOCK


def test_evidence_snapshot_blocks_future_lifecycle_event():
    a = asset()
    lifecycle = initial_lifecycle_record(a, occurred_at=NOW + timedelta(minutes=1), actor_id="u")
    result = build_privacy_evidence_snapshot(a, lifecycle, healthy_monitor(), generated_at=NOW, source_evidence_sha256=(SHA,), policy_version="v", snapshot_id="s")
    assert "LIFECYCLE_EVENT_FROM_FUTURE" in result.reasons


def test_evidence_automation_cannot_enable_legal_notification_promotion_or_wagering():
    with pytest.raises(ValueError):
        EvidenceAutomationResult(EvidenceAutomationStatus.COMPLETE, (), None, automatic_legal_notification_enabled=True)
    with pytest.raises(ValueError):
        EvidenceAutomationResult(EvidenceAutomationStatus.COMPLETE, (), None, automatic_model_promotion_enabled=True)
    with pytest.raises(ValueError):
        EvidenceAutomationResult(EvidenceAutomationStatus.COMPLETE, (), None, automatic_wager_execution_enabled=True)


def test_privacy_monitor_cannot_enable_legal_notification_promotion_or_wagering():
    with pytest.raises(ValueError):
        PrivacyMonitoringReport(MonitorStatus.HEALTHY, (), None, automatic_legal_notification_enabled=True)
    with pytest.raises(ValueError):
        PrivacyMonitoringReport(MonitorStatus.HEALTHY, (), None, automatic_model_promotion_enabled=True)
    with pytest.raises(ValueError):
        PrivacyMonitoringReport(MonitorStatus.HEALTHY, (), None, automatic_wager_execution_enabled=True)


def test_privacy_evidence_ledger_append_and_verify(tmp_path):
    a = asset()
    lifecycle = initial_lifecycle_record(a, occurred_at=NOW, actor_id="u")
    snap = build_privacy_evidence_snapshot(a, lifecycle, healthy_monitor(), generated_at=NOW, source_evidence_sha256=(SHA,), policy_version="v", snapshot_id="s").snapshot
    ledger = PrivacyEvidenceLedger(tmp_path / "privacy.jsonl")
    digest = ledger.append(snap)
    ok, count, last = verify_privacy_evidence_ledger(tmp_path / "privacy.jsonl")
    assert ok is True and count == 1 and last == digest


def test_privacy_evidence_ledger_detects_tampering(tmp_path):
    a = asset()
    lifecycle = initial_lifecycle_record(a, occurred_at=NOW, actor_id="u")
    snap = build_privacy_evidence_snapshot(a, lifecycle, healthy_monitor(), generated_at=NOW, source_evidence_sha256=(SHA,), policy_version="v", snapshot_id="s").snapshot
    path = tmp_path / "privacy.jsonl"
    PrivacyEvidenceLedger(path).append(snap)
    row = json.loads(path.read_text(encoding="utf-8"))
    row["payload"]["policy_version"] = "tampered"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert verify_privacy_evidence_ledger(path)[0] is False


def test_privacy_evidence_ledger_refuses_append_when_corrupt(tmp_path):
    path = tmp_path / "privacy.jsonl"
    path.write_text('{"broken":true}\n', encoding="utf-8")
    a = asset()
    lifecycle = initial_lifecycle_record(a, occurred_at=NOW, actor_id="u")
    snap = build_privacy_evidence_snapshot(a, lifecycle, healthy_monitor(), generated_at=NOW, source_evidence_sha256=(SHA,), policy_version="v", snapshot_id="s").snapshot
    with pytest.raises(RuntimeError):
        PrivacyEvidenceLedger(path).append(snap)

def test_deleted_rejects_source_fingerprint_mismatch():
    a = asset()
    i, v, ac, ar = full_lifecycle(a)
    dp = transition_lifecycle(ar, LifecycleStage.DELETION_PENDING, occurred_at=NOW + timedelta(minutes=4), actor_id="u", reason="retention")
    bad = DeletionEvidence("del-bad", a.asset_id, NOW, NOW + timedelta(minutes=5), "u", "erase", DeletionStatus.COMPLETED, "c" * 64, "d" * 64, True)
    with pytest.raises(ValueError):
        transition_lifecycle(dp, LifecycleStage.DELETED, occurred_at=NOW + timedelta(minutes=6), actor_id="u", reason="done", deletion_evidence=bad)


def test_lifecycle_verifier_detects_manual_legal_hold_bypass():
    a = asset()
    i, v, ac, _ = full_lifecycle(a)
    held = transition_lifecycle(ac, LifecycleStage.QUARANTINED, occurred_at=NOW + timedelta(minutes=4), actor_id="legal", reason="hold", legal_hold=True)
    bypass = type(held)(held.asset_id, held.asset_fingerprint, LifecycleStage.DELETION_PENDING, NOW + timedelta(minutes=5), "attacker", "bypass", held.fingerprint, True)
    ok, reasons = verify_lifecycle_chain((i, v, ac, held, bypass))
    assert ok is False
    assert "LEGAL_HOLD_BYPASSED_IN_CHAIN" in reasons


def test_incident_cannot_close_while_required_notification_incomplete():
    d = incident(PrivacyIncidentSeverity.MEDIUM, legal=True)
    t = transition_incident(d, PrivacyIncidentState.TRIAGED, updated_at=NOW + timedelta(minutes=1))
    c = transition_incident(t, PrivacyIncidentState.CONTAINED, updated_at=NOW + timedelta(minutes=2))
    r = transition_incident(c, PrivacyIncidentState.REMEDIATED, updated_at=NOW + timedelta(minutes=3), root_cause="x", remediation_reference="r")
    with pytest.raises(ValueError):
        transition_incident(r, PrivacyIncidentState.CLOSED, updated_at=NOW + timedelta(minutes=4), legal_notification_status="NOTIFICATION_REQUIRED")


def test_incident_rejects_duplicate_evidence_references():
    with pytest.raises(ValueError):
        PrivacyIncident("i", PrivacyIncidentCategory.OTHER, PrivacyIncidentSeverity.LOW, PrivacyIncidentState.DETECTED, NOW, NOW, "s", "x", ("a",), False, False, (SHA, SHA))
