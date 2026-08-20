from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3
from typing import Any, Mapping

from app.core.provider_endpoint_policy import (
    build_provider_endpoint_policy,
)
from app.core.provider_security_gate import (
    evaluate_provider_security,
)
from app.core.secret_reference import (
    SecretReference,
    attest_secret_available_runtime,
)


def _canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


def _load_verified_preflight_evidence(
    *,
    store,
    run_id: str,
) -> Mapping[str, Any] | None:
    report = store.audit_integrity()

    if not report.ok:
        raise ValueError(
            "PROVIDER_PREFLIGHT_EVIDENCE_INTEGRITY_VIOLATION"
        )

    path = getattr(store, "path", None)
    if path is None:
        raise ValueError(
            "PROVIDER_PREFLIGHT_EVIDENCE_STORE_PATH_UNAVAILABLE"
        )

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT
                evidence_id,
                sport,
                provider_key,
                decision_fingerprint,
                payload_json,
                payload_sha256
            FROM provider_preflight_evidence
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    if row is None:
        return None

    (
        evidence_id,
        sport,
        provider_key,
        decision_fingerprint,
        payload_json,
        stored_sha,
    ) = row

    payload = json.loads(payload_json)
    actual_sha = sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()

    if actual_sha != stored_sha:
        raise ValueError(
            "PROVIDER_PREFLIGHT_EVIDENCE_PAYLOAD_HASH_MISMATCH"
        )

    for key, expected in {
        "evidence_id": evidence_id,
        "run_id": run_id,
        "sport": sport,
        "provider_key": provider_key,
        "decision_fingerprint": decision_fingerprint,
    }.items():
        if payload.get(key) != expected:
            raise ValueError(
                "PROVIDER_PREFLIGHT_EVIDENCE_BINDING_MISMATCH:"
                f"{key}"
            )

    return payload


@dataclass(frozen=True)
class AuthoritativeProviderSecurityDecision:
    status: str
    executable: bool
    run_id: str
    sport: str
    provider_key: str
    mode: str
    preflight_decision_fingerprint: str
    preflight_evidence_id: str
    baseline_security_decision_fingerprint: str
    endpoint_target_fingerprint: str
    secret_reference_fingerprint: str
    secret_availability_attestation_fingerprint: str
    reason_codes: tuple[str, ...]
    decision_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.authoritative-provider-security-decision/1"
            ),
            "status": self.status,
            "executable": self.executable,
            "run_id": self.run_id,
            "sport": self.sport,
            "provider_key": self.provider_key,
            "mode": self.mode,
            "preflight_decision_fingerprint": (
                self.preflight_decision_fingerprint
            ),
            "preflight_evidence_id": self.preflight_evidence_id,
            "baseline_security_decision_fingerprint": (
                self.baseline_security_decision_fingerprint
            ),
            "endpoint_target_fingerprint": (
                self.endpoint_target_fingerprint
            ),
            "secret_reference_fingerprint": (
                self.secret_reference_fingerprint
            ),
            "secret_availability_attestation_fingerprint": (
                self.secret_availability_attestation_fingerprint
            ),
            "reason_codes": list(self.reason_codes),
            "raw_secret_persisted": False,
            "raw_secret_logged": False,
            "secret_value_fingerprinted": False,
            "certificate_verification_required": True,
            "authoritative_for_future_provider_calls": True,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "decision_fingerprint": self.decision_fingerprint,
        }


def _decision_fingerprint(
    *,
    status: str,
    executable: bool,
    run_id: str,
    sport: str,
    provider_key: str,
    mode: str,
    preflight_decision_fingerprint: str,
    preflight_evidence_id: str,
    baseline_security_decision_fingerprint: str,
    endpoint_target_fingerprint: str,
    secret_reference_fingerprint: str,
    secret_availability_attestation_fingerprint: str,
    reason_codes: tuple[str, ...] | list[str],
) -> str:
    return _sha(
        {
            "schema": (
                "matrix.authoritative-provider-security-decision/1"
            ),
            "status": status,
            "executable": executable,
            "run_id": run_id,
            "sport": sport,
            "provider_key": provider_key,
            "mode": mode,
            "preflight_decision_fingerprint": (
                preflight_decision_fingerprint
            ),
            "preflight_evidence_id": preflight_evidence_id,
            "baseline_security_decision_fingerprint": (
                baseline_security_decision_fingerprint
            ),
            "endpoint_target_fingerprint": (
                endpoint_target_fingerprint
            ),
            "secret_reference_fingerprint": (
                secret_reference_fingerprint
            ),
            "secret_availability_attestation_fingerprint": (
                secret_availability_attestation_fingerprint
            ),
            "reason_codes": sorted(reason_codes),
            "raw_secret_persisted": False,
            "raw_secret_logged": False,
            "secret_value_fingerprinted": False,
            "certificate_verification_required": True,
            "authoritative_for_future_provider_calls": True,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }
    )


