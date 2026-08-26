from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
import re

BOTO3_VERSION_PIN = "1.43.73"
BOTOCORE_VERSION_PIN = "1.43.73"
CONNECT_TIMEOUT_SECONDS = 3
READ_TIMEOUT_SECONDS = 8
TOTAL_MAX_ATTEMPTS = 1
CONTROLLED_LIVE_ADMISSIBLE = False
PRODUCTION_ADMISSIBLE = False
SPORTS_PROVIDER_NETWORK_AUTHORIZATION_INHERITED = False

READ_ONLY_OPERATIONS = frozenset(
    {
        "sts:GetCallerIdentity",
        "cloudformation:ValidateTemplate",
        "cloudformation:DescribeStacks",
        "s3:GetBucketVersioning",
        "s3:HeadObject",
        "kms:DescribeKey",
        "kms:GetPublicKey",
        "lambda:GetFunction",
        "iam:GetRole",
        "logs:DescribeLogGroups",
    }
)

MUTATION_OPERATIONS = frozenset(
    {
        "cloudformation:CreateChangeSet",
        "cloudformation:ExecuteChangeSet",
        "s3:CreateBucket",
        "s3:PutObject",
    }
)

ALL_OPERATIONS = READ_ONLY_OPERATIONS | MUTATION_OPERATIONS

_OPERATION_BINDINGS = {
    "sts:GetCallerIdentity": ("sts", "get_caller_identity"),
    "cloudformation:ValidateTemplate": ("cloudformation", "validate_template"),
    "cloudformation:DescribeStacks": ("cloudformation", "describe_stacks"),
    "cloudformation:CreateChangeSet": ("cloudformation", "create_change_set"),
    "cloudformation:ExecuteChangeSet": ("cloudformation", "execute_change_set"),
    "s3:GetBucketVersioning": ("s3", "get_bucket_versioning"),
    "s3:HeadObject": ("s3", "head_object"),
    "s3:CreateBucket": ("s3", "create_bucket"),
    "s3:PutObject": ("s3", "put_object"),
    "kms:DescribeKey": ("kms", "describe_key"),
    "kms:GetPublicKey": ("kms", "get_public_key"),
    "lambda:GetFunction": ("lambda", "get_function"),
    "iam:GetRole": ("iam", "get_role"),
    "logs:DescribeLogGroups": ("logs", "describe_log_groups"),
}

_ACCOUNT_RE = re.compile(r"^\d{12}$")
_REGION_RE = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d+$")


class ControlPlaneError(RuntimeError):
    pass


class AuthorizationDenied(ControlPlaneError):
    pass


class IdentityMismatch(ControlPlaneError):
    pass


class ConfigurationError(ControlPlaneError):
    pass


@dataclass(frozen=True)
class TemporaryAwsCredentials:
    access_key_id: str
    secret_access_key: str = field(repr=False)
    session_token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.access_key_id or not self.secret_access_key or not self.session_token:
            raise ConfigurationError("temporary AWS credentials require access key, secret, and session token")
        if not self.access_key_id.startswith("ASIA"):
            raise ConfigurationError("only real temporary/session access-key identifiers are accepted")


@dataclass(frozen=True)
class MutationResourceBinding:
    operation: str
    stack_name: str | None = None
    change_set_name: str | None = None
    bucket: str | None = None
    key: str | None = None

    def __post_init__(self) -> None:
        if self.operation not in MUTATION_OPERATIONS:
            raise ConfigurationError("resource binding operation must be a governed mutation")

        supplied = {
            "stack_name": self.stack_name,
            "change_set_name": self.change_set_name,
            "bucket": self.bucket,
            "key": self.key,
        }
        for name, value in supplied.items():
            if value is not None and (not isinstance(value, str) or not value):
                raise ConfigurationError(f"{name} must be a non-empty string when supplied")

        required: dict[str, tuple[str, ...]] = {
            "cloudformation:CreateChangeSet": ("stack_name", "change_set_name"),
            "cloudformation:ExecuteChangeSet": ("change_set_name",),
            "s3:CreateBucket": ("bucket",),
            "s3:PutObject": ("bucket", "key"),
        }
        allowed: dict[str, frozenset[str]] = {
            "cloudformation:CreateChangeSet": frozenset({"stack_name", "change_set_name"}),
            "cloudformation:ExecuteChangeSet": frozenset({"change_set_name"}),
            "s3:CreateBucket": frozenset({"bucket"}),
            "s3:PutObject": frozenset({"bucket", "key"}),
        }
        for name in required[self.operation]:
            if not supplied[name]:
                raise ConfigurationError(f"{self.operation} resource binding requires {name}")
        unexpected = [name for name, value in supplied.items() if value is not None and name not in allowed[self.operation]]
        if unexpected:
            raise ConfigurationError(
                f"{self.operation} resource binding has unexpected fields: {sorted(unexpected)!r}"
            )


