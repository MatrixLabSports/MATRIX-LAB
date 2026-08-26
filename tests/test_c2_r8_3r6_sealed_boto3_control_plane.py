from __future__ import annotations

import ast
import dataclasses
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
from pathlib import Path
import sys
import types
import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "infra" / "aws" / "r8_3r6" / "sealed_boto3_control_plane.py"
spec = importlib.util.spec_from_file_location("sealed_boto3_control_plane", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeClient:
    def __init__(self, service, responses=None):
        self.service = service
        self.calls = []
        self.responses = responses or {}

    def __getattr__(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            value = self.responses.get(name, {"service": self.service, "method": name, "kwargs": kwargs})
            if callable(value):
                return value(**kwargs)
            return value
        return call


class FakeSession:
    def __init__(self, clients):
        self.clients = clients
        self.client_calls = []

    def client(self, service, **kwargs):
        self.client_calls.append((service, kwargs))
        return self.clients[service]


def binding(operation):
    if operation == "cloudformation:CreateChangeSet":
        template = '{"Resources":{}}'
        return m.MutationResourceBinding(
            operation=operation,
            stack_name="s",
            change_set_name="c",
            change_set_type="UPDATE",
            template_sha256=sha256(template.encode("utf-8")).hexdigest(),
        )
    if operation == "cloudformation:ExecuteChangeSet":
        return m.MutationResourceBinding(operation=operation, stack_name="s", change_set_name="c")
    if operation == "s3:CreateBucket":
        return m.MutationResourceBinding(operation=operation, bucket="b")
    if operation == "s3:PutObject":
        return m.MutationResourceBinding(
            operation=operation,
            bucket="b",
            key="k",
            body_sha256=sha256(b"x").hexdigest(),
        )
    raise AssertionError(operation)


def permit(*ops, provisioning=False, account="123456789012", region="us-east-1", bindings=None):
    ops = tuple(ops)
    if any(op != "sts:GetCallerIdentity" for op in ops) and "sts:GetCallerIdentity" not in ops:
        ops = ("sts:GetCallerIdentity",) + ops
    if bindings is None:
        bindings = tuple(binding(op) for op in ops if op in m.MUTATION_OPERATIONS)
    return m.ControlPlanePermit(
        account_id=account,
        region=region,
        credential_mode="STS_SESSION",
        allowed_operations=frozenset(ops),
        aws_network_authorized=False,
        offline_test_authorized=True,
        resource_provisioning_authorized=provisioning,
        resource_bindings=bindings,
    )


def plane(*ops, provisioning=False, sts_account="123456789012", sts_arn="arn:aws:sts::123456789012:assumed-role/matrix-deployer/session", bindings=None):
    clients = {
        "sts": FakeClient("sts", {"get_caller_identity": {"Account": sts_account, "Arn": sts_arn}}),
        "cloudformation": FakeClient("cloudformation"),
        "s3": FakeClient("s3"),
        "kms": FakeClient("kms"),
        "lambda": FakeClient("lambda"),
        "iam": FakeClient("iam"),
        "logs": FakeClient("logs"),
    }
    session = FakeSession(clients)
    boundary = m.create_offline_test_session_boundary(
        session,
        region="us-east-1",
    )
    cp = m.SealedBoto3ControlPlane(
        session=boundary,
        permit=permit(*ops, provisioning=provisioning, bindings=bindings),
    )
    return cp, session, clients


def test_constants_are_fail_closed():
    assert m.CONTROLLED_LIVE_ADMISSIBLE is False
    assert m.PRODUCTION_ADMISSIBLE is False
    assert m.SPORTS_PROVIDER_NETWORK_AUTHORIZATION_INHERITED is False


def test_operation_sets_are_disjoint():
    assert not (m.READ_ONLY_OPERATIONS & m.MUTATION_OPERATIONS)


def test_all_bindings_match_all_operations():
    assert set(m._OPERATION_BINDINGS) == set(m.ALL_OPERATIONS)


def test_no_top_level_boto3_or_botocore_import():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    assert not [n for n in names if n == "boto3" or n.startswith("botocore")]


@pytest.mark.parametrize("args", [
    ("", "secret", "token"),
    ("ASIA1234", "", "token"),
    ("ASIA1234", "secret", ""),
    ("AKIA1234", "secret", "token"),
    ("MATRIX_TEST_ONLY", "secret", "token"),
])
def test_temporary_credentials_reject_missing_long_lived_or_test_sentinel(args):
    with pytest.raises(m.ConfigurationError):
        m.TemporaryAwsCredentials(*args)


def test_temporary_credentials_repr_hides_secret_and_token():
    c = m.TemporaryAwsCredentials("ASIA0000000000000000", "SUPERSECRET", "SESSIONTOKEN")
    r = repr(c)
    assert "SUPERSECRET" not in r
    assert "SESSIONTOKEN" not in r
    assert "ASIA0000000000000000" in r


@pytest.mark.parametrize("account", ["", "123", "abcdefghijkl", "1234567890123"])
def test_permit_rejects_invalid_account(account):
    with pytest.raises(m.ConfigurationError):
        permit("sts:GetCallerIdentity", account=account)


@pytest.mark.parametrize("region", ["", "USE1", "us_east_1", "eu-1"])
def test_permit_rejects_invalid_region(region):
    with pytest.raises(m.ConfigurationError):
        permit("sts:GetCallerIdentity", region=region)


def test_permit_rejects_non_sts_credential_mode():
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="DEFAULT_CHAIN",
            allowed_operations=frozenset(),
            aws_network_authorized=False,
        )


def test_permit_rejects_unknown_operation():
    with pytest.raises(m.ConfigurationError):
        permit("ec2:RunInstances")


def test_permit_rejects_operations_when_network_false():
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"sts:GetCallerIdentity"}),
            aws_network_authorized=False,
        )


