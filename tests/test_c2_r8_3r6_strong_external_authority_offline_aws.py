from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import inspect

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from app.application.football.external_integrity_root import (
    EphemeralEd25519SigningAuthority,
    R83R6RootReceipt,
    R83R6StoreHead,
    _canonical,
    _sha,
    build_signed_receipt,
)
from app.application.football.strong_external_authority import (
    R8_3R6_AWS_KMS_SIGNING_ALGORITHM,
    R8_3R6_STRONG_AUTHORITY_ARCHITECTURE,
    R83R6AwsApiRequest,
    R83R6AwsApiResponse,
    R83R6AwsKmsActivationEvidence,
    R83R6AwsS3ActivationEvidence,
    R83R6OfflineAwsKmsEd25519SigningAuthority,
    R83R6OfflineAwsStrongAuthorityAdapter,
    R83R6StrongAuthorityStreamIdentity,
    R83R6StrongExternalAuthorityPort,
)


BASE = datetime(2026, 8, 25, 22, 0, tzinfo=UTC)
ROOT = "a" * 64
DB = "b" * 64


class FakeTransport:
    offline_only = True

    def __init__(self, responses=()):
        self.responses = list(responses)
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected transport call")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return item(request)
        return item


class OnlineTransport(FakeTransport):
    offline_only = False


def _identity(**changes):
    values = dict(
        project_domain_id="matrix.c2",
        sport_id="football",
        root_store_id=ROOT,
        database_instance_id=DB,
        authority_profile=R8_3R6_STRONG_AUTHORITY_ARCHITECTURE,
        archive_account_id="111122223333",
        archive_bucket_arn="arn:aws:s3:::matrix-c2-eir-test",
        archive_region="us-east-1",
        authority_service_id="matrix-c2-eir-authority-v1",
        signing_account_id="444455556666",
        kms_key_arn=(
            "arn:aws:kms:us-west-2:444455556666:"
            "key/12345678-1234-1234-1234-123456789abc"
        ),
        key_epoch=1,
    )
    values.update(changes)
    return R83R6StrongAuthorityStreamIdentity(**values)


def _s3_evidence(identity=None, **changes):
    identity = _identity() if identity is None else identity
    values = dict(
        bucket_arn=identity.archive_bucket_arn,
        account_id=identity.archive_account_id,
        region=identity.archive_region,
        versioning_status="Enabled",
        object_lock_enabled=True,
        default_retention_mode="COMPLIANCE",
        default_retention_days=365,
        conditional_write_enforced=True,
        runtime_can_delete_receipts=False,
        runtime_can_change_retention=False,
        runtime_can_change_bucket_policy=False,
    )
    values.update(changes)
    return R83R6AwsS3ActivationEvidence(**values)


def _kms_evidence(identity=None, **changes):
    identity = _identity() if identity is None else identity
    values = dict(
        key_arn=identity.kms_key_arn,
        account_id=identity.signing_account_id,
        region=identity.kms_region,
        key_spec="ECC_NIST_EDWARDS25519",
        key_usage="SIGN_VERIFY",
        signing_algorithms=("ED25519_SHA_512",),
        key_state="Enabled",
        private_key_exportable=False,
        runtime_can_administer_key=False,
    )
    values.update(changes)
    return R83R6AwsKmsActivationEvidence(**values)


def _receipt(*, sequence=1, previous=None, root=ROOT, db=DB, op="c" * 64):
    signer = EphemeralEd25519SigningAuthority.generate()
    previous = R83R6StoreHead(0, None, None) if previous is None else previous
    unsigned = {
        "domain_separator": "matrix.c2-r8-3r6-external-integrity-root/1",
        "root_sequence": sequence,
        "previous_receipt_id": previous.receipt_id,
        "previous_receipt_sha256": previous.receipt_sha256,
        "receipt_type": "ROOT_GENESIS" if sequence == 1 else "ROOT_ABORTED",
        "operation_id": op,
        "project_domain_id": "matrix.c2",
        "sport_id": "football",
        "database_instance_id": db,
        "control_id": None,
        "run_id": None,
        "local_transition_event_id": None,
        "local_transition_event_sha256": None,
        "local_transition_sequence": None,
        "local_control_state_version": None,
        "local_schema_user_version": 87,
        "receipt_protocol_version": 1,
        "created_at": BASE.isoformat(),
        "signer_key_id": signer.key_id,
        "root_store_id": root,
        "metadata": {},
    }
    payload_sha = _sha(unsigned)
    import base64
    sig = base64.b64encode(signer.sign(_canonical(unsigned).encode("utf-8"))).decode("ascii")
    receipt_id = _sha({
        "schema": "matrix.c2-r8-3r6-receipt-id/1",
        "canonical_payload_sha256": payload_sha,
        "signature_b64": sig,
    })
    return R83R6RootReceipt(
        receipt_id=receipt_id,
        root_sequence=sequence,
        previous_receipt_id=previous.receipt_id,
        previous_receipt_sha256=previous.receipt_sha256,
        receipt_type=str(unsigned["receipt_type"]),
        operation_id=op,
        project_domain_id="matrix.c2",
        sport_id="football",
        database_instance_id=db,
        control_id=None,
        run_id=None,
        local_transition_event_id=None,
        local_transition_event_sha256=None,
        local_transition_sequence=None,
        local_control_state_version=None,
        local_schema_user_version=87,
        receipt_protocol_version=1,
        created_at=BASE.isoformat(),
        signer_key_id=signer.key_id,
        canonical_payload_sha256=payload_sha,
        signature_b64=sig,
        root_store_id=root,
        metadata={},
    )


