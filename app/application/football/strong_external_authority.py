from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import base64
from hashlib import sha256
import re
from typing import Any, Protocol, runtime_checkable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.application.football.external_integrity_root import (
    R8_3R6_PROJECT_DOMAIN_ID,
    R8_3R6_SPORT_ID,
    R83R6RootReceipt,
    R83R6StoreHead,
)


R8_3R6_STRONG_AUTHORITY_ARCHITECTURE = (
    "AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1"
)
R8_3R6_AWS_KMS_KEY_SPEC = "ECC_NIST_EDWARDS25519"
R8_3R6_AWS_KMS_KEY_USAGE = "SIGN_VERIFY"
R8_3R6_AWS_KMS_SIGNING_ALGORITHM = "ED25519_SHA_512"
R8_3R6_AWS_KMS_MESSAGE_TYPE = "RAW"
R8_3R6_AWS_OBJECT_LOCK_MODE = "COMPLIANCE"
R8_3R6_AWS_VERSIONING_STATUS = "Enabled"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ACCOUNT_ID = re.compile(r"^[0-9]{12}$")
_REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_KMS_ARN = re.compile(
    r"^arn:(aws|aws-us-gov|aws-cn):kms:([a-z0-9-]+):([0-9]{12}):key/([A-Za-z0-9-]+)$"
)


def _nonempty(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"R8_3R6_STRONG_{name.upper()}_REQUIRED")
    return value.strip()


def _hex64(value: str, *, name: str) -> str:
    normalized = _nonempty(value, name=name).lower()
    if _HEX64.fullmatch(normalized) is None:
        raise ValueError(f"R8_3R6_STRONG_{name.upper()}_SHA256_REQUIRED")
    return normalized


def _positive_int(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"R8_3R6_STRONG_{name.upper()}_POSITIVE_INTEGER_REQUIRED")
    return value


def _sha_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


@dataclass(frozen=True)
class R83R6StrongAuthorityStreamIdentity:
    project_domain_id: str
    sport_id: str
    root_store_id: str
    database_instance_id: str
    authority_profile: str
    archive_account_id: str
    archive_bucket_arn: str
    archive_region: str
    authority_service_id: str
    signing_account_id: str
    kms_key_arn: str
    key_epoch: int

    def __post_init__(self) -> None:
        if self.project_domain_id != R8_3R6_PROJECT_DOMAIN_ID:
            raise ValueError("R8_3R6_STRONG_PROJECT_DOMAIN_MISMATCH")
        if self.sport_id != R8_3R6_SPORT_ID:
            raise ValueError("R8_3R6_STRONG_SPORT_MISMATCH")
        _hex64(self.root_store_id, name="root_store_id")
        _hex64(self.database_instance_id, name="database_instance_id")
        if self.authority_profile != R8_3R6_STRONG_AUTHORITY_ARCHITECTURE:
            raise ValueError("R8_3R6_STRONG_AUTHORITY_PROFILE_MISMATCH")
        if _ACCOUNT_ID.fullmatch(self.archive_account_id) is None:
            raise ValueError("R8_3R6_STRONG_ARCHIVE_ACCOUNT_ID_INVALID")
        if _REGION.fullmatch(self.archive_region) is None:
            raise ValueError("R8_3R6_STRONG_ARCHIVE_REGION_INVALID")
        _nonempty(self.authority_service_id, name="authority_service_id")
        if _ACCOUNT_ID.fullmatch(self.signing_account_id) is None:
            raise ValueError("R8_3R6_STRONG_SIGNING_ACCOUNT_ID_INVALID")
        _positive_int(self.key_epoch, name="key_epoch")
        bucket = self.bucket_name
        if self.archive_bucket_arn != f"arn:aws:s3:::{bucket}":
            raise ValueError("R8_3R6_STRONG_ARCHIVE_BUCKET_ARN_INVALID")
        match = _KMS_ARN.fullmatch(self.kms_key_arn)
        if match is None:
            raise ValueError("R8_3R6_STRONG_KMS_KEY_ARN_INVALID")
        if match.group(3) != self.signing_account_id:
            raise ValueError("R8_3R6_STRONG_KMS_KEY_ACCOUNT_MISMATCH")

    @property
    def kms_region(self) -> str:
        match = _KMS_ARN.fullmatch(self.kms_key_arn)
        if match is None:
            raise ValueError("R8_3R6_STRONG_KMS_KEY_ARN_INVALID")
        return match.group(2)

    @property
    def bucket_name(self) -> str:
        prefix = "arn:aws:s3:::"
        if not isinstance(self.archive_bucket_arn, str) or not self.archive_bucket_arn.startswith(prefix):
            raise ValueError("R8_3R6_STRONG_ARCHIVE_BUCKET_ARN_INVALID")
        bucket = self.archive_bucket_arn[len(prefix):]
        if _BUCKET.fullmatch(bucket) is None:
            raise ValueError("R8_3R6_STRONG_ARCHIVE_BUCKET_NAME_INVALID")
        return bucket

    @property
    def receipt_prefix(self) -> str:
        return (
            f"matrix-eir/v1/{self.project_domain_id}/{self.sport_id}/"
            f"{self.root_store_id}/{self.database_instance_id}/receipts/"
        )

    def receipt_key(self, sequence: int) -> str:
        seq = _positive_int(sequence, name="root_sequence")
        return f"{self.receipt_prefix}{seq:020d}.json"


