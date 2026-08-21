from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from app.core.provider_activation_readiness import (
    ProviderActivationReadinessCertification,
    verify_provider_activation_readiness_certification,
)
from app.core.provider_interruption_recovery import (
    ProviderRecoveredAttemptState,
)
from app.providers.api_football.shadow_runtime import (
    ApiFootballShadowReadiness,
    ApiFootballShadowRequest,
)


def _json(value: Any) -> str:
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
        _json(value).encode(
            "utf-8"
        )
    ).hexdigest()


@dataclass(frozen=True)
class ProviderActivationRehearsalCertification:
    status: str
    activation_readiness_fingerprint: str
    shadow_mode: str
    shadow_request_count: int
    governed_shadow_verified: bool
    zero_network_calls: bool
    zero_secret_resolution: bool
    zero_network_permits: bool
    interruption_recovery_fail_closed: bool
    real_provider_execution_authorized: bool
    blockers: tuple[str, ...]
    certification_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-activation-rehearsal-certification/1"
            ),
            "status": self.status,
            "activation_readiness_fingerprint": (
                self.activation_readiness_fingerprint
            ),
            "shadow_mode": self.shadow_mode,
            "shadow_request_count": (
                self.shadow_request_count
            ),
            "governed_shadow_verified": (
                self.governed_shadow_verified
            ),
            "zero_network_calls": (
                self.zero_network_calls
            ),
            "zero_secret_resolution": (
                self.zero_secret_resolution
            ),
            "zero_network_permits": (
                self.zero_network_permits
            ),
            "interruption_recovery_fail_closed": (
                self.interruption_recovery_fail_closed
            ),
            "blockers": list(
                self.blockers
            ),
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "certification_fingerprint": (
                self.certification_fingerprint
            ),
        }


def _base(
    *,
    status: str,
    activation_readiness_fingerprint: str,
    shadow_mode: str,
    shadow_request_count: int,
    governed_shadow_verified: bool,
    zero_network_calls: bool,
    zero_secret_resolution: bool,
    zero_network_permits: bool,
    interruption_recovery_fail_closed: bool,
    blockers: Sequence[str],
) -> Mapping[str, Any]:
    return {
        "schema": (
            "matrix.provider-activation-rehearsal-certification-id/1"
        ),
        "status": status,
        "activation_readiness_fingerprint": (
            activation_readiness_fingerprint
        ),
        "shadow_mode": shadow_mode,
        "shadow_request_count": (
            shadow_request_count
        ),
        "governed_shadow_verified": (
            governed_shadow_verified
        ),
        "zero_network_calls": (
            zero_network_calls
        ),
        "zero_secret_resolution": (
            zero_secret_resolution
        ),
        "zero_network_permits": (
            zero_network_permits
        ),
        "interruption_recovery_fail_closed": (
            interruption_recovery_fail_closed
        ),
        "blockers": list(
            blockers
        ),
        "real_provider_execution_authorized": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }


def verify_provider_activation_rehearsal_certification(
    certification: ProviderActivationRehearsalCertification,
) -> ProviderActivationRehearsalCertification:
    if not isinstance(
        certification,
        ProviderActivationRehearsalCertification,
    ):
        raise ValueError(
            "INVALID_PROVIDER_ACTIVATION_REHEARSAL_CERTIFICATION"
        )

    expected_status = (
        "REHEARSAL_CERTIFIED_FAIL_CLOSED"
        if all(
            (
                certification.governed_shadow_verified,
                certification.zero_network_calls,
                certification.zero_secret_resolution,
                certification.zero_network_permits,
                certification.interruption_recovery_fail_closed,
                certification.shadow_request_count
                > 0,
            )
        )
        else "NOT_CERTIFIED"
    )

    if (
        certification.status
        != expected_status
    ):
        raise ValueError(
            "PROVIDER_ACTIVATION_REHEARSAL_STATUS_MISMATCH"
        )

    if (
        certification.real_provider_execution_authorized
        is not False
    ):
        raise ValueError(
            "REAL_PROVIDER_EXECUTION_MUST_REMAIN_DISABLED"
        )

    expected = _sha(
        _base(
            status=certification.status,
            activation_readiness_fingerprint=(
                certification.activation_readiness_fingerprint
            ),
            shadow_mode=(
                certification.shadow_mode
            ),
            shadow_request_count=(
                certification.shadow_request_count
            ),
            governed_shadow_verified=(
                certification.governed_shadow_verified
            ),
            zero_network_calls=(
                certification.zero_network_calls
            ),
            zero_secret_resolution=(
                certification.zero_secret_resolution
            ),
            zero_network_permits=(
                certification.zero_network_permits
            ),
            interruption_recovery_fail_closed=(
                certification.interruption_recovery_fail_closed
            ),
            blockers=(
                certification.blockers
            ),
        )
    )

    if (
        expected
        != certification.certification_fingerprint
    ):
        raise ValueError(
            "PROVIDER_ACTIVATION_REHEARSAL_FINGERPRINT_MISMATCH"
        )

    return certification