@dataclass(frozen=True)
class ControlPlanePermit:
    account_id: str
    region: str
    credential_mode: str
    allowed_operations: frozenset[str] | Iterable[str]
    aws_network_authorized: bool
    resource_provisioning_authorized: bool = False
    resource_bindings: tuple[MutationResourceBinding, ...] | Iterable[MutationResourceBinding] = ()
    sports_provider_network_authorization_inherited: bool = False

    def __post_init__(self) -> None:
        if not _ACCOUNT_RE.fullmatch(self.account_id):
            raise ConfigurationError("account_id must be exactly 12 digits")
        if not _REGION_RE.fullmatch(self.region):
            raise ConfigurationError("region is not an admissible AWS region identifier")
        if self.credential_mode != "STS_SESSION":
            raise ConfigurationError("only STS_SESSION credential mode is admissible")

        try:
            operations = frozenset(self.allowed_operations)
        except TypeError as exc:
            raise ConfigurationError("allowed_operations must be an iterable of operation names") from exc
        if any(not isinstance(op, str) for op in operations):
            raise ConfigurationError("allowed_operations must contain strings only")
        object.__setattr__(self, "allowed_operations", operations)

        try:
            bindings = tuple(self.resource_bindings)
        except TypeError as exc:
            raise ConfigurationError("resource_bindings must be an iterable of MutationResourceBinding") from exc
        if any(not isinstance(binding, MutationResourceBinding) for binding in bindings):
            raise ConfigurationError("resource_bindings must contain MutationResourceBinding values only")
        object.__setattr__(self, "resource_bindings", bindings)

        unknown = operations - ALL_OPERATIONS
        if unknown:
            raise ConfigurationError(f"unknown operations: {sorted(unknown)!r}")
        if self.sports_provider_network_authorization_inherited:
            raise ConfigurationError("sports-provider network authorization cannot be inherited")
        if not self.aws_network_authorized and operations:
            raise ConfigurationError("allowed AWS operations require explicit AWS network authorization")

        non_sts = operations - {"sts:GetCallerIdentity"}
        if non_sts and "sts:GetCallerIdentity" not in operations:
            raise ConfigurationError("non-STS operations require sts:GetCallerIdentity in the same permit")

        mutations = operations & MUTATION_OPERATIONS
        if mutations and not self.resource_provisioning_authorized:
            raise ConfigurationError("mutation operations require explicit resource provisioning authorization")
        if self.resource_provisioning_authorized and not mutations and bindings:
            raise ConfigurationError("resource bindings are only valid for allowlisted mutation operations")

        bound_operations = [binding.operation for binding in bindings]
        if len(bound_operations) != len(set(bound_operations)):
            raise ConfigurationError("exactly one resource binding is allowed per mutation operation")
        if set(bound_operations) != set(mutations):
            missing = sorted(set(mutations) - set(bound_operations))
            extra = sorted(set(bound_operations) - set(mutations))
            raise ConfigurationError(
                f"resource bindings must exactly cover allowlisted mutations; missing={missing!r} extra={extra!r}"
            )

    def resource_binding_for(self, operation: str) -> MutationResourceBinding:
        for binding in self.resource_bindings:
            if binding.operation == operation:
                return binding
        raise AuthorizationDenied(f"no resource binding for mutation operation: {operation}")


def _require_runtime_versions() -> None:
    import boto3
    import botocore

    if getattr(boto3, "__version__", None) != BOTO3_VERSION_PIN:
        raise ConfigurationError(
            f"boto3 version mismatch: expected {BOTO3_VERSION_PIN}, "
            f"received {getattr(boto3, '__version__', '<missing>')}"
        )
    if getattr(botocore, "__version__", None) != BOTOCORE_VERSION_PIN:
        raise ConfigurationError(
            f"botocore version mismatch: expected {BOTOCORE_VERSION_PIN}, "
            f"received {getattr(botocore, '__version__', '<missing>')}"
        )


