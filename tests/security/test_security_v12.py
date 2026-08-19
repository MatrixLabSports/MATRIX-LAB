from datetime import datetime, timedelta, timezone
import pytest

from app.security.config_integrity import ConfigIntegrityCheck, canonical_json, config_sha256
from app.security.dependencies import parse_locked_dependencies, VulnerabilityScanEvidence
from app.security.rbac import Principal, Permission, is_allowed, require
from app.security.secrets import EnvironmentSecretRef, scan_text
from app.security.security_gate import SecurityGateInput, SecurityStatus, evaluate_security_gate
from app.security.threat_catalog import matrix_security_baseline
from app.security.threat_model import Severity, Threat, evaluate_threats

NOW = datetime(2026, 8, 18, 23, 25, tzinfo=timezone.utc)


def good_scan(**overrides):
    values = dict(
        scanner="pip-audit",
        scanner_version="X.Y",
        database_updated_at=NOW - timedelta(hours=1),
        scanned_at=NOW - timedelta(minutes=30),
        critical_count=0,
        high_count=0,
    )
    values.update(overrides)
    return VulnerabilityScanEvidence(**values)


def good_gate(**overrides):
    values = dict(
        threat_report=evaluate_threats(matrix_security_baseline()),
        secret_findings=(),
        config_integrity_ok=True,
        dependency_lock_ok=True,
        vulnerability_scan=good_scan(),
        environments_separated=True,
        access_logging_enabled=True,
        least_privilege_enforced=True,
    )
    values.update(overrides)
    return SecurityGateInput(**values)


def test_baseline_threat_catalog_passes():
    assert evaluate_threats(matrix_security_baseline()).passed


def test_unmitigated_critical_threat_blocks():
    r = evaluate_threats([Threat("X", "a", "b", "c", Severity.CRITICAL, ())])
    assert r.blocking_threat_ids == ("X",)


def test_unmitigated_medium_is_review():
    r = evaluate_threats([Threat("X", "a", "b", "c", Severity.MEDIUM, ())])
    assert r.review_threat_ids == ("X",)


def test_duplicate_threat_id_rejected():
    t = Threat("X", "a", "b", "c", Severity.LOW, ())
    with pytest.raises(ValueError):
        evaluate_threats([t, t])


def test_hardcoded_api_key_detected():
    assert scan_text('API_KEY = "1234567890abcdef"')


def test_placeholder_secret_not_flagged():
    assert scan_text('API_KEY = "placeholder"') == ()


def test_private_key_detected():
    assert scan_text('-----BEGIN PRIVATE KEY-----')[0].kind == "PRIVATE_KEY"


def test_uri_credentials_detected():
    assert scan_text('postgres://user:password@localhost/db')[0].kind == "URI_CREDENTIALS"


def test_environment_secret_resolves():
    ref = EnvironmentSecretRef("API_SECRET", min_length=8)
    assert ref.resolve({"API_SECRET": "12345678"}) == "12345678"


def test_environment_secret_missing_fails():
    with pytest.raises(RuntimeError):
        EnvironmentSecretRef("API_SECRET").resolve({})


def test_environment_secret_short_fails():
    with pytest.raises(RuntimeError):
        EnvironmentSecretRef("API_SECRET", min_length=8).resolve({"API_SECRET": "tiny"})


def test_environment_secret_name_policy():
    with pytest.raises(ValueError):
        EnvironmentSecretRef("FOO_VALUE")


def test_canonical_config_order_independent():
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_config_hash_changes_when_content_changes():
    assert config_sha256({"a": 1}) != config_sha256({"a": 2})


def test_config_integrity_verifies():
    config = {"mode": "research", "wagering": False}
    assert ConfigIntegrityCheck(config_sha256(config)).verify(config)


def test_config_integrity_detects_tamper():
    check = ConfigIntegrityCheck(config_sha256({"mode": "research"}))
    assert not check.verify({"mode": "production"})


def test_reader_is_default_deny_for_run():
    p = Principal("u1", ("reader",))
    assert not is_allowed(p, Permission.RUN_RESEARCH)


def test_analyst_can_run_research():
    p = Principal("u1", ("analyst",))
    assert is_allowed(p, Permission.RUN_RESEARCH)