def _adapter(transport, *, identity=None, evidence=None, max_attempts=3):
    identity = _identity() if identity is None else identity
    evidence = _s3_evidence(identity) if evidence is None else evidence
    return R83R6OfflineAwsStrongAuthorityAdapter(
        identity=identity,
        archive_evidence=evidence,
        transport=transport,
        max_conflict_attempts=max_attempts,
    )


def _get_response(receipt):
    return R83R6AwsApiResponse(200, {"Body": receipt.canonical_bytes()})


def test_identity_accepts_dual_boundary_and_distinct_kms_region():
    value = _identity()
    assert value.archive_region == "us-east-1"
    assert value.kms_region == "us-west-2"
    assert value.archive_account_id != value.signing_account_id


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"project_domain_id": "other"}, "PROJECT_DOMAIN"),
        ({"sport_id": "tennis"}, "SPORT"),
        ({"root_store_id": "x"}, "ROOT_STORE_ID"),
        ({"database_instance_id": "x"}, "DATABASE_INSTANCE_ID"),
        ({"authority_profile": "LOCAL_EXTERNAL_RESEARCH"}, "AUTHORITY_PROFILE"),
        ({"archive_account_id": "123"}, "ARCHIVE_ACCOUNT"),
        ({"archive_region": "bad"}, "ARCHIVE_REGION"),
        ({"signing_account_id": "123"}, "SIGNING_ACCOUNT"),
        ({"key_epoch": 0}, "KEY_EPOCH"),
    ],
)
def test_identity_rejects_invalid_core_fields(changes, message):
    with pytest.raises(ValueError, match=message):
        _identity(**changes)


def test_identity_rejects_bucket_arn_name_contract():
    with pytest.raises(ValueError, match="BUCKET"):
        _identity(archive_bucket_arn="arn:aws:s3:::BAD_BUCKET")


def test_identity_rejects_kms_account_mismatch():
    with pytest.raises(ValueError, match="KMS_KEY_ACCOUNT"):
        _identity(
            kms_key_arn=(
                "arn:aws:kms:us-west-2:999900001111:"
                "key/12345678-1234-1234-1234-123456789abc"
            )
        )


def test_receipt_key_genesis_is_sequence_one_and_global_stream():
    identity = _identity()
    key = identity.receipt_key(1)
    assert key.endswith("/receipts/00000000000000000001.json")
    assert "{control_id}" not in key
    assert "/control/" not in key


def test_receipt_key_does_not_accept_zero():
    with pytest.raises(ValueError, match="ROOT_SEQUENCE"):
        _identity().receipt_key(0)


def test_receipt_key_is_not_partitioned_by_control_or_run():
    identity = _identity()
    prefix = identity.receipt_prefix
    assert "control" not in prefix
    assert "run" not in prefix
    assert prefix == (
        f"matrix-eir/v1/matrix.c2/football/{ROOT}/{DB}/receipts/"
    )