def build_botocore_config() -> Any:
    _require_runtime_versions()
    from botocore.config import Config

    return Config(
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        read_timeout=READ_TIMEOUT_SECONDS,
        retries={"total_max_attempts": TOTAL_MAX_ATTEMPTS, "mode": "standard"},
        user_agent_extra="MATRIX-R8.3R6-SEALED-BOTO3-CONTROL-PLANE",
        ignore_configured_endpoint_urls=True,
    )


def create_explicit_boto3_session(
    *,
    credentials: TemporaryAwsCredentials,
    region: str,
) -> Any:
    if not _REGION_RE.fullmatch(region):
        raise ConfigurationError("region is not an admissible AWS region identifier")
    _require_runtime_versions()
    import boto3

    return boto3.Session(
        aws_access_key_id=credentials.access_key_id,
        aws_secret_access_key=credentials.secret_access_key,
        aws_session_token=credentials.session_token,
        region_name=region,
    )


class SealedBoto3ControlPlane:
    def __init__(
        self,
        *,
        session: Any,
        permit: ControlPlanePermit,
    ) -> None:
        if session is None:
            raise ConfigurationError("an explicitly constructed boto3 session is required")
        self._session = session
        self._permit = permit
        self._config = build_botocore_config()
        self._clients: dict[str, Any] = {}
        self._identity_verified = False
        self._verified_account_id: str | None = None

    @property
    def identity_verified(self) -> bool:
        return self._identity_verified

    @property
    def verified_account_id(self) -> str | None:
        return self._verified_account_id

    def _authorize(self, operation: str, *, mutation: bool = False) -> None:
        if not self._permit.aws_network_authorized:
            raise AuthorizationDenied("AWS network authorization is false")
        if operation not in self._permit.allowed_operations:
            raise AuthorizationDenied(f"operation not allowlisted: {operation}")
        if mutation:
            if operation not in MUTATION_OPERATIONS:
                raise AuthorizationDenied("operation is not a governed mutation")
            if not self._permit.resource_provisioning_authorized:
                raise AuthorizationDenied("resource provisioning authorization is false")
            self._permit.resource_binding_for(operation)
        elif operation in MUTATION_OPERATIONS:
            raise AuthorizationDenied("mutation operation requires mutation path")

    def _client(self, service: str) -> Any:
        if service not in self._clients:
            self._clients[service] = self._session.client(
                service,
                region_name=self._permit.region,
                config=self._config,
            )
        return self._clients[service]

    def verify_identity(self) -> Mapping[str, Any]:
        operation = "sts:GetCallerIdentity"
        self._authorize(operation)
        response = self._client("sts").get_caller_identity()
        account = str(response.get("Account", ""))
        if account != self._permit.account_id:
            self._identity_verified = False
            self._verified_account_id = None
            raise IdentityMismatch(
                f"STS account mismatch: expected {self._permit.account_id}, received {account or '<missing>'}"
            )
        self._identity_verified = True
        self._verified_account_id = account
        return response

    def _require_identity(self) -> None:
        if not self._identity_verified or self._verified_account_id != self._permit.account_id:
            raise AuthorizationDenied("AWS identity has not been verified for this permit")

    def _require_mutation_target(self, operation: str, kwargs: Mapping[str, Any]) -> None:
        binding = self._permit.resource_binding_for(operation)
        if operation == "cloudformation:CreateChangeSet":
            if kwargs.get("StackName") != binding.stack_name or kwargs.get("ChangeSetName") != binding.change_set_name:
                raise AuthorizationDenied("CloudFormation change-set target does not match permit resource binding")
        elif operation == "cloudformation:ExecuteChangeSet":
            if kwargs.get("ChangeSetName") != binding.change_set_name:
                raise AuthorizationDenied("CloudFormation execute target does not match permit resource binding")
        elif operation == "s3:CreateBucket":
            if kwargs.get("Bucket") != binding.bucket:
                raise AuthorizationDenied("S3 create-bucket target does not match permit resource binding")
        elif operation == "s3:PutObject":
            if kwargs.get("Bucket") != binding.bucket or kwargs.get("Key") != binding.key:
                raise AuthorizationDenied("S3 put-object target does not match permit resource binding")
        else:
            raise AuthorizationDenied(f"unsupported mutation target binding: {operation}")

    def _invoke(
        self,
        operation: str,
        *,
        kwargs: Mapping[str, Any] | None = None,
        mutation: bool = False,
    ) -> Any:
        self._authorize(operation, mutation=mutation)
        if operation != "sts:GetCallerIdentity":
            self._require_identity()
        payload = dict(kwargs or {})
        if mutation:
            self._require_mutation_target(operation, payload)
        service, method = _OPERATION_BINDINGS[operation]
        return getattr(self._client(service), method)(**payload)

    def validate_template(self, *, template_body: str) -> Any:
        if not isinstance(template_body, str) or not template_body.strip():
            raise ConfigurationError("template_body must be a non-empty string")
        return self._invoke(
            "cloudformation:ValidateTemplate",
            kwargs={"TemplateBody": template_body},
        )

    def describe_stack(self, *, stack_name: str) -> Any:
        if not stack_name:
            raise ConfigurationError("stack_name is required")
        return self._invoke(
            "cloudformation:DescribeStacks",
            kwargs={"StackName": stack_name},
        )

    def get_bucket_versioning(self, *, bucket: str) -> Any:
        if not bucket:
            raise ConfigurationError("bucket is required")
        return self._invoke(
            "s3:GetBucketVersioning",
            kwargs={"Bucket": bucket},
        )

    def head_object(self, *, bucket: str, key: str, version_id: str | None = None) -> Any:
        if not bucket or not key:
            raise ConfigurationError("bucket and key are required")
        kwargs: dict[str, Any] = {"Bucket": bucket, "Key": key}
        if version_id:
            kwargs["VersionId"] = version_id
        return self._invoke("s3:HeadObject", kwargs=kwargs)

    def describe_key(self, *, key_id: str) -> Any:
        if not key_id:
            raise ConfigurationError("key_id is required")
        return self._invoke("kms:DescribeKey", kwargs={"KeyId": key_id})

    def get_public_key(self, *, key_id: str) -> Any:
        if not key_id:
            raise ConfigurationError("key_id is required")
        return self._invoke("kms:GetPublicKey", kwargs={"KeyId": key_id})

    def get_function(self, *, function_name: str, qualifier: str | None = None) -> Any:
        if not function_name:
            raise ConfigurationError("function_name is required")
        kwargs: dict[str, Any] = {"FunctionName": function_name}
        if qualifier:
            kwargs["Qualifier"] = qualifier
        return self._invoke("lambda:GetFunction", kwargs=kwargs)

    def get_role(self, *, role_name: str) -> Any:
        if not role_name:
            raise ConfigurationError("role_name is required")
        return self._invoke("iam:GetRole", kwargs={"RoleName": role_name})

    def describe_log_groups(self, *, prefix: str | None = None) -> Any:
        kwargs: dict[str, Any] = {}
        if prefix:
            kwargs["logGroupNamePrefix"] = prefix
        return self._invoke("logs:DescribeLogGroups", kwargs=kwargs)

    def create_change_set(self, **kwargs: Any) -> Any:
        if not kwargs:
            raise ConfigurationError("create_change_set requires explicit parameters")
        if not kwargs.get("StackName") or not kwargs.get("ChangeSetName"):
            raise ConfigurationError("StackName and ChangeSetName are required")
        return self._invoke(
            "cloudformation:CreateChangeSet",
            kwargs=kwargs,
            mutation=True,
        )

    def execute_change_set(self, *, change_set_name: str) -> Any:
        if not change_set_name:
            raise ConfigurationError("change_set_name is required")
        return self._invoke(
            "cloudformation:ExecuteChangeSet",
            kwargs={"ChangeSetName": change_set_name},
            mutation=True,
        )

    def create_bucket(self, **kwargs: Any) -> Any:
        if not kwargs.get("Bucket"):
            raise ConfigurationError("Bucket is required")
        return self._invoke("s3:CreateBucket", kwargs=kwargs, mutation=True)

    def put_object(self, **kwargs: Any) -> Any:
        if not kwargs.get("Bucket") or not kwargs.get("Key"):
            raise ConfigurationError("Bucket and Key are required")
        return self._invoke("s3:PutObject", kwargs=kwargs, mutation=True)
