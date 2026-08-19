from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from base64 import b64decode, b64encode
import re
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.release.canonical import canonical_json, canonical_sha256

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sha256(value: str, name: str) -> None:
    if not _HEX64.fullmatch(value):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


@dataclass(frozen=True)
class AttestationPayload:
    subject_sha256: str
    predicate_type: str
    predicate_sha256: str
    issuer: str
    key_id: str
    issued_at: datetime
    expires_at: datetime
    nonce: str

    def __post_init__(self) -> None:
        _sha256(self.subject_sha256, "subject_sha256")
        _sha256(self.predicate_sha256, "predicate_sha256")
        if not self.predicate_type.strip() or not self.issuer.strip() or not self.key_id.strip():
            raise ValueError("predicate_type, issuer and key_id are required")
        _aware(self.issued_at, "issued_at")
        _aware(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        if not self.nonce.strip():
            raise ValueError("nonce is required")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class SignedAttestation:
    payload: AttestationPayload
    signature_b64: str
    algorithm: str = "ed25519"

    def __post_init__(self) -> None:
        if self.algorithm != "ed25519":
            raise ValueError("only ed25519 is supported")
        try:
            signature = b64decode(self.signature_b64, validate=True)
        except Exception as exc:
            raise ValueError("signature_b64 must be valid base64") from exc
        if len(signature) != 64:
            raise ValueError("ed25519 signature must be 64 bytes")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    issuer: str
    public_key_b64: str
    purposes: tuple[str, ...]
    valid_from: datetime
    valid_until: datetime
    revoked_at: datetime | None = None
    production_trusted: bool = False

    def __post_init__(self) -> None:
        if not self.key_id.strip() or not self.issuer.strip():
            raise ValueError("key_id and issuer are required")
        if not self.purposes or any(not p.strip() for p in self.purposes):
            raise ValueError("at least one non-empty purpose is required")
        _aware(self.valid_from, "valid_from")
        _aware(self.valid_until, "valid_until")
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if self.revoked_at is not None:
            _aware(self.revoked_at, "revoked_at")
        try:
            raw = b64decode(self.public_key_b64, validate=True)
            Ed25519PublicKey.from_public_bytes(raw)
        except Exception as exc:
            raise ValueError("public_key_b64 must contain a valid Ed25519 public key") from exc


@dataclass(frozen=True)
class AttestationVerificationResult:
    passed: bool
    reasons: tuple[str, ...]
    production_trusted: bool


class TrustStore:
    def __init__(self, keys: Mapping[str, TrustedKey]):
        if not keys:
            raise ValueError("trust store cannot be empty")
        normalized: dict[str, TrustedKey] = {}
        for key_id, key in keys.items():
            if key_id != key.key_id:
                raise ValueError("trust store key does not match TrustedKey.key_id")
            if key_id in normalized:
                raise ValueError(f"duplicate key_id: {key_id}")
            normalized[key_id] = key
        self._keys = normalized

    def verify(
        self,
        attestation: SignedAttestation,
        *,
        now: datetime,
        required_purpose: str,
        expected_subject_sha256: str | None = None,
        expected_predicate_sha256: str | None = None,
        max_future_skew_seconds: int = 300,
        require_production_trust: bool = False,
    ) -> AttestationVerificationResult:
        _aware(now, "now")
        reasons: list[str] = []
        payload = attestation.payload
        key = self._keys.get(payload.key_id)
        if key is None:
            return AttestationVerificationResult(False, ("UNTRUSTED_KEY_ID",), False)
        if payload.issuer != key.issuer:
            reasons.append("ISSUER_MISMATCH")
        if required_purpose not in key.purposes:
            reasons.append("KEY_PURPOSE_NOT_ALLOWED")
        if now < key.valid_from or now > key.valid_until:
            reasons.append("KEY_OUTSIDE_VALIDITY_WINDOW")
        if key.revoked_at is not None and now >= key.revoked_at:
            reasons.append("KEY_REVOKED")
        if payload.issued_at > now + timedelta(seconds=max_future_skew_seconds):
            reasons.append("ATTESTATION_FROM_FUTURE")
        if payload.expires_at < now:
            reasons.append("ATTESTATION_EXPIRED")
        if payload.issued_at < key.valid_from or payload.issued_at > key.valid_until:
            reasons.append("ATTESTATION_ISSUED_OUTSIDE_KEY_VALIDITY")
        if expected_subject_sha256 is not None and payload.subject_sha256 != expected_subject_sha256:
            reasons.append("ATTESTATION_SUBJECT_MISMATCH")
        if expected_predicate_sha256 is not None and payload.predicate_sha256 != expected_predicate_sha256:
            reasons.append("ATTESTATION_PREDICATE_MISMATCH")
        if require_production_trust and not key.production_trusted:
            reasons.append("KEY_NOT_PRODUCTION_TRUSTED")

        try:
            public_key = Ed25519PublicKey.from_public_bytes(b64decode(key.public_key_b64))
            public_key.verify(b64decode(attestation.signature_b64), canonical_json(payload).encode("utf-8"))
        except (InvalidSignature, ValueError):
            reasons.append("INVALID_SIGNATURE")
        return AttestationVerificationResult(not reasons, tuple(dict.fromkeys(reasons)), key.production_trusted)


def sign_attestation(private_key: Ed25519PrivateKey, payload: AttestationPayload) -> SignedAttestation:
    signature = private_key.sign(canonical_json(payload).encode("utf-8"))
    return SignedAttestation(payload=payload, signature_b64=b64encode(signature).decode("ascii"))


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return b64encode(raw).decode("ascii")