def test_s3_evidence_accepts_required_compliance_controls():
    identity = _identity()
    assert _s3_evidence(identity).validate_for(identity) is True


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"versioning_status": "Suspended"}, "VERSIONING"),
        ({"object_lock_enabled": False}, "OBJECT_LOCK"),
        ({"default_retention_mode": "GOVERNANCE"}, "COMPLIANCE"),
        ({"default_retention_days": 0}, "RETENTION_DAYS"),
        ({"conditional_write_enforced": False}, "CONDITIONAL_WRITE"),
        ({"runtime_can_delete_receipts": True}, "DELETE_AUTHORITY"),
        ({"runtime_can_change_retention": True}, "RETENTION_ADMIN"),
        ({"runtime_can_change_bucket_policy": True}, "BUCKET_POLICY_ADMIN"),
    ],
)
def test_s3_evidence_rejects_admission_weakening(changes, message):
    identity = _identity()
    with pytest.raises(ValueError, match=message):
        _s3_evidence(identity, **changes).validate_for(identity)


def test_kms_evidence_accepts_ed25519_sign_verify_nonexportable():
    identity = _identity()
    assert _kms_evidence(identity).validate_for(identity) is True


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"key_spec": "ECC_NIST_P256"}, "ED25519_KEY_SPEC"),
        ({"key_usage": "ENCRYPT_DECRYPT"}, "SIGN_VERIFY"),
        ({"signing_algorithms": ("ECDSA_SHA_256",)}, "ED25519_SHA512"),
        ({"key_state": "Disabled"}, "NOT_ENABLED"),
        ({"private_key_exportable": True}, "PRIVATE_EXPORT"),
        ({"runtime_can_administer_key": True}, "KMS_ADMIN"),
    ],
)
def test_kms_evidence_rejects_key_weakening(changes, message):
    identity = _identity()
    with pytest.raises(ValueError, match=message):
        _kms_evidence(identity, **changes).validate_for(identity)


def test_offline_kms_signer_builds_exact_kms_request_and_verifies_signature():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    def sign_response(request):
        assert request.service == "kms"
        assert request.operation == "Sign"
        assert request.parameters["MessageType"] == "RAW"
        assert request.parameters["SigningAlgorithm"] == R8_3R6_AWS_KMS_SIGNING_ALGORITHM
        assert request.parameters["KeyId"] == _identity().kms_key_arn
        return R83R6AwsApiResponse(
            200,
            {"Signature": private.sign(request.parameters["Message"])},
        )

    transport = FakeTransport([sign_response])
    signer = R83R6OfflineAwsKmsEd25519SigningAuthority(
        identity=_identity(),
        public_key_bytes=public,
        activation_evidence=_kms_evidence(),
        transport=transport,
    )
    payload = b"canonical payload\n"
    assert signer.sign(payload) == private.sign(payload)
    assert signer.key_id.startswith("ed25519:")
    assert "private_key=<remote-unavailable>" in repr(signer)


def test_offline_kms_signer_rejects_invalid_returned_signature():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    transport = FakeTransport([
        R83R6AwsApiResponse(200, {"Signature": b"x" * 64})
    ])
    signer = R83R6OfflineAwsKmsEd25519SigningAuthority(
        identity=_identity(),
        public_key_bytes=public,
        activation_evidence=_kms_evidence(),
        transport=transport,
    )
    with pytest.raises(ValueError, match="SIGNATURE_VERIFICATION"):
        signer.sign(b"payload")


def test_offline_kms_signer_fails_closed_on_service_error():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signer = R83R6OfflineAwsKmsEd25519SigningAuthority(
        identity=_identity(),
        public_key_bytes=public,
        activation_evidence=_kms_evidence(),
        transport=FakeTransport([
            R83R6AwsApiResponse(403, {}, "AccessDenied")
        ]),
    )
    with pytest.raises(ValueError, match="SIGN_FAIL_CLOSED"):
        signer.sign(b"payload")


def test_network_capable_transport_is_rejected_by_both_offline_adapters():
    identity = _identity()
    with pytest.raises(ValueError, match="NETWORK_CAPABLE"):
        _adapter(OnlineTransport())
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    with pytest.raises(ValueError, match="NETWORK_CAPABLE"):
        R83R6OfflineAwsKmsEd25519SigningAuthority(
            identity=identity,
            public_key_bytes=public,
            activation_evidence=_kms_evidence(identity),
            transport=OnlineTransport(),
        )


def test_adapter_is_provider_neutral_port_but_not_controlled_live():
    adapter = _adapter(FakeTransport())
    assert isinstance(adapter, R83R6StrongExternalAuthorityPort)
    assert adapter.controlled_live_admissible is False
    assert adapter.stronger_external_authority_implemented is False
    assert adapter.backend_profile == "OFFLINE_AWS_STRONG_AUTHORITY_PROTOCOL_CANDIDATE"


