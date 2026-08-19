from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .attestation import SignedAttestation, TrustStore
from .sca_contract import SCAContractResult, SCAStatus
from .secret_rotation import SecretRotationResult, SecretRotationStatus


class TrustedSupplyChainStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class TrustedSupplyChainInput:
    release_attestation: SignedAttestation
    sca_attestation: SignedAttestation
    trust_store: TrustStore
    expected_release_subject_sha256: str
    expected_release_predicate_sha256: str
    expected_sca_subject_sha256: str
    expected_sca_predicate_sha256: str
    secret_rotation: SecretRotationResult
    sca_contract: SCAContractResult
    require_production_trust: bool = False


@dataclass(frozen=True)
class TrustedSupplyChainResult:
    status: TrustedSupplyChainStatus
    reasons: tuple[str, ...]
    integration_review_eligible: bool
    production_release_enabled: bool = False
    automatic_model_promotion_enabled: bool = False
    automatic_wager_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.production_release_enabled:
            raise ValueError("V14 trusted supply-chain gate may not authorize production release")
        if self.automatic_model_promotion_enabled or self.automatic_wager_execution_enabled:
            raise ValueError("trusted supply-chain gate may never enable promotion or wagering")
        if self.integration_review_eligible and self.status is not TrustedSupplyChainStatus.PASS:
            raise ValueError("only PASS can be eligible for integration review")


def evaluate_trusted_supply_chain(data: TrustedSupplyChainInput, *, now: datetime) -> TrustedSupplyChainResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    blockers: list[str] = []
    watches: list[str] = []

    release_verification = data.trust_store.verify(
        data.release_attestation,
        now=now,
        required_purpose="release_attestation",
        expected_subject_sha256=data.expected_release_subject_sha256,
        expected_predicate_sha256=data.expected_release_predicate_sha256,
        require_production_trust=data.require_production_trust,
    )
    if not release_verification.passed:
        blockers.extend(f"RELEASE_ATTESTATION:{reason}" for reason in release_verification.reasons)

    sca_verification = data.trust_store.verify(
        data.sca_attestation,
        now=now,
        required_purpose="sca_attestation",
        expected_subject_sha256=data.expected_sca_subject_sha256,
        expected_predicate_sha256=data.expected_sca_predicate_sha256,
        require_production_trust=data.require_production_trust,
    )
    if not sca_verification.passed:
        blockers.extend(f"SCA_ATTESTATION:{reason}" for reason in sca_verification.reasons)

    if data.secret_rotation.status is SecretRotationStatus.BLOCK:
        blockers.extend(f"SECRET_ROTATION:{reason}" for reason in data.secret_rotation.reasons)
    elif data.secret_rotation.status is SecretRotationStatus.WATCH:
        watches.extend(f"SECRET_ROTATION:{reason}" for reason in data.secret_rotation.reasons)

    if data.sca_contract.status is SCAStatus.BLOCK:
        blockers.extend(f"SCA_CONTRACT:{reason}" for reason in data.sca_contract.reasons)
    elif data.sca_contract.status is SCAStatus.WATCH:
        watches.extend(f"SCA_CONTRACT:{reason}" for reason in data.sca_contract.reasons)

    reasons = tuple(dict.fromkeys(blockers + watches))
    if blockers:
        return TrustedSupplyChainResult(TrustedSupplyChainStatus.BLOCK, reasons, False)
    if watches:
        return TrustedSupplyChainResult(TrustedSupplyChainStatus.WATCH, reasons, False)
    return TrustedSupplyChainResult(TrustedSupplyChainStatus.PASS, (), True)
