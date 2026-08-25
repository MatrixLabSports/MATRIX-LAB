from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.application.football.bounded_live_control import (
    BoundedExecutorProcessScopeGuard,
    ExternalRootPreparedBinding,
    SQLiteBoundedFootballLiveControlStore,
    TransitionEventReference,
)


R8_3R6_ROOT_PROTOCOL_VERSION = 1
R8_3R6_PROJECT_DOMAIN_ID = "matrix.c2"
R8_3R6_SPORT_ID = "football"
R8_3R6_BACKEND_PROFILE_LOCAL_EXTERNAL_RESEARCH = "LOCAL_EXTERNAL_RESEARCH"
R8_3R6_BACKEND_PROFILE_CONTROLLED_LIVE = "CONTROLLED_LIVE_ADMISSIBLE"
R8_3R6_RECEIPT_TYPES = (
    "ROOT_GENESIS",
    "ROOT_PREPARED",
    "ROOT_COMMITTED",
    "ROOT_ABORTED",
    "ROOT_KEY_ROTATION",
)
R8_3R6_CRASH_POINTS = (
    "AFTER_EXTERNAL_PREPARE",
    "AFTER_LOCAL_COMMIT",
    "AFTER_EXTERNAL_COMMIT",
    "AFTER_LOCAL_ACK",
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> str:
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
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _sha256_hex(value: str, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"R8_3R6_{name.upper()}_SHA256_REQUIRED")
    normalized = value.strip().lower()
    if _HEX64.fullmatch(normalized) is None:
        raise ValueError(f"R8_3R6_{name.upper()}_SHA256_REQUIRED")
    return normalized


def _nonempty(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"R8_3R6_{name.upper()}_REQUIRED")
    return value.strip()


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"R8_3R6_{name.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def _canonical_timestamp(value: datetime, *, name: str) -> str:
    return _aware_utc(value, name=name).isoformat()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(value: str, *, name: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as error:
        raise ValueError(f"R8_3R6_{name.upper()}_BASE64_INVALID") from error


def _fsync_directory(path: Path) -> None:
    # Best-effort directory durability. Windows does not expose a portable
    # directory fsync through Python; file contents themselves are fsynced.
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_exclusive(path: Path, raw: bytes) -> None:
    # Publish fully-written bytes atomically without overwriting an existing
    # authority record. A crash can leave an ignored .tmp file, but never a
    # partially-written canonical receipt at the authoritative path.
    temp = path.parent / (
        "." + path.name + "." + os.urandom(8).hex() + ".tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(temp, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)
    try:
        os.link(temp, path)
        _fsync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)



@dataclass(frozen=True)
class R83R6RootReceipt:
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
        _sha256_hex(self.receipt_id, name="receipt_id")
        if type(self.root_sequence) is not int or self.root_sequence <= 0:
            raise ValueError("R8_3R6_ROOT_SEQUENCE_INVALID")
        if self.root_sequence == 1:
            if self.previous_receipt_id is not None or self.previous_receipt_sha256 is not None:
                raise ValueError("R8_3R6_GENESIS_PREDECESSOR_FORBIDDEN")
        else:
            _sha256_hex(str(self.previous_receipt_id), name="previous_receipt_id")
            _sha256_hex(str(self.previous_receipt_sha256), name="previous_receipt")
        if self.receipt_type not in R8_3R6_RECEIPT_TYPES:
            raise ValueError("R8_3R6_RECEIPT_TYPE_UNSUPPORTED")
        _sha256_hex(self.operation_id, name="operation_id")
        _nonempty(self.project_domain_id, name="project_domain_id")
        _nonempty(self.sport_id, name="sport_id")
        _sha256_hex(self.database_instance_id, name="database_instance_id")
        if self.control_id is not None:
            _sha256_hex(self.control_id, name="control_id")
        if self.run_id is not None:
            _sha256_hex(self.run_id, name="run_id")
        if self.local_transition_event_id is not None:
            _sha256_hex(self.local_transition_event_id, name="local_transition_event_id")
        if self.local_transition_event_sha256 is not None:
            _sha256_hex(self.local_transition_event_sha256, name="local_transition_event")
        if self.local_transition_sequence is not None and (
            type(self.local_transition_sequence) is not int or self.local_transition_sequence <= 0
        ):
            raise ValueError("R8_3R6_LOCAL_TRANSITION_SEQUENCE_INVALID")
        if self.local_control_state_version is not None and (
            type(self.local_control_state_version) is not int or self.local_control_state_version < 0
        ):
            raise ValueError("R8_3R6_LOCAL_STATE_VERSION_INVALID")
        if type(self.local_schema_user_version) is not int or self.local_schema_user_version <= 0:
            raise ValueError("R8_3R6_LOCAL_SCHEMA_USER_VERSION_INVALID")
        if self.receipt_protocol_version != R8_3R6_ROOT_PROTOCOL_VERSION:
            raise ValueError("R8_3R6_RECEIPT_SCHEMA_VERSION_UNSUPPORTED")
        parsed = datetime.fromisoformat(self.created_at)
        if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.astimezone(UTC).isoformat() != self.created_at:
            raise ValueError("R8_3R6_RECEIPT_TIMESTAMP_CANONICAL_REQUIRED")
        _nonempty(self.signer_key_id, name="signer_key_id")
        _sha256_hex(self.canonical_payload_sha256, name="canonical_payload")
        if not isinstance(self.signature_b64, str) or not self.signature_b64:
            raise ValueError("R8_3R6_SIGNATURE_REQUIRED")
        _sha256_hex(self.root_store_id, name="root_store_id")
        if not isinstance(self.metadata, Mapping):
            raise ValueError("R8_3R6_RECEIPT_METADATA_MAPPING_REQUIRED")

    def unsigned_payload(self) -> Mapping[str, Any]:
        return {
            "domain_separator": "matrix.c2-r8-3r6-external-integrity-root/1",
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
        return _canonical(self.storage_payload()).encode("utf-8")

    @property
    def receipt_sha256(self) -> str:
        return _sha_bytes(self.canonical_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes) -> "R83R6RootReceipt":
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("R8_3R6_RECEIPT_JSON_INVALID") from error
        if not isinstance(payload, dict):
            raise ValueError("R8_3R6_RECEIPT_OBJECT_REQUIRED")
        expected_keys = {
            "domain_separator", "root_sequence", "previous_receipt_id",
            "previous_receipt_sha256", "receipt_type", "operation_id",
            "project_domain_id", "sport_id", "database_instance_id",
            "control_id", "run_id", "local_transition_event_id",
            "local_transition_event_sha256", "local_transition_sequence",
            "local_control_state_version", "local_schema_user_version",
            "receipt_protocol_version", "created_at", "signer_key_id",
            "root_store_id", "metadata", "canonical_payload_sha256",
            "signature_b64", "receipt_id",
        }
        if set(payload) != expected_keys:
            raise ValueError("R8_3R6_RECEIPT_SCHEMA_KEYS_MISMATCH")
        if payload["domain_separator"] != "matrix.c2-r8-3r6-external-integrity-root/1":
            raise ValueError("R8_3R6_RECEIPT_DOMAIN_SEPARATOR_MISMATCH")
        obj = cls(
            receipt_id=str(payload["receipt_id"]),
            root_sequence=int(payload["root_sequence"]),
            previous_receipt_id=None if payload["previous_receipt_id"] is None else str(payload["previous_receipt_id"]),
            previous_receipt_sha256=None if payload["previous_receipt_sha256"] is None else str(payload["previous_receipt_sha256"]),
            receipt_type=str(payload["receipt_type"]),
            operation_id=str(payload["operation_id"]),
            project_domain_id=str(payload["project_domain_id"]),
            sport_id=str(payload["sport_id"]),
            database_instance_id=str(payload["database_instance_id"]),
            control_id=None if payload["control_id"] is None else str(payload["control_id"]),
            run_id=None if payload["run_id"] is None else str(payload["run_id"]),
            local_transition_event_id=None if payload["local_transition_event_id"] is None else str(payload["local_transition_event_id"]),
            local_transition_event_sha256=None if payload["local_transition_event_sha256"] is None else str(payload["local_transition_event_sha256"]),
            local_transition_sequence=None if payload["local_transition_sequence"] is None else int(payload["local_transition_sequence"]),
            local_control_state_version=None if payload["local_control_state_version"] is None else int(payload["local_control_state_version"]),
            local_schema_user_version=int(payload["local_schema_user_version"]),
            receipt_protocol_version=int(payload["receipt_protocol_version"]),
            created_at=str(payload["created_at"]),
            signer_key_id=str(payload["signer_key_id"]),
            canonical_payload_sha256=str(payload["canonical_payload_sha256"]),
            signature_b64=str(payload["signature_b64"]),
            root_store_id=str(payload["root_store_id"]),
            metadata=payload["metadata"],
        )
        if obj.canonical_bytes() != raw:
            raise ValueError("R8_3R6_RECEIPT_CANONICAL_BYTES_MISMATCH")
        unsigned_sha = _sha(obj.unsigned_payload())
        if obj.canonical_payload_sha256 != unsigned_sha:
            raise ValueError("R8_3R6_RECEIPT_PAYLOAD_DIGEST_MISMATCH")
        expected_id = _sha({
            "schema": "matrix.c2-r8-3r6-receipt-id/1",
            "canonical_payload_sha256": unsigned_sha,
            "signature_b64": obj.signature_b64,
        })
        if obj.receipt_id != expected_id:
            raise ValueError("R8_3R6_RECEIPT_ID_MISMATCH")
        return obj


class EphemeralEd25519SigningAuthority:
    """In-memory test/research signer. No persistence API is provided."""

    __slots__ = ("_private_key", "_public_raw", "key_id", "public_key_fingerprint")

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        if not isinstance(private_key, Ed25519PrivateKey):
            raise TypeError("R8_3R6_ED25519_PRIVATE_KEY_REQUIRED")
        self._private_key = private_key
        self._public_raw = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.public_key_fingerprint = _sha_bytes(self._public_raw)
        self.key_id = "ed25519:" + self.public_key_fingerprint

    @classmethod
    def generate(cls) -> "EphemeralEd25519SigningAuthority":
        return cls(Ed25519PrivateKey.generate())

    @property
    def public_key_bytes(self) -> bytes:
        return bytes(self._public_raw)

    def sign(self, payload: bytes) -> bytes:
        if not isinstance(payload, bytes):
            raise TypeError("R8_3R6_SIGNING_PAYLOAD_BYTES_REQUIRED")
        return self._private_key.sign(payload)

    def __repr__(self) -> str:
        return (
            "EphemeralEd25519SigningAuthority("
            f"key_id={self.key_id!r}, private_key=<redacted>)"
        )


@dataclass(frozen=True)
class R83R6TrustedPublicKey:
    key_id: str
    public_key_bytes: bytes

    def __post_init__(self) -> None:
        _nonempty(self.key_id, name="trusted_key_id")
        if not isinstance(self.public_key_bytes, bytes) or len(self.public_key_bytes) != 32:
            raise ValueError("R8_3R6_TRUSTED_PUBLIC_KEY_INVALID")
        fingerprint = _sha_bytes(self.public_key_bytes)
        if self.key_id != "ed25519:" + fingerprint:
            raise ValueError("R8_3R6_TRUSTED_KEY_ID_FINGERPRINT_MISMATCH")

    @property
    def fingerprint(self) -> str:
        return _sha_bytes(self.public_key_bytes)


@dataclass(frozen=True)
class R83R6StoreHead:
    sequence: int
    receipt_id: str | None
    receipt_sha256: str | None


class LocalDirectoryExternalIntegrityRootStore:
    """
    LOCAL_EXTERNAL_RESEARCH backend.

    Receipt and head-marker files are append-only through this API. The security
    claim assumes the external directory authority itself is not rolled back or
    rewritten by an attacker. It is not CONTROLLED_LIVE admissible.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        expected_root_store_id: str | None = None,
        create_if_missing: bool = True,
    ) -> None:
        self.path = Path(path).resolve()
        self.receipts_path = self.path / "receipts"
        self.heads_path = self.path / "head_markers"
        self.metadata_path = self.path / "store_metadata.json"
        self._lock = RLock()
        if self.metadata_path.exists():
            self._load_metadata(expected_root_store_id=expected_root_store_id)
        else:
            if not create_if_missing:
                raise ValueError("R8_3R6_ROOT_STORE_METADATA_REQUIRED")
            self._create(expected_root_store_id=expected_root_store_id)

    @property
    def backend_profile(self) -> str:
        return R8_3R6_BACKEND_PROFILE_LOCAL_EXTERNAL_RESEARCH

    @property
    def controlled_live_admissible(self) -> bool:
        return False

    def _create(self, *, expected_root_store_id: str | None) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self.receipts_path.mkdir(parents=True, exist_ok=True)
        self.heads_path.mkdir(parents=True, exist_ok=True)
        if expected_root_store_id is None:
            root_store_id = _sha({
                "schema": "matrix.c2-r8-3r6-root-store-id/1",
                "nonce": os.urandom(32).hex(),
            })
        else:
            root_store_id = _sha256_hex(expected_root_store_id, name="root_store_id")
        payload = {
            "schema": "matrix.c2-r8-3r6-local-external-research-store/1",
            "root_store_id": root_store_id,
            "protocol_version": R8_3R6_ROOT_PROTOCOL_VERSION,
            "backend_profile": R8_3R6_BACKEND_PROFILE_LOCAL_EXTERNAL_RESEARCH,
            "controlled_live_admissible": False,
        }
        raw = _canonical(payload).encode("utf-8")
        _write_exclusive(self.metadata_path, raw)
        self._load_metadata(expected_root_store_id=root_store_id)

    def _load_metadata(self, *, expected_root_store_id: str | None) -> None:
        try:
            raw = self.metadata_path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("R8_3R6_ROOT_STORE_METADATA_INVALID") from error
        if not isinstance(payload, dict) or set(payload) != {
            "schema", "root_store_id", "protocol_version", "backend_profile",
            "controlled_live_admissible",
        }:
            raise ValueError("R8_3R6_ROOT_STORE_METADATA_SCHEMA_MISMATCH")
        if raw != _canonical(payload).encode("utf-8"):
            raise ValueError("R8_3R6_ROOT_STORE_METADATA_CANONICAL_BYTES_MISMATCH")
        if payload["schema"] != "matrix.c2-r8-3r6-local-external-research-store/1":
            raise ValueError("R8_3R6_ROOT_STORE_METADATA_CONTRACT_MISMATCH")
        if int(payload["protocol_version"]) != R8_3R6_ROOT_PROTOCOL_VERSION:
            raise ValueError("R8_3R6_ROOT_STORE_PROTOCOL_VERSION_UNSUPPORTED")
        if payload["backend_profile"] != R8_3R6_BACKEND_PROFILE_LOCAL_EXTERNAL_RESEARCH:
            raise ValueError("R8_3R6_ROOT_STORE_BACKEND_PROFILE_MISMATCH")
        if payload["controlled_live_admissible"] is not False:
            raise ValueError("R8_3R6_ROOT_STORE_CONTROLLED_LIVE_CLAIM_FORBIDDEN")
        self.root_store_id = _sha256_hex(str(payload["root_store_id"]), name="root_store_id")
        if expected_root_store_id is not None and self.root_store_id != _sha256_hex(expected_root_store_id, name="expected_root_store_id"):
            raise ValueError("R8_3R6_ROOT_STORE_ID_MISMATCH")
        if not self.receipts_path.is_dir() or not self.heads_path.is_dir():
            raise ValueError("R8_3R6_ROOT_STORE_DIRECTORY_CONTRACT_MISMATCH")

    @staticmethod
    def _receipt_filename(sequence: int, receipt_id: str) -> str:
        return f"{sequence:020d}-{receipt_id}.receipt.json"

    @staticmethod
    def _head_filename(sequence: int, receipt_id: str, receipt_sha256: str) -> str:
        return f"{sequence:020d}-{receipt_id}-{receipt_sha256}.head"

    def _receipt_files(self) -> tuple[Path, ...]:
        return tuple(sorted(self.receipts_path.glob("*.receipt.json")))

    def _head_files(self) -> tuple[Path, ...]:
        return tuple(sorted(self.heads_path.glob("*.head")))

    def _scan_receipts(
        self,
        *,
        allow_one_trailing_unmarked_receipt: bool,
    ) -> tuple[tuple[R83R6RootReceipt, ...], R83R6RootReceipt | None]:
        self._load_metadata(expected_root_store_id=self.root_store_id)
        receipt_files = self._receipt_files()
        head_files = self._head_files()
        if len(receipt_files) == len(head_files):
            trailing_allowed = False
        elif (
            allow_one_trailing_unmarked_receipt
            and len(receipt_files) == len(head_files) + 1
        ):
            trailing_allowed = True
        else:
            raise ValueError(
                "R8_3R6_ROOT_STORE_RECEIPT_HEAD_CARDINALITY_MISMATCH"
            )

        receipts: list[R83R6RootReceipt] = []
        for expected_sequence, (receipt_path, head_path) in enumerate(
            zip(receipt_files[: len(head_files)], head_files), start=1
        ):
            raw = receipt_path.read_bytes()
            receipt = R83R6RootReceipt.from_bytes(raw)
            if receipt.root_sequence != expected_sequence:
                raise ValueError("R8_3R6_ROOT_STORE_SEQUENCE_GAP")
            if receipt.root_store_id != self.root_store_id:
                raise ValueError(
                    "R8_3R6_ROOT_STORE_RECEIPT_STORE_ID_MISMATCH"
                )
            expected_receipt_name = self._receipt_filename(
                expected_sequence, receipt.receipt_id
            )
            if receipt_path.name != expected_receipt_name:
                raise ValueError(
                    "R8_3R6_ROOT_STORE_RECEIPT_FILENAME_MISMATCH"
                )
            receipt_sha = _sha_bytes(raw)
            expected_head_name = self._head_filename(
                expected_sequence, receipt.receipt_id, receipt_sha
            )
            if head_path.name != expected_head_name:
                raise ValueError("R8_3R6_ROOT_STORE_HEAD_MARKER_MISMATCH")
            if head_path.read_bytes() != (expected_head_name + "\n").encode(
                "ascii"
            ):
                raise ValueError(
                    "R8_3R6_ROOT_STORE_HEAD_MARKER_CONTENT_MISMATCH"
                )
            receipts.append(receipt)

        trailing: R83R6RootReceipt | None = None
        if trailing_allowed:
            trailing_path = receipt_files[-1]
            raw = trailing_path.read_bytes()
            trailing = R83R6RootReceipt.from_bytes(raw)
            expected_sequence = len(receipts) + 1
            if trailing.root_sequence != expected_sequence:
                raise ValueError(
                    "R8_3R6_ROOT_STORE_TRAILING_RECEIPT_SEQUENCE_INVALID"
                )
            if trailing.root_store_id != self.root_store_id:
                raise ValueError(
                    "R8_3R6_ROOT_STORE_RECEIPT_STORE_ID_MISMATCH"
                )
            if trailing_path.name != self._receipt_filename(
                expected_sequence, trailing.receipt_id
            ):
                raise ValueError(
                    "R8_3R6_ROOT_STORE_RECEIPT_FILENAME_MISMATCH"
                )
            previous = receipts[-1] if receipts else None
            if trailing.previous_receipt_id != (
                None if previous is None else previous.receipt_id
            ):
                raise ValueError(
                    "R8_3R6_ROOT_STORE_TRAILING_PREDECESSOR_ID_MISMATCH"
                )
            if trailing.previous_receipt_sha256 != (
                None if previous is None else previous.receipt_sha256
            ):
                raise ValueError(
                    "R8_3R6_ROOT_STORE_TRAILING_PREDECESSOR_SHA_MISMATCH"
                )
        return tuple(receipts), trailing

    def read_receipts(self) -> tuple[R83R6RootReceipt, ...]:
        with self._lock:
            receipts, trailing = self._scan_receipts(
                allow_one_trailing_unmarked_receipt=False
            )
            assert trailing is None
            return receipts

    def head(self) -> R83R6StoreHead:
        receipts = self.read_receipts()
        if not receipts:
            return R83R6StoreHead(0, None, None)
        last = receipts[-1]
        return R83R6StoreHead(last.root_sequence, last.receipt_id, last.receipt_sha256)

    def append(
        self,
        receipt: R83R6RootReceipt,
        *,
        expected_head: R83R6StoreHead,
    ) -> R83R6RootReceipt:
        if not isinstance(receipt, R83R6RootReceipt):
            raise TypeError("R8_3R6_ROOT_RECEIPT_REQUIRED")
        if not isinstance(expected_head, R83R6StoreHead):
            raise TypeError("R8_3R6_EXPECTED_HEAD_REQUIRED")
        with self._lock:
            paired_receipts, trailing = self._scan_receipts(
                allow_one_trailing_unmarked_receipt=True
            )
            if paired_receipts:
                last = paired_receipts[-1]
                current = R83R6StoreHead(
                    last.root_sequence, last.receipt_id, last.receipt_sha256
                )
            else:
                current = R83R6StoreHead(0, None, None)

            if trailing is not None:
                if current != expected_head:
                    raise ValueError(
                        "R8_3R6_ROOT_STORE_COMPARE_AND_APPEND_CONFLICT"
                    )
                if trailing != receipt:
                    raise ValueError(
                        "R8_3R6_ROOT_STORE_UNFINALIZED_RECEIPT_DIVERGENCE"
                    )
                raw = trailing.canonical_bytes()
                head_name = self._head_filename(
                    trailing.root_sequence,
                    trailing.receipt_id,
                    _sha_bytes(raw),
                )
                head_path = self.heads_path / head_name
                if not head_path.exists():
                    _write_exclusive(
                        head_path, (head_name + "\n").encode("ascii")
                    )
                final = self.head()
                if (
                    final.sequence != trailing.root_sequence
                    or final.receipt_id != trailing.receipt_id
                    or final.receipt_sha256 != trailing.receipt_sha256
                ):
                    raise ValueError(
                        "R8_3R6_ROOT_STORE_TRAILING_RECEIPT_RECOVERY_FAILED"
                    )
                return trailing

            if current != expected_head:
                # Exact idempotent replay is permitted if the requested receipt
                # is already the authoritative current head.
                if (
                    current.sequence == receipt.root_sequence
                    and current.receipt_id == receipt.receipt_id
                    and current.receipt_sha256 == receipt.receipt_sha256
                ):
                    return receipt
                raise ValueError("R8_3R6_ROOT_STORE_COMPARE_AND_APPEND_CONFLICT")
            existing_receipts = paired_receipts
            for existing in existing_receipts:
                if (
                    existing.operation_id == receipt.operation_id
                    and existing.receipt_type == receipt.receipt_type
                ):
                    if existing == receipt:
                        return existing
                    raise ValueError("R8_3R6_OPERATION_TYPE_DIVERGENCE")
            if existing_receipts:
                previous_created = datetime.fromisoformat(
                    existing_receipts[-1].created_at
                ).astimezone(UTC)
                current_created = datetime.fromisoformat(
                    receipt.created_at
                ).astimezone(UTC)
                if current_created < previous_created:
                    raise ValueError("R8_3R6_RECEIPT_TIME_REGRESSION")

            if receipt.root_sequence != current.sequence + 1:
                raise ValueError("R8_3R6_ROOT_STORE_SEQUENCE_INVALID")
            if receipt.previous_receipt_id != current.receipt_id:
                raise ValueError("R8_3R6_ROOT_STORE_PREDECESSOR_ID_MISMATCH")
            if receipt.previous_receipt_sha256 != current.receipt_sha256:
                raise ValueError("R8_3R6_ROOT_STORE_PREDECESSOR_SHA_MISMATCH")
            if receipt.root_store_id != self.root_store_id:
                raise ValueError("R8_3R6_ROOT_STORE_ID_MISMATCH")

            raw = receipt.canonical_bytes()
            receipt_path = self.receipts_path / self._receipt_filename(
                receipt.root_sequence, receipt.receipt_id
            )
            head_name = self._head_filename(
                receipt.root_sequence, receipt.receipt_id, _sha_bytes(raw)
            )
            head_path = self.heads_path / head_name

            if receipt_path.exists():
                if receipt_path.read_bytes() != raw:
                    raise ValueError("R8_3R6_ROOT_STORE_EXISTING_RECEIPT_DIVERGENCE")
            else:
                _write_exclusive(receipt_path, raw)

            if head_path.exists():
                if head_path.read_bytes() != (head_name + "\n").encode("ascii"):
                    raise ValueError("R8_3R6_ROOT_STORE_EXISTING_HEAD_DIVERGENCE")
            else:
                _write_exclusive(head_path, (head_name + "\n").encode("ascii"))

            final_head = self.head()
            if (
                final_head.sequence != receipt.root_sequence
                or final_head.receipt_id != receipt.receipt_id
                or final_head.receipt_sha256 != receipt.receipt_sha256
            ):
                raise ValueError("R8_3R6_ROOT_STORE_DURABLE_APPEND_NOT_VERIFIED")
            return receipt

    def audit_integrity(self) -> bool:
        try:
            self.read_receipts()
            return True
        except (ValueError, OSError, TypeError, json.JSONDecodeError):
            return False


class R83R6InjectedCrash(RuntimeError):
    def __init__(self, point: str) -> None:
        super().__init__(f"R8_3R6_INJECTED_CRASH:{point}")
        self.point = point


def _maybe_crash(crash_point: str | None, point: str) -> None:
    if crash_point == point:
        raise R83R6InjectedCrash(point)


def _receipt_unsigned_payload(
    *,
    sequence: int,
    previous: R83R6StoreHead,
    receipt_type: str,
    operation_id: str,
    database_instance_id: str,
    root_store_id: str,
    signer_key_id: str,
    created_at: datetime,
    control_id: str | None = None,
    run_id: str | None = None,
    event: TransitionEventReference | None = None,
    local_schema_user_version: int = 87,
    metadata: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    if receipt_type not in R8_3R6_RECEIPT_TYPES:
        raise ValueError("R8_3R6_RECEIPT_TYPE_UNSUPPORTED")
    return {
        "domain_separator": "matrix.c2-r8-3r6-external-integrity-root/1",
        "root_sequence": sequence,
        "previous_receipt_id": previous.receipt_id,
        "previous_receipt_sha256": previous.receipt_sha256,
        "receipt_type": receipt_type,
        "operation_id": operation_id,
        "project_domain_id": R8_3R6_PROJECT_DOMAIN_ID,
        "sport_id": R8_3R6_SPORT_ID,
        "database_instance_id": database_instance_id,
        "control_id": control_id if control_id is not None else (None if event is None else event.control_id),
        "run_id": run_id if run_id is not None else (None if event is None else event.run_id),
        "local_transition_event_id": None if event is None else event.event_id,
        "local_transition_event_sha256": None if event is None else event.event_sha256,
        "local_transition_sequence": None if event is None else event.transition_sequence,
        "local_control_state_version": None if event is None else event.state_version_after,
        "local_schema_user_version": local_schema_user_version,
        "receipt_protocol_version": R8_3R6_ROOT_PROTOCOL_VERSION,
        "created_at": _canonical_timestamp(created_at, name="receipt_created_at"),
        "signer_key_id": signer_key_id,
        "root_store_id": root_store_id,
        "metadata": {} if metadata is None else dict(metadata),
    }


def build_signed_receipt(
    *,
    store: LocalDirectoryExternalIntegrityRootStore,
    signer: EphemeralEd25519SigningAuthority,
    receipt_type: str,
    operation_id: str,
    database_instance_id: str,
    created_at: datetime,
    control_id: str | None = None,
    run_id: str | None = None,
    event: TransitionEventReference | None = None,
    metadata: Mapping[str, Any] | None = None,
    expected_head: R83R6StoreHead | None = None,
) -> R83R6RootReceipt:
    head = store.head() if expected_head is None else expected_head
    unsigned = _receipt_unsigned_payload(
        sequence=head.sequence + 1,
        previous=head,
        receipt_type=receipt_type,
        operation_id=_sha256_hex(operation_id, name="operation_id"),
        database_instance_id=_sha256_hex(database_instance_id, name="database_instance_id"),
        root_store_id=store.root_store_id,
        signer_key_id=signer.key_id,
        created_at=created_at,
        control_id=control_id,
        run_id=run_id,
        event=event,
        metadata=metadata,
    )
    unsigned_sha = _sha(unsigned)
    signature = signer.sign(_canonical(unsigned).encode("utf-8"))
    signature_b64 = _b64(signature)
    receipt_id = _sha({
        "schema": "matrix.c2-r8-3r6-receipt-id/1",
        "canonical_payload_sha256": unsigned_sha,
        "signature_b64": signature_b64,
    })
    return R83R6RootReceipt(
        receipt_id=receipt_id,
        root_sequence=int(unsigned["root_sequence"]),
        previous_receipt_id=unsigned["previous_receipt_id"],
        previous_receipt_sha256=unsigned["previous_receipt_sha256"],
        receipt_type=str(unsigned["receipt_type"]),
        operation_id=str(unsigned["operation_id"]),
        project_domain_id=str(unsigned["project_domain_id"]),
        sport_id=str(unsigned["sport_id"]),
        database_instance_id=str(unsigned["database_instance_id"]),
        control_id=unsigned["control_id"],
        run_id=unsigned["run_id"],
        local_transition_event_id=unsigned["local_transition_event_id"],
        local_transition_event_sha256=unsigned["local_transition_event_sha256"],
        local_transition_sequence=unsigned["local_transition_sequence"],
        local_control_state_version=unsigned["local_control_state_version"],
        local_schema_user_version=int(unsigned["local_schema_user_version"]),
        receipt_protocol_version=int(unsigned["receipt_protocol_version"]),
        created_at=str(unsigned["created_at"]),
        signer_key_id=str(unsigned["signer_key_id"]),
        canonical_payload_sha256=unsigned_sha,
        signature_b64=signature_b64,
        root_store_id=str(unsigned["root_store_id"]),
        metadata=unsigned["metadata"],
    )


def verify_receipt_chain(
    receipts: tuple[R83R6RootReceipt, ...],
    *,
    expected_root_store_id: str,
    expected_database_instance_id: str,
    initial_trusted_key: R83R6TrustedPublicKey,
) -> Mapping[str, R83R6TrustedPublicKey]:
    root_store_id = _sha256_hex(expected_root_store_id, name="expected_root_store_id")
    database_instance_id = _sha256_hex(expected_database_instance_id, name="expected_database_instance_id")
    trusted: dict[str, R83R6TrustedPublicKey] = {initial_trusted_key.key_id: initial_trusted_key}
    active_key_id = initial_trusted_key.key_id
    previous_id: str | None = None
    previous_sha: str | None = None
    seen_receipt_ids: set[str] = set()
    seen_operations_by_type: dict[tuple[str, str], str] = {}
    prepared_by_operation: dict[str, R83R6RootReceipt] = {}
    terminal_operations: set[str] = set()
    previous_created_at: datetime | None = None

    for expected_sequence, receipt in enumerate(receipts, start=1):
        if receipt.root_sequence != expected_sequence:
            raise ValueError("R8_3R6_RECEIPT_SEQUENCE_GAP")
        if receipt.previous_receipt_id != previous_id:
            raise ValueError("R8_3R6_RECEIPT_PREDECESSOR_ID_MISMATCH")
        if receipt.previous_receipt_sha256 != previous_sha:
            raise ValueError("R8_3R6_RECEIPT_PREDECESSOR_SHA_MISMATCH")
        if receipt.receipt_id in seen_receipt_ids:
            raise ValueError("R8_3R6_RECEIPT_DUPLICATE_ID")
        seen_receipt_ids.add(receipt.receipt_id)
        if receipt.root_store_id != root_store_id:
            raise ValueError("R8_3R6_RECEIPT_ROOT_STORE_ID_MISMATCH")
        if receipt.database_instance_id != database_instance_id:
            raise ValueError("R8_3R6_RECEIPT_DATABASE_INSTANCE_MISMATCH")
        if receipt.project_domain_id != R8_3R6_PROJECT_DOMAIN_ID:
            raise ValueError("R8_3R6_RECEIPT_PROJECT_DOMAIN_MISMATCH")
        if receipt.sport_id != R8_3R6_SPORT_ID:
            raise ValueError("R8_3R6_RECEIPT_SPORT_MISMATCH")
        created = datetime.fromisoformat(receipt.created_at).astimezone(UTC)
        if previous_created_at is not None and created < previous_created_at:
            raise ValueError("R8_3R6_RECEIPT_TIME_REGRESSION")
        previous_created_at = created
        if receipt.signer_key_id != active_key_id:
            raise ValueError("R8_3R6_RECEIPT_SIGNER_KEY_CONTINUITY_MISMATCH")
        key = trusted.get(receipt.signer_key_id)
        if key is None:
            raise ValueError("R8_3R6_RECEIPT_SIGNER_UNTRUSTED")
        public_key = Ed25519PublicKey.from_public_bytes(key.public_key_bytes)
        try:
            public_key.verify(
                _unb64(receipt.signature_b64, name="signature"),
                _canonical(receipt.unsigned_payload()).encode("utf-8"),
            )
        except InvalidSignature as error:
            raise ValueError("R8_3R6_RECEIPT_SIGNATURE_INVALID") from error

        op_key = (receipt.operation_id, receipt.receipt_type)
        prior_same = seen_operations_by_type.get(op_key)
        if prior_same is not None and prior_same != receipt.receipt_id:
            raise ValueError("R8_3R6_OPERATION_TYPE_DIVERGENCE")
        seen_operations_by_type[op_key] = receipt.receipt_id

        if expected_sequence == 1:
            if receipt.receipt_type != "ROOT_GENESIS":
                raise ValueError("R8_3R6_ROOT_GENESIS_REQUIRED")
            if any(
                value is not None
                for value in (
                    receipt.control_id, receipt.run_id,
                    receipt.local_transition_event_id,
                    receipt.local_transition_event_sha256,
                    receipt.local_transition_sequence,
                    receipt.local_control_state_version,
                )
            ):
                raise ValueError("R8_3R6_GENESIS_TRANSITION_REFERENCE_FORBIDDEN")
        elif receipt.receipt_type == "ROOT_GENESIS":
            raise ValueError("R8_3R6_MULTIPLE_GENESIS_RECEIPTS_FORBIDDEN")

        if receipt.receipt_type == "ROOT_PREPARED":
            if receipt.operation_id in prepared_by_operation:
                raise ValueError("R8_3R6_PREPARE_DUPLICATE")
            if (
                receipt.control_id is None
                or receipt.run_id is None
                or receipt.local_transition_event_id is None
                or receipt.local_transition_event_sha256 is None
                or receipt.local_transition_sequence is None
                or receipt.local_control_state_version is None
            ):
                raise ValueError("R8_3R6_PREPARED_TRANSITION_REFERENCE_REQUIRED")
            prepared_by_operation[receipt.operation_id] = receipt
        elif receipt.receipt_type in {"ROOT_COMMITTED", "ROOT_ABORTED"}:
            prepared = prepared_by_operation.get(receipt.operation_id)
            if prepared is None:
                raise ValueError("R8_3R6_TERMINAL_RECEIPT_WITHOUT_PREPARE")
            if receipt.operation_id in terminal_operations:
                raise ValueError("R8_3R6_OPERATION_TERMINAL_DUPLICATE")
            terminal_operations.add(receipt.operation_id)
            metadata = dict(receipt.metadata)
            if (
                metadata.get("prepared_receipt_id") != prepared.receipt_id
                or metadata.get("prepared_receipt_sha256")
                != prepared.receipt_sha256
            ):
                raise ValueError("R8_3R6_TERMINAL_PREPARE_BINDING_MISMATCH")
            if receipt.receipt_type == "ROOT_COMMITTED":
                if (
                    receipt.control_id != prepared.control_id
                    or receipt.run_id != prepared.run_id
                    or receipt.local_transition_event_id
                    != prepared.local_transition_event_id
                    or receipt.local_transition_event_sha256
                    != prepared.local_transition_event_sha256
                    or receipt.local_transition_sequence
                    != prepared.local_transition_sequence
                ):
                    raise ValueError(
                        "R8_3R6_COMMITTED_PREPARED_TRANSITION_MISMATCH"
                    )
            else:
                if any(
                    value is not None
                    for value in (
                        receipt.local_transition_event_id,
                        receipt.local_transition_event_sha256,
                        receipt.local_transition_sequence,
                        receipt.local_control_state_version,
                    )
                ):
                    raise ValueError("R8_3R6_ABORTED_TRANSITION_REFERENCE_FORBIDDEN")

        if receipt.receipt_type == "ROOT_KEY_ROTATION":
            metadata = dict(receipt.metadata)
            required = {
                "new_key_id", "new_public_key_b64",
                "new_public_key_fingerprint",
                "new_key_proof_signature_b64", "activation_sequence",
                "proof_core",
            }
            if set(metadata) != required:
                raise ValueError("R8_3R6_KEY_ROTATION_METADATA_INVALID")
            new_raw = _unb64(
                str(metadata["new_public_key_b64"]),
                name="new_public_key",
            )
            if len(new_raw) != 32:
                raise ValueError("R8_3R6_KEY_ROTATION_PUBLIC_KEY_INVALID")
            new_fingerprint = _sha_bytes(new_raw)
            new_key_id = str(metadata["new_key_id"])
            if new_key_id != "ed25519:" + new_fingerprint:
                raise ValueError("R8_3R6_KEY_ROTATION_KEY_ID_MISMATCH")
            if str(metadata["new_public_key_fingerprint"]) != new_fingerprint:
                raise ValueError("R8_3R6_KEY_ROTATION_FINGERPRINT_MISMATCH")
            if int(metadata["activation_sequence"]) != receipt.root_sequence + 1:
                raise ValueError("R8_3R6_KEY_ROTATION_ACTIVATION_SEQUENCE_INVALID")
            expected_core = {
                "schema": "matrix.c2-r8-3r6-key-rotation-proof-core/1",
                "root_store_id": root_store_id,
                "database_instance_id": database_instance_id,
                "operation_id": receipt.operation_id,
                "new_key_id": new_key_id,
                "activation_sequence": receipt.root_sequence + 1,
            }
            if metadata["proof_core"] != expected_core:
                raise ValueError("R8_3R6_KEY_ROTATION_PROOF_CORE_MISMATCH")
            try:
                Ed25519PublicKey.from_public_bytes(new_raw).verify(
                    _unb64(
                        str(metadata["new_key_proof_signature_b64"]),
                        name="new_key_proof_signature",
                    ),
                    _canonical(expected_core).encode("utf-8"),
                )
            except InvalidSignature as error:
                raise ValueError(
                    "R8_3R6_KEY_ROTATION_NEW_KEY_PROOF_INVALID"
                ) from error
            trusted[new_key_id] = R83R6TrustedPublicKey(new_key_id, new_raw)
            active_key_id = new_key_id

        previous_id = receipt.receipt_id
        previous_sha = receipt.receipt_sha256

    return trusted


def _operation_id(
    *,
    database_instance_id: str,
    event: TransitionEventReference,
    root_store_id: str,
) -> str:
    return _sha({
        "schema": "matrix.c2-r8-3r6-root-operation/1",
        "database_instance_id": database_instance_id,
        "root_store_id": root_store_id,
        "event_id": event.event_id,
        "event_sha256": event.event_sha256,
        "transition_sequence": event.transition_sequence,
    })


class R83R6ExternalIntegrityRootCoordinator:
    def __init__(
        self,
        *,
        control_store: SQLiteBoundedFootballLiveControlStore,
        root_store: LocalDirectoryExternalIntegrityRootStore,
        signer: EphemeralEd25519SigningAuthority,
        bootstrap_trusted_key: R83R6TrustedPublicKey | None = None,
    ) -> None:
        if not isinstance(control_store, SQLiteBoundedFootballLiveControlStore):
            raise TypeError("R8_3R6_CONTROL_STORE_REQUIRED")
        if not isinstance(root_store, LocalDirectoryExternalIntegrityRootStore):
            raise TypeError("R8_3R6_EXTERNAL_ROOT_STORE_REQUIRED")
        if not isinstance(signer, EphemeralEd25519SigningAuthority):
            raise TypeError("R8_3R6_SIGNING_AUTHORITY_REQUIRED")
        self.control_store = control_store
        self.root_store = root_store
        self.signer = signer
        self.bootstrap_trusted_key = (
            R83R6TrustedPublicKey(signer.key_id, signer.public_key_bytes)
            if bootstrap_trusted_key is None
            else bootstrap_trusted_key
        )
        self._signers: dict[str, EphemeralEd25519SigningAuthority] = {
            signer.key_id: signer
        }

    def _state(self):
        return self.control_store.get_external_root_state()

    def ensure_genesis(self, *, created_at: datetime) -> R83R6RootReceipt:
        created = _aware_utc(created_at, name="genesis_created_at")
        state = self._state()
        receipts = self.root_store.read_receipts()
        if receipts:
            genesis = receipts[0]
            if genesis.receipt_type != "ROOT_GENESIS":
                raise ValueError("R8_3R6_ROOT_GENESIS_REQUIRED")
            if genesis.database_instance_id != state.database_instance_id:
                raise ValueError("R8_3R6_ROOT_GENESIS_DATABASE_INSTANCE_MISMATCH")
            if genesis.root_store_id != self.root_store.root_store_id:
                raise ValueError("R8_3R6_ROOT_GENESIS_STORE_ID_MISMATCH")
            # Recovery after external genesis but before local bind is only safe
            # if the current local snapshot is still exactly the genesis snapshot.
            if state.root_store_id is None:
                snapshot = self.control_store.external_root_genesis_snapshot()
                if str(genesis.metadata.get("local_snapshot_sha256")) != _sha(snapshot):
                    raise ValueError("R8_3R6_GENESIS_RECOVERY_LOCAL_SNAPSHOT_MISMATCH")
                self.control_store.bind_external_root_genesis(
                    root_store_id=self.root_store.root_store_id,
                    bootstrap_signer_key_id=self.bootstrap_trusted_key.key_id,
                    bootstrap_public_key_fingerprint=self.bootstrap_trusted_key.fingerprint,
                    genesis_receipt_id=genesis.receipt_id,
                    genesis_receipt_sha256=genesis.receipt_sha256,
                )
            else:
                self._assert_local_genesis_binding(genesis)
            return genesis

        if state.root_store_id is not None:
            raise ValueError("R8_3R6_BOUND_LOCAL_STATE_WITH_EMPTY_EXTERNAL_ROOT")
        snapshot = self.control_store.external_root_genesis_snapshot()
        metadata = {
            "backend_profile": self.root_store.backend_profile,
            "controlled_live_admissible": False,
            "local_snapshot_sha256": _sha(snapshot),
            "genesis_transition_events": list(snapshot["transition_events"]),
            "genesis_run_state": list(snapshot["run_state"]),
            "bootstrap_public_key_b64": _b64(self.bootstrap_trusted_key.public_key_bytes),
            "bootstrap_public_key_fingerprint": self.bootstrap_trusted_key.fingerprint,
            "bootstrap_signer_key_id": self.bootstrap_trusted_key.key_id,
        }
        operation_id = _sha({
            "schema": "matrix.c2-r8-3r6-root-genesis-operation/1",
            "database_instance_id": state.database_instance_id,
            "root_store_id": self.root_store.root_store_id,
            "local_snapshot_sha256": metadata["local_snapshot_sha256"],
        })
        receipt = build_signed_receipt(
            store=self.root_store,
            signer=self.signer,
            receipt_type="ROOT_GENESIS",
            operation_id=operation_id,
            database_instance_id=state.database_instance_id,
            created_at=created,
            metadata=metadata,
            expected_head=R83R6StoreHead(0, None, None),
        )
        self.root_store.append(receipt, expected_head=R83R6StoreHead(0, None, None))
        self.control_store.bind_external_root_genesis(
            root_store_id=self.root_store.root_store_id,
            bootstrap_signer_key_id=self.bootstrap_trusted_key.key_id,
            bootstrap_public_key_fingerprint=self.bootstrap_trusted_key.fingerprint,
            genesis_receipt_id=receipt.receipt_id,
            genesis_receipt_sha256=receipt.receipt_sha256,
        )
        return receipt

    def _assert_local_genesis_binding(self, genesis: R83R6RootReceipt) -> None:
        state = self._state()
        if state.root_store_id != self.root_store.root_store_id:
            raise ValueError("R8_3R6_LOCAL_ROOT_STORE_ID_MISMATCH")
        if state.bootstrap_signer_key_id != self.bootstrap_trusted_key.key_id:
            raise ValueError("R8_3R6_LOCAL_BOOTSTRAP_KEY_ID_MISMATCH")
        if state.bootstrap_public_key_fingerprint != self.bootstrap_trusted_key.fingerprint:
            raise ValueError("R8_3R6_LOCAL_BOOTSTRAP_KEY_FINGERPRINT_MISMATCH")
        if state.genesis_receipt_id != genesis.receipt_id:
            raise ValueError("R8_3R6_LOCAL_GENESIS_RECEIPT_ID_MISMATCH")
        if state.genesis_receipt_sha256 != genesis.receipt_sha256:
            raise ValueError("R8_3R6_LOCAL_GENESIS_RECEIPT_SHA_MISMATCH")

    def _active_signer_for_chain(self, receipts: tuple[R83R6RootReceipt, ...]) -> EphemeralEd25519SigningAuthority:
        verify_receipt_chain(
            receipts,
            expected_root_store_id=self.root_store.root_store_id,
            expected_database_instance_id=self._state().database_instance_id,
            initial_trusted_key=self.bootstrap_trusted_key,
        )
        active_key_id = self.bootstrap_trusted_key.key_id
        for receipt in receipts:
            if receipt.receipt_type == "ROOT_KEY_ROTATION":
                active_key_id = str(receipt.metadata["new_key_id"])
        signer = self._signers.get(active_key_id)
        if signer is None:
            raise ValueError("R8_3R6_ACTIVE_SIGNING_KEY_UNAVAILABLE")
        return signer

    def _append_terminal_for_prepare(
        self,
        *,
        prepared: R83R6RootReceipt,
        receipt_type: str,
        created_at: datetime,
        event: TransitionEventReference | None,
    ) -> R83R6RootReceipt:
        receipts = self.root_store.read_receipts()
        all_terminals = [
            item for item in receipts
            if item.operation_id == prepared.operation_id
            and item.receipt_type in {"ROOT_COMMITTED", "ROOT_ABORTED"}
        ]
        if all_terminals:
            if len(all_terminals) != 1:
                raise ValueError("R8_3R6_OPERATION_TERMINAL_DUPLICATE")
            existing = all_terminals[0]
            if existing.receipt_type != receipt_type:
                raise ValueError("R8_3R6_OPERATION_TERMINAL_CONFLICT")
            if receipt_type == "ROOT_COMMITTED":
                if event is None or (
                    existing.local_transition_event_id != event.event_id
                    or existing.local_transition_event_sha256 != event.event_sha256
                ):
                    raise ValueError("R8_3R6_CONFLICTING_COMMIT_REPLAY")
            elif event is not None:
                raise ValueError("R8_3R6_ABORT_REPLAY_EVENT_FORBIDDEN")
            return existing
        signer = self._active_signer_for_chain(receipts)
        metadata = {
            "prepared_receipt_id": prepared.receipt_id,
            "prepared_receipt_sha256": prepared.receipt_sha256,
        }
        terminal = build_signed_receipt(
            store=self.root_store,
            signer=signer,
            receipt_type=receipt_type,
            operation_id=prepared.operation_id,
            database_instance_id=prepared.database_instance_id,
            created_at=created_at,
            control_id=prepared.control_id,
            run_id=prepared.run_id,
            event=event,
            metadata=metadata,
            expected_head=self.root_store.head(),
        )
        self.root_store.append(terminal, expected_head=R83R6StoreHead(
            terminal.root_sequence - 1,
            terminal.previous_receipt_id,
            terminal.previous_receipt_sha256,
        ))
        return terminal

    def _prepare(
        self,
        *,
        event: TransitionEventReference,
        created_at: datetime,
    ) -> R83R6RootReceipt:
        state = self._state()
        operation_id = _operation_id(
            database_instance_id=state.database_instance_id,
            event=event,
            root_store_id=self.root_store.root_store_id,
        )
        receipts = self.root_store.read_receipts()
        prior = [
            item for item in receipts
            if item.operation_id == operation_id and item.receipt_type == "ROOT_PREPARED"
        ]
        if prior:
            if len(prior) != 1:
                raise ValueError("R8_3R6_PREPARE_DUPLICATE")
            existing = prior[0]
            if (
                existing.local_transition_event_id != event.event_id
                or existing.local_transition_event_sha256 != event.event_sha256
                or existing.run_id != event.run_id
                or existing.control_id != event.control_id
            ):
                raise ValueError("R8_3R6_CONFLICTING_PREPARE_REPLAY")
            terminals = [
                item for item in receipts
                if item.operation_id == operation_id
                and item.receipt_type in {"ROOT_COMMITTED", "ROOT_ABORTED"}
            ]
            if terminals:
                raise ValueError("R8_3R6_PREPARE_REPLAY_AFTER_TERMINAL_FORBIDDEN")
            return existing

        self.verify_and_reconcile(recovery_at=created_at)
        state = self._state()
        receipts = self.root_store.read_receipts()
        signer = self._active_signer_for_chain(receipts)
        metadata = {
            "expected_outcome": event.outcome,
            "expected_prior_state": event.prior_state,
            "expected_next_state": event.next_state,
            "expected_state_version_before": event.state_version_before,
            "expected_state_version_after": event.state_version_after,
        }
        receipt = build_signed_receipt(
            store=self.root_store,
            signer=signer,
            receipt_type="ROOT_PREPARED",
            operation_id=operation_id,
            database_instance_id=state.database_instance_id,
            created_at=created_at,
            event=event,
            metadata=metadata,
            expected_head=self.root_store.head(),
        )
        self.root_store.append(receipt, expected_head=R83R6StoreHead(
            receipt.root_sequence - 1,
            receipt.previous_receipt_id,
            receipt.previous_receipt_sha256,
        ))
        return receipt

    @staticmethod
    def _binding(prepared: R83R6RootReceipt, event: TransitionEventReference) -> ExternalRootPreparedBinding:
        return ExternalRootPreparedBinding(
            operation_id=prepared.operation_id,
            root_store_id=prepared.root_store_id,
            signer_key_id=prepared.signer_key_id,
            prepared_receipt_id=prepared.receipt_id,
            prepared_receipt_sha256=prepared.receipt_sha256,
            expected_transition_event_id=event.event_id,
            expected_transition_event_sha256=event.event_sha256,
            expected_transition_sequence=event.transition_sequence,
            expected_outcome=event.outcome,
        )

    def transition_run_state(
        self,
        run_id: str,
        *,
        expected_state: str,
        expected_state_version: int,
        new_state: str,
        changed_at: datetime,
        guard: BoundedExecutorProcessScopeGuard,
        lease,
        crash_point: str | None = None,
    ):
        if crash_point is not None and crash_point not in R8_3R6_CRASH_POINTS:
            raise ValueError("R8_3R6_CRASH_POINT_INVALID")
        self.ensure_genesis(created_at=changed_at)
        event = self.control_store.preview_transition_event(
            run_id,
            expected_state=expected_state,
            expected_state_version=expected_state_version,
            attempted_new_state=new_state,
            outcome="STATE_TRANSITION_COMMITTED",
            changed_at=changed_at,
            guard=guard,
            lease=lease,
        )
        prepared = self._prepare(event=event, created_at=changed_at)
        _maybe_crash(crash_point, "AFTER_EXTERNAL_PREPARE")
        binding = self._binding(prepared, event)
        snapshot = self.control_store.transition_run_state(
            run_id,
            expected_state=expected_state,
            expected_state_version=expected_state_version,
            new_state=new_state,
            changed_at=changed_at,
            guard=guard,
            lease=lease,
            external_root_prepare=binding,
        )
        _maybe_crash(crash_point, "AFTER_LOCAL_COMMIT")
        actual = self.control_store.get_transition_event(event.event_id)
        if actual != event:
            raise ValueError("R8_3R6_LOCAL_COMMIT_EVENT_DIVERGENCE")
        committed = self._append_terminal_for_prepare(
            prepared=prepared,
            receipt_type="ROOT_COMMITTED",
            created_at=changed_at,
            event=actual,
        )
        _maybe_crash(crash_point, "AFTER_EXTERNAL_COMMIT")
        self.control_store.acknowledge_external_root_commit(
            operation_id=prepared.operation_id,
            root_store_id=self.root_store.root_store_id,
            committed_receipt_id=committed.receipt_id,
            committed_receipt_sha256=committed.receipt_sha256,
            acknowledged_at=changed_at,
        )
        _maybe_crash(crash_point, "AFTER_LOCAL_ACK")
        self.verify_and_reconcile(recovery_at=changed_at)
        return snapshot

    def record_transition_attempt_outcome(
        self,
        run_id: str,
        *,
        expected_state: str,
        expected_state_version: int,
        attempted_new_state: str,
        outcome: str,
        changed_at: datetime,
        guard: BoundedExecutorProcessScopeGuard,
        lease,
        crash_point: str | None = None,
    ):
        if outcome not in {"STATE_TRANSITION_FAILED", "STATE_TRANSITION_ABANDONED"}:
            raise ValueError("R8_3R6_NONCOMMITTED_OUTCOME_REQUIRED")
        if crash_point is not None and crash_point not in R8_3R6_CRASH_POINTS:
            raise ValueError("R8_3R6_CRASH_POINT_INVALID")
        self.ensure_genesis(created_at=changed_at)
        event = self.control_store.preview_transition_event(
            run_id,
            expected_state=expected_state,
            expected_state_version=expected_state_version,
            attempted_new_state=attempted_new_state,
            outcome=outcome,
            changed_at=changed_at,
            guard=guard,
            lease=lease,
        )
        prepared = self._prepare(event=event, created_at=changed_at)
        _maybe_crash(crash_point, "AFTER_EXTERNAL_PREPARE")
        binding = self._binding(prepared, event)
        snapshot = self.control_store.record_transition_attempt_outcome(
            run_id,
            expected_state=expected_state,
            expected_state_version=expected_state_version,
            attempted_new_state=attempted_new_state,
            outcome=outcome,
            changed_at=changed_at,
            guard=guard,
            lease=lease,
            external_root_prepare=binding,
        )
        _maybe_crash(crash_point, "AFTER_LOCAL_COMMIT")
        actual = self.control_store.get_transition_event(event.event_id)
        if actual != event:
            raise ValueError("R8_3R6_LOCAL_COMMIT_EVENT_DIVERGENCE")
        committed = self._append_terminal_for_prepare(
            prepared=prepared,
            receipt_type="ROOT_COMMITTED",
            created_at=changed_at,
            event=actual,
        )
        _maybe_crash(crash_point, "AFTER_EXTERNAL_COMMIT")
        self.control_store.acknowledge_external_root_commit(
            operation_id=prepared.operation_id,
            root_store_id=self.root_store.root_store_id,
            committed_receipt_id=committed.receipt_id,
            committed_receipt_sha256=committed.receipt_sha256,
            acknowledged_at=changed_at,
        )
        _maybe_crash(crash_point, "AFTER_LOCAL_ACK")
        self.verify_and_reconcile(recovery_at=changed_at)
        return snapshot

    def verify_and_reconcile(self, *, recovery_at: datetime) -> bool:
        recovery_time = _aware_utc(recovery_at, name="recovery_at")
        if not self.control_store.audit_integrity():
            raise ValueError("R8_3R6_LOCAL_CONTROL_INTEGRITY_FAILURE")
        state = self._state()
        receipts = self.root_store.read_receipts()
        if not receipts:
            if state.root_store_id is not None:
                raise ValueError("R8_3R6_EXTERNAL_ROOT_HISTORY_MISSING")
            return True
        genesis = receipts[0]
        if genesis.receipt_type != "ROOT_GENESIS":
            raise ValueError("R8_3R6_ROOT_GENESIS_REQUIRED")
        if state.root_store_id is None:
            # Only exact crash-after-genesis-before-local-bind can be repaired.
            snapshot = self.control_store.external_root_genesis_snapshot()
            if genesis.database_instance_id != state.database_instance_id:
                raise ValueError("R8_3R6_DATABASE_REPLACEMENT_DETECTED")
            if str(genesis.metadata.get("local_snapshot_sha256")) != _sha(snapshot):
                raise ValueError("R8_3R6_GENESIS_RECOVERY_LOCAL_SNAPSHOT_MISMATCH")
            self.control_store.bind_external_root_genesis(
                root_store_id=self.root_store.root_store_id,
                bootstrap_signer_key_id=self.bootstrap_trusted_key.key_id,
                bootstrap_public_key_fingerprint=self.bootstrap_trusted_key.fingerprint,
                genesis_receipt_id=genesis.receipt_id,
                genesis_receipt_sha256=genesis.receipt_sha256,
            )
            state = self._state()
        self._assert_local_genesis_binding(genesis)

        verify_receipt_chain(
            receipts,
            expected_root_store_id=self.root_store.root_store_id,
            expected_database_instance_id=state.database_instance_id,
            initial_trusted_key=self.bootstrap_trusted_key,
        )

        # Resolve outstanding PREPARE operations deterministically.
        prepared_by_op: dict[str, R83R6RootReceipt] = {}
        terminal_by_op: dict[str, R83R6RootReceipt] = {}
        for receipt in receipts[1:]:
            if receipt.receipt_type == "ROOT_PREPARED":
                if receipt.operation_id in prepared_by_op:
                    raise ValueError("R8_3R6_PREPARE_DUPLICATE")
                prepared_by_op[receipt.operation_id] = receipt
            elif receipt.receipt_type in {"ROOT_COMMITTED", "ROOT_ABORTED"}:
                if receipt.operation_id in terminal_by_op:
                    raise ValueError("R8_3R6_OPERATION_TERMINAL_DUPLICATE")
                terminal_by_op[receipt.operation_id] = receipt

        for operation_id, prepared in tuple(prepared_by_op.items()):
            terminal = terminal_by_op.get(operation_id)
            event = None
            if prepared.local_transition_event_id is not None:
                event = self.control_store.find_transition_event(prepared.local_transition_event_id)
            if terminal is None:
                if event is None:
                    terminal = self._append_terminal_for_prepare(
                        prepared=prepared,
                        receipt_type="ROOT_ABORTED",
                        created_at=recovery_time,
                        event=None,
                    )
                else:
                    if event.event_sha256 != prepared.local_transition_event_sha256:
                        raise ValueError("R8_3R6_PREPARED_LOCAL_EVENT_SHA_MISMATCH")
                    terminal = self._append_terminal_for_prepare(
                        prepared=prepared,
                        receipt_type="ROOT_COMMITTED",
                        created_at=recovery_time,
                        event=event,
                    )
                terminal_by_op[operation_id] = terminal
            if terminal.receipt_type == "ROOT_ABORTED":
                if event is not None:
                    raise ValueError("R8_3R6_ABORTED_OPERATION_HAS_LOCAL_TRANSITION")
            elif terminal.receipt_type == "ROOT_COMMITTED":
                if event is None:
                    raise ValueError("R8_3R6_COMMITTED_ROOT_MISSING_LOCAL_TRANSITION")
                if (
                    terminal.local_transition_event_id != event.event_id
                    or terminal.local_transition_event_sha256 != event.event_sha256
                    or prepared.local_transition_event_id != event.event_id
                    or prepared.local_transition_event_sha256 != event.event_sha256
                ):
                    raise ValueError("R8_3R6_COMMITTED_ROOT_LOCAL_TRANSITION_MISMATCH")
                coordination = self.control_store.find_external_root_coordination(operation_id)
                if coordination is None:
                    raise ValueError("R8_3R6_LOCAL_ROOT_COORDINATION_MISSING")
                if coordination.status == "LOCAL_COMMITTED":
                    self.control_store.acknowledge_external_root_commit(
                        operation_id=operation_id,
                        root_store_id=self.root_store.root_store_id,
                        committed_receipt_id=terminal.receipt_id,
                        committed_receipt_sha256=terminal.receipt_sha256,
                        acknowledged_at=recovery_time,
                    )
                elif (
                    coordination.status != "ACKNOWLEDGED"
                    or coordination.committed_receipt_id != terminal.receipt_id
                    or coordination.committed_receipt_sha256 != terminal.receipt_sha256
                ):
                    raise ValueError("R8_3R6_LOCAL_ACK_DIVERGENCE")

        # Re-read after possible recovery appends and verify the complete chain.
        receipts = self.root_store.read_receipts()
        verify_receipt_chain(
            receipts,
            expected_root_store_id=self.root_store.root_store_id,
            expected_database_instance_id=state.database_instance_id,
            initial_trusted_key=self.bootstrap_trusted_key,
        )

        genesis_events = tuple(
            (str(item["run_id"]), int(item["transition_sequence"]), str(item["event_id"]), str(item["event_sha256"]))
            for item in genesis.metadata.get("genesis_transition_events", [])
        )
        committed_events: list[tuple[str, int, str, str]] = []
        for receipt in receipts:
            if receipt.receipt_type == "ROOT_COMMITTED":
                if receipt.run_id is None or receipt.local_transition_sequence is None or receipt.local_transition_event_id is None or receipt.local_transition_event_sha256 is None:
                    raise ValueError("R8_3R6_COMMITTED_RECEIPT_TRANSITION_REFERENCE_REQUIRED")
                committed_events.append((
                    receipt.run_id,
                    receipt.local_transition_sequence,
                    receipt.local_transition_event_id,
                    receipt.local_transition_event_sha256,
                ))
        expected_events = tuple(sorted(genesis_events + tuple(committed_events)))
        actual_events = tuple(sorted(
            (item.run_id, item.transition_sequence, item.event_id, item.event_sha256)
            for item in self.control_store.list_transition_events()
        ))
        if actual_events != expected_events:
            raise ValueError("R8_3R6_LOCAL_EXTERNAL_TRANSITION_HISTORY_MISMATCH")
        return True

    def rotate_key(
        self,
        *,
        new_signer: EphemeralEd25519SigningAuthority,
        changed_at: datetime,
    ) -> R83R6RootReceipt:
        if not isinstance(new_signer, EphemeralEd25519SigningAuthority):
            raise TypeError("R8_3R6_NEW_SIGNER_REQUIRED")
        self.ensure_genesis(created_at=changed_at)
        self.verify_and_reconcile(recovery_at=changed_at)
        receipts = self.root_store.read_receipts()
        current_signer = self._active_signer_for_chain(receipts)
        head = self.root_store.head()
        operation_id = _sha({
            "schema": "matrix.c2-r8-3r6-key-rotation-operation/1",
            "root_store_id": self.root_store.root_store_id,
            "database_instance_id": self._state().database_instance_id,
            "prior_key_id": current_signer.key_id,
            "new_key_id": new_signer.key_id,
            "sequence": head.sequence + 1,
        })
        # The new-key proof must reference the eventual deterministic receipt ID,
        # but receipt ID also contains metadata. Break that cycle by binding proof
        # to the unsigned rotation core instead of the receipt ID.
        proof_core = {
            "schema": "matrix.c2-r8-3r6-key-rotation-proof-core/1",
            "root_store_id": self.root_store.root_store_id,
            "database_instance_id": self._state().database_instance_id,
            "operation_id": operation_id,
            "new_key_id": new_signer.key_id,
            "activation_sequence": head.sequence + 2,
        }
        proof_signature = new_signer.sign(_canonical(proof_core).encode("utf-8"))
        metadata = {
            "new_key_id": new_signer.key_id,
            "new_public_key_b64": _b64(new_signer.public_key_bytes),
            "new_public_key_fingerprint": new_signer.public_key_fingerprint,
            "new_key_proof_signature_b64": _b64(proof_signature),
            "activation_sequence": head.sequence + 2,
            "proof_core": proof_core,
        }
        receipt = build_signed_receipt(
            store=self.root_store,
            signer=current_signer,
            receipt_type="ROOT_KEY_ROTATION",
            operation_id=operation_id,
            database_instance_id=self._state().database_instance_id,
            created_at=changed_at,
            metadata=metadata,
            expected_head=head,
        )
        self.root_store.append(receipt, expected_head=head)
        self._signers[new_signer.key_id] = new_signer
        verify_receipt_chain(
            self.root_store.read_receipts(),
            expected_root_store_id=self.root_store.root_store_id,
            expected_database_instance_id=self._state().database_instance_id,
            initial_trusted_key=self.bootstrap_trusted_key,
        )
        return receipt