def test_permit_rejects_sports_provider_inheritance():
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset(),
            aws_network_authorized=False,
            sports_provider_network_authorization_inherited=True,
        )


def test_permit_rejects_mutation_without_provisioning():
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"sts:GetCallerIdentity", "s3:PutObject"}),
            aws_network_authorized=True,
            resource_provisioning_authorized=False,
            resource_bindings=(binding("s3:PutObject"),),
        )


def test_identity_verification_passes_and_is_sticky():
    cp, _, _ = plane("sts:GetCallerIdentity")
    out = cp.verify_identity()
    assert out["Account"] == "123456789012"
    assert cp.identity_verified is True
    assert cp.verified_account_id == "123456789012"


def test_identity_mismatch_fails_closed():
    cp, _, _ = plane("sts:GetCallerIdentity", sts_account="999999999999")
    with pytest.raises(m.IdentityMismatch):
        cp.verify_identity()
    assert cp.identity_verified is False
    assert cp.verified_account_id is None


def test_non_sts_operation_requires_identity_verification():
    cp, _, _ = plane("cloudformation:ValidateTemplate")
    with pytest.raises(m.AuthorizationDenied):
        cp.validate_template(template_body="{}")


def test_operation_not_allowlisted_is_blocked_after_identity():
    cp, _, _ = plane("sts:GetCallerIdentity")
    cp.verify_identity()
    with pytest.raises(m.AuthorizationDenied):
        cp.validate_template(template_body="{}")


def test_client_is_cached_per_service():
    cp, session, _ = plane("sts:GetCallerIdentity", "s3:GetBucketVersioning")
    cp.verify_identity()
    cp.get_bucket_versioning(bucket="b")
    cp.get_bucket_versioning(bucket="b")
    assert [x[0] for x in session.client_calls].count("s3") == 1


def test_client_uses_permit_region():
    cp, session, _ = plane("sts:GetCallerIdentity")
    cp.verify_identity()
    assert session.client_calls[0][1]["region_name"] == "us-east-1"


@pytest.mark.parametrize("method,args,operation,service,api", [
    ("validate_template", {"template_body": "{}"}, "cloudformation:ValidateTemplate", "cloudformation", "validate_template"),
    ("describe_stack", {"stack_name": "s"}, "cloudformation:DescribeStacks", "cloudformation", "describe_stacks"),
    ("get_bucket_versioning", {"bucket": "b"}, "s3:GetBucketVersioning", "s3", "get_bucket_versioning"),
    ("describe_key", {"key_id": "k"}, "kms:DescribeKey", "kms", "describe_key"),
    ("get_public_key", {"key_id": "k"}, "kms:GetPublicKey", "kms", "get_public_key"),
    ("get_role", {"role_name": "r"}, "iam:GetRole", "iam", "get_role"),
])
def test_read_methods_call_expected_api(method, args, operation, service, api):
    cp, _, clients = plane(operation)
    cp.verify_identity()
    getattr(cp, method)(**args)
    assert clients[service].calls[-1][0] == api


def test_head_object_includes_optional_version_id():
    cp, _, clients = plane("s3:HeadObject")
    cp.verify_identity()
    cp.head_object(bucket="b", key="k", version_id="v1")
    assert clients["s3"].calls[-1] == ("head_object", {"Bucket": "b", "Key": "k", "VersionId": "v1"})