def test_put_request_requires_if_none_match_star_and_global_key():
    receipt = _receipt()
    adapter = _adapter(FakeTransport())
    request = adapter.build_put_receipt_request(
        receipt,
        expected_head=R83R6StoreHead(0, None, None),
    )
    assert request.service == "s3"
    assert request.operation == "PutObject"
    assert request.parameters["IfNoneMatch"] == "*"
    assert request.parameters["Body"] == receipt.canonical_bytes()
    assert request.parameters["Key"].endswith("00000000000000000001.json")
    assert receipt.control_id is None


@pytest.mark.parametrize(
    ("receipt_changes", "message"),
    [
        ({"project_domain_id": "other"}, "PROJECT_DOMAIN"),
        ({"sport_id": "tennis"}, "SPORT"),
        ({"root_store_id": "d" * 64}, "ROOT_STORE"),
        ({"database_instance_id": "e" * 64}, "DATABASE_INSTANCE"),
    ],
)
def test_put_request_rejects_cross_identity_receipt(receipt_changes, message):
    receipt = replace(_receipt(), **receipt_changes)
    with pytest.raises(ValueError, match=message):
        _adapter(FakeTransport()).build_put_receipt_request(
            receipt,
            expected_head=R83R6StoreHead(0, None, None),
        )


def test_put_request_rejects_wrong_expected_predecessor():
    receipt = _receipt()
    with pytest.raises(ValueError, match="SEQUENCE_MISMATCH"):
        _adapter(FakeTransport()).build_put_receipt_request(
            receipt,
            expected_head=R83R6StoreHead(1, "d" * 64, "e" * 64),
        )


def test_get_and_list_requests_are_scoped_to_pinned_bucket_and_prefix():
    adapter = _adapter(FakeTransport())
    get = adapter.build_get_receipt_request(1)
    listing = adapter.build_list_receipts_request()
    assert get.parameters == {
        "Bucket": "matrix-c2-eir-test",
        "Key": adapter.receipt_key(1),
    }
    assert listing.parameters["Bucket"] == "matrix-c2-eir-test"
    assert listing.parameters["Prefix"] == _identity().receipt_prefix


def test_append_success_requires_read_after_write_exact_bytes():
    receipt = _receipt()
    transport = FakeTransport([
        R83R6AwsApiResponse(200, {"ETag": '"x"'}),
        _get_response(receipt),
    ])
    result = _adapter(transport).append_with_result(
        receipt,
        expected_head=R83R6StoreHead(0, None, None),
    )
    assert result.status == "APPENDED"
    assert result.attempts == 1
    assert len(transport.requests) == 2


def test_412_exact_existing_receipt_is_idempotent_success():
    receipt = _receipt()
    transport = FakeTransport([
        R83R6AwsApiResponse(412, {}, "PreconditionFailed"),
        _get_response(receipt),
    ])
    result = _adapter(transport).append_with_result(
        receipt,
        expected_head=R83R6StoreHead(0, None, None),
    )
    assert result.status == "IDEMPOTENT_EXISTING"


def test_412_conflicting_existing_receipt_is_fork_rejected():
    receipt = _receipt()
    conflict = _receipt(op="d" * 64)
    transport = FakeTransport([
        R83R6AwsApiResponse(412, {}, "PreconditionFailed"),
        _get_response(conflict),
    ])
    with pytest.raises(ValueError, match="FORK"):
        _adapter(transport).append(
            receipt,
            expected_head=R83R6StoreHead(0, None, None),
        )


def test_409_is_bounded_then_successful():
    receipt = _receipt()
    transport = FakeTransport([
        R83R6AwsApiResponse(409, {}, "ConditionalRequestConflict"),
        R83R6AwsApiResponse(200, {}),
        _get_response(receipt),
    ])
    result = _adapter(transport).append_with_result(
        receipt,
        expected_head=R83R6StoreHead(0, None, None),
    )
    assert result.status == "APPENDED"
    assert result.attempts == 2


def test_409_exhaustion_fails_closed():
    receipt = _receipt()
    transport = FakeTransport([
        R83R6AwsApiResponse(409, {}, "ConditionalRequestConflict"),
        R83R6AwsApiResponse(409, {}, "ConditionalRequestConflict"),
    ])
    with pytest.raises(ValueError, match="CONFLICT_RETRY_EXHAUSTED"):
        _adapter(transport, max_attempts=2).append(
            receipt,
            expected_head=R83R6StoreHead(0, None, None),
        )
    assert len(transport.requests) == 2