@dataclass(frozen=True)
class R83R6AwsS3ActivationEvidence:
    bucket_arn: str
    account_id: str
    region: str
    versioning_status: str
    object_lock_enabled: bool
    default_retention_mode: str
    default_retention_days: int
    conditional_write_enforced: bool
    runtime_can_delete_receipts: bool
    runtime_can_change_retention: bool
    runtime_can_change_bucket_policy: bool

    def validate_for(self, identity: R83R6StrongAuthorityStreamIdentity) -> bool:
        if self.bucket_arn != identity.archive_bucket_arn:
            raise ValueError("R8_3R6_STRONG_ARCHIVE_BUCKET_IDENTITY_MISMATCH")
        if self.account_id != identity.archive_account_id:
            raise ValueError("R8_3R6_STRONG_ARCHIVE_ACCOUNT_IDENTITY_MISMATCH")
        if self.region != identity.archive_region:
            raise ValueError("R8_3R6_STRONG_ARCHIVE_REGION_IDENTITY_MISMATCH")
        if self.versioning_status != R8_3R6_AWS_VERSIONING_STATUS:
            raise ValueError("R8_3R6_STRONG_S3_VERSIONING_REQUIRED")
        if self.object_lock_enabled is not True:
            raise ValueError("R8_3R6_STRONG_S3_OBJECT_LOCK_REQUIRED")
        if self.default_retention_mode != R8_3R6_AWS_OBJECT_LOCK_MODE:
            raise ValueError("R8_3R6_STRONG_S3_COMPLIANCE_RETENTION_REQUIRED")
        _positive_int(self.default_retention_days, name="retention_days")
        if self.conditional_write_enforced is not True:
            raise ValueError("R8_3R6_STRONG_S3_CONDITIONAL_WRITE_POLICY_REQUIRED")
        if self.runtime_can_delete_receipts is not False:
            raise ValueError("R8_3R6_STRONG_RUNTIME_DELETE_AUTHORITY_FORBIDDEN")
        if self.runtime_can_change_retention is not False:
            raise ValueError("R8_3R6_STRONG_RUNTIME_RETENTION_ADMIN_FORBIDDEN")
        if self.runtime_can_change_bucket_policy is not False:
            raise ValueError("R8_3R6_STRONG_RUNTIME_BUCKET_POLICY_ADMIN_FORBIDDEN")
        return True