def test_get_function_includes_qualifier():
    cp, _, clients = plane("lambda:GetFunction")
    cp.verify_identity()
    cp.get_function(function_name="fn", qualifier="7")
    assert clients["lambda"].calls[-1] == ("get_function", {"FunctionName": "fn", "Qualifier": "7"})


def test_describe_log_groups_prefix():
    cp, _, clients = plane("logs:DescribeLogGroups")
    cp.verify_identity()
    cp.describe_log_groups(prefix="/aws/lambda/")
    assert clients["logs"].calls[-1] == ("describe_log_groups", {"logGroupNamePrefix": "/aws/lambda/"})


@pytest.mark.parametrize("method,args", [
    ("validate_template", {"template_body": ""}),
    ("describe_stack", {"stack_name": ""}),
    ("get_bucket_versioning", {"bucket": ""}),
    ("head_object", {"bucket": "", "key": "k"}),
    ("describe_key", {"key_id": ""}),
    ("get_public_key", {"key_id": ""}),
    ("get_function", {"function_name": ""}),
    ("get_role", {"role_name": ""}),
])
def test_read_methods_validate_required_arguments(method, args):
    cp, _, _ = plane()
    with pytest.raises(m.ConfigurationError):
        getattr(cp, method)(**args)


def test_mutation_is_blocked_without_provisioning_at_permit_construction():
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"sts:GetCallerIdentity", "s3:PutObject"}),
            aws_network_authorized=True,
            resource_provisioning_authorized=False,
            resource_bindings=(binding("s3:PutObject"),),
        )


@pytest.mark.parametrize("method,args,operation,service,api", [
    ("create_change_set", {"StackName": "s", "ChangeSetName": "c", "ChangeSetType": "UPDATE", "TemplateBody": '{"Resources":{}}'}, "cloudformation:CreateChangeSet", "cloudformation", "create_change_set"),
    ("execute_change_set", {"change_set_name": "c"}, "cloudformation:ExecuteChangeSet", "cloudformation", "execute_change_set"),
    ("create_bucket", {"Bucket": "b"}, "s3:CreateBucket", "s3", "create_bucket"),
    ("put_object", {"Bucket": "b", "Key": "k", "Body": b"x"}, "s3:PutObject", "s3", "put_object"),
])
def test_mutation_methods_require_and_use_provisioning(method, args, operation, service, api):
    cp, _, clients = plane(operation, provisioning=True)
    cp.verify_identity()
    getattr(cp, method)(**args)
    assert clients[service].calls[-1][0] == api


def test_create_change_set_rejects_empty_kwargs():
    cp, _, _ = plane("cloudformation:CreateChangeSet", provisioning=True)
    cp.verify_identity()
    with pytest.raises(m.ConfigurationError):
        cp.create_change_set()


def test_execute_change_set_rejects_empty_name():
    cp, _, _ = plane("cloudformation:ExecuteChangeSet", provisioning=True)
    cp.verify_identity()
    with pytest.raises(m.ConfigurationError):
        cp.execute_change_set(change_set_name="")


def test_create_bucket_requires_bucket():
    cp, _, _ = plane("s3:CreateBucket", provisioning=True)
    cp.verify_identity()
    with pytest.raises(m.ConfigurationError):
        cp.create_bucket()


def test_put_object_requires_bucket_and_key():
    cp, _, _ = plane("s3:PutObject", provisioning=True)
    cp.verify_identity()
    with pytest.raises(m.ConfigurationError):
        cp.put_object(Bucket="b")


