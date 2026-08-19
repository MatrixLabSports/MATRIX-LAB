from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from base64 import b64encode

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.release.canonical import canonical_sha256
from app.security.attestation import (
    AttestationPayload,
    SignedAttestation,
    TrustedKey,
    TrustStore,
    public_key_b64,
    sign_attestation,
)
from app.security.sca_contract import (
    SCAExecutionEvidence,
    SCAFinding,
    SCAStatus,
    Severity,
    evaluate_sca_contract,
)
from app.security.secret_rotation import (
    RotationEvidence,
    SecretMetadata,
    SecretRotationPolicy,
    SecretRotationStatus,
    evaluate_secret_rotation,
)
from app.security.trusted_supply_chain_gate import (
    TrustedSupplyChainInput,
    TrustedSupplyChainStatus,
    evaluate_trusted_supply_chain,
)

NOW = datetime(2026, 8, 18, 23, 34, tzinfo=timezone.utc)
H40 = "a" * 40
H64 = "b" * 64
H64C = "c" * 64
H64D = "d" * 64


def make_key(*, key_id="root-1", purposes=("release_attestation", "sca_attestation"), production=False, revoked_at=None):
    private = Ed25519PrivateKey.generate()
    trusted = TrustedKey(
        key_id=key_id,
        issuer="matrix-isolated-test-root",
        public_key_b64=public_key_b64(private),
        purposes=purposes,
        valid_from=NOW - timedelta(days=30),
        valid_until=NOW + timedelta(days=30),
        revoked_at=revoked_at,
        production_trusted=production,
    )
    return private, trusted


def payload(*, key_id="root-1", predicate_type="matrix/release", subject=H64, predicate=H64C, issued_at=None, expires_at=None):
    return AttestationPayload(
        subject_sha256=subject,
        predicate_type=predicate_type,
        predicate_sha256=predicate,
        issuer="matrix-isolated-test-root",
        key_id=key_id,
        issued_at=issued_at or NOW - timedelta(minutes=1),
        expires_at=expires_at or NOW + timedelta(hours=1),
        nonce="nonce-001",
    )


def test_attestation_round_trip_passes():
    private, trusted = make_key()
    signed = sign_attestation(private, payload())
    result = TrustStore({trusted.key_id: trusted}).verify(
        signed, now=NOW, required_purpose="release_attestation", expected_subject_sha256=H64, expected_predicate_sha256=H64C
    )
    assert result.passed is True


def test_tampered_attestation_signature_is_rejected():
    private, trusted = make_key()
    signed = sign_attestation(private, payload())
    tampered_payload = replace(signed.payload, predicate_sha256=H64D)
    tampered = SignedAttestation(tampered_payload, signed.signature_b64)
    result = TrustStore({trusted.key_id: trusted}).verify(tampered, now=NOW, required_purpose="release_attestation")
    assert result.passed is False
    assert "INVALID_SIGNATURE" in result.reasons


def test_attestation_wrong_subject_is_rejected():
    private, trusted = make_key()
    signed = sign_attestation(private, payload())
    result = TrustStore({trusted.key_id: trusted}).verify(
        signed, now=NOW, required_purpose="release_attestation", expected_subject_sha256=H64D
    )
    assert "ATTESTATION_SUBJECT_MISMATCH" in result.reasons


def test_attestation_expiry_is_rejected():
    private, trusted = make_key()
    signed = sign_attestation(private, payload(issued_at=NOW-timedelta(hours=2), expires_at=NOW-timedelta(hours=1)))
    result = TrustStore({trusted.key_id: trusted}).verify(signed, now=NOW, required_purpose="release_attestation")
    assert "ATTESTATION_EXPIRED" in result.reasons


def test_future_attestation_is_rejected():
    private, trusted = make_key()
    signed = sign_attestation(private, payload(issued_at=NOW+timedelta(hours=2), expires_at=NOW+timedelta(hours=3)))
    result = TrustStore({trusted.key_id: trusted}).verify(signed, now=NOW, required_purpose="release_attestation")
    assert "ATTESTATION_FROM_FUTURE" in result.reasons


