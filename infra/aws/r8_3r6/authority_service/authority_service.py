from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import base64
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
import json
import os
import re
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


PROJECT_DOMAIN_ID = "matrix.c2"
SPORT_ID = "football"
RECEIPT_PROTOCOL = "matrix-eir/v1"
AUTHORITY_PROFILE = "AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1"
REQUEST_SCHEMA = "matrix.c2-r8-3r6-authority-request/1"
RESPONSE_SCHEMA = "matrix.c2-r8-3r6-authority-response/1"
RECEIPT_DOMAIN_SEPARATOR = "matrix.c2-r8-3r6-external-integrity-root/1"
RECEIPT_ID_SCHEMA = "matrix.c2-r8-3r6-receipt-id/1"
ROOT_PROTOCOL_VERSION = 1
LOCAL_SCHEMA_USER_VERSION = 87
GOVERNED_ALIAS = "governed"

RECEIPT_TYPES = (
    "ROOT_GENESIS",
    "ROOT_PREPARED",
    "ROOT_COMMITTED",
    "ROOT_ABORTED",
    "ROOT_KEY_ROTATION",
)
APPENDABLE_RECEIPT_TYPES = (
    "ROOT_GENESIS",
    "ROOT_PREPARED",
    "ROOT_COMMITTED",
    "ROOT_ABORTED",
)
RUN_STATES = (
    "PLANNED",
    "IN_PROGRESS",
    "RECOVERY_REQUIRED",
    "COMPLETED",
    "ABORTED",
)
TRANSITION_OUTCOMES = (
    "STATE_TRANSITION_COMMITTED",
    "STATE_TRANSITION_FAILED",
    "STATE_TRANSITION_ABANDONED",
)
ALLOWED_TRANSITIONS = {
    "PLANNED": {"IN_PROGRESS", "ABORTED"},
    "IN_PROGRESS": {"RECOVERY_REQUIRED", "COMPLETED", "ABORTED"},
    "RECOVERY_REQUIRED": {"IN_PROGRESS", "ABORTED"},
    "COMPLETED": set(),
    "ABORTED": set(),
}