@dataclass(frozen=True)
class R83R6AwsKmsActivationEvidence:
    key_arn: str
    account_id: str
    region: str
    key_spec: str
    key_usage: str
    signing_algorithms: tuple[str, ...]
    key_state: str
    private_key_exportable: bool
    runtime_can_administer_key: bool

    def validate_for(self, identity: R83R6StrongAuthorityStreamIdentity) -> bool:
        if self.key_arn != identity.kms_key_arn:
            raise ValueError("R8_3R6_STRONG_KMS_KEY_IDENTITY_MISMATCH")
        if self.account_id != identity.signing_account_id:
            raise ValueError("R8_3R6_STRONG_KMS_ACCOUNT_IDENTITY_MISMATCH")
        if self.region != identity.kms_region:
            raise ValueError("R8_3R6_STRONG_KMS_REGION_IDENTITY_MISMATCH")
        if self.key_spec != R8_3R6_AWS_KMS_KEY_SPEC:
            raise ValueError("R8_3R6_STRONG_KMS_ED25519_KEY_SPEC_REQUIRED")
        if self.key_usage != R8_3R6_AWS_KMS_KEY_USAGE:
            raise ValueError("R8_3R6_STRONG_KMS_SIGN_VERIFY_USAGE_REQUIRED")
        if R8_3R6_AWS_KMS_SIGNING_ALGORITHM not in self.signing_algorithms:
            raise ValueError("R8_3R6_STRONG_KMS_ED25519_SHA512_REQUIRED")
        if self.key_state != "Enabled":
            raise ValueError("R8_3R6_STRONG_KMS_KEY_NOT_ENABLED")
        if self.private_key_exportable is not False:
            raise ValueError("R8_3R6_STRONG_KMS_PRIVATE_EXPORT_FORBIDDEN")
        if self.runtime_can_administer_key is not False:
            raise ValueError("R8_3R6_STRONG_RUNTIME_KMS_ADMIN_FORBIDDEN")
        return True


@dataclass(frozen=True)
class R83R6AwsApiRequest:
    service: str
    operation: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class R83R6AwsApiResponse:
    http_status: int
    payload: Mapping[str, Any]
    error_code: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.http_status, bool) or not isinstance(self.http_status, int):
            raise ValueError("R8_3R6_STRONG_AWS_HTTP_STATUS_INTEGER_REQUIRED")
        if not isinstance(self.payload, Mapping):
            raise ValueError("R8_3R6_STRONG_AWS_RESPONSE_PAYLOAD_MAPPING_REQUIRED")


@runtime_checkable
class R83R6OfflineAwsInjectedTransport(Protocol):
    offline_only: bool

    def execute(self, request: R83R6AwsApiRequest) -> R83R6AwsApiResponse:
        ...


@runtime_checkable
class R83R6StrongExternalAuthorityPort(Protocol):
    """Provider-neutral receipt-store contract used by the R8.3R6 coordinator."""

    @property
    def controlled_live_admissible(self) -> bool:
        ...

    @property
    def stronger_external_authority_implemented(self) -> bool:
        ...

    @property
    def root_store_id(self) -> str:
        ...

    def read_receipts(self) -> tuple[R83R6RootReceipt, ...]:
        ...

    def head(self) -> R83R6StoreHead:
        ...

    def append(
        self,
        receipt: R83R6RootReceipt,
        *,
        expected_head: R83R6StoreHead,
    ) -> R83R6RootReceipt:
        ...


@dataclass(frozen=True)
class R83R6OfflineAwsAppendResult:
    status: str
    receipt: R83R6RootReceipt
    attempts: int
    reconciled_after_ambiguous_outcome: bool = False