def test_revoked_key_is_rejected():
    private, trusted = make_key(revoked_at=NOW - timedelta(seconds=1))
    signed = sign_attestation(private, payload())
    result = TrustStore({trusted.key_id: trusted}).verify(signed, now=NOW, required_purpose="release_attestation")
    assert "KEY_REVOKED" in result.reasons


def test_wrong_key_purpose_is_rejected():
    private, trusted = make_key(purposes=("sca_attestation",))
    signed = sign_attestation(private, payload())
    result = TrustStore({trusted.key_id: trusted}).verify(signed, now=NOW, required_purpose="release_attestation")
    assert "KEY_PURPOSE_NOT_ALLOWED" in result.reasons


def test_isolated_key_cannot_claim_production_trust():
    private, trusted = make_key(production=False)
    signed = sign_attestation(private, payload())
    result = TrustStore({trusted.key_id: trusted}).verify(
        signed, now=NOW, required_purpose="release_attestation", require_production_trust=True
    )
    assert "KEY_NOT_PRODUCTION_TRUSTED" in result.reasons


def test_production_trusted_key_can_satisfy_production_trust():
    private, trusted = make_key(production=True)
    signed = sign_attestation(private, payload())
    result = TrustStore({trusted.key_id: trusted}).verify(
        signed, now=NOW, required_purpose="release_attestation", require_production_trust=True
    )
    assert result.passed is True


def test_invalid_signature_encoding_rejected():
    with pytest.raises(ValueError):
        SignedAttestation(payload(), "not-base64")


def make_secret(*, name="API_FOOTBALL_KEY", version="v2", created=None, expires=None, enabled=True):
    return SecretMetadata(
        name=name,
        provider="vault-contract",
        version=version,
        created_at=created or NOW - timedelta(days=10),
        expires_at=expires or NOW + timedelta(days=20),
        enabled=enabled,
    )


def rotation(*, name="API_FOOTBALL_KEY", old="v1", new="v2", actor=True, revoked=True, validated=True, rotated=None):
    return RotationEvidence(
        secret_name=name,
        provider="vault-contract",
        previous_version=old,
        new_version=new,
        rotated_at=rotated or NOW - timedelta(days=1),
        actor_id="security-automation",
        actor_verified=actor,
        old_version_revoked=revoked,
        validation_passed=validated,
    )


POLICY = SecretRotationPolicy(max_age_days=60, warning_days_before_expiry=7, max_rotation_evidence_age_days=45)


def test_secret_rotation_passes_without_secret_material():
    result = evaluate_secret_rotation((make_secret(),), required_secret_names=("API_FOOTBALL_KEY",), rotation_evidence=(rotation(),), policy=POLICY, now=NOW)
    assert result.status is SecretRotationStatus.PASS


def test_missing_required_secret_blocks():
    result = evaluate_secret_rotation((), required_secret_names=("API_FOOTBALL_KEY",), rotation_evidence=(), policy=POLICY, now=NOW)
    assert result.status is SecretRotationStatus.BLOCK
    assert "MISSING_REQUIRED_SECRET:API_FOOTBALL_KEY" in result.reasons


def test_expired_secret_blocks():
    result = evaluate_secret_rotation((make_secret(expires=NOW-timedelta(seconds=1)),), required_secret_names=("API_FOOTBALL_KEY",), rotation_evidence=(), policy=POLICY, now=NOW)
    assert any(reason.startswith("SECRET_EXPIRED") for reason in result.reasons)


def test_old_secret_blocks():
    result = evaluate_secret_rotation((make_secret(created=NOW-timedelta(days=90), expires=NOW+timedelta(days=1)),), required_secret_names=("API_FOOTBALL_KEY",), rotation_evidence=(), policy=POLICY, now=NOW)
    assert any(reason.startswith("SECRET_MAX_AGE_EXCEEDED") for reason in result.reasons)