def test_ambiguous_timeout_with_committed_object_reconciles_without_rewrite():
    receipt = _receipt()
    transport = FakeTransport([
        TimeoutError("response lost"),
        _get_response(receipt),
    ])
    result = _adapter(transport).append_with_result(
        receipt,
        expected_head=R83R6StoreHead(0, None, None),
    )
    assert result.status == "IDEMPOTENT_AFTER_AMBIGUOUS_TIMEOUT"
    assert result.reconciled_after_ambiguous_outcome is True
    assert len(transport.requests) == 2


def test_ambiguous_timeout_with_conflicting_object_is_fork():
    receipt = _receipt()
    conflict = _receipt(op="e" * 64)
    transport = FakeTransport([
        TimeoutError("response lost"),
        _get_response(conflict),
    ])
    with pytest.raises(ValueError, match="AMBIGUOUS_TIMEOUT_FORK"):
        _adapter(transport).append(
            receipt,
            expected_head=R83R6StoreHead(0, None, None),
        )


def test_ambiguous_timeout_missing_object_is_bounded():
    receipt = _receipt()
    transport = FakeTransport([
        TimeoutError("1"),
        R83R6AwsApiResponse(404, {}, "NoSuchKey"),
        TimeoutError("2"),
        R83R6AwsApiResponse(404, {}, "NoSuchKey"),
    ])
    with pytest.raises(ValueError, match="AMBIGUOUS_TIMEOUT_EXHAUSTED"):
        _adapter(transport, max_attempts=2).append(
            receipt,
            expected_head=R83R6StoreHead(0, None, None),
        )


@pytest.mark.parametrize(
    "response",
    [
        R83R6AwsApiResponse(401, {}, "ExpiredToken"),
        R83R6AwsApiResponse(403, {}, "AccessDenied"),
    ],
)
def test_authentication_or_authorization_failure_is_not_retried(response):
    receipt = _receipt()
    transport = FakeTransport([response])
    with pytest.raises(ValueError, match="AUTHORIZATION_FAIL_CLOSED"):
        _adapter(transport).append(
            receipt,
            expected_head=R83R6StoreHead(0, None, None),
        )
    assert len(transport.requests) == 1


def test_service_failure_retry_is_bounded():
    receipt = _receipt()
    transport = FakeTransport([
        R83R6AwsApiResponse(503, {}, "ServiceUnavailable"),
        R83R6AwsApiResponse(503, {}, "ServiceUnavailable"),
    ])
    with pytest.raises(ValueError, match="SERVICE_RETRY_EXHAUSTED"):
        _adapter(transport, max_attempts=2).append(
            receipt,
            expected_head=R83R6StoreHead(0, None, None),
        )
    assert len(transport.requests) == 2


def test_retry_bound_cannot_be_unbounded():
    with pytest.raises(ValueError, match="RETRY_BOUND_TOO_LARGE"):
        _adapter(FakeTransport(), max_attempts=6)


def test_reconstruct_empty_listing_returns_zero_head():
    transport = FakeTransport([
        R83R6AwsApiResponse(200, {"Keys": []}),
    ])
    assert _adapter(transport).reconstruct_head_from_listing() == R83R6StoreHead(
        0, None, None
    )


def test_reconstruct_contiguous_listing_reads_and_returns_last_receipt():
    first = _receipt()
    second = _receipt(
        sequence=2,
        previous=R83R6StoreHead(
            first.root_sequence, first.receipt_id, first.receipt_sha256
        ),
        op="d" * 64,
    )
    identity = _identity()
    transport = FakeTransport([
        R83R6AwsApiResponse(
            200,
            {"Keys": [identity.receipt_key(2), identity.receipt_key(1)]},
        ),
        _get_response(first),
        _get_response(second),
    ])
    head = _adapter(transport).reconstruct_head_from_listing()
    assert head == R83R6StoreHead(2, second.receipt_id, second.receipt_sha256)


def test_reconstruct_listing_gap_fails_closed():
    identity = _identity()
    transport = FakeTransport([
        R83R6AwsApiResponse(
            200,
            {"Keys": [identity.receipt_key(1), identity.receipt_key(3)]},
        ),
    ])
    with pytest.raises(ValueError, match="SEQUENCE_GAP"):
        _adapter(transport).reconstruct_head_from_listing()


def test_reconstruct_listing_namespace_substitution_fails_closed():
    transport = FakeTransport([
        R83R6AwsApiResponse(
            200,
            {"Keys": ["other/prefix/00000000000000000001.json"]},
        ),
    ])
    with pytest.raises(ValueError, match="NAMESPACE_MISMATCH"):
        _adapter(transport).reconstruct_head_from_listing()


