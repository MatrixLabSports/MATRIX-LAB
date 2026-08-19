from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.release import (
    REQUIRED_CI_STAGES,
    CIEvidenceSet,
    ReleaseGateInput,
    ReleaseGateStatus,
    ReleaseProvenance,
    StageEvidence,
    StageStatus,
    TestRunEvidence,
    build_deterministic_zip,
    canonical_json,
    canonical_sha256,
    evaluate_release_gate,
    file_sha256,
)
from app.security.dependencies import VulnerabilityScanEvidence
from app.security.security_gate import SecurityGateInput, evaluate_security_gate
from app.security.threat_catalog import matrix_security_baseline
from app.security.threat_model import Threat, Severity, evaluate_threats

NOW = datetime(2026, 8, 18, 23, 29, tzinfo=timezone.utc)
COMMIT = "a" * 40
HEX = "b" * 64


def stage(name: str, **overrides) -> StageEvidence:
    values = dict(
        stage=name,
        status=StageStatus.PASS,
        commit_sha=COMMIT,
        observed_at=NOW - timedelta(minutes=5),
        evidence_sha256=canonical_sha256({"stage": name, "result": "pass"}),
        tool="matrix-ci",
        tool_version="13.0",
    )
    values.update(overrides)
    return StageEvidence(**values)


def good_ci(**overrides) -> CIEvidenceSet:
    values = dict(commit_sha=COMMIT, stages=tuple(stage(name) for name in REQUIRED_CI_STAGES))
    values.update(overrides)
    return CIEvidenceSet(**values)


def good_security(now=NOW, watch=False):
    threat_report = evaluate_threats(matrix_security_baseline())
    if watch:
        threat_report = evaluate_threats([
            Threat("REVIEW", "a", "b", "c", Severity.HIGH, ("mitigation",), residual_risk_accepted=True)
        ])
    scan = VulnerabilityScanEvidence(
        scanner="pip-audit",
        scanner_version="X.Y",
        database_updated_at=now - timedelta(hours=1),
        scanned_at=now - timedelta(minutes=30),
        critical_count=0,
        high_count=0,
    )
    return evaluate_security_gate(
        SecurityGateInput(
            threat_report=threat_report,
            secret_findings=(),
            config_integrity_ok=True,
            dependency_lock_ok=True,
            vulnerability_scan=scan,
            environments_separated=True,
            access_logging_enabled=True,
            least_privilege_enforced=True,
        ),
        now=now,
    )


def make_artifact(tmp_path: Path, text="release") -> Path:
    artifact = tmp_path / "release.zip"
    artifact.write_bytes(text.encode("utf-8"))
    return artifact


def provenance(artifact: Path, ci: CIEvidenceSet, **overrides) -> ReleaseProvenance:
    values = dict(
        release_id="matrix-v13-test",
        source_repository="MatrixLabSports/MATRIX-LAB-SPORTS",
        commit_sha=COMMIT,
        source_tree_clean=True,
        source_commit_verified=True,
        builder_id="matrix-isolated-builder-v13",
        builder_identity_verified=True,
        build_started_at=NOW - timedelta(minutes=10),
        build_finished_at=NOW - timedelta(minutes=8),
        source_archive_sha256="1" * 64,
        build_recipe_sha256="2" * 64,
        dependency_lock_sha256="3" * 64,
        environment_lock_sha256="4" * 64,
        artifact_sha256=file_sha256(artifact),
        ci_evidence_sha256=ci.fingerprint,
        security_evidence_sha256="5" * 64,
        rollback_plan_sha256="6" * 64,
    )
    values.update(overrides)
    return ReleaseProvenance(**values)


