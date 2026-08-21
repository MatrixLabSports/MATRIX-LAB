from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from app.core.provider_activation_readiness import (
    ProviderActivationReadinessCertification,
    verify_provider_activation_readiness_certification,
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
    shadow_readiness_evidence_id: str
    shadow_mode: str
    shadow_request_count: int
    governed_shadow_verified: bool
    shadow_evidence_integrity: bool
    zero_network_calls: bool
    zero_secret_resolution: bool
    zero_network_permits: bool
    interruption_recovery_fail_closed: bool
    interruption_evidence_integrity: bool
    real_provider_execution_authorized: bool
    blockers: tuple[str, ...]
    certification_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-activation-rehearsal-certification/2"
            ),
            "status": self.status,
            "activation_readiness_fingerprint": (
                self.activation_readiness_fingerprint
            ),
            "shadow_readiness_evidence_id": (
                self.shadow_readiness_evidence_id
            ),
            "shadow_mode": self.shadow_mode,
            "shadow_request_count": (
                self.shadow_request_count
            ),
            "governed_shadow_verified": (
                self.governed_shadow_verified
            ),
            "shadow_evidence_integrity": (
                self.shadow_evidence_integrity
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
            "interruption_evidence_integrity": (
                self.interruption_evidence_integrity
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
    shadow_readiness_evidence_id: str,
    shadow_mode: str,
    shadow_request_count: int,
    governed_shadow_verified: bool,
    shadow_evidence_integrity: bool,
    zero_network_calls: bool,
    zero_secret_resolution: bool,
    zero_network_permits: bool,
    interruption_recovery_fail_closed: bool,
    interruption_evidence_integrity: bool,
    blockers: Sequence[str],
) -> Mapping[str, Any]:
    return {
        "schema": (
            "matrix.provider-activation-rehearsal-certification-id/2"
        ),
        "status": status,
        "activation_readiness_fingerprint": (
            activation_readiness_fingerprint
        ),
        "shadow_readiness_evidence_id": (
            shadow_readiness_evidence_id
        ),
        "shadow_mode": shadow_mode,
        "shadow_request_count": (
            shadow_request_count
        ),
        "governed_shadow_verified": (
            governed_shadow_verified
        ),
        "shadow_evidence_integrity": (
            shadow_evidence_integrity
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
        "interruption_evidence_integrity": (
            interruption_evidence_integrity
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
                certification.shadow_evidence_integrity,
                certification.zero_network_calls,
                certification.zero_secret_resolution,
                certification.zero_network_permits,
                certification.interruption_recovery_fail_closed,
                certification.interruption_evidence_integrity,
                certification.shadow_request_count > 0,
            )
        )
        else "NOT_CERTIFIED"
    )

    if certification.status != expected_status:
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
            shadow_readiness_evidence_id=(
                certification.shadow_readiness_evidence_id
            ),
            shadow_mode=certification.shadow_mode,
            shadow_request_count=(
                certification.shadow_request_count
            ),
            governed_shadow_verified=(
                certification.governed_shadow_verified
            ),
            shadow_evidence_integrity=(
                certification.shadow_evidence_integrity
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
            interruption_evidence_integrity=(
                certification.interruption_evidence_integrity
            ),
            blockers=certification.blockers,
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
    shadow_evidence_store,
    shadow_readiness_evidence_id: str,
    interruption_recovery_store,
    interruption_permit_ids: Sequence[str],
) -> ProviderActivationRehearsalCertification:
    readiness = (
        verify_provider_activation_readiness_certification(
            activation_readiness
        )
    )

    shadow_evidence_integrity = bool(
        shadow_evidence_store.audit_integrity()
    )

    try:
        readiness_evidence = (
            shadow_evidence_store.get_verified(
                shadow_readiness_evidence_id
            )
        )
    except Exception:
        readiness_evidence = None
        shadow_evidence_integrity = False

    if (
        readiness_evidence is None
        or readiness_evidence.evidence_type
        != "READINESS"
        or readiness_evidence.provider_key
        != "api_football"
    ):
        shadow_evidence_integrity = False
        readiness_payload: Mapping[str, Any] = {}
    else:
        readiness_payload = (
            readiness_evidence.payload
        )

    requests = ()
    if readiness_evidence is not None:
        try:
            requests = (
                shadow_evidence_store.list_verified_requests(
                    shadow_readiness_evidence_id
                )
            )
        except Exception:
            shadow_evidence_integrity = False
            requests = ()

    governed_shadow_verified = (
        readiness.status
        == "TECHNICALLY_READY_RIGHTS_BLOCKED"
        and shadow_evidence_integrity
        and readiness_payload.get(
            "schema"
        )
        == "matrix.api-football-shadow-readiness/2"
        and readiness_payload.get(
            "mode"
        )
        in {
            "DRY_RUN",
            "SHADOW",
        }
        and readiness_payload.get(
            "governed_request_client_verified"
        )
        is True
        and readiness_payload.get(
            "governed_transport_topology_verified"
        )
        is True
        and readiness_payload.get(
            "network_authority_type_verified"
        )
        is True
        and readiness_payload.get(
            "external_network_allowed"
        )
        is False
        and readiness_payload.get(
            "real_provider_execution_authorized"
        )
        is False
    )

    valid_requests = (
        bool(requests)
        and all(
            evidence.evidence_type
            == "REQUEST"
            and evidence.provider_key
            == "api_football"
            and evidence.parent_readiness_evidence_id
            == shadow_readiness_evidence_id
            and evidence.payload.get(
                "schema"
            )
            == "matrix.api-football-shadow-request/2"
            and evidence.payload.get(
                "governed_request_client_used"
            )
            is True
            and evidence.payload.get(
                "governed_transport_topology_verified"
            )
            is True
            for evidence
            in requests
        )
    )

    zero_network_calls = (
        valid_requests
        and all(
            evidence.payload.get(
                "network_call_performed"
            )
            is False
            for evidence
            in requests
        )
    )

    zero_secret_resolution = (
        valid_requests
        and all(
            evidence.payload.get(
                "secret_resolved"
            )
            is False
            for evidence
            in requests
        )
    )

    zero_network_permits = (
        valid_requests
        and all(
            evidence.payload.get(
                "network_permit_issued"
            )
            is False
            for evidence
            in requests
        )
    )

    interruption_evidence_integrity = bool(
        interruption_recovery_store.audit_integrity()
    )

    permit_ids = tuple(
        str(permit_id)
        for permit_id
        in interruption_permit_ids
    )

    interruption_records = []

    if not permit_ids:
        interruption_evidence_integrity = False
    else:
        for permit_id in permit_ids:
            try:
                evidence = (
                    interruption_recovery_store.get_by_permit(
                        permit_id
                    )
                )
            except Exception:
                evidence = None

            if evidence is None:
                interruption_evidence_integrity = False
                break

            interruption_records.append(
                evidence
            )

    interruption_recovery_fail_closed = (
        interruption_evidence_integrity
        and bool(interruption_records)
        and any(
            evidence.status
            == "INTERRUPTED_UNKNOWN_OUTCOME"
            for evidence
            in interruption_records
        )
        and all(
            evidence.safe_to_retry
            is False
            and evidence.request_units_refunded
            is False
            for evidence
            in interruption_records
        )
    )

    blockers: list[str] = []

    checks = (
        (
            governed_shadow_verified,
            "GOVERNED_SHADOW_NOT_VERIFIED",
        ),
        (
            shadow_evidence_integrity,
            "SHADOW_EVIDENCE_STORE_INTEGRITY_FAILED",
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
            interruption_evidence_integrity,
            "INTERRUPTION_EVIDENCE_STORE_INTEGRITY_FAILED",
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

    shadow_mode = str(
        readiness_payload.get(
            "mode",
            "UNKNOWN",
        )
    )

    base = _base(
        status=status,
        activation_readiness_fingerprint=(
            readiness.certification_fingerprint
        ),
        shadow_readiness_evidence_id=(
            shadow_readiness_evidence_id
        ),
        shadow_mode=shadow_mode,
        shadow_request_count=len(
            requests
        ),
        governed_shadow_verified=(
            governed_shadow_verified
        ),
        shadow_evidence_integrity=(
            shadow_evidence_integrity
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
        interruption_evidence_integrity=(
            interruption_evidence_integrity
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
            shadow_readiness_evidence_id=(
                shadow_readiness_evidence_id
            ),
            shadow_mode=shadow_mode,
            shadow_request_count=len(
                requests
            ),
            governed_shadow_verified=(
                governed_shadow_verified
            ),
            shadow_evidence_integrity=(
                shadow_evidence_integrity
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
            interruption_evidence_integrity=(
                interruption_evidence_integrity
            ),
            real_provider_execution_authorized=False,
            blockers=tuple(
                blockers
            ),
            certification_fingerprint=_sha(
                base
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