def test_create_explicit_boto3_session_passes_only_explicit_temporary_credentials(monkeypatch):
    calls = []
    fake_boto3 = types.SimpleNamespace(__version__="1.43.73", Session=lambda **kwargs: calls.append(kwargs) or FakeSession({}))
    fake_botocore = types.SimpleNamespace(__version__="1.43.73")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    creds = m.TemporaryAwsCredentials(
        "ASIA0000000000000000",
        "secret",
        "token",
        expiration=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    m.create_explicit_boto3_session(credentials=creds, region="us-east-1")
    assert calls == [{
        "aws_access_key_id": "ASIA0000000000000000",
        "aws_secret_access_key": "secret",
        "aws_session_token": "token",
        "region_name": "us-east-1",
    }]


def test_create_explicit_boto3_session_rejects_invalid_region(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(__version__="1.43.73", Session=lambda **kwargs: FakeSession({})))
    monkeypatch.setitem(sys.modules, "botocore", types.SimpleNamespace(__version__="1.43.73"))
    creds = m.TemporaryAwsCredentials(
        "ASIA0000000000000000",
        "secret",
        "token",
        expiration=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    with pytest.raises(m.ConfigurationError):
        m.create_explicit_boto3_session(credentials=creds, region="bad")


def test_build_botocore_config_has_expected_fail_closed_values():
    cfg = m.build_botocore_config()
    assert cfg.connect_timeout == 3
    assert cfg.read_timeout == 8
    assert cfg.retries["total_max_attempts"] == 1
    assert cfg.retries["mode"] == "standard"
    assert cfg.ignore_configured_endpoint_urls is True


# R8.3R6 independent-audit hardening regressions A01-A07.

def test_a01_permit_normalizes_mutable_allowlist_to_frozenset():
    raw = ["sts:GetCallerIdentity"]
    p = m.ControlPlanePermit(
        account_id="123456789012",
        region="us-east-1",
        credential_mode="STS_SESSION",
        allowed_operations=raw,
        aws_network_authorized=True,
    )
    raw.append("s3:PutObject")
    assert isinstance(p.allowed_operations, frozenset)
    assert p.allowed_operations == frozenset({"sts:GetCallerIdentity"})


def test_a01_resource_bindings_are_immutable_tuple():
    raw = [binding("s3:PutObject")]
    p = m.ControlPlanePermit(
        account_id="123456789012",
        region="us-east-1",
        credential_mode="STS_SESSION",
        allowed_operations=["sts:GetCallerIdentity", "s3:PutObject"],
        aws_network_authorized=True,
        resource_provisioning_authorized=True,
        resource_bindings=raw,
    )
    raw.clear()
    assert isinstance(p.resource_bindings, tuple)
    assert len(p.resource_bindings) == 1


def test_a02_constructor_rejects_caller_supplied_config_by_signature():
    clients = {"sts": FakeClient("sts")}
    with pytest.raises(TypeError):
        m.SealedBoto3ControlPlane(
            session=FakeSession(clients),
            permit=permit("sts:GetCallerIdentity"),
            config=object(),
        )


def test_a02_constructor_builds_canonical_config():
    cp, session, _ = plane("sts:GetCallerIdentity")
    cp.verify_identity()
    cfg = session.client_calls[0][1]["config"]
    assert cfg.connect_timeout == 3
    assert cfg.read_timeout == 8
    assert cfg.retries["total_max_attempts"] == 1
    assert cfg.ignore_configured_endpoint_urls is True


def test_a03_configured_endpoint_overrides_are_disabled():
    cfg = m.build_botocore_config()
    assert cfg.ignore_configured_endpoint_urls is True


@pytest.mark.parametrize("boto3_version,botocore_version", [
    ("99.0.0", "1.43.73"),
    ("1.43.73", "99.0.0"),
    (None, "1.43.73"),
    ("1.43.73", None),
])
def test_a04_runtime_version_drift_is_rejected(monkeypatch, boto3_version, botocore_version):
    fake_boto3 = types.SimpleNamespace(Session=lambda **kwargs: object())
    if boto3_version is not None:
        fake_boto3.__version__ = boto3_version
    fake_botocore = types.SimpleNamespace()
    if botocore_version is not None:
        fake_botocore.__version__ = botocore_version
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    creds = m.TemporaryAwsCredentials(
        "ASIA0000000000000000",
        "secret",
        "token",
        expiration=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    with pytest.raises(m.ConfigurationError):
        m.create_explicit_boto3_session(credentials=creds, region="us-east-1")


@pytest.mark.parametrize("kwargs", [
    {"operation": "cloudformation:CreateChangeSet", "stack_name": "s", "change_set_name": "c"},
    {"operation": "cloudformation:ExecuteChangeSet", "stack_name": "s", "change_set_name": "c"},
    {"operation": "s3:CreateBucket", "bucket": "b"},
    {"operation": "s3:PutObject", "bucket": "b", "key": "k"},
])
def test_a05_valid_mutation_resource_bindings(kwargs):
    assert m.MutationResourceBinding(**kwargs).operation == kwargs["operation"]


@pytest.mark.parametrize("kwargs", [
    {"operation": "cloudformation:CreateChangeSet", "stack_name": "s"},
    {"operation": "cloudformation:ExecuteChangeSet"},
    {"operation": "s3:CreateBucket"},
    {"operation": "s3:PutObject", "bucket": "b"},
    {"operation": "s3:PutObject", "bucket": "b", "key": "k", "stack_name": "s"},
    {"operation": "s3:GetBucketVersioning", "bucket": "b"},
])
def test_a05_invalid_mutation_resource_bindings_rejected(kwargs):
    with pytest.raises(m.ConfigurationError):
        m.MutationResourceBinding(**kwargs)


def test_a05_missing_resource_binding_rejected():
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"sts:GetCallerIdentity", "s3:PutObject"}),
            aws_network_authorized=True,
            resource_provisioning_authorized=True,
            resource_bindings=(),
        )