def evaluate_authoritative_provider_security(
    *,
    run_id: str,
    sport: str,
    provider_key: str,
    mode: str,
    preflight_decision: object,
    preflight_evidence_store,
    endpoint_url: str,
    secret_reference: SecretReference,
    secret_reference_registry,
) -> AuthoritativeProviderSecurityDecision:
    reasons: list[str] = []

    preflight_fp = "0" * 64
    preflight_evidence_id = "0" * 64
    baseline_security_fp = "0" * 64
    endpoint_target_fp = "0" * 64
    secret_reference_fp = "0" * 64
    secret_attestation_fp = "0" * 64

    try:
        preflight_fp = _hex64(
            "PREFLIGHT_DECISION_FINGERPRINT",
            getattr(
                preflight_decision,
                "decision_fingerprint",
                None,
            ),
        )
    except ValueError:
        reasons.append(
            "INVALID_PREFLIGHT_DECISION_FINGERPRINT"
        )

    try:
        baseline = evaluate_provider_security(
            run_id=run_id,
            sport=sport,
            provider_key=provider_key,
            mode=mode,
            preflight_decision=preflight_decision,
            endpoint_url=endpoint_url,
            secret_reference=secret_reference,
        )
    except Exception as error:
        baseline = None
        reasons.append(
            "BASELINE_SECURITY_ERROR:"
            f"{type(error).__name__}"
        )

    if baseline is None:
        reasons.append(
            "BASELINE_SECURITY_UNAVAILABLE"
        )
    else:
        baseline_security_fp = baseline.decision_fingerprint
        if (
            baseline.status != "EXECUTE"
            or baseline.executable is not True
        ):
            reasons.append(
                "BASELINE_SECURITY_NOT_EXECUTABLE"
            )

    try:
        evidence = _load_verified_preflight_evidence(
            store=preflight_evidence_store,
            run_id=run_id,
        )
    except Exception as error:
        evidence = None
        reasons.append(
            "PREFLIGHT_EVIDENCE_ERROR:"
            f"{type(error).__name__}"
        )

    if evidence is None:
        reasons.append(
            "MISSING_DURABLE_PREFLIGHT_EVIDENCE"
        )
    else:
        try:
            preflight_evidence_id = _hex64(
                "PREFLIGHT_EVIDENCE_ID",
                evidence["evidence_id"],
            )
        except (KeyError, ValueError):
            reasons.append(
                "INVALID_PREFLIGHT_EVIDENCE_ID"
            )

        if (
            evidence.get("decision_fingerprint")
            != preflight_fp
        ):
            reasons.append(
                "PREFLIGHT_EVIDENCE_DECISION_MISMATCH"
            )

        for key, expected in {
            "run_id": run_id,
            "sport": sport,
            "provider_key": provider_key,
            "mode": mode,
            "status": "EXECUTE",
            "executable": True,
        }.items():
            if evidence.get(key) != expected:
                reasons.append(
                    "PREFLIGHT_EVIDENCE_BINDING_MISMATCH:"
                    f"{key}"
                )

    try:
        endpoint_policy = build_provider_endpoint_policy(
            provider_key=provider_key,
            endpoint_url=endpoint_url,
        )
    except Exception as error:
        reasons.append(
            "ENDPOINT_POLICY_ERROR:"
            f"{type(error).__name__}"
        )
    else:
        endpoint_target_fp = (
            endpoint_policy.endpoint_target_fingerprint
        )

    try:
        secret_reference_fp = _hex64(
            "SECRET_REFERENCE_FINGERPRINT",
            secret_reference.reference_fingerprint,
        )
    except Exception:
        reasons.append(
            "INVALID_SECRET_REFERENCE_FINGERPRINT"
        )

    try:
        registered_reference = (
            secret_reference_registry.get_verified(
                secret_reference_fp
            )
        )
    except Exception as error:
        registered_reference = None
        reasons.append(
            "SECRET_REFERENCE_REGISTRY_ERROR:"
            f"{type(error).__name__}"
        )

    if registered_reference is None:
        reasons.append(
            "UNREGISTERED_SECRET_REFERENCE"
        )
    elif registered_reference != secret_reference:
        reasons.append(
            "SECRET_REFERENCE_REGISTRY_MISMATCH"
        )

    if (
        getattr(
            secret_reference,
            "provider_key",
            None,
        )
        != provider_key
    ):
        reasons.append(
            "SECRET_REFERENCE_PROVIDER_MISMATCH"
        )

    if registered_reference is not None:
        try:
            attestation = attest_secret_available_runtime(
                registered_reference
            )
        except Exception as error:
            reasons.append(
                "SECRET_RUNTIME_ERROR:"
                f"{type(error).__name__}"
            )
        else:
            secret_attestation_fp = (
                attestation.attestation_fingerprint
            )

    reasons = sorted(set(reasons))
    status = (
        "EXECUTE"
        if not reasons
        else "QUARANTINE"
    )
    executable = status == "EXECUTE"

    decision_fp = _decision_fingerprint(
        status=status,
        executable=executable,
        run_id=run_id,
        sport=sport,
        provider_key=provider_key,
        mode=mode,
        preflight_decision_fingerprint=preflight_fp,
        preflight_evidence_id=preflight_evidence_id,
        baseline_security_decision_fingerprint=(
            baseline_security_fp
        ),
        endpoint_target_fingerprint=endpoint_target_fp,
        secret_reference_fingerprint=secret_reference_fp,
        secret_availability_attestation_fingerprint=(
            secret_attestation_fp
        ),
        reason_codes=reasons,
    )

    return AuthoritativeProviderSecurityDecision(
        status=status,
        executable=executable,
        run_id=run_id,
        sport=sport,
        provider_key=provider_key,
        mode=mode,
        preflight_decision_fingerprint=preflight_fp,
        preflight_evidence_id=preflight_evidence_id,
        baseline_security_decision_fingerprint=(
            baseline_security_fp
        ),
        endpoint_target_fingerprint=endpoint_target_fp,
        secret_reference_fingerprint=secret_reference_fp,
        secret_availability_attestation_fingerprint=(
            secret_attestation_fp
        ),
        reason_codes=tuple(reasons),
        decision_fingerprint=decision_fp,
    )