def test_secret_expiring_soon_is_watch():
    result = evaluate_secret_rotation((make_secret(expires=NOW+timedelta(days=2)),), required_secret_names=("API_FOOTBALL_KEY",), rotation_evidence=(), policy=POLICY, now=NOW)
    assert result.status is SecretRotationStatus.WATCH


@pytest.mark.parametrize("kwargs,expected", [
    ({"actor": False}, "ROTATION_ACTOR_NOT_VERIFIED"),
    ({"revoked": False}, "OLD_SECRET_VERSION_NOT_REVOKED"),
    ({"validated": False}, "ROTATED_SECRET_NOT_VALIDATED"),
])
def test_bad_rotation_evidence_blocks(kwargs, expected):
    result = evaluate_secret_rotation((make_secret(),), required_secret_names=("API_FOOTBALL_KEY",), rotation_evidence=(rotation(**kwargs),), policy=POLICY, now=NOW)
    assert result.status is SecretRotationStatus.BLOCK
    assert any(reason.startswith(expected) for reason in result.reasons)


def test_rotation_current_version_mismatch_blocks():
    result = evaluate_secret_rotation((make_secret(version="v3"),), required_secret_names=("API_FOOTBALL_KEY",), rotation_evidence=(rotation(new="v2"),), policy=POLICY, now=NOW)
    assert "ROTATION_CURRENT_VERSION_MISMATCH:API_FOOTBALL_KEY" in result.reasons


def finding(severity):
    return SCAFinding("CVE-2026-0001", "example", "1.0", severity, "1.1")


def sca(*, commit=H40, lock=H64, scanner="pip-audit", exit_code=0, findings=(), scanned=None, db=None):
    return SCAExecutionEvidence(
        scanner=scanner,
        scanner_version="2.9.0",
        database_updated_at=db or NOW-timedelta(hours=1),
        scanned_at=scanned or NOW-timedelta(minutes=10),
        source_commit_sha=commit,
        dependency_lock_sha256=lock,
        result_artifact_sha256=H64C,
        exit_code=exit_code,
        findings=tuple(findings),
    )


def eval_sca(value):
    return evaluate_sca_contract(value, now=NOW, expected_commit_sha=H40, expected_dependency_lock_sha256=H64, allowed_scanners=("pip-audit", "osv-scanner"))


def test_sca_clean_passes():
    assert eval_sca(sca()).status is SCAStatus.PASS


def test_sca_commit_mismatch_blocks():
    assert "SCA_SOURCE_COMMIT_MISMATCH" in eval_sca(sca(commit="c"*40)).reasons


def test_sca_lock_mismatch_blocks():
    assert "SCA_DEPENDENCY_LOCK_MISMATCH" in eval_sca(sca(lock=H64D)).reasons


def test_unapproved_scanner_blocks():
    assert "SCA_SCANNER_NOT_ALLOWED" in eval_sca(sca(scanner="mystery")).reasons


def test_nonzero_sca_exit_blocks():
    assert "SCA_SCANNER_NONZERO_EXIT" in eval_sca(sca(exit_code=2)).reasons


def test_stale_scan_blocks():
    assert "SCA_SCAN_STALE" in eval_sca(sca(scanned=NOW-timedelta(days=2))).reasons


def test_stale_db_blocks():
    assert "SCA_DATABASE_STALE" in eval_sca(sca(db=NOW-timedelta(days=2))).reasons


def test_future_sca_timestamp_blocks():
    assert "SCA_FUTURE_TIMESTAMP" in eval_sca(sca(scanned=NOW+timedelta(hours=1))).reasons


def test_high_vulnerability_blocks():
    assert "SCA_HIGH_VULNERABILITY" in eval_sca(sca(findings=(finding(Severity.HIGH),))).reasons


def test_critical_vulnerability_blocks():
    assert "SCA_CRITICAL_VULNERABILITY" in eval_sca(sca(findings=(finding(Severity.CRITICAL),))).reasons


def test_medium_vulnerability_is_watch():
    assert eval_sca(sca(findings=(finding(Severity.MEDIUM),))).status is SCAStatus.WATCH