def test_a05_extra_resource_binding_rejected():
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"sts:GetCallerIdentity"}),
            aws_network_authorized=True,
            resource_provisioning_authorized=True,
            resource_bindings=(binding("s3:PutObject"),),
        )


def test_a05_duplicate_resource_binding_rejected():
    b = binding("s3:PutObject")
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"sts:GetCallerIdentity", "s3:PutObject"}),
            aws_network_authorized=True,
            resource_provisioning_authorized=True,
            resource_bindings=(b, b),
        )


@pytest.mark.parametrize("method,args,operation,bindings", [
    ("create_change_set", {"StackName": "other", "ChangeSetName": "c"}, "cloudformation:CreateChangeSet",
     (m.MutationResourceBinding(operation="cloudformation:CreateChangeSet", stack_name="s", change_set_name="c"),)),
    ("create_change_set", {"StackName": "s", "ChangeSetName": "other"}, "cloudformation:CreateChangeSet",
     (m.MutationResourceBinding(operation="cloudformation:CreateChangeSet", stack_name="s", change_set_name="c"),)),
    ("execute_change_set", {"change_set_name": "other"}, "cloudformation:ExecuteChangeSet",
     (m.MutationResourceBinding(operation="cloudformation:ExecuteChangeSet", stack_name="s", change_set_name="c"),)),
    ("create_bucket", {"Bucket": "other"}, "s3:CreateBucket",
     (m.MutationResourceBinding(operation="s3:CreateBucket", bucket="b"),)),
    ("put_object", {"Bucket": "other", "Key": "k", "Body": b"x"}, "s3:PutObject",
     (m.MutationResourceBinding(operation="s3:PutObject", bucket="b", key="k"),)),
    ("put_object", {"Bucket": "b", "Key": "other", "Body": b"x"}, "s3:PutObject",
     (m.MutationResourceBinding(operation="s3:PutObject", bucket="b", key="k"),)),
])
def test_a05_mutation_target_mismatch_fails_closed(method, args, operation, bindings):
    cp, _, _ = plane(operation, provisioning=True, bindings=bindings)
    cp.verify_identity()
    with pytest.raises(m.AuthorizationDenied):
        getattr(cp, method)(**args)


def test_a06_non_sts_permit_requires_get_caller_identity():
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"cloudformation:ValidateTemplate"}),
            aws_network_authorized=True,
        )


def test_a06_empty_permit_is_allowed_without_identity_operation():
    p = m.ControlPlanePermit(
        account_id="123456789012",
        region="us-east-1",
        credential_mode="STS_SESSION",
        allowed_operations=frozenset(),
        aws_network_authorized=False,
    )
    assert p.allowed_operations == frozenset()


def test_a07_matrix_test_only_sentinel_is_rejected():
    with pytest.raises(m.ConfigurationError):
        m.TemporaryAwsCredentials("MATRIX_TEST_ONLY", "secret", "token")


def test_build_botocore_config_rejects_botocore_version_drift(monkeypatch):
    fake_boto3 = types.SimpleNamespace(__version__="1.43.73")
    fake_botocore = types.ModuleType("botocore")
    fake_botocore.__version__ = "99.0.0"
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    with pytest.raises(m.ConfigurationError):
        m.build_botocore_config()


def test_control_plane_rejects_none_session():
    with pytest.raises(m.ConfigurationError):
        m.SealedBoto3ControlPlane(session=None, permit=permit("sts:GetCallerIdentity"))


def test_create_change_set_requires_both_bound_target_fields():
    cp, _, _ = plane("cloudformation:CreateChangeSet", provisioning=True)
    cp.verify_identity()
    with pytest.raises(m.ConfigurationError):
        cp.create_change_set(StackName="s")


# R8.3R6 post-independent-audit R2 hardening regressions B01-B08.