class R83R6OfflineAwsKmsEd25519SigningAuthority:
    """
    Offline protocol adapter for a future AWS KMS Ed25519 signer.

    It accepts only an injected transport explicitly marked offline_only. No AWS
    SDK import, credential loading, endpoint resolution, or network client is
    implemented here.
    """

    __slots__ = (
        "_transport",
        "_public_key_bytes",
        "identity",
        "key_id",
        "public_key_fingerprint",
    )

    def __init__(
        self,
        *,
        identity: R83R6StrongAuthorityStreamIdentity,
        public_key_bytes: bytes,
        activation_evidence: R83R6AwsKmsActivationEvidence,
        transport: R83R6OfflineAwsInjectedTransport,
    ) -> None:
        if not isinstance(identity, R83R6StrongAuthorityStreamIdentity):
            raise TypeError("R8_3R6_STRONG_STREAM_IDENTITY_REQUIRED")
        if not isinstance(public_key_bytes, bytes) or len(public_key_bytes) != 32:
            raise ValueError("R8_3R6_STRONG_ED25519_PUBLIC_KEY_RAW32_REQUIRED")
        if not isinstance(activation_evidence, R83R6AwsKmsActivationEvidence):
            raise TypeError("R8_3R6_STRONG_KMS_EVIDENCE_REQUIRED")
        activation_evidence.validate_for(identity)
        if not isinstance(transport, R83R6OfflineAwsInjectedTransport):
            raise TypeError("R8_3R6_STRONG_OFFLINE_AWS_TRANSPORT_REQUIRED")
        if transport.offline_only is not True:
            raise ValueError("R8_3R6_STRONG_NETWORK_CAPABLE_TRANSPORT_FORBIDDEN")
        self._transport = transport
        self._public_key_bytes = bytes(public_key_bytes)
        self.identity = identity
        self.public_key_fingerprint = _sha_bytes(self._public_key_bytes)
        self.key_id = "ed25519:" + self.public_key_fingerprint

    @property
    def public_key_bytes(self) -> bytes:
        return bytes(self._public_key_bytes)

    def build_sign_request(self, payload: bytes) -> R83R6AwsApiRequest:
        if not isinstance(payload, bytes):
            raise TypeError("R8_3R6_STRONG_SIGNING_PAYLOAD_BYTES_REQUIRED")
        return R83R6AwsApiRequest(
            service="kms",
            operation="Sign",
            parameters={
                "KeyId": self.identity.kms_key_arn,
                "Message": bytes(payload),
                "MessageType": R8_3R6_AWS_KMS_MESSAGE_TYPE,
                "SigningAlgorithm": R8_3R6_AWS_KMS_SIGNING_ALGORITHM,
            },
        )

    def sign(self, payload: bytes) -> bytes:
        request = self.build_sign_request(payload)
        response = self._transport.execute(request)
        if response.http_status not in {200, 201} or response.error_code is not None:
            raise ValueError("R8_3R6_STRONG_KMS_SIGN_FAIL_CLOSED")
        signature = response.payload.get("Signature")
        if not isinstance(signature, bytes) or not signature:
            raise ValueError("R8_3R6_STRONG_KMS_SIGNATURE_BYTES_REQUIRED")
        try:
            Ed25519PublicKey.from_public_bytes(self._public_key_bytes).verify(
                signature,
                payload,
            )
        except InvalidSignature as error:
            raise ValueError("R8_3R6_STRONG_KMS_SIGNATURE_VERIFICATION_FAILED") from error
        return bytes(signature)

    def __repr__(self) -> str:
        return (
            "R83R6OfflineAwsKmsEd25519SigningAuthority("
            f"key_id={self.key_id!r}, kms_key_arn={self.identity.kms_key_arn!r}, "
            "private_key=<remote-unavailable>, transport=<offline-injected>)"
        )


