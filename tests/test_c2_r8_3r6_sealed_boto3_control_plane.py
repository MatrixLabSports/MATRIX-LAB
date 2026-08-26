from __future__ import annotations

import ast
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


def permit(*ops, provisioning=False, account="123456789012", region="us-east-1"):
    return m.ControlPlanePermit(
        account_id=account,
        region=region,
        credential_mode="STS_SESSION",
        allowed_operations=frozenset(ops),
        aws_network_authorized=True,
        resource_provisioning_authorized=provisioning,
    )


def plane(*ops, provisioning=False, sts_account="123456789012"):
    clients = {
        "sts": FakeClient("sts", {"get_caller_identity": {"Account": sts_account, "Arn": "arn:test"}}),
        "cloudformation": FakeClient("cloudformation"),
        "s3": FakeClient("s3"),
        "kms": FakeClient("kms"),
        "lambda": FakeClient("lambda"),
        "iam": FakeClient("iam"),
        "logs": FakeClient("logs"),
    }
    session = FakeSession(clients)
    cp = m.SealedBoto3ControlPlane(
        session=session,
        permit=permit(*ops, provisioning=provisioning),
        config=object(),
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
])
def test_temporary_credentials_reject_missing_or_long_lived(args):
    with pytest.raises(m.ConfigurationError):
        m.TemporaryAwsCredentials(*args)


def test_temporary_credentials_repr_hides_secret_and_token():
    c = m.TemporaryAwsCredentials("ASIA1234", "SUPERSECRET", "SESSIONTOKEN")
    r = repr(c)
    assert "SUPERSECRET" not in r
    assert "SESSIONTOKEN" not in r
    assert "ASIA1234" in r


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
        permit("s3:PutObject", provisioning=False)


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
    cp, _, clients = plane("sts:GetCallerIdentity", operation)
    cp.verify_identity()
    getattr(cp, method)(**args)
    assert clients[service].calls[-1][0] == api


def test_head_object_includes_optional_version_id():
    cp, _, clients = plane("sts:GetCallerIdentity", "s3:HeadObject")
    cp.verify_identity()
    cp.head_object(bucket="b", key="k", version_id="v1")
    assert clients["s3"].calls[-1] == ("head_object", {"Bucket": "b", "Key": "k", "VersionId": "v1"})


def test_get_function_includes_qualifier():
    cp, _, clients = plane("sts:GetCallerIdentity", "lambda:GetFunction")
    cp.verify_identity()
    cp.get_function(function_name="fn", qualifier="7")
    assert clients["lambda"].calls[-1] == ("get_function", {"FunctionName": "fn", "Qualifier": "7"})


def test_describe_log_groups_prefix():
    cp, _, clients = plane("sts:GetCallerIdentity", "logs:DescribeLogGroups")
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
        permit("sts:GetCallerIdentity", "s3:PutObject", provisioning=False)


@pytest.mark.parametrize("method,args,operation,service,api", [
    ("create_change_set", {"StackName": "s", "ChangeSetName": "c"}, "cloudformation:CreateChangeSet", "cloudformation", "create_change_set"),
    ("execute_change_set", {"change_set_name": "c"}, "cloudformation:ExecuteChangeSet", "cloudformation", "execute_change_set"),
    ("create_bucket", {"Bucket": "b"}, "s3:CreateBucket", "s3", "create_bucket"),
    ("put_object", {"Bucket": "b", "Key": "k", "Body": b"x"}, "s3:PutObject", "s3", "put_object"),
])
def test_mutation_methods_require_and_use_provisioning(method, args, operation, service, api):
    cp, _, clients = plane("sts:GetCallerIdentity", operation, provisioning=True)
    cp.verify_identity()
    getattr(cp, method)(**args)
    assert clients[service].calls[-1][0] == api


def test_create_change_set_rejects_empty_kwargs():
    cp, _, _ = plane("sts:GetCallerIdentity", "cloudformation:CreateChangeSet", provisioning=True)
    cp.verify_identity()
    with pytest.raises(m.ConfigurationError):
        cp.create_change_set()


def test_execute_change_set_rejects_empty_name():
    cp, _, _ = plane("sts:GetCallerIdentity", "cloudformation:ExecuteChangeSet", provisioning=True)
    cp.verify_identity()
    with pytest.raises(m.ConfigurationError):
        cp.execute_change_set(change_set_name="")


def test_create_bucket_requires_bucket():
    cp, _, _ = plane("sts:GetCallerIdentity", "s3:CreateBucket", provisioning=True)
    cp.verify_identity()
    with pytest.raises(m.ConfigurationError):
        cp.create_bucket()


def test_put_object_requires_bucket_and_key():
    cp, _, _ = plane("sts:GetCallerIdentity", "s3:PutObject", provisioning=True)
    cp.verify_identity()
    with pytest.raises(m.ConfigurationError):
        cp.put_object(Bucket="b")


def test_create_explicit_boto3_session_passes_only_explicit_temporary_credentials(monkeypatch):
    calls = []
    fake = types.SimpleNamespace(Session=lambda **kwargs: calls.append(kwargs) or object())
    monkeypatch.setitem(sys.modules, "boto3", fake)
    creds = m.TemporaryAwsCredentials("ASIA1234", "secret", "token")
    m.create_explicit_boto3_session(credentials=creds, region="us-east-1")
    assert calls == [{
        "aws_access_key_id": "ASIA1234",
        "aws_secret_access_key": "secret",
        "aws_session_token": "token",
        "region_name": "us-east-1",
    }]


def test_create_explicit_boto3_session_rejects_invalid_region(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(Session=lambda **kwargs: object()))
    creds = m.TemporaryAwsCredentials("ASIA1234", "secret", "token")
    with pytest.raises(m.ConfigurationError):
        m.create_explicit_boto3_session(credentials=creds, region="bad")


def test_build_botocore_config_has_expected_fail_closed_values(monkeypatch):
    captured = {}
    class FakeConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)
    config_mod = types.SimpleNamespace(Config=FakeConfig)
    botocore_pkg = types.ModuleType("botocore")
    monkeypatch.setitem(sys.modules, "botocore", botocore_pkg)
    monkeypatch.setitem(sys.modules, "botocore.config", config_mod)
    m.build_botocore_config()
    assert captured["connect_timeout"] == 3
    assert captured["read_timeout"] == 8
    assert captured["retries"]["total_max_attempts"] == 1
    assert captured["retries"]["mode"] == "standard"