MAX_REQUEST_CANONICAL_BYTES = 65536
MAX_METADATA_CANONICAL_BYTES = 32768
MAX_RECEIPT_BYTES = 262144
MAX_LIST_PAGES = 128
MAX_RECEIPTS = 100000
MAX_RETRY_ATTEMPTS = 5
DEFAULT_RETRY_ATTEMPTS = 3
RECONCILIATION_RESERVE_MS = 5000
MIN_REMOTE_CALL_BUDGET_MS = 500
STS_DURATION_SECONDS = 900

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ACCOUNT_ID = re.compile(r"^[0-9]{12}$")
_REGION = re.compile(r"^[a-z]{2}-[a-z0-9-]+-\d$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_ROLE_NAME = re.compile(r"^[A-Za-z0-9+=,.@_-]{1,64}$")
_KMS_ARN = re.compile(
    r"^arn:aws:kms:([a-z]{2}-[a-z0-9-]+-\d):([0-9]{12}):key/([A-Za-z0-9-]+)$"
)
_LAMBDA_ARN = re.compile(
    r"^arn:aws:lambda:([a-z]{2}-[a-z0-9-]+-\d):([0-9]{12}):function:([^:]+):([^:]+)$"
)
_NONCE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SIGNER_KEY_ID = re.compile(r"^ed25519:([0-9a-f]{64})$")
_RECEIPT_KEY = re.compile(r"^([0-9]{20})\.json$")


class AuthorityError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise AuthorityError(code)


def _canonical(value: Any) -> str:
    try:
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
    except (TypeError, ValueError):
        _fail("R8_3R6_AUTH_JSON_CANONICALIZATION_FAILED")


def _canonical_bytes(value: Any) -> bytes:
    return _canonical(value).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _sha(value: Any) -> str:
    return _sha_bytes(_canonical_bytes(value))


def _hex64(value: Any, *, code: str) -> str:
    if not isinstance(value, str):
        _fail(code)
    normalized = value.strip().lower()
    if _HEX64.fullmatch(normalized) is None:
        _fail(code)
    return normalized


def _positive_int(value: Any, *, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(code)
    return value


def _nonnegative_int(value: Any, *, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(code)
    return value


def _optional_hex64(value: Any, *, code: str) -> str | None:
    if value is None:
        return None
    return _hex64(value, code=code)


def _strict_b64(value: Any, *, code: str) -> bytes:
    if not isinstance(value, str) or not value:
        _fail(code)
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception:
        _fail(code)


def _canonical_utc(value: datetime, *, code: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        _fail(code)
    return value.astimezone(UTC).isoformat()


def _parse_canonical_utc(value: Any, *, code: str) -> datetime:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _fail(code)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    utc = parsed.astimezone(UTC)
    if utc.isoformat() != value:
        _fail(code)
    return utc


def _json_tree(value: Any, *, depth: int = 0) -> None:
    if depth > 16:
        _fail("R8_3R6_AUTH_JSON_DEPTH_EXCEEDED")
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, list):
        if len(value) > 10000:
            _fail("R8_3R6_AUTH_JSON_ARRAY_TOO_LARGE")
        for item in value:
            _json_tree(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 256:
            _fail("R8_3R6_AUTH_JSON_OBJECT_TOO_LARGE")
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("R8_3R6_AUTH_JSON_KEY_STRING_REQUIRED")
            _json_tree(item, depth=depth + 1)
        return
    _fail("R8_3R6_AUTH_JSON_TYPE_UNSUPPORTED")


def _bounded_canonical(value: Any, *, maximum: int, code: str) -> bytes:
    _json_tree(value)
    raw = _canonical_bytes(value)
    if len(raw) > maximum:
        _fail(code)
    return raw


def _exact_keys(mapping: Any, expected: set[str], *, code: str) -> Mapping[str, Any]:
    if not isinstance(mapping, Mapping):
        _fail(code)
    if set(mapping) != expected:
        _fail(code)
    return mapping


@dataclass(frozen=True)
class AuthorityHead:
    sequence: int
    receipt_id: str | None
    receipt_sha256: str | None

    def __post_init__(self) -> None:
        _nonnegative_int(self.sequence, code="R8_3R6_AUTH_HEAD_SEQUENCE_INVALID")
        if self.sequence == 0:
            if self.receipt_id is not None or self.receipt_sha256 is not None:
                _fail("R8_3R6_AUTH_GENESIS_HEAD_INVALID")
        else:
            _hex64(self.receipt_id, code="R8_3R6_AUTH_HEAD_RECEIPT_ID_INVALID")
            _hex64(self.receipt_sha256, code="R8_3R6_AUTH_HEAD_RECEIPT_SHA_INVALID")

    def payload(self) -> Mapping[str, Any]:
        return {
            "sequence": self.sequence,
            "receipt_id": self.receipt_id,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True)
class AuthorityReceipt:
    receipt_id: str
    root_sequence: int
    previous_receipt_id: str | None
    previous_receipt_sha256: str | None
    receipt_type: str
    operation_id: str
    project_domain_id: str
    sport_id: str
    database_instance_id: str
    control_id: str | None
    run_id: str | None
    local_transition_event_id: str | None
    local_transition_event_sha256: str | None
    local_transition_sequence: int | None
    local_control_state_version: int | None
    local_schema_user_version: int
    receipt_protocol_version: int
    created_at: str
    signer_key_id: str
    canonical_payload_sha256: str
    signature_b64: str
    root_store_id: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        _hex64(self.receipt_id, code="R8_3R6_AUTH_RECEIPT_ID_INVALID")
        _positive_int(self.root_sequence, code="R8_3R6_AUTH_RECEIPT_SEQUENCE_INVALID")
        if self.root_sequence == 1:
            if self.previous_receipt_id is not None or self.previous_receipt_sha256 is not None:
                _fail("R8_3R6_AUTH_GENESIS_PREDECESSOR_FORBIDDEN")
        else:
            _hex64(self.previous_receipt_id, code="R8_3R6_AUTH_PREDECESSOR_ID_INVALID")
            _hex64(self.previous_receipt_sha256, code="R8_3R6_AUTH_PREDECESSOR_SHA_INVALID")
        if self.receipt_type not in RECEIPT_TYPES:
            _fail("R8_3R6_AUTH_RECEIPT_TYPE_UNSUPPORTED")
        _hex64(self.operation_id, code="R8_3R6_AUTH_OPERATION_ID_INVALID")
        if self.project_domain_id != PROJECT_DOMAIN_ID:
            _fail("R8_3R6_AUTH_RECEIPT_PROJECT_MISMATCH")
        if self.sport_id != SPORT_ID:
            _fail("R8_3R6_AUTH_RECEIPT_SPORT_MISMATCH")
        _hex64(self.database_instance_id, code="R8_3R6_AUTH_DATABASE_ID_INVALID")
        _optional_hex64(self.control_id, code="R8_3R6_AUTH_CONTROL_ID_INVALID")
        _optional_hex64(self.run_id, code="R8_3R6_AUTH_RUN_ID_INVALID")
        _optional_hex64(
            self.local_transition_event_id,
            code="R8_3R6_AUTH_TRANSITION_EVENT_ID_INVALID",
        )
        _optional_hex64(
            self.local_transition_event_sha256,
            code="R8_3R6_AUTH_TRANSITION_EVENT_SHA_INVALID",
        )
        if self.local_transition_sequence is not None:
            _positive_int(
                self.local_transition_sequence,
                code="R8_3R6_AUTH_TRANSITION_SEQUENCE_INVALID",
            )
        if self.local_control_state_version is not None:
            _nonnegative_int(
                self.local_control_state_version,
                code="R8_3R6_AUTH_CONTROL_STATE_VERSION_INVALID",
            )
        if self.local_schema_user_version != LOCAL_SCHEMA_USER_VERSION:
            _fail("R8_3R6_AUTH_LOCAL_SCHEMA_VERSION_MISMATCH")
        if self.receipt_protocol_version != ROOT_PROTOCOL_VERSION:
            _fail("R8_3R6_AUTH_RECEIPT_PROTOCOL_VERSION_MISMATCH")
        _parse_canonical_utc(self.created_at, code="R8_3R6_AUTH_RECEIPT_TIME_INVALID")
        if not isinstance(self.signer_key_id, str) or _SIGNER_KEY_ID.fullmatch(self.signer_key_id) is None:
            _fail("R8_3R6_AUTH_SIGNER_KEY_ID_INVALID")
        _hex64(
            self.canonical_payload_sha256,
            code="R8_3R6_AUTH_CANONICAL_PAYLOAD_SHA_INVALID",
        )
        if len(_strict_b64(self.signature_b64, code="R8_3R6_AUTH_SIGNATURE_B64_INVALID")) != 64:
            _fail("R8_3R6_AUTH_SIGNATURE_LENGTH_INVALID")
        _hex64(self.root_store_id, code="R8_3R6_AUTH_ROOT_STORE_ID_INVALID")
        if not isinstance(self.metadata, Mapping):
            _fail("R8_3R6_AUTH_METADATA_MAPPING_REQUIRED")
        _bounded_canonical(
            dict(self.metadata),
            maximum=MAX_METADATA_CANONICAL_BYTES,
            code="R8_3R6_AUTH_METADATA_TOO_LARGE",
        )

    def unsigned_payload(self) -> Mapping[str, Any]:
        return {
            "domain_separator": RECEIPT_DOMAIN_SEPARATOR,
            "root_sequence": self.root_sequence,
            "previous_receipt_id": self.previous_receipt_id,
            "previous_receipt_sha256": self.previous_receipt_sha256,
            "receipt_type": self.receipt_type,
            "operation_id": self.operation_id,
            "project_domain_id": self.project_domain_id,
            "sport_id": self.sport_id,
            "database_instance_id": self.database_instance_id,
            "control_id": self.control_id,
            "run_id": self.run_id,
            "local_transition_event_id": self.local_transition_event_id,
            "local_transition_event_sha256": self.local_transition_event_sha256,
            "local_transition_sequence": self.local_transition_sequence,
            "local_control_state_version": self.local_control_state_version,
            "local_schema_user_version": self.local_schema_user_version,
            "receipt_protocol_version": self.receipt_protocol_version,
            "created_at": self.created_at,
            "signer_key_id": self.signer_key_id,
            "root_store_id": self.root_store_id,
            "metadata": dict(self.metadata),
        }

    def storage_payload(self) -> Mapping[str, Any]:
        return {
            **self.unsigned_payload(),
            "canonical_payload_sha256": self.canonical_payload_sha256,
            "signature_b64": self.signature_b64,
            "receipt_id": self.receipt_id,
        }

    def canonical_bytes(self) -> bytes:
        raw = _canonical_bytes(self.storage_payload())
        if len(raw) > MAX_RECEIPT_BYTES:
            _fail("R8_3R6_AUTH_RECEIPT_TOO_LARGE")
        return raw

    @property
    def receipt_sha256(self) -> str:
        return _sha_bytes(self.canonical_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes) -> "AuthorityReceipt":
        if not isinstance(raw, bytes):
            _fail("R8_3R6_AUTH_RECEIPT_BYTES_REQUIRED")
        if len(raw) > MAX_RECEIPT_BYTES:
            _fail("R8_3R6_AUTH_RECEIPT_TOO_LARGE")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _fail("R8_3R6_AUTH_RECEIPT_JSON_INVALID")
        expected = {
            "domain_separator",
            "root_sequence",
            "previous_receipt_id",
            "previous_receipt_sha256",
            "receipt_type",
            "operation_id",
            "project_domain_id",
            "sport_id",
            "database_instance_id",
            "control_id",
            "run_id",
            "local_transition_event_id",
            "local_transition_event_sha256",
            "local_transition_sequence",
            "local_control_state_version",
            "local_schema_user_version",
            "receipt_protocol_version",
            "created_at",
            "signer_key_id",
            "root_store_id",
            "metadata",
            "canonical_payload_sha256",
            "signature_b64",
            "receipt_id",
        }
        _exact_keys(payload, expected, code="R8_3R6_AUTH_RECEIPT_SCHEMA_MISMATCH")
        if payload["domain_separator"] != RECEIPT_DOMAIN_SEPARATOR:
            _fail("R8_3R6_AUTH_RECEIPT_DOMAIN_SEPARATOR_MISMATCH")
        strict_int_fields = (
            "root_sequence",
            "local_schema_user_version",
            "receipt_protocol_version",
        )
        for name in strict_int_fields:
            if isinstance(payload[name], bool) or not isinstance(payload[name], int):
                _fail("R8_3R6_AUTH_RECEIPT_INTEGER_FIELD_INVALID")
        for name in ("local_transition_sequence", "local_control_state_version"):
            if payload[name] is not None and (
                isinstance(payload[name], bool) or not isinstance(payload[name], int)
            ):
                _fail("R8_3R6_AUTH_RECEIPT_INTEGER_FIELD_INVALID")
        obj = cls(
            receipt_id=payload["receipt_id"],
            root_sequence=payload["root_sequence"],
            previous_receipt_id=payload["previous_receipt_id"],
            previous_receipt_sha256=payload["previous_receipt_sha256"],
            receipt_type=payload["receipt_type"],
            operation_id=payload["operation_id"],
            project_domain_id=payload["project_domain_id"],
            sport_id=payload["sport_id"],
            database_instance_id=payload["database_instance_id"],
            control_id=payload["control_id"],
            run_id=payload["run_id"],
            local_transition_event_id=payload["local_transition_event_id"],
            local_transition_event_sha256=payload["local_transition_event_sha256"],
            local_transition_sequence=payload["local_transition_sequence"],
            local_control_state_version=payload["local_control_state_version"],
            local_schema_user_version=payload["local_schema_user_version"],
            receipt_protocol_version=payload["receipt_protocol_version"],
            created_at=payload["created_at"],
            signer_key_id=payload["signer_key_id"],
            canonical_payload_sha256=payload["canonical_payload_sha256"],
            signature_b64=payload["signature_b64"],
            root_store_id=payload["root_store_id"],
            metadata=payload["metadata"],
        )
        if obj.canonical_bytes() != raw:
            _fail("R8_3R6_AUTH_RECEIPT_CANONICAL_BYTES_MISMATCH")
        unsigned_sha = _sha(obj.unsigned_payload())
        if obj.canonical_payload_sha256 != unsigned_sha:
            _fail("R8_3R6_AUTH_RECEIPT_PAYLOAD_DIGEST_MISMATCH")
        expected_id = _sha(
            {
                "schema": RECEIPT_ID_SCHEMA,
                "canonical_payload_sha256": unsigned_sha,
                "signature_b64": obj.signature_b64,
            }
        )
        if obj.receipt_id != expected_id:
            _fail("R8_3R6_AUTH_RECEIPT_ID_MISMATCH")
        return obj


@dataclass(frozen=True)
class AuthorityConfig:
    root_store_id: str
    database_instance_id: str
    archive_account_id: str
    archive_region: str
    archive_bucket: str
    archive_append_role_name: str
    signing_key_arn: str
    key_epoch: int
    authority_code_sha256: str
    project_domain_id: str = PROJECT_DOMAIN_ID
    sport_id: str = SPORT_ID
    receipt_protocol: str = RECEIPT_PROTOCOL
    authority_profile: str = AUTHORITY_PROFILE
    research_only: bool = True

    def __post_init__(self) -> None:
        if self.project_domain_id != PROJECT_DOMAIN_ID:
            _fail("R8_3R6_AUTH_CONFIG_PROJECT_MISMATCH")
        if self.sport_id != SPORT_ID:
            _fail("R8_3R6_AUTH_CONFIG_SPORT_MISMATCH")
        if self.receipt_protocol != RECEIPT_PROTOCOL:
            _fail("R8_3R6_AUTH_CONFIG_PROTOCOL_MISMATCH")
        if self.authority_profile != AUTHORITY_PROFILE:
            _fail("R8_3R6_AUTH_CONFIG_PROFILE_MISMATCH")
        if self.research_only is not True:
            _fail("R8_3R6_AUTH_RESEARCH_ONLY_REQUIRED")
        _hex64(self.root_store_id, code="R8_3R6_AUTH_CONFIG_ROOT_INVALID")
        _hex64(self.database_instance_id, code="R8_3R6_AUTH_CONFIG_DATABASE_INVALID")
        if _ACCOUNT_ID.fullmatch(self.archive_account_id) is None:
            _fail("R8_3R6_AUTH_ARCHIVE_ACCOUNT_INVALID")
        if _REGION.fullmatch(self.archive_region) is None:
            _fail("R8_3R6_AUTH_ARCHIVE_REGION_INVALID")
        if _BUCKET.fullmatch(self.archive_bucket) is None:
            _fail("R8_3R6_AUTH_ARCHIVE_BUCKET_INVALID")
        if _ROLE_NAME.fullmatch(self.archive_append_role_name) is None:
            _fail("R8_3R6_AUTH_ARCHIVE_ROLE_NAME_INVALID")
        match = _KMS_ARN.fullmatch(self.signing_key_arn)
        if match is None:
            _fail("R8_3R6_AUTH_KMS_ARN_INVALID")
        _positive_int(self.key_epoch, code="R8_3R6_AUTH_KEY_EPOCH_INVALID")
        _hex64(
            self.authority_code_sha256,
            code="R8_3R6_AUTH_CODE_SHA256_INVALID",
        )

    @property
    def signing_region(self) -> str:
        match = _KMS_ARN.fullmatch(self.signing_key_arn)
        assert match is not None
        return match.group(1)

    @property
    def signing_account_id(self) -> str:
        match = _KMS_ARN.fullmatch(self.signing_key_arn)
        assert match is not None
        return match.group(2)

    @property
    def signing_key_uuid(self) -> str:
        match = _KMS_ARN.fullmatch(self.signing_key_arn)
        assert match is not None
        return match.group(3)

    @property
    def archive_role_arn(self) -> str:
        return (
            f"arn:aws:iam::{self.archive_account_id}:role/"
            f"{self.archive_append_role_name}"
        )

    @property
    def receipt_prefix(self) -> str:
        return (
            f"{RECEIPT_PROTOCOL}/{PROJECT_DOMAIN_ID}/{SPORT_ID}/"
            f"{self.root_store_id}/{self.database_instance_id}/receipts/"
        )

    def receipt_key(self, sequence: int) -> str:
        seq = _positive_int(sequence, code="R8_3R6_AUTH_RECEIPT_SEQUENCE_INVALID")
        return f"{self.receipt_prefix}{seq:020d}.json"

    @classmethod
    def from_environ(cls, env: Mapping[str, str]) -> "AuthorityConfig":
        def req(name: str) -> str:
            value = env.get(name)
            if not isinstance(value, str) or not value:
                _fail("R8_3R6_AUTH_CONFIG_REQUIRED")
            return value

        epoch_text = req("MATRIX_KEY_EPOCH")
        if not epoch_text.isdigit():
            _fail("R8_3R6_AUTH_KEY_EPOCH_INVALID")
        research = req("MATRIX_RESEARCH_ONLY")
        if research != "true":
            _fail("R8_3R6_AUTH_RESEARCH_ONLY_REQUIRED")
        return cls(
            root_store_id=req("MATRIX_ROOT_STORE_ID"),
            database_instance_id=req("MATRIX_DATABASE_INSTANCE_ID"),
            archive_account_id=req("MATRIX_ARCHIVE_ACCOUNT_ID"),
            archive_region=req("MATRIX_ARCHIVE_REGION"),
            archive_bucket=req("MATRIX_ARCHIVE_BUCKET"),
            archive_append_role_name=req("MATRIX_ARCHIVE_APPEND_ROLE_NAME"),
            signing_key_arn=req("MATRIX_SIGNING_KEY_ARN"),
            key_epoch=int(epoch_text),
            authority_code_sha256=req("MATRIX_AUTHORITY_CODE_SHA256"),
            project_domain_id=req("MATRIX_PROJECT_DOMAIN_ID"),
            sport_id=req("MATRIX_SPORT_ID"),
            receipt_protocol=req("MATRIX_RECEIPT_PROTOCOL"),
            authority_profile=req("MATRIX_AUTHORITY_PROFILE"),
            research_only=True,
        )


@dataclass(frozen=True)
class InvocationMetadata:
    invoked_function_arn: str
    remaining_time_in_millis: Callable[[], int]

    def validate_for(self, config: AuthorityConfig) -> None:
        if not isinstance(self.invoked_function_arn, str):
            _fail("R8_3R6_AUTH_GOVERNED_ALIAS_REQUIRED")
        match = _LAMBDA_ARN.fullmatch(self.invoked_function_arn)
        if match is None:
            _fail("R8_3R6_AUTH_GOVERNED_ALIAS_REQUIRED")
        region, account_id, _function_name, qualifier = match.groups()
        if qualifier != GOVERNED_ALIAS:
            _fail("R8_3R6_AUTH_GOVERNED_ALIAS_REQUIRED")
        if region != config.signing_region:
            _fail("R8_3R6_AUTH_SIGNING_REGION_MISMATCH")
        if account_id != config.signing_account_id:
            _fail("R8_3R6_AUTH_SIGNING_ACCOUNT_MISMATCH")

    def remaining_ms(self) -> int:
        value = self.remaining_time_in_millis()
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _fail("R8_3R6_AUTH_LAMBDA_REMAINING_TIME_INVALID")
        return value


@dataclass
class AttemptCounter:
    kms_describe: int = 0
    kms_get_public_key: int = 0
    kms_sign: int = 0
    sts_assume_role: int = 0
    s3_list: int = 0
    s3_get: int = 0
    s3_put: int = 0

    @property
    def total(self) -> int:
        return (
            self.kms_describe
            + self.kms_get_public_key
            + self.kms_sign
            + self.sts_assume_role
            + self.s3_list
            + self.s3_get
            + self.s3_put
        )

    def payload(self) -> Mapping[str, int]:
        return {
            "kms_describe": self.kms_describe,
            "kms_get_public_key": self.kms_get_public_key,
            "kms_sign": self.kms_sign,
            "sts_assume_role": self.sts_assume_role,
            "s3_list": self.s3_list,
            "s3_get": self.s3_get,
            "s3_put": self.s3_put,
            "total": self.total,
        }


@dataclass(frozen=True)
class ParsedRequest:
    operation: str
    request_nonce: str
    root_store_id: str
    database_instance_id: str
    expected_head: AuthorityHead | None = None
    receipt_intent: Mapping[str, Any] | None = None
    sequence: int | None = None


@dataclass(frozen=True)
class KeyMaterial:
    public_raw: bytes
    public_fingerprint: str
    signer_key_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.public_raw, bytes) or len(self.public_raw) != 32:
            _fail("R8_3R6_AUTH_ED25519_PUBLIC_RAW_INVALID")
        if self.public_fingerprint != _sha_bytes(self.public_raw):
            _fail("R8_3R6_AUTH_PUBLIC_KEY_FINGERPRINT_MISMATCH")
        if self.signer_key_id != "ed25519:" + self.public_fingerprint:
            _fail("R8_3R6_AUTH_SIGNER_KEY_ID_MISMATCH")


def _parse_expected_head(value: Any) -> AuthorityHead:
    mapping = _exact_keys(
        value,
        {"sequence", "receipt_id", "receipt_sha256"},
        code="R8_3R6_AUTH_EXPECTED_HEAD_SCHEMA_MISMATCH",
    )
    sequence = _nonnegative_int(
        mapping["sequence"],
        code="R8_3R6_AUTH_EXPECTED_HEAD_SEQUENCE_INVALID",
    )
    receipt_id = mapping["receipt_id"]
    receipt_sha256 = mapping["receipt_sha256"]
    if sequence == 0:
        if receipt_id is not None or receipt_sha256 is not None:
            _fail("R8_3R6_AUTH_EXPECTED_GENESIS_HEAD_INVALID")
    else:
        receipt_id = _hex64(
            receipt_id,
            code="R8_3R6_AUTH_EXPECTED_HEAD_RECEIPT_ID_INVALID",
        )
        receipt_sha256 = _hex64(
            receipt_sha256,
            code="R8_3R6_AUTH_EXPECTED_HEAD_RECEIPT_SHA_INVALID",
        )
    return AuthorityHead(sequence, receipt_id, receipt_sha256)


def _validate_genesis_snapshot_lists(metadata: Mapping[str, Any]) -> None:
    events = metadata["genesis_transition_events"]
    runs = metadata["genesis_run_state"]
    if not isinstance(events, list) or not isinstance(runs, list):
        _fail("R8_3R6_AUTH_GENESIS_SNAPSHOT_LIST_REQUIRED")
    if len(events) > 10000 or len(runs) > 10000:
        _fail("R8_3R6_AUTH_GENESIS_SNAPSHOT_TOO_LARGE")
    for item in events:
        row = _exact_keys(
            item,
            {"run_id", "transition_sequence", "event_id", "event_sha256"},
            code="R8_3R6_AUTH_GENESIS_EVENT_SCHEMA_MISMATCH",
        )
        _hex64(row["run_id"], code="R8_3R6_AUTH_GENESIS_RUN_ID_INVALID")
        _positive_int(
            row["transition_sequence"],
            code="R8_3R6_AUTH_GENESIS_TRANSITION_SEQUENCE_INVALID",
        )
        _hex64(row["event_id"], code="R8_3R6_AUTH_GENESIS_EVENT_ID_INVALID")
        _hex64(row["event_sha256"], code="R8_3R6_AUTH_GENESIS_EVENT_SHA_INVALID")
    for item in runs:
        row = _exact_keys(
            item,
            {"run_id", "state", "state_version", "updated_at"},
            code="R8_3R6_AUTH_GENESIS_RUN_SCHEMA_MISMATCH",
        )
        _hex64(row["run_id"], code="R8_3R6_AUTH_GENESIS_RUN_ID_INVALID")
        if row["state"] not in RUN_STATES:
            _fail("R8_3R6_AUTH_GENESIS_RUN_STATE_INVALID")
        _nonnegative_int(
            row["state_version"],
            code="R8_3R6_AUTH_GENESIS_STATE_VERSION_INVALID",
        )
        _parse_canonical_utc(
            row["updated_at"],
            code="R8_3R6_AUTH_GENESIS_RUN_TIME_INVALID",
        )


def _parse_receipt_intent(value: Any) -> Mapping[str, Any]:
    expected = {
        "receipt_type",
        "operation_id",
        "control_id",
        "run_id",
        "local_transition_event_id",
        "local_transition_event_sha256",
        "local_transition_sequence",
        "local_control_state_version",
        "local_schema_user_version",
        "metadata",
    }
    mapping = dict(
        _exact_keys(
            value,
            expected,
            code="R8_3R6_AUTH_RECEIPT_INTENT_SCHEMA_MISMATCH",
        )
    )
    receipt_type = mapping["receipt_type"]
    if receipt_type not in RECEIPT_TYPES:
        _fail("R8_3R6_AUTH_RECEIPT_TYPE_UNSUPPORTED")
    if receipt_type == "ROOT_KEY_ROTATION":
        _fail("R8_3R6_AUTH_KEY_ROTATION_NOT_GOVERNED")
    if receipt_type not in APPENDABLE_RECEIPT_TYPES:
        _fail("R8_3R6_AUTH_RECEIPT_TYPE_UNSUPPORTED")
    mapping["operation_id"] = _hex64(
        mapping["operation_id"],
        code="R8_3R6_AUTH_OPERATION_ID_INVALID",
    )
    for name, code in (
        ("control_id", "R8_3R6_AUTH_CONTROL_ID_INVALID"),
        ("run_id", "R8_3R6_AUTH_RUN_ID_INVALID"),
        ("local_transition_event_id", "R8_3R6_AUTH_TRANSITION_EVENT_ID_INVALID"),
        ("local_transition_event_sha256", "R8_3R6_AUTH_TRANSITION_EVENT_SHA_INVALID"),
    ):
        mapping[name] = _optional_hex64(mapping[name], code=code)
    if mapping["local_transition_sequence"] is not None:
        mapping["local_transition_sequence"] = _positive_int(
            mapping["local_transition_sequence"],
            code="R8_3R6_AUTH_TRANSITION_SEQUENCE_INVALID",
        )
    if mapping["local_control_state_version"] is not None:
        mapping["local_control_state_version"] = _nonnegative_int(
            mapping["local_control_state_version"],
            code="R8_3R6_AUTH_CONTROL_STATE_VERSION_INVALID",
        )
    if mapping["local_schema_user_version"] != LOCAL_SCHEMA_USER_VERSION:
        _fail("R8_3R6_AUTH_LOCAL_SCHEMA_VERSION_MISMATCH")
    metadata = mapping["metadata"]
    if not isinstance(metadata, Mapping):
        _fail("R8_3R6_AUTH_METADATA_MAPPING_REQUIRED")
    metadata = dict(metadata)
    _bounded_canonical(
        metadata,
        maximum=MAX_METADATA_CANONICAL_BYTES,
        code="R8_3R6_AUTH_METADATA_TOO_LARGE",
    )
    mapping["metadata"] = metadata

    if receipt_type == "ROOT_GENESIS":
        if any(
            mapping[name] is not None
            for name in (
                "control_id",
                "run_id",
                "local_transition_event_id",
                "local_transition_event_sha256",
                "local_transition_sequence",
                "local_control_state_version",
            )
        ):
            _fail("R8_3R6_AUTH_GENESIS_TRANSITION_REFERENCE_FORBIDDEN")
        _exact_keys(
            metadata,
            {
                "local_snapshot_sha256",
                "genesis_transition_events",
                "genesis_run_state",
            },
            code="R8_3R6_AUTH_GENESIS_METADATA_SCHEMA_MISMATCH",
        )
        metadata["local_snapshot_sha256"] = _hex64(
            metadata["local_snapshot_sha256"],
            code="R8_3R6_AUTH_GENESIS_SNAPSHOT_SHA_INVALID",
        )
        _validate_genesis_snapshot_lists(metadata)

    elif receipt_type == "ROOT_PREPARED":
        if any(
            mapping[name] is None
            for name in (
                "control_id",
                "run_id",
                "local_transition_event_id",
                "local_transition_event_sha256",
                "local_transition_sequence",
                "local_control_state_version",
            )
        ):
            _fail("R8_3R6_AUTH_PREPARED_TRANSITION_REFERENCE_REQUIRED")
        _exact_keys(
            metadata,
            {
                "expected_outcome",
                "expected_prior_state",
                "expected_next_state",
                "expected_state_version_before",
                "expected_state_version_after",
            },
            code="R8_3R6_AUTH_PREPARED_METADATA_SCHEMA_MISMATCH",
        )
        if metadata["expected_outcome"] not in TRANSITION_OUTCOMES:
            _fail("R8_3R6_AUTH_PREPARED_OUTCOME_INVALID")
        if metadata["expected_prior_state"] not in RUN_STATES:
            _fail("R8_3R6_AUTH_PREPARED_PRIOR_STATE_INVALID")
        if metadata["expected_next_state"] not in RUN_STATES:
            _fail("R8_3R6_AUTH_PREPARED_NEXT_STATE_INVALID")
        if metadata["expected_next_state"] not in ALLOWED_TRANSITIONS[
            metadata["expected_prior_state"]
        ]:
            _fail("R8_3R6_AUTH_PREPARED_STATE_EDGE_INVALID")
        before = _nonnegative_int(
            metadata["expected_state_version_before"],
            code="R8_3R6_AUTH_PREPARED_VERSION_BEFORE_INVALID",
        )
        after = _nonnegative_int(
            metadata["expected_state_version_after"],
            code="R8_3R6_AUTH_PREPARED_VERSION_AFTER_INVALID",
        )
        if metadata["expected_outcome"] == "STATE_TRANSITION_COMMITTED":
            if after != before + 1:
                _fail("R8_3R6_AUTH_PREPARED_VERSION_CONTINUITY_MISMATCH")
        elif after != before:
            _fail("R8_3R6_AUTH_PREPARED_NONCOMMITTED_VERSION_ADVANCE")

    elif receipt_type in {"ROOT_COMMITTED", "ROOT_ABORTED"}:
        _exact_keys(
            metadata,
            {"prepared_receipt_id", "prepared_receipt_sha256"},
            code="R8_3R6_AUTH_TERMINAL_METADATA_SCHEMA_MISMATCH",
        )
        metadata["prepared_receipt_id"] = _hex64(
            metadata["prepared_receipt_id"],
            code="R8_3R6_AUTH_PREPARED_RECEIPT_ID_INVALID",
        )
        metadata["prepared_receipt_sha256"] = _hex64(
            metadata["prepared_receipt_sha256"],
            code="R8_3R6_AUTH_PREPARED_RECEIPT_SHA_INVALID",
        )
        if mapping["control_id"] is None or mapping["run_id"] is None:
            _fail("R8_3R6_AUTH_TERMINAL_CONTROL_RUN_REQUIRED")
        if receipt_type == "ROOT_COMMITTED":
            if any(
                mapping[name] is None
                for name in (
                    "local_transition_event_id",
                    "local_transition_event_sha256",
                    "local_transition_sequence",
                    "local_control_state_version",
                )
            ):
                _fail("R8_3R6_AUTH_COMMITTED_TRANSITION_REFERENCE_REQUIRED")
        else:
            if any(
                mapping[name] is not None
                for name in (
                    "local_transition_event_id",
                    "local_transition_event_sha256",
                    "local_transition_sequence",
                    "local_control_state_version",
                )
            ):
                _fail("R8_3R6_AUTH_ABORTED_TRANSITION_REFERENCE_FORBIDDEN")

    return mapping


def parse_request(event: Any, config: AuthorityConfig) -> ParsedRequest:
    _bounded_canonical(
        event,
        maximum=MAX_REQUEST_CANONICAL_BYTES,
        code="R8_3R6_AUTH_REQUEST_TOO_LARGE",
    )
    if not isinstance(event, Mapping):
        _fail("R8_3R6_AUTH_REQUEST_OBJECT_REQUIRED")
    operation = event.get("operation")
    common = {
        "schema",
        "operation",
        "request_nonce",
        "root_store_id",
        "database_instance_id",
    }
    if operation == "APPEND_RECEIPT":
        expected = common | {"expected_head", "receipt_intent"}
    elif operation == "READ_HEAD":
        expected = common
    elif operation == "READ_RECEIPT":
        expected = common | {"sequence"}
    else:
        _fail("R8_3R6_AUTH_OPERATION_UNSUPPORTED")
    _exact_keys(event, expected, code="R8_3R6_AUTH_REQUEST_SCHEMA_MISMATCH")
    if event["schema"] != REQUEST_SCHEMA:
        _fail("R8_3R6_AUTH_REQUEST_VERSION_MISMATCH")
    nonce = event["request_nonce"]
    if not isinstance(nonce, str) or _NONCE.fullmatch(nonce) is None:
        _fail("R8_3R6_AUTH_REQUEST_NONCE_INVALID")
    root = _hex64(event["root_store_id"], code="R8_3R6_AUTH_REQUEST_ROOT_INVALID")
    database = _hex64(
        event["database_instance_id"],
        code="R8_3R6_AUTH_REQUEST_DATABASE_INVALID",
    )
    if root != config.root_store_id:
        _fail("R8_3R6_AUTH_REQUEST_ROOT_MISMATCH")
    if database != config.database_instance_id:
        _fail("R8_3R6_AUTH_REQUEST_DATABASE_MISMATCH")
    if operation == "APPEND_RECEIPT":
        return ParsedRequest(
            operation=operation,
            request_nonce=nonce,
            root_store_id=root,
            database_instance_id=database,
            expected_head=_parse_expected_head(event["expected_head"]),
            receipt_intent=_parse_receipt_intent(event["receipt_intent"]),
        )
    if operation == "READ_RECEIPT":
        return ParsedRequest(
            operation=operation,
            request_nonce=nonce,
            root_store_id=root,
            database_instance_id=database,
            sequence=_positive_int(
                event["sequence"],
                code="R8_3R6_AUTH_READ_SEQUENCE_INVALID",
            ),
        )
    return ParsedRequest(
        operation=operation,
        request_nonce=nonce,
        root_store_id=root,
        database_instance_id=database,
    )


def _validate_genesis_full_metadata(metadata: Mapping[str, Any]) -> bytes:
    mapping = _exact_keys(
        metadata,
        {
            "backend_profile",
            "controlled_live_admissible",
            "local_snapshot_sha256",
            "genesis_transition_events",
            "genesis_run_state",
            "bootstrap_public_key_b64",
            "bootstrap_public_key_fingerprint",
            "bootstrap_signer_key_id",
        },
        code="R8_3R6_AUTH_GENESIS_METADATA_SCHEMA_MISMATCH",
    )
    if mapping["backend_profile"] != AUTHORITY_PROFILE:
        _fail("R8_3R6_AUTH_GENESIS_PROFILE_MISMATCH")
    if mapping["controlled_live_admissible"] is not False:
        _fail("R8_3R6_AUTH_GENESIS_CONTROLLED_LIVE_FORBIDDEN")
    _hex64(
        mapping["local_snapshot_sha256"],
        code="R8_3R6_AUTH_GENESIS_SNAPSHOT_SHA_INVALID",
    )
    _validate_genesis_snapshot_lists(mapping)
    raw = _strict_b64(
        mapping["bootstrap_public_key_b64"],
        code="R8_3R6_AUTH_GENESIS_BOOTSTRAP_KEY_B64_INVALID",
    )
    if len(raw) != 32:
        _fail("R8_3R6_AUTH_GENESIS_BOOTSTRAP_KEY_LENGTH_INVALID")
    fp = _sha_bytes(raw)
    if mapping["bootstrap_public_key_fingerprint"] != fp:
        _fail("R8_3R6_AUTH_GENESIS_BOOTSTRAP_FINGERPRINT_MISMATCH")
    if mapping["bootstrap_signer_key_id"] != "ed25519:" + fp:
        _fail("R8_3R6_AUTH_GENESIS_BOOTSTRAP_KEY_ID_MISMATCH")
    return raw


def verify_receipt_chain(
    receipts: Sequence[AuthorityReceipt],
    *,
    expected_root_store_id: str,
    expected_database_instance_id: str,
) -> tuple[str | None, Mapping[str, bytes]]:
    root_store_id = _hex64(
        expected_root_store_id,
        code="R8_3R6_AUTH_EXPECTED_ROOT_INVALID",
    )
    database_instance_id = _hex64(
        expected_database_instance_id,
        code="R8_3R6_AUTH_EXPECTED_DATABASE_INVALID",
    )
    trusted: dict[str, bytes] = {}
    active_key_id: str | None = None
    previous_id: str | None = None
    previous_sha: str | None = None
    previous_created_at: datetime | None = None
    seen_receipt_ids: set[str] = set()
    seen_operations_by_type: dict[tuple[str, str], str] = {}
    prepared_by_operation: dict[str, AuthorityReceipt] = {}
    terminal_operations: set[str] = set()

    for expected_sequence, receipt in enumerate(receipts, start=1):
        if receipt.root_sequence != expected_sequence:
            _fail("R8_3R6_AUTH_RECEIPT_SEQUENCE_GAP")
        if receipt.previous_receipt_id != previous_id:
            _fail("R8_3R6_AUTH_RECEIPT_PREDECESSOR_ID_MISMATCH")
        if receipt.previous_receipt_sha256 != previous_sha:
            _fail("R8_3R6_AUTH_RECEIPT_PREDECESSOR_SHA_MISMATCH")
        if receipt.receipt_id in seen_receipt_ids:
            _fail("R8_3R6_AUTH_RECEIPT_DUPLICATE_ID")
        seen_receipt_ids.add(receipt.receipt_id)
        if receipt.root_store_id != root_store_id:
            _fail("R8_3R6_AUTH_RECEIPT_ROOT_STORE_ID_MISMATCH")
        if receipt.database_instance_id != database_instance_id:
            _fail("R8_3R6_AUTH_RECEIPT_DATABASE_INSTANCE_MISMATCH")
        if receipt.project_domain_id != PROJECT_DOMAIN_ID:
            _fail("R8_3R6_AUTH_RECEIPT_PROJECT_MISMATCH")
        if receipt.sport_id != SPORT_ID:
            _fail("R8_3R6_AUTH_RECEIPT_SPORT_MISMATCH")
        created = _parse_canonical_utc(
            receipt.created_at,
            code="R8_3R6_AUTH_RECEIPT_TIME_INVALID",
        )
        if previous_created_at is not None and created < previous_created_at:
            _fail("R8_3R6_AUTH_RECEIPT_TIME_REGRESSION")
        previous_created_at = created

        if expected_sequence == 1:
            if receipt.receipt_type != "ROOT_GENESIS":
                _fail("R8_3R6_AUTH_ROOT_GENESIS_REQUIRED")
            bootstrap_raw = _validate_genesis_full_metadata(receipt.metadata)
            bootstrap_id = "ed25519:" + _sha_bytes(bootstrap_raw)
            if receipt.signer_key_id != bootstrap_id:
                _fail("R8_3R6_AUTH_GENESIS_SIGNER_KEY_MISMATCH")
            trusted[bootstrap_id] = bootstrap_raw
            active_key_id = bootstrap_id
            if any(
                value is not None
                for value in (
                    receipt.control_id,
                    receipt.run_id,
                    receipt.local_transition_event_id,
                    receipt.local_transition_event_sha256,
                    receipt.local_transition_sequence,
                    receipt.local_control_state_version,
                )
            ):
                _fail("R8_3R6_AUTH_GENESIS_TRANSITION_REFERENCE_FORBIDDEN")
        elif receipt.receipt_type == "ROOT_GENESIS":
            _fail("R8_3R6_AUTH_MULTIPLE_GENESIS_RECEIPTS_FORBIDDEN")

        if active_key_id is None or receipt.signer_key_id != active_key_id:
            _fail("R8_3R6_AUTH_RECEIPT_SIGNER_CONTINUITY_MISMATCH")
        public_raw = trusted.get(receipt.signer_key_id)
        if public_raw is None:
            _fail("R8_3R6_AUTH_RECEIPT_SIGNER_UNTRUSTED")
        try:
            Ed25519PublicKey.from_public_bytes(public_raw).verify(
                _strict_b64(
                    receipt.signature_b64,
                    code="R8_3R6_AUTH_SIGNATURE_B64_INVALID",
                ),
                _canonical_bytes(receipt.unsigned_payload()),
            )
        except InvalidSignature:
            _fail("R8_3R6_AUTH_RECEIPT_SIGNATURE_INVALID")

        op_key = (receipt.operation_id, receipt.receipt_type)
        prior_same = seen_operations_by_type.get(op_key)
        if prior_same is not None and prior_same != receipt.receipt_id:
            _fail("R8_3R6_AUTH_OPERATION_TYPE_DIVERGENCE")
        seen_operations_by_type[op_key] = receipt.receipt_id

        if receipt.receipt_type == "ROOT_PREPARED":
            if receipt.operation_id in prepared_by_operation:
                _fail("R8_3R6_AUTH_PREPARE_DUPLICATE")
            if any(
                value is None
                for value in (
                    receipt.control_id,
                    receipt.run_id,
                    receipt.local_transition_event_id,
                    receipt.local_transition_event_sha256,
                    receipt.local_transition_sequence,
                    receipt.local_control_state_version,
                )
            ):
                _fail("R8_3R6_AUTH_PREPARED_TRANSITION_REFERENCE_REQUIRED")
            _exact_keys(
                receipt.metadata,
                {
                    "expected_outcome",
                    "expected_prior_state",
                    "expected_next_state",
                    "expected_state_version_before",
                    "expected_state_version_after",
                },
                code="R8_3R6_AUTH_PREPARED_METADATA_SCHEMA_MISMATCH",
            )
            prepared_by_operation[receipt.operation_id] = receipt

        elif receipt.receipt_type in {"ROOT_COMMITTED", "ROOT_ABORTED"}:
            metadata = _exact_keys(
                receipt.metadata,
                {"prepared_receipt_id", "prepared_receipt_sha256"},
                code="R8_3R6_AUTH_TERMINAL_METADATA_SCHEMA_MISMATCH",
            )
            _hex64(
                metadata["prepared_receipt_id"],
                code="R8_3R6_AUTH_PREPARED_RECEIPT_ID_INVALID",
            )
            _hex64(
                metadata["prepared_receipt_sha256"],
                code="R8_3R6_AUTH_PREPARED_RECEIPT_SHA_INVALID",
            )
            if receipt.control_id is None or receipt.run_id is None:
                _fail("R8_3R6_AUTH_TERMINAL_CONTROL_RUN_REQUIRED")
            if receipt.receipt_type == "ROOT_COMMITTED":
                if any(
                    value is None
                    for value in (
                        receipt.local_transition_event_id,
                        receipt.local_transition_event_sha256,
                        receipt.local_transition_sequence,
                        receipt.local_control_state_version,
                    )
                ):
                    _fail("R8_3R6_AUTH_COMMITTED_TRANSITION_REFERENCE_REQUIRED")
            elif any(
                value is not None
                for value in (
                    receipt.local_transition_event_id,
                    receipt.local_transition_event_sha256,
                    receipt.local_transition_sequence,
                    receipt.local_control_state_version,
                )
            ):
                _fail("R8_3R6_AUTH_ABORTED_TRANSITION_REFERENCE_FORBIDDEN")
            prepared = prepared_by_operation.get(receipt.operation_id)
            if prepared is None:
                _fail("R8_3R6_AUTH_TERMINAL_WITHOUT_PREPARE")
            if receipt.operation_id in terminal_operations:
                _fail("R8_3R6_AUTH_OPERATION_TERMINAL_DUPLICATE")
            terminal_operations.add(receipt.operation_id)
            if (
                metadata["prepared_receipt_id"] != prepared.receipt_id
                or metadata["prepared_receipt_sha256"] != prepared.receipt_sha256
            ):
                _fail("R8_3R6_AUTH_TERMINAL_PREPARE_BINDING_MISMATCH")
            if receipt.control_id != prepared.control_id or receipt.run_id != prepared.run_id:
                _fail("R8_3R6_AUTH_TERMINAL_CONTROL_RUN_MISMATCH")
            if receipt.receipt_type == "ROOT_COMMITTED":
                if (
                    receipt.local_transition_event_id
                    != prepared.local_transition_event_id
                    or receipt.local_transition_event_sha256
                    != prepared.local_transition_event_sha256
                    or receipt.local_transition_sequence
                    != prepared.local_transition_sequence
                    or receipt.local_control_state_version
                    != prepared.local_control_state_version
                ):
                    _fail("R8_3R6_AUTH_COMMITTED_PREPARED_TRANSITION_MISMATCH")

        elif receipt.receipt_type == "ROOT_KEY_ROTATION":
            metadata = dict(receipt.metadata)
            required = {
                "new_key_id",
                "new_public_key_b64",
                "new_public_key_fingerprint",
                "new_key_proof_signature_b64",
                "activation_sequence",
                "proof_core",
            }
            _exact_keys(
                metadata,
                required,
                code="R8_3R6_AUTH_KEY_ROTATION_METADATA_INVALID",
            )
            new_raw = _strict_b64(
                metadata["new_public_key_b64"],
                code="R8_3R6_AUTH_KEY_ROTATION_PUBLIC_KEY_INVALID",
            )
            if len(new_raw) != 32:
                _fail("R8_3R6_AUTH_KEY_ROTATION_PUBLIC_KEY_INVALID")
            new_fp = _sha_bytes(new_raw)
            new_key_id = metadata["new_key_id"]
            if new_key_id != "ed25519:" + new_fp:
                _fail("R8_3R6_AUTH_KEY_ROTATION_KEY_ID_MISMATCH")
            if metadata["new_public_key_fingerprint"] != new_fp:
                _fail("R8_3R6_AUTH_KEY_ROTATION_FINGERPRINT_MISMATCH")
            if metadata["activation_sequence"] != receipt.root_sequence + 1:
                _fail("R8_3R6_AUTH_KEY_ROTATION_ACTIVATION_SEQUENCE_INVALID")
            expected_core = {
                "schema": "matrix.c2-r8-3r6-key-rotation-proof-core/1",
                "root_store_id": root_store_id,
                "database_instance_id": database_instance_id,
                "operation_id": receipt.operation_id,
                "new_key_id": new_key_id,
                "activation_sequence": receipt.root_sequence + 1,
            }
            if metadata["proof_core"] != expected_core:
                _fail("R8_3R6_AUTH_KEY_ROTATION_PROOF_CORE_MISMATCH")
            try:
                Ed25519PublicKey.from_public_bytes(new_raw).verify(
                    _strict_b64(
                        metadata["new_key_proof_signature_b64"],
                        code="R8_3R6_AUTH_KEY_ROTATION_PROOF_B64_INVALID",
                    ),
                    _canonical_bytes(expected_core),
                )
            except InvalidSignature:
                _fail("R8_3R6_AUTH_KEY_ROTATION_NEW_KEY_PROOF_INVALID")
            trusted[new_key_id] = new_raw
            active_key_id = new_key_id

        previous_id = receipt.receipt_id
        previous_sha = receipt.receipt_sha256

    return active_key_id, trusted


def _aws_error_info(error: Exception) -> tuple[int | None, str | None, bool]:
    response = getattr(error, "response", None)
    status: int | None = None
    code: str | None = None
    if isinstance(response, Mapping):
        metadata = response.get("ResponseMetadata")
        if isinstance(metadata, Mapping):
            raw_status = metadata.get("HTTPStatusCode")
            if isinstance(raw_status, int) and not isinstance(raw_status, bool):
                status = raw_status
        err = response.get("Error")
        if isinstance(err, Mapping):
            raw_code = err.get("Code")
            if isinstance(raw_code, str):
                code = raw_code
    name = type(error).__name__.lower()
    ambiguous = isinstance(error, (TimeoutError, ConnectionError)) or any(
        marker in name
        for marker in (
            "timeout",
            "connection",
            "endpointconnection",
            "connectionclosed",
            "readtimeout",
        )
    )
    return status, code, ambiguous


_AUTH_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "ExpiredToken",
    "ExpiredTokenException",
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
    "UnrecognizedClientException",
    "InvalidClientTokenId",
}
_TRANSIENT_CODES = {
    "InternalError",
    "InternalFailure",
    "ServiceUnavailable",
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "RequestTimeout",
    "RequestTimeoutException",
}


class AuthorityService:
    def __init__(
        self,
        *,
        config: AuthorityConfig,
        kms_client: Any,
        sts_client: Any,
        s3_client_factory: Callable[[Mapping[str, str], str], Any],
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[int], None] | None = None,
        max_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    ) -> None:
        if not isinstance(config, AuthorityConfig):
            _fail("R8_3R6_AUTH_CONFIG_REQUIRED")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            _fail("R8_3R6_AUTH_RETRY_BUDGET_INVALID")
        if max_attempts <= 0 or max_attempts > MAX_RETRY_ATTEMPTS:
            _fail("R8_3R6_AUTH_RETRY_BUDGET_INVALID")
        self.config = config
        self.kms_client = kms_client
        self.sts_client = sts_client
        self.s3_client_factory = s3_client_factory
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleeper = sleeper or (lambda _attempt: None)
        self.max_attempts = max_attempts

    def _remaining_guard(
        self,
        invocation: InvocationMetadata,
        *,
        mutation: bool = False,
    ) -> None:
        minimum = RECONCILIATION_RESERVE_MS if mutation else MIN_REMOTE_CALL_BUDGET_MS
        if invocation.remaining_ms() < minimum:
            _fail(
                "R8_3R6_AUTH_INSUFFICIENT_RECONCILIATION_BUDGET"
                if mutation
                else "R8_3R6_AUTH_INSUFFICIENT_REMOTE_CALL_BUDGET"
            )

    def _count(self, attempts: AttemptCounter, name: str) -> None:
        setattr(attempts, name, getattr(attempts, name) + 1)

    def _call_read(
        self,
        *,
        attempts: AttemptCounter,
        counter_name: str,
        invocation: InvocationMetadata,
        call: Callable[[], Any],
    ) -> Any:
        for attempt in range(1, self.max_attempts + 1):
            self._remaining_guard(invocation)
            self._count(attempts, counter_name)
            try:
                return call()
            except Exception as error:
                status, code, ambiguous = _aws_error_info(error)
                if status in {401, 403} or code in _AUTH_CODES:
                    _fail("R8_3R6_AUTH_AWS_AUTHORIZATION_FAILED")
                if ambiguous or (status is not None and status >= 500) or code in _TRANSIENT_CODES:
                    if attempt >= self.max_attempts:
                        _fail("R8_3R6_AUTH_AWS_READ_RETRY_EXHAUSTED")
                    self.sleeper(attempt)
                    continue
                raise
        _fail("R8_3R6_AUTH_AWS_READ_RETRY_EXHAUSTED")

    def _kms_identity_matches(self, value: Any) -> bool:
        return isinstance(value, str) and value in {
            self.config.signing_key_arn,
            self.config.signing_key_uuid,
        }

    def _load_key_material(
        self,
        *,
        attempts: AttemptCounter,
        invocation: InvocationMetadata,
    ) -> KeyMaterial:
        describe = self._call_read(
            attempts=attempts,
            counter_name="kms_describe",
            invocation=invocation,
            call=lambda: self.kms_client.describe_key(
                KeyId=self.config.signing_key_arn
            ),
        )
        if not isinstance(describe, Mapping):
            _fail("R8_3R6_AUTH_KMS_DESCRIBE_RESPONSE_INVALID")
        metadata = describe.get("KeyMetadata")
        if not isinstance(metadata, Mapping):
            _fail("R8_3R6_AUTH_KMS_DESCRIBE_METADATA_INVALID")
        if metadata.get("Arn") != self.config.signing_key_arn:
            _fail("R8_3R6_AUTH_KMS_KEY_IDENTITY_MISMATCH")
        if not self._kms_identity_matches(metadata.get("KeyId")):
            _fail("R8_3R6_AUTH_KMS_KEY_IDENTITY_MISMATCH")
        if metadata.get("KeySpec") != "ECC_NIST_EDWARDS25519":
            _fail("R8_3R6_AUTH_KMS_KEY_SPEC_MISMATCH")
        if metadata.get("KeyUsage") != "SIGN_VERIFY":
            _fail("R8_3R6_AUTH_KMS_KEY_USAGE_MISMATCH")
        if metadata.get("KeyState") != "Enabled":
            _fail("R8_3R6_AUTH_KMS_KEY_NOT_ENABLED")

        response = self._call_read(
            attempts=attempts,
            counter_name="kms_get_public_key",
            invocation=invocation,
            call=lambda: self.kms_client.get_public_key(
                KeyId=self.config.signing_key_arn
            ),
        )
        if not isinstance(response, Mapping):
            _fail("R8_3R6_AUTH_KMS_PUBLIC_KEY_RESPONSE_INVALID")
        if not self._kms_identity_matches(response.get("KeyId")):
            _fail("R8_3R6_AUTH_KMS_PUBLIC_KEY_IDENTITY_MISMATCH")
        if response.get("KeySpec") != "ECC_NIST_EDWARDS25519":
            _fail("R8_3R6_AUTH_KMS_PUBLIC_KEY_SPEC_MISMATCH")
        if response.get("KeyUsage") != "SIGN_VERIFY":
            _fail("R8_3R6_AUTH_KMS_PUBLIC_KEY_USAGE_MISMATCH")
        algorithms = response.get("SigningAlgorithms")
        if (
            not isinstance(algorithms, Sequence)
            or isinstance(algorithms, (str, bytes))
            or "ED25519_SHA_512" not in algorithms
        ):
            _fail("R8_3R6_AUTH_KMS_SIGNING_ALGORITHM_MISMATCH")
        der = response.get("PublicKey")
        if not isinstance(der, bytes):
            _fail("R8_3R6_AUTH_KMS_PUBLIC_KEY_DER_REQUIRED")
        try:
            public = serialization.load_der_public_key(der)
        except Exception:
            _fail("R8_3R6_AUTH_KMS_PUBLIC_KEY_DER_INVALID")
        if not isinstance(public, Ed25519PublicKey):
            _fail("R8_3R6_AUTH_KMS_PUBLIC_KEY_NOT_ED25519")
        raw = public.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        if len(raw) != 32:
            _fail("R8_3R6_AUTH_ED25519_PUBLIC_RAW_INVALID")
        fingerprint = _sha_bytes(raw)
        return KeyMaterial(raw, fingerprint, "ed25519:" + fingerprint)

    def _sign(
        self,
        payload: bytes,
        *,
        key: KeyMaterial,
        attempts: AttemptCounter,
        invocation: InvocationMetadata,
    ) -> bytes:
        for attempt in range(1, self.max_attempts + 1):
            self._remaining_guard(invocation)
            self._count(attempts, "kms_sign")
            try:
                response = self.kms_client.sign(
                    KeyId=self.config.signing_key_arn,
                    Message=payload,
                    MessageType="RAW",
                    SigningAlgorithm="ED25519_SHA_512",
                )
            except Exception as error:
                status, code, ambiguous = _aws_error_info(error)
                if status in {401, 403} or code in _AUTH_CODES:
                    _fail("R8_3R6_AUTH_KMS_SIGN_AUTHORIZATION_FAILED")
                if ambiguous or (status is not None and status >= 500) or code in _TRANSIENT_CODES:
                    if attempt >= self.max_attempts:
                        _fail("R8_3R6_AUTH_KMS_SIGN_RETRY_EXHAUSTED")
                    self.sleeper(attempt)
                    continue
                raise
            if not isinstance(response, Mapping):
                _fail("R8_3R6_AUTH_KMS_SIGN_RESPONSE_INVALID")
            if not self._kms_identity_matches(response.get("KeyId")):
                _fail("R8_3R6_AUTH_KMS_SIGN_KEY_IDENTITY_MISMATCH")
            if response.get("SigningAlgorithm") != "ED25519_SHA_512":
                _fail("R8_3R6_AUTH_KMS_SIGN_ALGORITHM_MISMATCH")
            signature = response.get("Signature")
            if not isinstance(signature, bytes) or len(signature) != 64:
                _fail("R8_3R6_AUTH_KMS_SIGNATURE_INVALID")
            try:
                Ed25519PublicKey.from_public_bytes(key.public_raw).verify(
                    signature,
                    payload,
                )
            except InvalidSignature:
                _fail("R8_3R6_AUTH_KMS_SIGNATURE_VERIFICATION_FAILED")
            return bytes(signature)
        _fail("R8_3R6_AUTH_KMS_SIGN_RETRY_EXHAUSTED")

    def _assume_archive_role(
        self,
        *,
        request_nonce: str,
        attempts: AttemptCounter,
        invocation: InvocationMetadata,
    ) -> Mapping[str, str]:
        session_name = "matrix-r836-" + _sha_bytes(
            request_nonce.encode("utf-8")
        )[:24]
        response = self._call_read(
            attempts=attempts,
            counter_name="sts_assume_role",
            invocation=invocation,
            call=lambda: self.sts_client.assume_role(
                RoleArn=self.config.archive_role_arn,
                RoleSessionName=session_name,
                DurationSeconds=STS_DURATION_SECONDS,
            ),
        )
        if not isinstance(response, Mapping):
            _fail("R8_3R6_AUTH_STS_RESPONSE_INVALID")
        assumed = response.get("AssumedRoleUser")
        credentials = response.get("Credentials")
        if not isinstance(assumed, Mapping) or not isinstance(credentials, Mapping):
            _fail("R8_3R6_AUTH_STS_RESPONSE_INVALID")
        expected_arn = (
            f"arn:aws:sts::{self.config.archive_account_id}:assumed-role/"
            f"{self.config.archive_append_role_name}/{session_name}"
        )
        if assumed.get("Arn") != expected_arn:
            _fail("R8_3R6_AUTH_STS_ASSUMED_ROLE_IDENTITY_MISMATCH")
        safe: dict[str, str] = {}
        for name in ("AccessKeyId", "SecretAccessKey", "SessionToken"):
            value = credentials.get(name)
            if not isinstance(value, str) or not value:
                _fail("R8_3R6_AUTH_STS_CREDENTIAL_RESPONSE_INVALID")
            safe[name] = value
        return safe

    def _s3_client(
        self,
        *,
        request_nonce: str,
        attempts: AttemptCounter,
        invocation: InvocationMetadata,
    ) -> Any:
        credentials = self._assume_archive_role(
            request_nonce=request_nonce,
            attempts=attempts,
            invocation=invocation,
        )
        return self.s3_client_factory(credentials, self.config.archive_region)

    def _read_body(self, response: Any) -> bytes:
        if not isinstance(response, Mapping):
            _fail("R8_3R6_AUTH_S3_GET_RESPONSE_INVALID")
        length = response.get("ContentLength")
        if length is not None:
            if isinstance(length, bool) or not isinstance(length, int) or length < 0:
                _fail("R8_3R6_AUTH_S3_CONTENT_LENGTH_INVALID")
            if length > MAX_RECEIPT_BYTES:
                _fail("R8_3R6_AUTH_RECEIPT_TOO_LARGE")
        body = response.get("Body")
        if isinstance(body, bytes):
            raw = body
        elif hasattr(body, "read"):
            raw = body.read(MAX_RECEIPT_BYTES + 1)
            if not isinstance(raw, bytes):
                _fail("R8_3R6_AUTH_S3_BODY_BYTES_REQUIRED")
        else:
            _fail("R8_3R6_AUTH_S3_BODY_REQUIRED")
        if len(raw) > MAX_RECEIPT_BYTES:
            _fail("R8_3R6_AUTH_RECEIPT_TOO_LARGE")
        if length is not None and len(raw) != length:
            _fail("R8_3R6_AUTH_S3_CONTENT_LENGTH_MISMATCH")
        return raw

    def _get_receipt(
        self,
        *,
        s3: Any,
        sequence: int,
        attempts: AttemptCounter,
        invocation: InvocationMetadata,
        allow_missing: bool = False,
    ) -> AuthorityReceipt | None:
        key = self.config.receipt_key(sequence)

        def call() -> Any:
            return s3.get_object(Bucket=self.config.archive_bucket, Key=key)

        for attempt in range(1, self.max_attempts + 1):
            self._remaining_guard(invocation)
            self._count(attempts, "s3_get")
            try:
                response = call()
            except Exception as error:
                status, code, ambiguous = _aws_error_info(error)
                if status == 404 or code in {"NoSuchKey", "NotFound"}:
                    if allow_missing:
                        return None
                    _fail("R8_3R6_AUTH_S3_RECEIPT_MISSING")
                if status in {401, 403} or code in _AUTH_CODES:
                    _fail("R8_3R6_AUTH_AWS_AUTHORIZATION_FAILED")
                if ambiguous or (status is not None and status >= 500) or code in _TRANSIENT_CODES:
                    if attempt >= self.max_attempts:
                        _fail("R8_3R6_AUTH_S3_READ_RETRY_EXHAUSTED")
                    self.sleeper(attempt)
                    continue
                raise
            raw = self._read_body(response)
            receipt = AuthorityReceipt.from_bytes(raw)
            if receipt.root_sequence != sequence:
                _fail("R8_3R6_AUTH_S3_OBJECT_SEQUENCE_MISMATCH")
            if receipt.root_store_id != self.config.root_store_id:
                _fail("R8_3R6_AUTH_S3_OBJECT_ROOT_MISMATCH")
            if receipt.database_instance_id != self.config.database_instance_id:
                _fail("R8_3R6_AUTH_S3_OBJECT_DATABASE_MISMATCH")
            return receipt
        _fail("R8_3R6_AUTH_S3_READ_RETRY_EXHAUSTED")

    def _list_sequences(
        self,
        *,
        s3: Any,
        attempts: AttemptCounter,
        invocation: InvocationMetadata,
    ) -> tuple[int, ...]:
        keys: list[str] = []
        continuation: str | None = None
        for page_number in range(1, MAX_LIST_PAGES + 1):
            kwargs: dict[str, Any] = {
                "Bucket": self.config.archive_bucket,
                "Prefix": self.config.receipt_prefix,
                "MaxKeys": 1000,
            }
            if continuation is not None:
                kwargs["ContinuationToken"] = continuation
            response = self._call_read(
                attempts=attempts,
                counter_name="s3_list",
                invocation=invocation,
                call=lambda kwargs=kwargs: s3.list_objects_v2(**kwargs),
            )
            if not isinstance(response, Mapping):
                _fail("R8_3R6_AUTH_S3_LIST_RESPONSE_INVALID")
            contents = response.get("Contents", [])
            if not isinstance(contents, Sequence) or isinstance(contents, (str, bytes)):
                _fail("R8_3R6_AUTH_S3_LIST_CONTENTS_INVALID")
            for item in contents:
                if not isinstance(item, Mapping):
                    _fail("R8_3R6_AUTH_S3_LIST_ITEM_INVALID")
                key = item.get("Key")
                if not isinstance(key, str) or not key.startswith(self.config.receipt_prefix):
                    _fail("R8_3R6_AUTH_S3_LIST_KEY_NAMESPACE_MISMATCH")
                keys.append(key)
                if len(keys) > MAX_RECEIPTS:
                    _fail("R8_3R6_AUTH_S3_RECEIPT_BOUND_EXCEEDED")
            truncated = response.get("IsTruncated", False)
            if truncated is False:
                break
            if truncated is not True:
                _fail("R8_3R6_AUTH_S3_LIST_TRUNCATION_FLAG_INVALID")
            token = response.get("NextContinuationToken")
            if not isinstance(token, str) or not token or token == continuation:
                _fail("R8_3R6_AUTH_S3_LIST_CONTINUATION_INVALID")
            continuation = token
        else:
            _fail("R8_3R6_AUTH_S3_LIST_PAGE_BOUND_EXCEEDED")

        sequences: list[int] = []
        seen_keys: set[str] = set()
        for key in keys:
            if key in seen_keys:
                _fail("R8_3R6_AUTH_S3_LIST_DUPLICATE_KEY")
            seen_keys.add(key)
            tail = key[len(self.config.receipt_prefix) :]
            match = _RECEIPT_KEY.fullmatch(tail)
            if match is None:
                _fail("R8_3R6_AUTH_S3_LIST_KEY_FORMAT_INVALID")
            sequence = int(match.group(1))
            if sequence <= 0:
                _fail("R8_3R6_AUTH_S3_LIST_KEY_SEQUENCE_INVALID")
            sequences.append(sequence)
        sequences.sort()
        if sequences != list(range(1, len(sequences) + 1)):
            _fail("R8_3R6_AUTH_S3_SEQUENCE_GAP_OR_DUPLICATE")
        return tuple(sequences)

    def _read_chain(
        self,
        *,
        s3: Any,
        attempts: AttemptCounter,
        invocation: InvocationMetadata,
    ) -> tuple[AuthorityReceipt, ...]:
        sequences = self._list_sequences(
            s3=s3,
            attempts=attempts,
            invocation=invocation,
        )
        receipts: list[AuthorityReceipt] = []
        for sequence in sequences:
            receipt = self._get_receipt(
                s3=s3,
                sequence=sequence,
                attempts=attempts,
                invocation=invocation,
            )
            assert receipt is not None
            receipts.append(receipt)
        verify_receipt_chain(
            receipts,
            expected_root_store_id=self.config.root_store_id,
            expected_database_instance_id=self.config.database_instance_id,
        )
        return tuple(receipts)

    @staticmethod
    def _head(receipts: Sequence[AuthorityReceipt]) -> AuthorityHead:
        if not receipts:
            return AuthorityHead(0, None, None)
        last = receipts[-1]
        return AuthorityHead(
            last.root_sequence,
            last.receipt_id,
            last.receipt_sha256,
        )

    def _full_metadata_for_intent(
        self,
        intent: Mapping[str, Any],
        *,
        key: KeyMaterial,
    ) -> Mapping[str, Any]:
        metadata = dict(intent["metadata"])
        if intent["receipt_type"] == "ROOT_GENESIS":
            return {
                "backend_profile": AUTHORITY_PROFILE,
                "controlled_live_admissible": False,
                "local_snapshot_sha256": metadata["local_snapshot_sha256"],
                "genesis_transition_events": metadata["genesis_transition_events"],
                "genesis_run_state": metadata["genesis_run_state"],
                "bootstrap_public_key_b64": base64.b64encode(key.public_raw).decode("ascii"),
                "bootstrap_public_key_fingerprint": key.public_fingerprint,
                "bootstrap_signer_key_id": key.signer_key_id,
            }
        return metadata

    def _receipt_semantically_matches_intent(
        self,
        receipt: AuthorityReceipt,
        *,
        intent: Mapping[str, Any],
        expected_head: AuthorityHead,
        full_metadata: Mapping[str, Any] | None = None,
        signer_key_id: str | None = None,
    ) -> bool:
        metadata = dict(intent["metadata"]) if full_metadata is None else dict(full_metadata)
        if receipt.root_sequence != expected_head.sequence + 1:
            return False
        if receipt.previous_receipt_id != expected_head.receipt_id:
            return False
        if receipt.previous_receipt_sha256 != expected_head.receipt_sha256:
            return False
        if receipt.receipt_type != intent["receipt_type"]:
            return False
        if receipt.operation_id != intent["operation_id"]:
            return False
        if receipt.control_id != intent["control_id"] or receipt.run_id != intent["run_id"]:
            return False
        if receipt.local_transition_event_id != intent["local_transition_event_id"]:
            return False
        if receipt.local_transition_event_sha256 != intent["local_transition_event_sha256"]:
            return False
        if receipt.local_transition_sequence != intent["local_transition_sequence"]:
            return False
        if receipt.local_control_state_version != intent["local_control_state_version"]:
            return False
        if receipt.local_schema_user_version != intent["local_schema_user_version"]:
            return False
        if dict(receipt.metadata) != metadata:
            return False
        if signer_key_id is not None and receipt.signer_key_id != signer_key_id:
            return False
        return True

    def _build_receipt(
        self,
        *,
        intent: Mapping[str, Any],
        expected_head: AuthorityHead,
        key: KeyMaterial,
        receipts: Sequence[AuthorityReceipt],
        attempts: AttemptCounter,
        invocation: InvocationMetadata,
    ) -> AuthorityReceipt:
        now = self.clock()
        created_at = _canonical_utc(
            now,
            code="R8_3R6_AUTH_AUTHORITY_CLOCK_INVALID",
        )
        if receipts:
            previous_created = _parse_canonical_utc(
                receipts[-1].created_at,
                code="R8_3R6_AUTH_RECEIPT_TIME_INVALID",
            )
            if now.astimezone(UTC) < previous_created:
                _fail("R8_3R6_AUTH_RECEIPT_TIME_REGRESSION")

        full_metadata = self._full_metadata_for_intent(intent, key=key)
        unsigned = {
            "domain_separator": RECEIPT_DOMAIN_SEPARATOR,
            "root_sequence": expected_head.sequence + 1,
            "previous_receipt_id": expected_head.receipt_id,
            "previous_receipt_sha256": expected_head.receipt_sha256,
            "receipt_type": intent["receipt_type"],
            "operation_id": intent["operation_id"],
            "project_domain_id": PROJECT_DOMAIN_ID,
            "sport_id": SPORT_ID,
            "database_instance_id": self.config.database_instance_id,
            "control_id": intent["control_id"],
            "run_id": intent["run_id"],
            "local_transition_event_id": intent["local_transition_event_id"],
            "local_transition_event_sha256": intent[
                "local_transition_event_sha256"
            ],
            "local_transition_sequence": intent["local_transition_sequence"],
            "local_control_state_version": intent["local_control_state_version"],
            "local_schema_user_version": LOCAL_SCHEMA_USER_VERSION,
            "receipt_protocol_version": ROOT_PROTOCOL_VERSION,
            "created_at": created_at,
            "signer_key_id": key.signer_key_id,
            "root_store_id": self.config.root_store_id,
            "metadata": full_metadata,
        }
        payload_bytes = _canonical_bytes(unsigned)
        payload_sha = _sha_bytes(payload_bytes)
        signature = self._sign(
            payload_bytes,
            key=key,
            attempts=attempts,
            invocation=invocation,
        )
        signature_b64 = base64.b64encode(signature).decode("ascii")
        receipt_id = _sha(
            {
                "schema": RECEIPT_ID_SCHEMA,
                "canonical_payload_sha256": payload_sha,
                "signature_b64": signature_b64,
            }
        )
        receipt = AuthorityReceipt(
            receipt_id=receipt_id,
            root_sequence=expected_head.sequence + 1,
            previous_receipt_id=expected_head.receipt_id,
            previous_receipt_sha256=expected_head.receipt_sha256,
            receipt_type=intent["receipt_type"],
            operation_id=intent["operation_id"],
            project_domain_id=PROJECT_DOMAIN_ID,
            sport_id=SPORT_ID,
            database_instance_id=self.config.database_instance_id,
            control_id=intent["control_id"],
            run_id=intent["run_id"],
            local_transition_event_id=intent["local_transition_event_id"],
            local_transition_event_sha256=intent[
                "local_transition_event_sha256"
            ],
            local_transition_sequence=intent["local_transition_sequence"],
            local_control_state_version=intent["local_control_state_version"],
            local_schema_user_version=LOCAL_SCHEMA_USER_VERSION,
            receipt_protocol_version=ROOT_PROTOCOL_VERSION,
            created_at=created_at,
            signer_key_id=key.signer_key_id,
            canonical_payload_sha256=payload_sha,
            signature_b64=signature_b64,
            root_store_id=self.config.root_store_id,
            metadata=full_metadata,
        )
        reparsed = AuthorityReceipt.from_bytes(receipt.canonical_bytes())
        verify_receipt_chain(
            [*receipts, reparsed],
            expected_root_store_id=self.config.root_store_id,
            expected_database_instance_id=self.config.database_instance_id,
        )
        return reparsed

    def _verify_extension(
        self,
        prior_receipts: Sequence[AuthorityReceipt],
        candidate: AuthorityReceipt,
    ) -> None:
        verify_receipt_chain(
            [*prior_receipts, candidate],
            expected_root_store_id=self.config.root_store_id,
            expected_database_instance_id=self.config.database_instance_id,
        )

    def _put_receipt(
        self,
        *,
        s3: Any,
        receipt: AuthorityReceipt,
        intent: Mapping[str, Any],
        expected_head: AuthorityHead,
        prior_receipts: Sequence[AuthorityReceipt],
        attempts: AttemptCounter,
        invocation: InvocationMetadata,
    ) -> tuple[str, AuthorityReceipt, bool]:
        self._remaining_guard(invocation, mutation=True)
        raw = receipt.canonical_bytes()
        key = self.config.receipt_key(receipt.root_sequence)
        params = {
            "Bucket": self.config.archive_bucket,
            "Key": key,
            "Body": raw,
            "ContentType": "application/json",
            "IfNoneMatch": "*",
            "Metadata": {
                "matrix-receipt-sha256": receipt.receipt_sha256,
                "matrix-receipt-id": receipt.receipt_id,
                "matrix-root-store-id": receipt.root_store_id,
                "matrix-database-instance-id": receipt.database_instance_id,
            },
        }
        ambiguous = False
        for attempt in range(1, self.max_attempts + 1):
            self._count(attempts, "s3_put")
            try:
                response = s3.put_object(**params)
            except Exception as error:
                status, code, ambiguous_error = _aws_error_info(error)
                if status in {401, 403} or code in _AUTH_CODES:
                    _fail("R8_3R6_AUTH_AWS_AUTHORIZATION_FAILED")
                if status == 412 or code == "PreconditionFailed":
                    existing = self._get_receipt(
                        s3=s3,
                        sequence=receipt.root_sequence,
                        attempts=attempts,
                        invocation=invocation,
                    )
                    assert existing is not None
                    self._verify_extension(prior_receipts, existing)
                    if (
                        existing.canonical_bytes() == raw
                        or self._receipt_semantically_matches_intent(
                            existing,
                            intent=intent,
                            expected_head=expected_head,
                            full_metadata=receipt.metadata,
                            signer_key_id=receipt.signer_key_id,
                        )
                    ):
                        return "IDEMPOTENT_EXISTING", existing, ambiguous
                    _fail("R8_3R6_AUTH_S3_COMPARE_AND_APPEND_FORK")
                if ambiguous_error:
                    ambiguous = True
                    existing = self._get_receipt(
                        s3=s3,
                        sequence=receipt.root_sequence,
                        attempts=attempts,
                        invocation=invocation,
                        allow_missing=True,
                    )
                    if existing is not None:
                        self._verify_extension(prior_receipts, existing)
                        if (
                            existing.canonical_bytes() == raw
                            or self._receipt_semantically_matches_intent(
                                existing,
                                intent=intent,
                                expected_head=expected_head,
                                full_metadata=receipt.metadata,
                                signer_key_id=receipt.signer_key_id,
                            )
                        ):
                            return (
                                "IDEMPOTENT_AFTER_AMBIGUOUS_OUTCOME",
                                existing,
                                True,
                            )
                        _fail("R8_3R6_AUTH_S3_AMBIGUOUS_OUTCOME_FORK")
                    if attempt >= self.max_attempts:
                        _fail("R8_3R6_AUTH_S3_AMBIGUOUS_OUTCOME_EXHAUSTED")
                    self.sleeper(attempt)
                    continue
                if status == 409 or code in {
                    "ConditionalRequestConflict",
                    "OperationAborted",
                }:
                    existing = self._get_receipt(
                        s3=s3,
                        sequence=receipt.root_sequence,
                        attempts=attempts,
                        invocation=invocation,
                        allow_missing=True,
                    )
                    if existing is not None:
                        self._verify_extension(prior_receipts, existing)
                        if (
                            existing.canonical_bytes() == raw
                            or self._receipt_semantically_matches_intent(
                                existing,
                                intent=intent,
                                expected_head=expected_head,
                                full_metadata=receipt.metadata,
                                signer_key_id=receipt.signer_key_id,
                            )
                        ):
                            return "IDEMPOTENT_EXISTING", existing, ambiguous
                        _fail("R8_3R6_AUTH_S3_COMPARE_AND_APPEND_FORK")
                    if attempt >= self.max_attempts:
                        _fail("R8_3R6_AUTH_S3_CONFLICT_RETRY_EXHAUSTED")
                    self.sleeper(attempt)
                    continue
                if (status is not None and status >= 500) or code in _TRANSIENT_CODES:
                    ambiguous = True
                    existing = self._get_receipt(
                        s3=s3,
                        sequence=receipt.root_sequence,
                        attempts=attempts,
                        invocation=invocation,
                        allow_missing=True,
                    )
                    if existing is not None:
                        self._verify_extension(prior_receipts, existing)
                        if (
                            existing.canonical_bytes() == raw
                            or self._receipt_semantically_matches_intent(
                                existing,
                                intent=intent,
                                expected_head=expected_head,
                                full_metadata=receipt.metadata,
                                signer_key_id=receipt.signer_key_id,
                            )
                        ):
                            return (
                                "IDEMPOTENT_AFTER_AMBIGUOUS_OUTCOME",
                                existing,
                                True,
                            )
                        _fail("R8_3R6_AUTH_S3_AMBIGUOUS_OUTCOME_FORK")
                    if attempt >= self.max_attempts:
                        _fail("R8_3R6_AUTH_S3_SERVICE_RETRY_EXHAUSTED")
                    self.sleeper(attempt)
                    continue
                raise

            if not isinstance(response, Mapping):
                _fail("R8_3R6_AUTH_S3_PUT_RESPONSE_INVALID")
            existing = self._get_receipt(
                s3=s3,
                sequence=receipt.root_sequence,
                attempts=attempts,
                invocation=invocation,
            )
            assert existing is not None
            if existing.canonical_bytes() != raw:
                _fail("R8_3R6_AUTH_S3_WRITE_READBACK_DIVERGENCE")
            return "APPENDED", existing, ambiguous
        _fail("R8_3R6_AUTH_S3_APPEND_RETRY_EXHAUSTED")

    def _response(
        self,
        *,
        status: str,
        request: ParsedRequest,
        attempts: AttemptCounter,
        receipt: AuthorityReceipt | None = None,
        head: AuthorityHead | None = None,
        reconciled: bool = False,
    ) -> Mapping[str, Any]:
        result: dict[str, Any] = {
            "schema": RESPONSE_SCHEMA,
            "ok": True,
            "status": status,
            "request_nonce": request.request_nonce,
            "operation": request.operation,
            "operation_id": None if receipt is None else receipt.operation_id,
            "root_store_id": self.config.root_store_id,
            "database_instance_id": self.config.database_instance_id,
            "authority_profile": AUTHORITY_PROFILE,
            "key_epoch": self.config.key_epoch,
            "receipt": None,
            "head": None,
            "archive": {
                "account_id": self.config.archive_account_id,
                "region": self.config.archive_region,
                "bucket": self.config.archive_bucket,
            },
            "attempts": attempts.payload(),
            "reconciled": bool(reconciled),
            "controlled_live_admissible": False,
            "stronger_external_authority_implemented": False,
            "production_admissible": False,
        }
        if receipt is not None:
            result["receipt"] = {
                "root_sequence": receipt.root_sequence,
                "receipt_id": receipt.receipt_id,
                "receipt_sha256": receipt.receipt_sha256,
                "receipt_type": receipt.receipt_type,
                "operation_id": receipt.operation_id,
                "signer_key_id": receipt.signer_key_id,
                "canonical_payload_sha256": receipt.canonical_payload_sha256,
                "created_at": receipt.created_at,
                "archive_key": self.config.receipt_key(receipt.root_sequence),
            }
        if head is not None:
            result["head"] = head.payload()
        return result

    def handle(
        self,
        event: Any,
        *,
        invocation: InvocationMetadata,
    ) -> Mapping[str, Any]:
        if not isinstance(invocation, InvocationMetadata):
            _fail("R8_3R6_AUTH_INVOCATION_METADATA_REQUIRED")
        invocation.validate_for(self.config)
        request = parse_request(event, self.config)
        attempts = AttemptCounter()

        if request.operation == "READ_HEAD":
            s3 = self._s3_client(
                request_nonce=request.request_nonce,
                attempts=attempts,
                invocation=invocation,
            )
            receipts = self._read_chain(
                s3=s3,
                attempts=attempts,
                invocation=invocation,
            )
            return self._response(
                status="HEAD",
                request=request,
                attempts=attempts,
                head=self._head(receipts),
            )

        if request.operation == "READ_RECEIPT":
            s3 = self._s3_client(
                request_nonce=request.request_nonce,
                attempts=attempts,
                invocation=invocation,
            )
            receipts = self._read_chain(
                s3=s3,
                attempts=attempts,
                invocation=invocation,
            )
            assert request.sequence is not None
            if request.sequence > len(receipts):
                _fail("R8_3R6_AUTH_S3_RECEIPT_MISSING")
            receipt = receipts[request.sequence - 1]
            return self._response(
                status="RECEIPT",
                request=request,
                attempts=attempts,
                receipt=receipt,
                head=self._head(receipts),
            )

        assert request.expected_head is not None
        assert request.receipt_intent is not None
        intent = request.receipt_intent

        # Every mutating invocation revalidates the configured KMS identity before
        # crossing into the archive boundary, including exact idempotent replays.
        key = self._load_key_material(
            attempts=attempts,
            invocation=invocation,
        )
        s3 = self._s3_client(
            request_nonce=request.request_nonce,
            attempts=attempts,
            invocation=invocation,
        )
        receipts = self._read_chain(
            s3=s3,
            attempts=attempts,
            invocation=invocation,
        )
        current_head = self._head(receipts)
        if receipts:
            active_key_id, _trusted = verify_receipt_chain(
                receipts,
                expected_root_store_id=self.config.root_store_id,
                expected_database_instance_id=self.config.database_instance_id,
            )
            if active_key_id != key.signer_key_id:
                _fail("R8_3R6_AUTH_ACTIVE_SIGNING_KEY_MISMATCH")
        full_metadata = self._full_metadata_for_intent(intent, key=key)

        if current_head != request.expected_head:
            if (
                current_head.sequence == request.expected_head.sequence + 1
                and receipts
                and self._receipt_semantically_matches_intent(
                    receipts[-1],
                    intent=intent,
                    expected_head=request.expected_head,
                    full_metadata=full_metadata,
                    signer_key_id=key.signer_key_id,
                )
            ):
                return self._response(
                    status="IDEMPOTENT_EXISTING",
                    request=request,
                    attempts=attempts,
                    receipt=receipts[-1],
                    head=current_head,
                )
            _fail("R8_3R6_AUTH_EXPECTED_HEAD_MISMATCH")

        # A same-sequence object may have appeared after list/reconstruction and
        # before KMS signing. Detect it before mutation when possible.
        existing = self._get_receipt(
            s3=s3,
            sequence=request.expected_head.sequence + 1,
            attempts=attempts,
            invocation=invocation,
            allow_missing=True,
        )
        if existing is not None:
            self._verify_extension(receipts, existing)
            if self._receipt_semantically_matches_intent(
                existing,
                intent=intent,
                expected_head=request.expected_head,
                full_metadata=full_metadata,
                signer_key_id=key.signer_key_id,
            ):
                return self._response(
                    status="IDEMPOTENT_EXISTING",
                    request=request,
                    attempts=attempts,
                    receipt=existing,
                    head=AuthorityHead(
                        existing.root_sequence,
                        existing.receipt_id,
                        existing.receipt_sha256,
                    ),
                )
            _fail("R8_3R6_AUTH_S3_COMPARE_AND_APPEND_FORK")

        receipt = self._build_receipt(
            intent=intent,
            expected_head=request.expected_head,
            key=key,
            receipts=receipts,
            attempts=attempts,
            invocation=invocation,
        )
        status, authoritative, reconciled = self._put_receipt(
            s3=s3,
            receipt=receipt,
            intent=intent,
            expected_head=request.expected_head,
            prior_receipts=receipts,
            attempts=attempts,
            invocation=invocation,
        )
        final_head = AuthorityHead(
            authoritative.root_sequence,
            authoritative.receipt_id,
            authoritative.receipt_sha256,
        )
        return self._response(
            status=status,
            request=request,
            attempts=attempts,
            receipt=authoritative,
            head=final_head,
            reconciled=reconciled,
        )


def build_real_service(
    *,
    env: Mapping[str, str] | None = None,
) -> AuthorityService:
    config = AuthorityConfig.from_environ(os.environ if env is None else env)
    try:
        import boto3
        from botocore.config import Config
    except ImportError as error:
        raise AuthorityError("R8_3R6_AUTH_RUNTIME_DEPENDENCIES_UNAVAILABLE") from error

    sdk_config = Config(
        retries={"total_max_attempts": 1, "mode": "standard"},
        connect_timeout=3,
        read_timeout=5,
    )
    kms = boto3.client(
        "kms",
        region_name=config.signing_region,
        config=sdk_config,
    )
    sts = boto3.client(
        "sts",
        region_name=config.signing_region,
        config=sdk_config,
    )

    def s3_factory(credentials: Mapping[str, str], region: str) -> Any:
        return boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            config=sdk_config,
        )

    return AuthorityService(
        config=config,
        kms_client=kms,
        sts_client=sts,
        s3_client_factory=s3_factory,
    )