def test_security_admin_cannot_submit_human_review():
    p = Principal("sec", ("security_admin",))
    assert not is_allowed(p, Permission.SUBMIT_HUMAN_REVIEW)


def test_require_denies_missing_permission():
    with pytest.raises(PermissionError):
        require(Principal("u1", ("reader",)), Permission.VIEW_AUDIT)


def test_unknown_role_rejected():
    with pytest.raises(ValueError):
        Principal("u1", ("superuser",))


def test_dependency_lock_requires_exact_version_and_hash():
    deps = parse_locked_dependencies(["requests==2.32.5 --hash=sha256:" + "a" * 64])
    assert deps[0].version == "2.32.5"


def test_dependency_without_hash_rejected():
    with pytest.raises(ValueError):
        parse_locked_dependencies(["requests==2.32.5"])


def test_dependency_range_rejected():
    with pytest.raises(ValueError):
        parse_locked_dependencies(["requests>=2.32 --hash=sha256:" + "a" * 64])


def test_duplicate_dependency_rejected():
    line = "requests==2.32.5 --hash=sha256:" + "a" * 64
    with pytest.raises(ValueError):
        parse_locked_dependencies([line, line])


def test_fresh_zero_high_critical_scan_accepted():
    assert good_scan().acceptable(now=NOW, max_scan_age_hours=24, max_db_age_hours=24)


def test_high_vulnerability_blocks_scan():
    assert not good_scan(high_count=1).acceptable(now=NOW, max_scan_age_hours=24, max_db_age_hours=24)


def test_stale_scan_rejected():
    assert not good_scan(scanned_at=NOW - timedelta(days=2)).acceptable(now=NOW, max_scan_age_hours=24, max_db_age_hours=24)


def test_stale_vulnerability_db_rejected():
    assert not good_scan(database_updated_at=NOW - timedelta(days=2)).acceptable(now=NOW, max_scan_age_hours=24, max_db_age_hours=24)


def test_future_scan_timestamp_rejected():
    assert not good_scan(scanned_at=NOW + timedelta(minutes=1)).acceptable(now=NOW, max_scan_age_hours=24, max_db_age_hours=24)


def test_security_gate_passes_good_evidence():
    r = evaluate_security_gate(good_gate(), now=NOW)
    assert r.status == SecurityStatus.PASS


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("config_integrity_ok", False, "CONFIG_INTEGRITY_FAILURE"),
        ("dependency_lock_ok", False, "DEPENDENCY_LOCK_FAILURE"),
        ("environments_separated", False, "ENVIRONMENT_SEPARATION_MISSING"),
        ("access_logging_enabled", False, "ACCESS_LOGGING_MISSING"),
        ("least_privilege_enforced", False, "LEAST_PRIVILEGE_MISSING"),
    ],
)
def test_security_gate_blocks_required_control_failure(field, value, reason):
    r = evaluate_security_gate(good_gate(**{field: value}), now=NOW)
    assert r.status == SecurityStatus.BLOCK
    assert reason in r.reasons


def test_security_gate_blocks_secret_findings():
    findings = scan_text('TOKEN = "abcdefgh12345678"')
    r = evaluate_security_gate(good_gate(secret_findings=findings), now=NOW)
    assert r.status == SecurityStatus.BLOCK
    assert "HARDCODED_SECRET_EVIDENCE" in r.reasons


def test_security_gate_blocks_missing_vulnerability_evidence():
    r = evaluate_security_gate(good_gate(vulnerability_scan=None), now=NOW)
    assert r.status == SecurityStatus.BLOCK


def test_security_gate_blocks_unacceptable_vulnerability_scan():
    r = evaluate_security_gate(good_gate(vulnerability_scan=good_scan(critical_count=1)), now=NOW)
    assert r.status == SecurityStatus.BLOCK


def test_security_gate_watch_for_residual_review_only():
    report = evaluate_threats([Threat("X", "a", "b", "c", Severity.HIGH, ("m",), residual_risk_accepted=True)])
    r = evaluate_security_gate(good_gate(threat_report=report), now=NOW)
    assert r.status == SecurityStatus.WATCH


def test_security_gate_never_enables_promotion_or_wagering():
    r = evaluate_security_gate(good_gate(), now=NOW)
    assert r.automatic_promotion_enabled is False
    assert r.automatic_wager_execution_enabled is False