class R83R6OfflineAwsStrongAuthorityAdapter:
    """
    Provider-neutral strong-authority port backed by pure AWS protocol requests.

    This class is intentionally NOT a CONTROLLED_LIVE backend. It cannot accept a
    network-capable transport and it does not provision or verify a real cloud
    authority. Its purpose is deterministic offline implementation/testing of the
    future S3 Object Lock/KMS protocol.
    """

    def __init__(
        self,
        *,
        identity: R83R6StrongAuthorityStreamIdentity,
        archive_evidence: R83R6AwsS3ActivationEvidence,
        transport: R83R6OfflineAwsInjectedTransport,
        max_conflict_attempts: int = 3,
    ) -> None:
        if not isinstance(identity, R83R6StrongAuthorityStreamIdentity):
            raise TypeError("R8_3R6_STRONG_STREAM_IDENTITY_REQUIRED")
        if not isinstance(archive_evidence, R83R6AwsS3ActivationEvidence):
            raise TypeError("R8_3R6_STRONG_S3_EVIDENCE_REQUIRED")
        archive_evidence.validate_for(identity)
        if not isinstance(transport, R83R6OfflineAwsInjectedTransport):
            raise TypeError("R8_3R6_STRONG_OFFLINE_AWS_TRANSPORT_REQUIRED")
        if transport.offline_only is not True:
            raise ValueError("R8_3R6_STRONG_NETWORK_CAPABLE_TRANSPORT_FORBIDDEN")
        attempts = _positive_int(max_conflict_attempts, name="max_conflict_attempts")
        if attempts > 5:
            raise ValueError("R8_3R6_STRONG_RETRY_BOUND_TOO_LARGE")
        self.identity = identity
        self.archive_evidence = archive_evidence
        self._transport = transport
        self.max_conflict_attempts = attempts

    @property
    def controlled_live_admissible(self) -> bool:
        return False

    @property
    def stronger_external_authority_implemented(self) -> bool:
        return False

    @property
    def backend_profile(self) -> str:
        return "OFFLINE_AWS_STRONG_AUTHORITY_PROTOCOL_CANDIDATE"

    @property
    def root_store_id(self) -> str:
        return self.identity.root_store_id

    def receipt_key(self, sequence: int) -> str:
        return self.identity.receipt_key(sequence)

    def build_put_receipt_request(
        self,
        receipt: R83R6RootReceipt,
        *,
        expected_head: R83R6StoreHead,
    ) -> R83R6AwsApiRequest:
        if not isinstance(receipt, R83R6RootReceipt):
            raise TypeError("R8_3R6_STRONG_ROOT_RECEIPT_REQUIRED")
        if not isinstance(expected_head, R83R6StoreHead):
            raise TypeError("R8_3R6_STRONG_EXPECTED_HEAD_REQUIRED")
        if receipt.project_domain_id != self.identity.project_domain_id:
            raise ValueError("R8_3R6_STRONG_RECEIPT_PROJECT_DOMAIN_MISMATCH")
        if receipt.sport_id != self.identity.sport_id:
            raise ValueError("R8_3R6_STRONG_RECEIPT_SPORT_MISMATCH")
        if receipt.root_store_id != self.identity.root_store_id:
            raise ValueError("R8_3R6_STRONG_RECEIPT_ROOT_STORE_MISMATCH")
        if receipt.database_instance_id != self.identity.database_instance_id:
            raise ValueError("R8_3R6_STRONG_RECEIPT_DATABASE_INSTANCE_MISMATCH")
        if receipt.root_sequence != expected_head.sequence + 1:
            raise ValueError("R8_3R6_STRONG_RECEIPT_SEQUENCE_MISMATCH")
        if receipt.previous_receipt_id != expected_head.receipt_id:
            raise ValueError("R8_3R6_STRONG_RECEIPT_PREDECESSOR_ID_MISMATCH")
        if receipt.previous_receipt_sha256 != expected_head.receipt_sha256:
            raise ValueError("R8_3R6_STRONG_RECEIPT_PREDECESSOR_SHA_MISMATCH")
        raw = receipt.canonical_bytes()
        return R83R6AwsApiRequest(
            service="s3",
            operation="PutObject",
            parameters={
                "Bucket": self.identity.bucket_name,
                "Key": self.receipt_key(receipt.root_sequence),
                "Body": raw,
                "ContentType": "application/json",
                "IfNoneMatch": "*",
                "Metadata": {
                    "matrix-receipt-sha256": receipt.receipt_sha256,
                    "matrix-receipt-id": receipt.receipt_id,
                    "matrix-root-store-id": receipt.root_store_id,
                    "matrix-database-instance-id": receipt.database_instance_id,
                },
            },
        )

    def build_get_receipt_request(self, sequence: int) -> R83R6AwsApiRequest:
        return R83R6AwsApiRequest(
            service="s3",
            operation="GetObject",
            parameters={
                "Bucket": self.identity.bucket_name,
                "Key": self.receipt_key(sequence),
            },
        )

    def build_list_receipts_request(self) -> R83R6AwsApiRequest:
        return R83R6AwsApiRequest(
            service="s3",
            operation="ListObjectsV2",
            parameters={
                "Bucket": self.identity.bucket_name,
                "Prefix": self.identity.receipt_prefix,
            },
        )

    def _read_existing(self, sequence: int) -> R83R6RootReceipt | None:
        response = self._transport.execute(self.build_get_receipt_request(sequence))
        if response.http_status == 404 or response.error_code in {"NoSuchKey", "NotFound"}:
            return None
        if response.http_status != 200 or response.error_code is not None:
            raise ValueError("R8_3R6_STRONG_S3_READ_FAIL_CLOSED")
        raw = response.payload.get("Body")
        if not isinstance(raw, bytes):
            raise ValueError("R8_3R6_STRONG_S3_OBJECT_BODY_BYTES_REQUIRED")
        receipt = R83R6RootReceipt.from_bytes(raw)
        if receipt.root_sequence != sequence:
            raise ValueError("R8_3R6_STRONG_S3_OBJECT_SEQUENCE_MISMATCH")
        if receipt.root_store_id != self.identity.root_store_id:
            raise ValueError("R8_3R6_STRONG_S3_OBJECT_ROOT_STORE_MISMATCH")
        if receipt.database_instance_id != self.identity.database_instance_id:
            raise ValueError("R8_3R6_STRONG_S3_OBJECT_DATABASE_INSTANCE_MISMATCH")
        return receipt

    def append_with_result(
        self,
        receipt: R83R6RootReceipt,
        *,
        expected_head: R83R6StoreHead,
    ) -> R83R6OfflineAwsAppendResult:
        request = self.build_put_receipt_request(receipt, expected_head=expected_head)
        ambiguous = False
        for attempt in range(1, self.max_conflict_attempts + 1):
            try:
                response = self._transport.execute(request)
            except TimeoutError:
                ambiguous = True
                existing = self._read_existing(receipt.root_sequence)
                if existing is not None:
                    if existing.canonical_bytes() == receipt.canonical_bytes():
                        return R83R6OfflineAwsAppendResult(
                            "IDEMPOTENT_AFTER_AMBIGUOUS_TIMEOUT",
                            existing,
                            attempt,
                            True,
                        )
                    raise ValueError("R8_3R6_STRONG_S3_AMBIGUOUS_TIMEOUT_FORK_DETECTED")
                if attempt >= self.max_conflict_attempts:
                    raise ValueError("R8_3R6_STRONG_S3_AMBIGUOUS_TIMEOUT_EXHAUSTED")
                continue

            if response.http_status in {200, 201} and response.error_code is None:
                existing = self._read_existing(receipt.root_sequence)
                if existing is None:
                    raise ValueError("R8_3R6_STRONG_S3_WRITE_NOT_READABLE")
                if existing.canonical_bytes() != receipt.canonical_bytes():
                    raise ValueError("R8_3R6_STRONG_S3_WRITE_READBACK_DIVERGENCE")
                return R83R6OfflineAwsAppendResult(
                    "APPENDED",
                    existing,
                    attempt,
                    ambiguous,
                )

            if response.http_status == 412 or response.error_code in {
                "PreconditionFailed",
            }:
                existing = self._read_existing(receipt.root_sequence)
                if existing is not None and existing.canonical_bytes() == receipt.canonical_bytes():
                    return R83R6OfflineAwsAppendResult(
                        "IDEMPOTENT_EXISTING",
                        existing,
                        attempt,
                        ambiguous,
                    )
                raise ValueError("R8_3R6_STRONG_S3_COMPARE_AND_APPEND_FORK")

            if response.http_status == 409 or response.error_code in {
                "ConditionalRequestConflict",
                "OperationAborted",
            }:
                if attempt >= self.max_conflict_attempts:
                    raise ValueError("R8_3R6_STRONG_S3_CONFLICT_RETRY_EXHAUSTED")
                continue

            if response.http_status in {401, 403} or response.error_code in {
                "AccessDenied",
                "ExpiredToken",
                "InvalidAccessKeyId",
                "SignatureDoesNotMatch",
            }:
                raise ValueError("R8_3R6_STRONG_AWS_AUTHORIZATION_FAIL_CLOSED")

            if response.http_status >= 500 or response.error_code in {
                "InternalError",
                "ServiceUnavailable",
                "SlowDown",
                "Throttling",
                "ThrottlingException",
            }:
                if attempt >= self.max_conflict_attempts:
                    raise ValueError("R8_3R6_STRONG_AWS_SERVICE_RETRY_EXHAUSTED")
                continue

            raise ValueError("R8_3R6_STRONG_S3_APPEND_FAIL_CLOSED")

        raise AssertionError("R8_3R6_STRONG_APPEND_RETRY_LOOP_UNREACHABLE")

    def _listed_sequences(self) -> tuple[int, ...]:
        response = self._transport.execute(self.build_list_receipts_request())
        if response.http_status != 200 or response.error_code is not None:
            raise ValueError("R8_3R6_STRONG_S3_LIST_FAIL_CLOSED")
        keys = response.payload.get("Keys")
        if not isinstance(keys, Sequence) or isinstance(keys, (str, bytes)):
            raise ValueError("R8_3R6_STRONG_S3_LIST_KEYS_SEQUENCE_REQUIRED")
        sequences: list[int] = []
        prefix = self.identity.receipt_prefix
        for key in keys:
            if not isinstance(key, str) or not key.startswith(prefix) or not key.endswith(".json"):
                raise ValueError("R8_3R6_STRONG_S3_LIST_KEY_NAMESPACE_MISMATCH")
            tail = key[len(prefix):-5]
            if len(tail) != 20 or not tail.isdigit():
                raise ValueError("R8_3R6_STRONG_S3_LIST_KEY_SEQUENCE_INVALID")
            sequence = int(tail)
            _positive_int(sequence, name="listed_root_sequence")
            sequences.append(sequence)
        sequences.sort()
        expected = list(range(1, len(sequences) + 1))
        if sequences != expected:
            raise ValueError("R8_3R6_STRONG_S3_SEQUENCE_GAP_OR_DUPLICATE")
        return tuple(sequences)

    def read_receipts(self) -> tuple[R83R6RootReceipt, ...]:
        sequences = self._listed_sequences()
        receipts: list[R83R6RootReceipt] = []
        prior = R83R6StoreHead(0, None, None)
        for sequence in sequences:
            receipt = self._read_existing(sequence)
            if receipt is None:
                raise ValueError("R8_3R6_STRONG_S3_LISTED_RECEIPT_MISSING")
            if receipt.previous_receipt_id != prior.receipt_id:
                raise ValueError("R8_3R6_STRONG_S3_PREDECESSOR_ID_MISMATCH")
            if receipt.previous_receipt_sha256 != prior.receipt_sha256:
                raise ValueError("R8_3R6_STRONG_S3_PREDECESSOR_SHA_MISMATCH")
            receipts.append(receipt)
            prior = R83R6StoreHead(
                receipt.root_sequence,
                receipt.receipt_id,
                receipt.receipt_sha256,
            )
        return tuple(receipts)

    def head(self) -> R83R6StoreHead:
        receipts = self.read_receipts()
        if not receipts:
            return R83R6StoreHead(0, None, None)
        receipt = receipts[-1]
        return R83R6StoreHead(
            receipt.root_sequence,
            receipt.receipt_id,
            receipt.receipt_sha256,
        )

    def append(
        self,
        receipt: R83R6RootReceipt,
        *,
        expected_head: R83R6StoreHead,
    ) -> R83R6RootReceipt:
        return self.append_with_result(
            receipt,
            expected_head=expected_head,
        ).receipt

    def reconstruct_head_from_listing(self) -> R83R6StoreHead:
        return self.head()