def make_gate(*, production=False, secret_result=None, sca_result=None):
    release_private, release_key = make_key(key_id="release-key", purposes=("release_attestation",), production=production)
    sca_private, sca_key = make_key(key_id="sca-key", purposes=("sca_attestation",), production=production)
    release_payload = payload(key_id="release-key", predicate_type="matrix/release", subject=H64, predicate=H64C)
    sca_payload = payload(key_id="sca-key", predicate_type="matrix/sca", subject=H64D, predicate=H64)
    release_signed = sign_attestation(release_private, release_payload)
    sca_signed = sign_attestation(sca_private, sca_payload)
    rotation_result = secret_result or evaluate_secret_rotation((make_secret(),), required_secret_names=("API_FOOTBALL_KEY",), rotation_evidence=(rotation(),), policy=POLICY, now=NOW)
    sca_contract = sca_result or eval_sca(sca())
    return TrustedSupplyChainInput(
        release_attestation=release_signed,
        sca_attestation=sca_signed,
        trust_store=TrustStore({release_key.key_id: release_key, sca_key.key_id: sca_key}),
        expected_release_subject_sha256=H64,
        expected_release_predicate_sha256=H64C,
        expected_sca_subject_sha256=H64D,
        expected_sca_predicate_sha256=H64,
        secret_rotation=rotation_result,
        sca_contract=sca_contract,
        require_production_trust=production,
    )


def test_trusted_supply_chain_passes_for_integration_review():
    result = evaluate_trusted_supply_chain(make_gate(), now=NOW)
    assert result.status is TrustedSupplyChainStatus.PASS
    assert result.integration_review_eligible is True
    assert result.production_release_enabled is False
    assert result.automatic_wager_execution_enabled is False


def test_trusted_supply_chain_blocks_bad_release_subject():
    data = make_gate()
    data = replace(data, expected_release_subject_sha256=H64D)
    result = evaluate_trusted_supply_chain(data, now=NOW)
    assert result.status is TrustedSupplyChainStatus.BLOCK
    assert any("ATTESTATION_SUBJECT_MISMATCH" in reason for reason in result.reasons)


def test_trusted_supply_chain_blocks_secret_rotation_failure():
    failed = evaluate_secret_rotation((), required_secret_names=("API_FOOTBALL_KEY",), rotation_evidence=(), policy=POLICY, now=NOW)
    result = evaluate_trusted_supply_chain(make_gate(secret_result=failed), now=NOW)
    assert result.status is TrustedSupplyChainStatus.BLOCK


def test_trusted_supply_chain_watches_medium_sca():
    watched = eval_sca(sca(findings=(finding(Severity.MEDIUM),)))
    result = evaluate_trusted_supply_chain(make_gate(sca_result=watched), now=NOW)
    assert result.status is TrustedSupplyChainStatus.WATCH
    assert result.integration_review_eligible is False


def test_production_trust_requirement_blocks_test_root():
    data = make_gate(production=False)
    data = replace(data, require_production_trust=True)
    result = evaluate_trusted_supply_chain(data, now=NOW)
    assert result.status is TrustedSupplyChainStatus.BLOCK
    assert any("KEY_NOT_PRODUCTION_TRUSTED" in reason for reason in result.reasons)


def test_production_trusted_attestations_can_pass_trust_layer_but_not_release_production():
    result = evaluate_trusted_supply_chain(make_gate(production=True), now=NOW)
    assert result.status is TrustedSupplyChainStatus.PASS
    assert result.production_release_enabled is False


def test_rotation_evidence_fingerprint_changes_when_actor_changes():
    a = rotation()
    b = replace(a, actor_id="other-security-actor")
    assert a.fingerprint != b.fingerprint


def test_sca_fingerprint_changes_when_finding_changes():
    clean = sca()
    changed = sca(findings=(finding(Severity.LOW),))
    assert clean.fingerprint != changed.fingerprint


def test_attestation_payload_fingerprint_is_deterministic():
    assert payload().fingerprint == payload().fingerprint