def test_b01_generic_injected_session_is_rejected():
    raw = FakeSession({"sts": FakeClient("sts")})
    with pytest.raises(m.ConfigurationError):
        m.SealedBoto3ControlPlane(
            session=raw,
            permit=permit("sts:GetCallerIdentity"),
        )


def test_b01_explicit_offline_test_boundary_is_sealed_and_network_false():
    cp, _, _ = plane("sts:GetCallerIdentity")
    assert isinstance(cp._session, m.SealedSessionBoundary)
    assert cp._session.is_offline_test_session is True
    assert cp._session.is_real_explicit_session is False
    assert cp._permit.aws_network_authorized is False
    assert cp._permit.offline_test_authorized is True


def test_b01_direct_boto3_session_injection_is_forbidden(monkeypatch):
    DirectBotoSession = type(
        "Session",
        (),
        {
            "__module__": "boto3.session",
            "client": lambda self, service, **kwargs: object(),
        },
    )
    with pytest.raises(m.ConfigurationError):
        m.SealedBoto3ControlPlane(
            session=DirectBotoSession(),
            permit=permit("sts:GetCallerIdentity"),
        )


def test_b02_default_principal_is_bound_to_matrix_deployer_role():
    p = permit("sts:GetCallerIdentity")
    assert (
        p.expected_principal_arn
        == "arn:aws:sts::123456789012:assumed-role/matrix-deployer/*"
    )


def test_b02_same_account_unexpected_principal_is_rejected():
    cp, _, _ = plane(
        "sts:GetCallerIdentity",
        sts_arn="arn:aws:iam::123456789012:user/unexpected-admin",
    )
    with pytest.raises(m.IdentityMismatch):
        cp.verify_identity()
    assert cp.identity_verified is False
    assert cp.verified_principal_arn is None


def test_b03_execute_change_set_name_without_stack_or_arn_is_rejected():
    with pytest.raises(m.ConfigurationError):
        m.MutationResourceBinding(
            operation="cloudformation:ExecuteChangeSet",
            change_set_name="matrix-change",
        )


def test_b03_execute_change_set_full_arn_is_accepted_without_stack():
    arn = (
        "arn:aws:cloudformation:us-east-1:123456789012:"
        "changeSet/matrix-change/01234567-89ab-cdef-0123-456789abcdef"
    )
    b = m.MutationResourceBinding(
        operation="cloudformation:ExecuteChangeSet",
        change_set_name=arn,
    )
    assert b.stack_name is None
    assert b.change_set_name == arn


def test_b04_unbound_or_mismatched_create_change_set_fields_are_rejected():
    cp, _, clients = plane(
        "sts:GetCallerIdentity",
        "cloudformation:CreateChangeSet",
        provisioning=True,
    )
    cp.verify_identity()
    with pytest.raises(m.AuthorizationDenied):
        cp.create_change_set(
            StackName="s",
            ChangeSetName="c",
            ChangeSetType="UPDATE",
            TemplateBody='{"Resources":{"Unexpected":{"Type":"AWS::S3::Bucket"}}}',
            RoleARN="arn:aws:iam::123456789012:role/unexpected-pass-role",
        )
    assert clients["cloudformation"].calls == []


def test_b04_bound_create_change_set_contract_is_exactly_dispatched():
    template = '{"Resources":{}}'
    digest = sha256(template.encode("utf-8")).hexdigest()
    b = m.MutationResourceBinding(
        operation="cloudformation:CreateChangeSet",
        stack_name="s",
        change_set_name="c",
        change_set_type="UPDATE",
        role_arn="arn:aws:iam::123456789012:role/matrix-deployer",
        template_sha256=digest,
    )
    cp, _, clients = plane(
        "sts:GetCallerIdentity",
        "cloudformation:CreateChangeSet",
        provisioning=True,
        bindings=(b,),
    )
    cp.verify_identity()
    cp.create_change_set(
        StackName="s",
        ChangeSetName="c",
        ChangeSetType="UPDATE",
        RoleARN="arn:aws:iam::123456789012:role/matrix-deployer",
        TemplateBody=template,
    )
    assert clients["cloudformation"].calls[-1][1] == {
        "StackName": "s",
        "ChangeSetName": "c",
        "ChangeSetType": "UPDATE",
        "RoleARN": "arn:aws:iam::123456789012:role/matrix-deployer",
        "TemplateBody": template,
    }


def test_b05_put_object_binding_exposes_body_sha256():
    assert "body_sha256" in {f.name for f in dataclasses.fields(m.MutationResourceBinding)}