def certify_provider_activation_rehearsal(
    *,
    activation_readiness: ProviderActivationReadinessCertification,
    shadow_readiness: ApiFootballShadowReadiness,
    shadow_requests: Sequence[
        ApiFootballShadowRequest
    ],
    interruption_states: Sequence[
        ProviderRecoveredAttemptState
    ],
) -> ProviderActivationRehearsalCertification:
    readiness = (
        verify_provider_activation_readiness_certification(
            activation_readiness
        )
    )

    requests = tuple(
        shadow_requests
    )
    states = tuple(
        interruption_states
    )

    governed_shadow_verified = (
        readiness.status
        == "TECHNICALLY_READY_RIGHTS_BLOCKED"
        and isinstance(
            shadow_readiness,
            ApiFootballShadowReadiness,
        )
        and shadow_readiness.mode
        in {
            "DRY_RUN",
            "SHADOW",
        }
        and shadow_readiness.governed_request_client_verified
        is True
        and shadow_readiness.governed_transport_topology_verified
        is True
        and shadow_readiness.network_authority_type_verified
        is True
        and shadow_readiness.external_network_allowed
        is False
        and shadow_readiness.real_provider_execution_authorized
        is False
    )

    valid_requests = (
        bool(
            requests
        )
        and all(
            isinstance(
                request,
                ApiFootballShadowRequest,
            )
            and request.governed_request_client_used
            is True
            and request.governed_transport_topology_verified
            is True
            for request
            in requests
        )
    )

    zero_network_calls = (
        valid_requests
        and all(
            request.network_call_performed
            is False
            for request
            in requests
        )
    )

    zero_secret_resolution = (
        valid_requests
        and all(
            request.secret_resolved
            is False
            for request
            in requests
        )
    )

    zero_network_permits = (
        valid_requests
        and all(
            request.network_permit_issued
            is False
            for request
            in requests
        )
    )

    interruption_recovery_fail_closed = (
        bool(
            states
        )
        and any(
            state.state
            == "INTERRUPTED_UNKNOWN_OUTCOME"
            for state
            in states
        )
        and all(
            isinstance(
                state,
                ProviderRecoveredAttemptState,
            )
            and state.safe_to_retry
            is False
            and state.state
            != "INVALID"
            for state
            in states
        )
    )

    blockers: list[
        str
    ] = []

    checks = (
        (
            governed_shadow_verified,
            "GOVERNED_SHADOW_NOT_VERIFIED",
        ),
        (
            valid_requests,
            "SHADOW_REQUEST_EVIDENCE_REQUIRED",
        ),
        (
            zero_network_calls,
            "SHADOW_NETWORK_CALL_DETECTED",
        ),
        (
            zero_secret_resolution,
            "SHADOW_SECRET_RESOLUTION_DETECTED",
        ),
        (
            zero_network_permits,
            "SHADOW_NETWORK_PERMIT_DETECTED",
        ),
        (
            interruption_recovery_fail_closed,
            "INTERRUPTION_RECOVERY_REHEARSAL_REQUIRED",
        ),
    )

    for ok, reason in checks:
        if not ok:
            blockers.append(
                reason
            )

    status = (
        "REHEARSAL_CERTIFIED_FAIL_CLOSED"
        if not blockers
        else "NOT_CERTIFIED"
    )

    base = _base(
        status=status,
        activation_readiness_fingerprint=(
            readiness.certification_fingerprint
        ),
        shadow_mode=(
            shadow_readiness.mode
        ),
        shadow_request_count=len(
            requests
        ),
        governed_shadow_verified=(
            governed_shadow_verified
        ),
        zero_network_calls=(
            zero_network_calls
        ),
        zero_secret_resolution=(
            zero_secret_resolution
        ),
        zero_network_permits=(
            zero_network_permits
        ),
        interruption_recovery_fail_closed=(
            interruption_recovery_fail_closed
        ),
        blockers=tuple(
            blockers
        ),
    )

    certification = (
        ProviderActivationRehearsalCertification(
            status=status,
            activation_readiness_fingerprint=(
                readiness.certification_fingerprint
            ),
            shadow_mode=(
                shadow_readiness.mode
            ),
            shadow_request_count=len(
                requests
            ),
            governed_shadow_verified=(
                governed_shadow_verified
            ),
            zero_network_calls=(
                zero_network_calls
            ),
            zero_secret_resolution=(
                zero_secret_resolution
            ),
            zero_network_permits=(
                zero_network_permits
            ),
            interruption_recovery_fail_closed=(
                interruption_recovery_fail_closed
            ),
            real_provider_execution_authorized=False,
            blockers=tuple(
                blockers
            ),
            certification_fingerprint=(
                _sha(
                    base
                )
            ),
        )
    )

    return (
        verify_provider_activation_rehearsal_certification(
            certification
        )
    )


def require_activation_rehearsal_for_real_execution(
    certification: ProviderActivationRehearsalCertification,
) -> None:
    verify_provider_activation_rehearsal_certification(
        certification
    )

    if (
        certification.real_provider_execution_authorized
        is not True
    ):
        raise ValueError(
            "REAL_PROVIDER_EXECUTION_NOT_AUTHORIZED"
        )

    raise ValueError(
        "PROVIDER_ACTIVATION_REHEARSAL_SCHEMA_NOT_ENABLED"
    )