def test_read_existing_rejects_cross_database_transplant():
    receipt = _receipt(db="d" * 64)
    transport = FakeTransport([_get_response(receipt)])
    with pytest.raises(ValueError, match="DATABASE_INSTANCE_MISMATCH"):
        _adapter(transport)._read_existing(1)


def test_source_has_no_boto_requests_socket_or_environment_secret_reads():
    import app.application.football.strong_external_authority as module
    source = inspect.getsource(module)
    lowered = source.lower()
    assert "import boto3" not in lowered
    assert "import botocore" not in lowered
    assert "import requests" not in lowered
    assert "import socket" not in lowered
    assert "os.environ" not in lowered
    assert "getenv(" not in lowered


def test_request_parameters_do_not_contain_credential_fields():
    receipt = _receipt()
    adapter = _adapter(FakeTransport())
    requests = [
        adapter.build_put_receipt_request(
            receipt, expected_head=R83R6StoreHead(0, None, None)
        ),
        adapter.build_get_receipt_request(1),
        adapter.build_list_receipts_request(),
    ]
    forbidden = {
        "accesskeyid",
        "secretaccesskey",
        "sessiontoken",
        "credential",
        "password",
        "privatekey",
    }
    for request in requests:
        normalized = {str(key).replace("_", "").lower() for key in request.parameters}
        assert normalized.isdisjoint(forbidden)


def test_offline_adapter_never_claims_stronger_authority_implemented():
    adapter = _adapter(FakeTransport())
    assert adapter.stronger_external_authority_implemented is False
    assert adapter.controlled_live_admissible is False


def test_provider_neutral_append_returns_receipt_for_existing_store_contract():
    receipt = _receipt()
    transport = FakeTransport([
        R83R6AwsApiResponse(200, {}),
        _get_response(receipt),
    ])
    adapter = _adapter(transport)
    returned = adapter.append(
        receipt,
        expected_head=R83R6StoreHead(0, None, None),
    )
    assert returned == receipt


def test_read_receipts_validates_predecessor_chain():
    first = _receipt()
    second = _receipt(
        sequence=2,
        previous=R83R6StoreHead(
            first.root_sequence, first.receipt_id, first.receipt_sha256
        ),
        op="d" * 64,
    )
    identity = _identity()
    transport = FakeTransport([
        R83R6AwsApiResponse(
            200,
            {"Keys": [identity.receipt_key(1), identity.receipt_key(2)]},
        ),
        _get_response(first),
        _get_response(second),
    ])
    assert _adapter(transport).read_receipts() == (first, second)


def test_read_receipts_rejects_predecessor_divergence():
    first = _receipt()
    second = _receipt(
        sequence=2,
        previous=R83R6StoreHead(1, "d" * 64, "e" * 64),
        op="f" * 64,
    )
    identity = _identity()
    transport = FakeTransport([
        R83R6AwsApiResponse(
            200,
            {"Keys": [identity.receipt_key(1), identity.receipt_key(2)]},
        ),
        _get_response(first),
        _get_response(second),
    ])
    with pytest.raises(ValueError, match="PREDECESSOR"):
        _adapter(transport).read_receipts()


def test_existing_receipt_builder_accepts_offline_strong_port_and_remote_signer_structurally():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    def sign_response(request):
        return R83R6AwsApiResponse(
            200,
            {"Signature": private.sign(request.parameters["Message"])},
        )

    signer = R83R6OfflineAwsKmsEd25519SigningAuthority(
        identity=_identity(),
        public_key_bytes=public,
        activation_evidence=_kms_evidence(),
        transport=FakeTransport([sign_response]),
    )
    archive_transport = FakeTransport([
        R83R6AwsApiResponse(200, {"Keys": []}),
    ])
    adapter = _adapter(archive_transport)
    receipt = build_signed_receipt(
        store=adapter,
        signer=signer,
        receipt_type="ROOT_GENESIS",
        operation_id="c" * 64,
        database_instance_id=DB,
        created_at=BASE,
        metadata={
            "backend_profile": "OFFLINE_AWS_STRONG_AUTHORITY_PROTOCOL_CANDIDATE",
            "controlled_live_admissible": False,
        },
    )
    assert receipt.root_sequence == 1
    assert receipt.root_store_id == ROOT
    assert receipt.signer_key_id == signer.key_id