def gate_input(tmp_path: Path, **overrides) -> ReleaseGateInput:
    ci = overrides.pop("ci_evidence", good_ci())
    artifact = overrides.pop("artifact_path", make_artifact(tmp_path))
    values = dict(
        provenance=provenance(artifact, ci),
        artifact_path=artifact,
        ci_evidence=ci,
        tests=TestRunEvidence(passed=100, failed=0, errors=0, skipped=1, duration_ms=500),
        security_result=good_security(),
        release_notes_present=True,
        rollback_plan_present=True,
        evidence_bundle_verified=True,
    )
    values.update(overrides)
    return ReleaseGateInput(**values)


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_canonical_fingerprint_rejects_float():
    with pytest.raises(TypeError):
        canonical_sha256({"ratio": 0.1})


def test_stage_requires_known_name():
    with pytest.raises(ValueError):
        stage("UNKNOWN")


def test_stage_requires_aware_time():
    with pytest.raises(ValueError):
        stage("TESTS", observed_at=datetime(2026, 8, 18))


def test_stage_requires_real_git_sha_shape():
    with pytest.raises(ValueError):
        stage("TESTS", commit_sha="abc")


def test_ci_rejects_duplicate_stage():
    s = stage("TESTS")
    with pytest.raises(ValueError):
        CIEvidenceSet(COMMIT, (s, s))


def test_ci_rejects_cross_commit_evidence():
    with pytest.raises(ValueError):
        CIEvidenceSet(COMMIT, (stage("TESTS", commit_sha="c" * 40),))


def test_ci_reports_missing_required_stages():
    ci = CIEvidenceSet(COMMIT, (stage("TESTS"),))
    assert "SECRET_SCAN" in ci.missing_required_stages()


def test_ci_reports_failed_stage():
    ci = CIEvidenceSet(COMMIT, (stage("TESTS", status=StageStatus.FAIL),))
    assert ci.failed_stages() == ("TESTS",)


def test_ci_reports_stale_stage():
    ci = CIEvidenceSet(COMMIT, (stage("TESTS", observed_at=NOW - timedelta(days=2)),))
    assert ci.stale_stages(now=NOW, max_age_hours=24) == ("TESTS",)


def test_ci_reports_future_stage_as_invalid_age():
    ci = CIEvidenceSet(COMMIT, (stage("TESTS", observed_at=NOW + timedelta(minutes=1)),))
    assert ci.stale_stages(now=NOW, max_age_hours=24) == ("TESTS",)


def test_ci_fingerprint_independent_of_stage_order():
    a = stage("TESTS")
    b = stage("SECRET_SCAN")
    assert CIEvidenceSet(COMMIT, (a, b)).fingerprint == CIEvidenceSet(COMMIT, (b, a)).fingerprint


def test_test_evidence_requires_non_empty_run():
    with pytest.raises(ValueError):
        TestRunEvidence(0, 0, 0, 0, 0)


def test_test_evidence_clean_requires_no_failures_or_errors():
    assert TestRunEvidence(1, 0, 0, 0, 1).clean
    assert not TestRunEvidence(1, 1, 0, 0, 1).clean
    assert not TestRunEvidence(1, 0, 1, 0, 1).clean


def test_provenance_rejects_dirty_flag_non_boolean(tmp_path):
    artifact = make_artifact(tmp_path)
    ci = good_ci()
    with pytest.raises(TypeError):
        provenance(artifact, ci, source_tree_clean=1)


def test_provenance_rejects_end_before_start(tmp_path):
    artifact = make_artifact(tmp_path)
    ci = good_ci()
    with pytest.raises(ValueError):
        provenance(
            artifact,
            ci,
            build_started_at=NOW,
            build_finished_at=NOW - timedelta(minutes=1),
        )


def test_provenance_fingerprint_changes_when_artifact_changes(tmp_path):
    artifact = make_artifact(tmp_path, "a")
    ci = good_ci()
    p1 = provenance(artifact, ci)
    artifact.write_text("b", encoding="utf-8")
    p2 = provenance(artifact, ci)
    assert p1.fingerprint != p2.fingerprint


def test_deterministic_bundle_same_input_same_hash(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "b.txt").write_text("B", encoding="utf-8")
    (root / "a.txt").write_text("A", encoding="utf-8")
    first = build_deterministic_zip(root, tmp_path / "one.zip")
    second = build_deterministic_zip(root, tmp_path / "two.zip")
    assert first.sha256 == second.sha256
    assert first.file_count == 2