def test_b05_bound_body_digest_mismatch_is_rejected():
    b = m.MutationResourceBinding(
        operation="s3:PutObject",
        bucket="b",
        key="k",
        body_sha256=sha256(b"expected").hexdigest(),
    )
    cp, _, _ = plane(
        "sts:GetCallerIdentity",
        "s3:PutObject",
        provisioning=True,
        bindings=(b,),
    )
    cp.verify_identity()
    with pytest.raises(m.AuthorizationDenied):
        cp.put_object(Bucket="b", Key="k", Body=b"unexpected")


@pytest.mark.parametrize(
    "access_key_id",
    [
        "ASIA1234",
        "ASIA123456789012345",
        "ASIA00000000000000007",
        "asia1234567890123456",
        "ASIA12345678901234$6",
    ],
)
def test_b06_temporary_access_key_exact_shape(access_key_id):
    with pytest.raises(m.ConfigurationError):
        m.TemporaryAwsCredentials(access_key_id, "secret", "token")


def test_b07_credentials_expose_expiration_field():
    assert "expiration" in {
        f.name for f in __import__("dataclasses").fields(m.TemporaryAwsCredentials)
    }


def test_b07_naive_expiration_is_rejected():
    with pytest.raises(m.ConfigurationError):
        m.TemporaryAwsCredentials(
            "ASIA0000000000000000",
            "secret",
            "token",
            expiration=datetime.now(),
        )


def test_b07_expired_credentials_are_rejected():
    with pytest.raises(m.ConfigurationError):
        m.TemporaryAwsCredentials(
            "ASIA0000000000000000",
            "secret",
            "token",
            expiration=datetime.now(timezone.utc) - timedelta(seconds=1),
        )


def test_b07_real_session_factory_requires_expiration(monkeypatch):
    import boto3

    monkeypatch.setattr(
        boto3,
        "Session",
        lambda **kwargs: FakeSession({}),
    )
    creds = m.TemporaryAwsCredentials(
        "ASIA0000000000000000",
        "secret",
        "token",
    )
    with pytest.raises(m.ConfigurationError):
        m.create_explicit_boto3_session(
            credentials=creds,
            region="us-east-1",
        )


def test_b08_caller_acl_is_not_forwarded():
    cp, _, clients = plane(
        "sts:GetCallerIdentity",
        "s3:PutObject",
        provisioning=True,
    )
    cp.verify_identity()
    cp.put_object(
        Bucket="b",
        Key="k",
        Body=b"x",
        ACL="public-read",
    )
    sent = clients["s3"].calls[-1][1]
    assert "ACL" not in sent


def test_b08_only_bound_private_acl_is_forwarded():
    b = m.MutationResourceBinding(
        operation="s3:PutObject",
        bucket="b",
        key="k",
        body_sha256=sha256(b"x").hexdigest(),
        s3_acl="private",
    )
    cp, _, clients = plane(
        "sts:GetCallerIdentity",
        "s3:PutObject",
        provisioning=True,
        bindings=(b,),
    )
    cp.verify_identity()
    cp.put_object(
        Bucket="b",
        Key="k",
        Body=b"x",
        ACL="public-read",
    )
    assert clients["s3"].calls[-1][1]["ACL"] == "private"


def test_b08_public_acl_cannot_be_bound():
    with pytest.raises(m.ConfigurationError):
        m.MutationResourceBinding(
            operation="s3:PutObject",
            bucket="b",
            key="k",
            s3_acl="public-read",
        )


# R8.3R6 post-independent-audit R3 composition hardening regressions C01-C09.

def test_c01_raw_test_double_cannot_enter_network_authorized_control_plane():
    raw = FakeSession({"sts": FakeClient("sts"), "s3": FakeClient("s3")})
    real_permit = m.ControlPlanePermit(
        account_id="123456789012",
        region="us-east-1",
        credential_mode="STS_SESSION",
        allowed_operations=frozenset({"sts:GetCallerIdentity", "s3:GetBucketVersioning"}),
        aws_network_authorized=True,
    )
    with pytest.raises(m.ConfigurationError):
        m.SealedBoto3ControlPlane(session=raw, permit=real_permit)


def test_c01_offline_test_boundary_cannot_pair_with_network_authorized_permit():
    raw = FakeSession({"sts": FakeClient("sts")})
    boundary = m.create_offline_test_session_boundary(raw, region="us-east-1")
    real_permit = m.ControlPlanePermit(
        account_id="123456789012",
        region="us-east-1",
        credential_mode="STS_SESSION",
        allowed_operations=frozenset({"sts:GetCallerIdentity"}),
        aws_network_authorized=True,
    )
    with pytest.raises(m.ConfigurationError):
        m.SealedBoto3ControlPlane(session=boundary, permit=real_permit)