def _safe_nonce(event: Any) -> str | None:
    if isinstance(event, Mapping):
        value = event.get("request_nonce")
        if isinstance(value, str) and _NONCE.fullmatch(value) is not None:
            return value
    return None


def _error_response(code: str, *, request_nonce: str | None) -> Mapping[str, Any]:
    return {
        "schema": RESPONSE_SCHEMA,
        "ok": False,
        "status": "FAIL_CLOSED",
        "error_code": code,
        "request_nonce": request_nonce,
        "controlled_live_admissible": False,
        "stronger_external_authority_implemented": False,
        "production_admissible": False,
    }


def _safe_log_error(code: str, request_nonce: str | None) -> None:
    payload = {
        "schema": "matrix.c2-r8-3r6-authority-log/1",
        "level": "ERROR",
        "error_code": code,
        "request_nonce_sha256": (
            None
            if request_nonce is None
            else _sha_bytes(request_nonce.encode("utf-8"))
        ),
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def handler(event: Any, context: Any) -> Mapping[str, Any]:
    nonce = _safe_nonce(event)
    try:
        if context is None:
            _fail("R8_3R6_AUTH_LAMBDA_CONTEXT_REQUIRED")
        invoked_arn = getattr(context, "invoked_function_arn", None)
        remaining = getattr(context, "get_remaining_time_in_millis", None)
        if not callable(remaining):
            _fail("R8_3R6_AUTH_LAMBDA_CONTEXT_REQUIRED")
        service = build_real_service()
        return service.handle(
            event,
            invocation=InvocationMetadata(
                invoked_function_arn=invoked_arn,
                remaining_time_in_millis=remaining,
            ),
        )
    except AuthorityError as error:
        _safe_log_error(error.code, nonce)
        return _error_response(error.code, request_nonce=nonce)
    except Exception:
        code = "R8_3R6_AUTH_UNEXPECTED_FAIL_CLOSED"
        _safe_log_error(code, nonce)
        return _error_response(code, request_nonce=nonce)