def test_deterministic_bundle_changes_when_content_changes(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    f = root / "a.txt"
    f.write_text("A", encoding="utf-8")
    first = build_deterministic_zip(root, tmp_path / "one.zip")
    f.write_text("B", encoding="utf-8")
    second = build_deterministic_zip(root, tmp_path / "two.zip")
    assert first.sha256 != second.sha256


def test_bundle_refuses_empty_directory(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    with pytest.raises(ValueError):
        build_deterministic_zip(root, tmp_path / "x.zip")


def test_bundle_refuses_symlink_file(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("secret", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available")
    with pytest.raises(ValueError):
        build_deterministic_zip(root, tmp_path / "x.zip")


def test_bundle_excludes_pycache(tmp_path):
    root = tmp_path / "src"
    (root / "__pycache__").mkdir(parents=True)
    (root / "__pycache__" / "x.pyc").write_bytes(b"compiled")
    (root / "x.py").write_text("x=1\n", encoding="utf-8")
    result = build_deterministic_zip(root, tmp_path / "x.zip")
    assert result.file_count == 1


def test_release_gate_passes_complete_evidence(tmp_path):
    result = evaluate_release_gate(gate_input(tmp_path), now=NOW)
    assert result.status is ReleaseGateStatus.PASS
    assert result.integration_review_eligible is True


def test_release_gate_never_enables_production_or_wagering(tmp_path):
    result = evaluate_release_gate(gate_input(tmp_path), now=NOW)
    assert result.production_release_enabled is False
    assert result.automatic_model_promotion_enabled is False
    assert result.automatic_wager_execution_enabled is False


def test_release_gate_blocks_dirty_source(tmp_path):
    data = gate_input(tmp_path)
    p = ReleaseProvenance(**{**data.provenance.__dict__, "source_tree_clean": False})
    r = evaluate_release_gate(ReleaseGateInput(**{**data.__dict__, "provenance": p}), now=NOW)
    assert r.status is ReleaseGateStatus.BLOCK
    assert "SOURCE_TREE_NOT_CLEAN" in r.reasons



def test_release_gate_blocks_unverified_source_commit(tmp_path):
    data = gate_input(tmp_path)
    p = ReleaseProvenance(**{**data.provenance.__dict__, "source_commit_verified": False})
    r = evaluate_release_gate(ReleaseGateInput(**{**data.__dict__, "provenance": p}), now=NOW)
    assert r.status is ReleaseGateStatus.BLOCK
    assert "SOURCE_COMMIT_NOT_VERIFIED" in r.reasons


def test_release_gate_blocks_unverified_builder_identity(tmp_path):
    data = gate_input(tmp_path)
    p = ReleaseProvenance(**{**data.provenance.__dict__, "builder_identity_verified": False})
    r = evaluate_release_gate(ReleaseGateInput(**{**data.__dict__, "provenance": p}), now=NOW)
    assert r.status is ReleaseGateStatus.BLOCK
    assert "BUILDER_IDENTITY_NOT_VERIFIED" in r.reasons

def test_release_gate_blocks_artifact_tamper(tmp_path):
    data = gate_input(tmp_path)
    data.artifact_path.write_text("tampered", encoding="utf-8")
    r = evaluate_release_gate(data, now=NOW)
    assert r.status is ReleaseGateStatus.BLOCK
    assert "RELEASE_ARTIFACT_HASH_MISMATCH" in r.reasons


def test_release_gate_blocks_missing_stage(tmp_path):
    ci = CIEvidenceSet(COMMIT, tuple(stage(name) for name in REQUIRED_CI_STAGES if name != "SECRET_SCAN"))
    artifact = make_artifact(tmp_path)
    data = gate_input(tmp_path, ci_evidence=ci, artifact_path=artifact)
    data = ReleaseGateInput(**{**data.__dict__, "provenance": provenance(artifact, ci)})
    r = evaluate_release_gate(data, now=NOW)
    assert "MISSING_CI_STAGE:SECRET_SCAN" in r.reasons


def test_release_gate_blocks_failed_stage(tmp_path):
    stages = [stage(name, status=StageStatus.FAIL if name == "TESTS" else StageStatus.PASS) for name in REQUIRED_CI_STAGES]
    ci = CIEvidenceSet(COMMIT, tuple(stages))
    artifact = make_artifact(tmp_path)
    data = gate_input(tmp_path, ci_evidence=ci, artifact_path=artifact)
    data = ReleaseGateInput(**{**data.__dict__, "provenance": provenance(artifact, ci)})
    r = evaluate_release_gate(data, now=NOW)
    assert "FAILED_CI_STAGE:TESTS" in r.reasons


def test_release_gate_blocks_stale_stage(tmp_path):
    stages = [stage(name, observed_at=NOW - timedelta(days=2) if name == "VULNERABILITY_SCAN" else NOW) for name in REQUIRED_CI_STAGES]
    ci = CIEvidenceSet(COMMIT, tuple(stages))
    artifact = make_artifact(tmp_path)
    data = gate_input(tmp_path, ci_evidence=ci, artifact_path=artifact)
    data = ReleaseGateInput(**{**data.__dict__, "provenance": provenance(artifact, ci)})
    r = evaluate_release_gate(data, now=NOW)
    assert "STALE_OR_FUTURE_CI_STAGE:VULNERABILITY_SCAN" in r.reasons


def test_release_gate_blocks_ci_fingerprint_mismatch(tmp_path):
    data = gate_input(tmp_path)
    p = ReleaseProvenance(**{**data.provenance.__dict__, "ci_evidence_sha256": "f" * 64})
    r = evaluate_release_gate(ReleaseGateInput(**{**data.__dict__, "provenance": p}), now=NOW)
    assert "CI_EVIDENCE_FINGERPRINT_MISMATCH" in r.reasons


def test_release_gate_blocks_commit_mismatch(tmp_path):
    ci = good_ci()
    artifact = make_artifact(tmp_path)
    p = provenance(artifact, ci, commit_sha="c" * 40)
    data = gate_input(tmp_path, ci_evidence=ci, artifact_path=artifact, provenance=p)
    r = evaluate_release_gate(data, now=NOW)
    assert "PROVENANCE_CI_COMMIT_MISMATCH" in r.reasons


def test_release_gate_blocks_failed_test_summary(tmp_path):
    data = gate_input(tmp_path, tests=TestRunEvidence(10, 1, 0, 0, 100))
    r = evaluate_release_gate(data, now=NOW)
    assert "TEST_RUN_NOT_CLEAN" in r.reasons


def test_release_gate_security_watch_requires_review(tmp_path):
    r = evaluate_release_gate(gate_input(tmp_path, security_result=good_security(watch=True)), now=NOW)
    assert r.status is ReleaseGateStatus.WATCH
    assert r.integration_review_eligible is False


def test_release_gate_security_block_blocks(tmp_path):
    security = good_security()
    blocked = type(security)(status=security.status.BLOCK, reasons=("X",))
    r = evaluate_release_gate(gate_input(tmp_path, security_result=blocked), now=NOW)
    assert r.status is ReleaseGateStatus.BLOCK
    assert "SECURITY_GATE_BLOCKED" in r.reasons


@pytest.mark.parametrize(
    "field,reason",
    [
        ("release_notes_present", "RELEASE_NOTES_MISSING"),
        ("rollback_plan_present", "ROLLBACK_PLAN_MISSING"),
        ("evidence_bundle_verified", "EVIDENCE_BUNDLE_NOT_VERIFIED"),
    ],
)
def test_release_gate_blocks_missing_release_control(tmp_path, field, reason):
    data = gate_input(tmp_path, **{field: False})
    r = evaluate_release_gate(data, now=NOW)
    assert r.status is ReleaseGateStatus.BLOCK
    assert reason in r.reasons