def test_c02_put_object_requires_digest_even_for_offline_test_boundary():
    b = m.MutationResourceBinding(operation="s3:PutObject", bucket="b", key="k")
    cp, _, clients = plane(
        "sts:GetCallerIdentity", "s3:PutObject", provisioning=True, bindings=(b,)
    )
    cp.verify_identity()
    with pytest.raises(m.AuthorizationDenied):
        cp.put_object(Bucket="b", Key="k", Body=b"unbound")
    assert clients["s3"].calls == []


def test_c03_create_change_set_requires_type_and_template_digest_even_offline():
    b = m.MutationResourceBinding(
        operation="cloudformation:CreateChangeSet",
        stack_name="s",
        change_set_name="c",
    )
    cp, _, clients = plane(
        "sts:GetCallerIdentity",
        "cloudformation:CreateChangeSet",
        provisioning=True,
        bindings=(b,),
    )
    cp.verify_identity()
    with pytest.raises(m.AuthorizationDenied):
        cp.create_change_set(StackName="s", ChangeSetName="c")
    assert clients["cloudformation"].calls == []


def test_c04_legacy_real_session_seal_globals_are_not_exposed():
    assert not hasattr(m, "_SESSION_SEAL")
    assert not hasattr(m, "_REAL_SESSION_PROVENANCE")


def test_c04_direct_boundary_construction_cannot_mint_real_provenance():
    raw = FakeSession({"sts": FakeClient("sts")})
    with pytest.raises(m.ConfigurationError):
        m.SealedSessionBoundary(
            raw,
            region="us-east-1",
            provenance="EXPLICIT_TEMPORARY_STS_SESSION",
        )


def test_c05_empty_assumed_role_session_name_is_rejected():
    cp, _, _ = plane(
        "sts:GetCallerIdentity",
        sts_arn="arn:aws:sts::123456789012:assumed-role/matrix-deployer/",
    )
    with pytest.raises(m.IdentityMismatch):
        cp.verify_identity()


def test_c06_execute_change_set_full_arn_is_bound_to_permit_account_region():
    bad = m.MutationResourceBinding(
        operation="cloudformation:ExecuteChangeSet",
        change_set_name="arn:aws:cloudformation:us-west-2:999999999999:changeSet/c/abc123",
    )
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"sts:GetCallerIdentity", "cloudformation:ExecuteChangeSet"}),
            aws_network_authorized=True,
            resource_provisioning_authorized=True,
            resource_bindings=(bad,),
        )


def test_c07_create_change_set_role_arn_is_bound_to_permit_account():
    b = m.MutationResourceBinding(
        operation="cloudformation:CreateChangeSet",
        stack_name="s",
        change_set_name="c",
        change_set_type="UPDATE",
        role_arn="arn:aws:iam::999999999999:role/cross-account-role",
        template_sha256=sha256(b"{}").hexdigest(),
    )
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"sts:GetCallerIdentity", "cloudformation:CreateChangeSet"}),
            aws_network_authorized=True,
            resource_provisioning_authorized=True,
            resource_bindings=(b,),
        )


def test_c08_ssekms_key_arn_is_bound_to_permit_account_region():
    b = m.MutationResourceBinding(
        operation="s3:PutObject",
        bucket="b",
        key="k",
        body_sha256=sha256(b"x").hexdigest(),
        s3_server_side_encryption="aws:kms",
        s3_ssekms_key_id="arn:aws:kms:us-west-2:999999999999:key/00000000-0000-0000-0000-000000000000",
    )
    with pytest.raises(m.ConfigurationError):
        m.ControlPlanePermit(
            account_id="123456789012",
            region="us-east-1",
            credential_mode="STS_SESSION",
            allowed_operations=frozenset({"sts:GetCallerIdentity", "s3:PutObject"}),
            aws_network_authorized=True,
            resource_provisioning_authorized=True,
            resource_bindings=(b,),
        )


@pytest.mark.parametrize("field,value", [("secret_access_key", 123), ("session_token", 456)])
def test_c09_temporary_credential_secret_and_token_types_are_strict(field, value):
    kwargs = {
        "access_key_id": "ASIA0000000000000000",
        "secret_access_key": "secret",
        "session_token": "token",
    }
    kwargs[field] = value
    with pytest.raises(m.ConfigurationError):
        m.TemporaryAwsCredentials(**kwargs)
