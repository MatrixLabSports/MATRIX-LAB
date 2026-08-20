from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from app.core.provider_endpoint_policy import (
    ProviderEndpointPolicy,
    build_provider_endpoint_policy,
)
from app.core.secret_reference import (
    SecretReference,
    build_secret_reference,
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


def _hex64(
    name: str,
    value: object,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
    ):
        raise ValueError(
            f"INVALID_{name}"
        )
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(
            f"INVALID_{name}"
        ) from error
    return value.lower()


@dataclass(frozen=True)
class ProviderSecurityDecision:
    status: str
    executable: bool
    run_id: str
    sport: str
    provider_key: str
    mode: str
    preflight_decision_fingerprint: str
    endpoint_policy_fingerprint: str
    secret_reference_fingerprint: str
    reason_codes: tuple[str, ...]
    decision_fingerprint: str

    def payload(
        self,
    ) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-security-decision/1"
            ),
            "status": self.status,
            "executable": (
                self.executable
            ),
            "run_id": self.run_id,
            "sport": self.sport,
            "provider_key": (
                self.provider_key
            ),
            "mode": self.mode,
            "preflight_decision_fingerprint": (
                self
                .preflight_decision_fingerprint
            ),
            "endpoint_policy_fingerprint": (
                self
                .endpoint_policy_fingerprint
            ),
            "secret_reference_fingerprint": (
                self
                .secret_reference_fingerprint
            ),
            "reason_codes": list(
                self.reason_codes
            ),
            "raw_secret_persisted": False,
            "raw_secret_logged": False,
            "certificate_verification_required": True,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "decision_fingerprint": (
                self.decision_fingerprint
            ),
        }


def evaluate_provider_security(
    *,
    run_id: str,
    sport: str,
    provider_key: str,
    mode: str,
    preflight_decision: object,
    endpoint_url: str,
    secret_reference: SecretReference,
) -> ProviderSecurityDecision:
    reasons: list[str] = []

    if (
        not isinstance(run_id, str)
        or not run_id
    ):
        reasons.append("INVALID_RUN_ID")

    if sport not in {
        "football",
        "tennis",
    }:
        reasons.append("INVALID_SPORT")

    if (
        not isinstance(
            provider_key,
            str,
        )
        or not provider_key
    ):
        reasons.append(
            "INVALID_PROVIDER_KEY"
        )

    if mode not in {
        "PRODUCTION",
        "BOOTSTRAP_PROBE",
    }:
        reasons.append(
            "INVALID_PROVIDER_MODE"
        )

    preflight_fp = _hex64(
        "PREFLIGHT_DECISION_FINGERPRINT",
        getattr(
            preflight_decision,
            "decision_fingerprint",
            None,
        ),
    )

    if (
        getattr(
            preflight_decision,
            "status",
            None,
        )
        != "EXECUTE"
        or getattr(
            preflight_decision,
            "executable",
            None,
        )
        is not True
    ):
        reasons.append(
            "PREFLIGHT_NOT_EXECUTABLE"
        )

    for name, expected in {
        "run_id": run_id,
        "sport": sport,
        "provider_key": (
            provider_key
        ),
        "mode": mode,
    }.items():
        if (
            getattr(
                preflight_decision,
                name,
                None,
            )
            != expected
        ):
            reasons.append(
                "PREFLIGHT_BINDING_MISMATCH:"
                f"{name}"
            )

    try:
        endpoint_policy = (
            build_provider_endpoint_policy(
                provider_key=(
                    provider_key
                ),
                endpoint_url=(
                    endpoint_url
                ),
            )
        )
    except ValueError as error:
        endpoint_policy = None
        reasons.append(
            f"ENDPOINT:{error}"
        )

    try:
        expected_secret_ref = (
            build_secret_reference(
                provider_key=(
                    secret_reference
                    .provider_key
                ),
                environment_variable=(
                    secret_reference
                    .environment_variable
                ),
                secret_type=(
                    secret_reference
                    .secret_type
                ),
            )
        )
    except Exception as error:
        expected_secret_ref = None
        reasons.append(
            f"SECRET_REFERENCE:{error}"
        )

    if (
        expected_secret_ref
        is not None
    ):
        if (
            expected_secret_ref
            != secret_reference
        ):
            reasons.append(
                "SECRET_REFERENCE_DERIVATION_MISMATCH"
            )

        if (
            secret_reference
            .provider_key
            != provider_key
        ):
            reasons.append(
                "SECRET_REFERENCE_PROVIDER_MISMATCH"
            )

    reasons = sorted(
        set(reasons)
    )

    status = (
        "EXECUTE"
        if not reasons
        else "QUARANTINE"
    )
    executable = (
        status == "EXECUTE"
    )

    endpoint_fp = (
        "0" * 64
        if endpoint_policy is None
        else endpoint_policy
        .policy_fingerprint
    )

    secret_fp = (
        "0" * 64
        if expected_secret_ref
        is None
        else secret_reference
        .reference_fingerprint
    )

    base = {
        "schema": (
            "matrix.provider-security-decision/1"
        ),
        "status": status,
        "executable": executable,
        "run_id": run_id,
        "sport": sport,
        "provider_key": (
            provider_key
        ),
        "mode": mode,
        "preflight_decision_fingerprint": (
            preflight_fp
        ),
        "endpoint_policy_fingerprint": (
            endpoint_fp
        ),
        "secret_reference_fingerprint": (
            secret_fp
        ),
        "reason_codes": reasons,
        "raw_secret_persisted": False,
        "raw_secret_logged": False,
        "certificate_verification_required": True,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return ProviderSecurityDecision(
        status=status,
        executable=executable,
        run_id=run_id,
        sport=sport,
        provider_key=provider_key,
        mode=mode,
        preflight_decision_fingerprint=(
            preflight_fp
        ),
        endpoint_policy_fingerprint=(
            endpoint_fp
        ),
        secret_reference_fingerprint=(
            secret_fp
        ),
        reason_codes=tuple(
            reasons
        ),
        decision_fingerprint=_sha(
            base
        ),
    )
