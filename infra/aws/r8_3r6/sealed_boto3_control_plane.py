from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
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
_TEMP_ACCESS_KEY_RE = re.compile(r"^ASIA[0-9A-Z]{16}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CHANGE_SET_ARN_RE = re.compile(
    r"^arn:aws(?:-[a-z0-9-]+)?:cloudformation:[a-z0-9-]+:\d{12}:changeSet/[^/]+/[A-Za-z0-9-]+$"
)
_ROLE_ARN_RE = re.compile(r"^arn:aws(?:-[a-z0-9-]+)?:iam::\d{12}:role/[A-Za-z0-9+=,.@_/-]+$")
_SESSION_SEAL = object()
_REAL_SESSION_PROVENANCE = "EXPLICIT_TEMPORARY_STS_SESSION"
_TEST_SESSION_PROVENANCE = "INJECTED_OFFLINE_TEST_DOUBLE"


class ControlPlaneError(RuntimeError):
    pass


class AuthorizationDenied(ControlPlaneError):
    pass


class IdentityMismatch(ControlPlaneError):
    pass


class ConfigurationError(ControlPlaneError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_bytes(value: Any) -> str:
    if isinstance(value, str):
        data = value.encode("utf-8")
    elif isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
    else:
        raise ConfigurationError("payload must be str or bytes-like for SHA256 binding")
    return sha256(data).hexdigest()


def _canonical_expected_principal(account_id: str) -> str:
    return f"arn:aws:sts::{account_id}:assumed-role/matrix-deployer/*"


def _principal_matches(expected: str, actual: str) -> bool:
    if expected.endswith("/*"):
        return actual.startswith(expected[:-1])
    return actual == expected


@dataclass(frozen=True)
class TemporaryAwsCredentials:
    access_key_id: str
    secret_access_key: str = field(repr=False)
    session_token: str = field(repr=False)
    expiration: datetime | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.access_key_id or not self.secret_access_key or not self.session_token:
            raise ConfigurationError(
                "temporary AWS credentials require access key, secret, and session token"
            )
        if not _TEMP_ACCESS_KEY_RE.fullmatch(self.access_key_id):
            raise ConfigurationError(
                "temporary access_key_id must match exact ASIA + 16 uppercase alphanumeric shape"
            )
        if self.expiration is not None:
            if not isinstance(self.expiration, datetime):
                raise ConfigurationError("credential expiration must be a datetime when supplied")
            if self.expiration.tzinfo is None or self.expiration.utcoffset() is None:
                raise ConfigurationError("credential expiration must be timezone-aware")
            if self.expiration.astimezone(timezone.utc) <= _utc_now():
                raise ConfigurationError("temporary AWS credentials are already expired")


@dataclass(frozen=True)
class MutationResourceBinding:
    operation: str
    stack_name: str | None = None
    change_set_name: str | None = None
    bucket: str | None = None
    key: str | None = None
    change_set_type: str | None = None
    role_arn: str | None = None
    template_sha256: str | None = None
    body_sha256: str | None = None
    s3_acl: str | None = None
    s3_server_side_encryption: str | None = None
    s3_ssekms_key_id: str | None = None

    def __post_init__(self) -> None:
        if self.operation not in MUTATION_OPERATIONS:
            raise ConfigurationError("resource binding operation must be a governed mutation")

        supplied = {
            "stack_name": self.stack_name,
            "change_set_name": self.change_set_name,
            "bucket": self.bucket,
            "key": self.key,
            "change_set_type": self.change_set_type,
            "role_arn": self.role_arn,
            "template_sha256": self.template_sha256,
            "body_sha256": self.body_sha256,
            "s3_acl": self.s3_acl,
            "s3_server_side_encryption": self.s3_server_side_encryption,
            "s3_ssekms_key_id": self.s3_ssekms_key_id,
        }
        for name, value in supplied.items():
            if value is not None and (not isinstance(value, str) or not value):
                raise ConfigurationError(f"{name} must be a non-empty string when supplied")

        allowed: dict[str, frozenset[str]] = {
            "cloudformation:CreateChangeSet": frozenset(
                {
                    "stack_name",
                    "change_set_name",
                    "change_set_type",
                    "role_arn",
                    "template_sha256",
                }
            ),
            "cloudformation:ExecuteChangeSet": frozenset(
                {"stack_name", "change_set_name"}
            ),
            "s3:CreateBucket": frozenset({"bucket"}),
            "s3:PutObject": frozenset(
                {
                    "bucket",
                    "key",
                    "body_sha256",
                    "s3_acl",
                    "s3_server_side_encryption",
                    "s3_ssekms_key_id",
                }
            ),
        }
        unexpected = [
            name
            for name, value in supplied.items()
            if value is not None and name not in allowed[self.operation]
        ]
        if unexpected:
            raise ConfigurationError(
                f"{self.operation} resource binding has unexpected fields: {sorted(unexpected)!r}"
            )

        if self.operation == "cloudformation:CreateChangeSet":
            if not self.stack_name or not self.change_set_name:
                raise ConfigurationError(
                    "cloudformation:CreateChangeSet resource binding requires stack_name and change_set_name"
                )
            if self.change_set_type is not None and self.change_set_type not in {
                "CREATE",
                "UPDATE",
                "IMPORT",
            }:
                raise ConfigurationError("change_set_type is not admissible")
            if self.role_arn is not None and not _ROLE_ARN_RE.fullmatch(self.role_arn):
                raise ConfigurationError("role_arn is not an admissible IAM role ARN")
            if self.template_sha256 is not None and not _SHA256_RE.fullmatch(
                self.template_sha256
            ):
                raise ConfigurationError("template_sha256 must be lowercase SHA256 hex")
        elif self.operation == "cloudformation:ExecuteChangeSet":
            if not self.change_set_name:
                raise ConfigurationError(
                    "cloudformation:ExecuteChangeSet resource binding requires change_set_name"
                )
            if not self.stack_name and not _CHANGE_SET_ARN_RE.fullmatch(
                self.change_set_name
            ):
                raise ConfigurationError(
                    "cloudformation:ExecuteChangeSet requires stack_name or full change-set ARN"
                )
        elif self.operation == "s3:CreateBucket":
            if not self.bucket:
                raise ConfigurationError("s3:CreateBucket resource binding requires bucket")
        elif self.operation == "s3:PutObject":
            if not self.bucket or not self.key:
                raise ConfigurationError(
                    "s3:PutObject resource binding requires bucket and key"
                )
            if self.body_sha256 is not None and not _SHA256_RE.fullmatch(
                self.body_sha256
            ):
                raise ConfigurationError("body_sha256 must be lowercase SHA256 hex")
            if self.s3_acl is not None and self.s3_acl != "private":
                raise ConfigurationError("only private S3 ACL is admissible")
            if self.s3_server_side_encryption is not None and (
                self.s3_server_side_encryption != "aws:kms"
            ):
                raise ConfigurationError("only aws:kms S3 server-side encryption is admissible")
            if self.s3_ssekms_key_id is not None and (
                self.s3_server_side_encryption != "aws:kms"
            ):
                raise ConfigurationError(
                    "s3_ssekms_key_id requires aws:kms server-side encryption binding"
                )


@dataclass(frozen=True)
class ControlPlanePermit:
    account_id: str
    region: str
    credential_mode: str
    allowed_operations: frozenset[str] | Iterable[str]
    aws_network_authorized: bool
    resource_provisioning_authorized: bool = False
    resource_bindings: tuple[MutationResourceBinding, ...] | Iterable[
        MutationResourceBinding
    ] = ()
    sports_provider_network_authorization_inherited: bool = False
    expected_principal_arn: str | None = None

    def __post_init__(self) -> None:
        if not _ACCOUNT_RE.fullmatch(self.account_id):
            raise ConfigurationError("account_id must be exactly 12 digits")
        if not _REGION_RE.fullmatch(self.region):
            raise ConfigurationError("region is not an admissible AWS region identifier")
        if self.credential_mode != "STS_SESSION":
            raise ConfigurationError("only STS_SESSION credential mode is admissible")

        expected_principal = self.expected_principal_arn
        if expected_principal is None:
            expected_principal = _canonical_expected_principal(self.account_id)
        if not isinstance(expected_principal, str) or not expected_principal:
            raise ConfigurationError("expected_principal_arn must be a non-empty string")
        if not (
            expected_principal.startswith(f"arn:aws:sts::{self.account_id}:assumed-role/")
            and (expected_principal.endswith("/*") or expected_principal.count("/") >= 2)
        ):
            raise ConfigurationError(
                "expected_principal_arn must bind an STS assumed-role principal in the permit account"
            )
        object.__setattr__(self, "expected_principal_arn", expected_principal)

        try:
            operations = frozenset(self.allowed_operations)
        except TypeError as exc:
            raise ConfigurationError(
                "allowed_operations must be an iterable of operation names"
            ) from exc
        if any(not isinstance(op, str) for op in operations):
            raise ConfigurationError("allowed_operations must contain strings only")
        object.__setattr__(self, "allowed_operations", operations)

        try:
            bindings = tuple(self.resource_bindings)
        except TypeError as exc:
            raise ConfigurationError(
                "resource_bindings must be an iterable of MutationResourceBinding"
            ) from exc
        if any(not isinstance(binding, MutationResourceBinding) for binding in bindings):
            raise ConfigurationError(
                "resource_bindings must contain MutationResourceBinding values only"
            )
        object.__setattr__(self, "resource_bindings", bindings)

        unknown = operations - ALL_OPERATIONS
        if unknown:
            raise ConfigurationError(f"unknown operations: {sorted(unknown)!r}")
        if self.sports_provider_network_authorization_inherited:
            raise ConfigurationError(
                "sports-provider network authorization cannot be inherited"
            )
        if not self.aws_network_authorized and operations:
            raise ConfigurationError(
                "allowed AWS operations require explicit AWS network authorization"
            )

        non_sts = operations - {"sts:GetCallerIdentity"}
        if non_sts and "sts:GetCallerIdentity" not in operations:
            raise ConfigurationError(
                "non-STS operations require sts:GetCallerIdentity in the same permit"
            )

        mutations = operations & MUTATION_OPERATIONS
        if mutations and not self.resource_provisioning_authorized:
            raise ConfigurationError(
                "mutation operations require explicit resource provisioning authorization"
            )
        if self.resource_provisioning_authorized and not mutations and bindings:
            raise ConfigurationError(
                "resource bindings are only valid for allowlisted mutation operations"
            )

        bound_operations = [binding.operation for binding in bindings]
        if len(bound_operations) != len(set(bound_operations)):
            raise ConfigurationError(
                "exactly one resource binding is allowed per mutation operation"
            )
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


class SealedSessionBoundary:
    __slots__ = ("_delegate", "region", "provenance")

    def __init__(
        self,
        delegate: Any,
        *,
        region: str,
        provenance: str,
        _seal: object | None = None,
    ) -> None:
        if delegate is None or not callable(getattr(delegate, "client", None)):
            raise ConfigurationError("session delegate must expose callable client()")
        if not _REGION_RE.fullmatch(region):
            raise ConfigurationError("session boundary region is not admissible")
        if provenance == _REAL_SESSION_PROVENANCE:
            if _seal is not _SESSION_SEAL:
                raise ConfigurationError("real session provenance can only be minted by the factory")
        elif provenance != _TEST_SESSION_PROVENANCE:
            raise ConfigurationError("unknown session provenance")

        module_name = type(delegate).__module__
        if provenance == _TEST_SESSION_PROVENANCE and (
            module_name == "boto3.session"
            or module_name.startswith("botocore.")
        ):
            raise ConfigurationError(
                "direct boto3/botocore session injection is forbidden; use create_explicit_boto3_session"
            )

        self._delegate = delegate
        self.region = region
        self.provenance = provenance

    @property
    def is_real_explicit_session(self) -> bool:
        return self.provenance == _REAL_SESSION_PROVENANCE

    def client(self, service: str, **kwargs: Any) -> Any:
        if service not in {value[0] for value in _OPERATION_BINDINGS.values()}:
            raise ConfigurationError(f"service is not bound to the sealed control plane: {service}")
        if "endpoint_url" in kwargs:
            raise ConfigurationError("endpoint_url override is forbidden")
        requested_region = kwargs.get("region_name")
        if requested_region != self.region:
            raise ConfigurationError("client region must match sealed session boundary")
        if "config" not in kwargs:
            raise ConfigurationError("canonical botocore config is required")
        return self._delegate.client(service, **kwargs)


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
) -> SealedSessionBoundary:
    if not _REGION_RE.fullmatch(region):
        raise ConfigurationError("region is not an admissible AWS region identifier")
    if credentials.expiration is None:
        raise ConfigurationError(
            "explicit temporary AWS session creation requires credential expiration"
        )
    if credentials.expiration.astimezone(timezone.utc) <= _utc_now():
        raise ConfigurationError("temporary AWS credentials are expired")
    _require_runtime_versions()
    import boto3

    raw = boto3.Session(
        aws_access_key_id=credentials.access_key_id,
        aws_secret_access_key=credentials.secret_access_key,
        aws_session_token=credentials.session_token,
        region_name=region,
    )
    return SealedSessionBoundary(
        raw,
        region=region,
        provenance=_REAL_SESSION_PROVENANCE,
        _seal=_SESSION_SEAL,
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
        if isinstance(session, SealedSessionBoundary):
            if session.region != permit.region:
                raise ConfigurationError("session boundary region does not match permit region")
            boundary = session
        else:
            boundary = SealedSessionBoundary(
                session,
                region=permit.region,
                provenance=_TEST_SESSION_PROVENANCE,
            )
        self._session = boundary
        self._permit = permit
        self._config = build_botocore_config()
        self._clients: dict[str, Any] = {}
        self._identity_verified = False
        self._verified_account_id: str | None = None
        self._verified_principal_arn: str | None = None

    @property
    def identity_verified(self) -> bool:
        return self._identity_verified

    @property
    def verified_account_id(self) -> str | None:
        return self._verified_account_id

    @property
    def verified_principal_arn(self) -> str | None:
        return self._verified_principal_arn

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

    def _clear_identity(self) -> None:
        self._identity_verified = False
        self._verified_account_id = None
        self._verified_principal_arn = None

    def verify_identity(self) -> Mapping[str, Any]:
        operation = "sts:GetCallerIdentity"
        self._authorize(operation)
        response = self._client("sts").get_caller_identity()
        account = str(response.get("Account", ""))
        principal = str(response.get("Arn", ""))
        if account != self._permit.account_id:
            self._clear_identity()
            raise IdentityMismatch(
                f"STS account mismatch: expected {self._permit.account_id}, received {account or '<missing>'}"
            )
        expected = str(self._permit.expected_principal_arn)
        if not principal or not _principal_matches(expected, principal):
            self._clear_identity()
            raise IdentityMismatch(
                f"STS principal mismatch: expected {expected}, received {principal or '<missing>'}"
            )
        self._identity_verified = True
        self._verified_account_id = account
        self._verified_principal_arn = principal
        return response

    def _require_identity(self) -> None:
        if (
            not self._identity_verified
            or self._verified_account_id != self._permit.account_id
            or self._verified_principal_arn is None
            or not _principal_matches(
                str(self._permit.expected_principal_arn),
                self._verified_principal_arn,
            )
        ):
            raise AuthorizationDenied("AWS identity has not been verified for this permit")

    def _require_mutation_target(
        self, operation: str, kwargs: Mapping[str, Any]
    ) -> MutationResourceBinding:
        binding = self._permit.resource_binding_for(operation)
        if operation == "cloudformation:CreateChangeSet":
            if (
                kwargs.get("StackName") != binding.stack_name
                or kwargs.get("ChangeSetName") != binding.change_set_name
            ):
                raise AuthorizationDenied(
                    "CloudFormation change-set target does not match permit resource binding"
                )
        elif operation == "cloudformation:ExecuteChangeSet":
            if kwargs.get("ChangeSetName") != binding.change_set_name:
                raise AuthorizationDenied(
                    "CloudFormation execute target does not match permit resource binding"
                )
            if binding.stack_name is not None and kwargs.get("StackName") != binding.stack_name:
                raise AuthorizationDenied(
                    "CloudFormation execute stack does not match permit resource binding"
                )
        elif operation == "s3:CreateBucket":
            if kwargs.get("Bucket") != binding.bucket:
                raise AuthorizationDenied(
                    "S3 create-bucket target does not match permit resource binding"
                )
        elif operation == "s3:PutObject":
            if kwargs.get("Bucket") != binding.bucket or kwargs.get("Key") != binding.key:
                raise AuthorizationDenied(
                    "S3 put-object target does not match permit resource binding"
                )
        else:
            raise AuthorizationDenied(
                f"unsupported mutation target binding: {operation}"
            )
        return binding

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

    def head_object(
        self, *, bucket: str, key: str, version_id: str | None = None
    ) -> Any:
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

    def get_function(
        self, *, function_name: str, qualifier: str | None = None
    ) -> Any:
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
        binding = self._permit.resource_binding_for(
            "cloudformation:CreateChangeSet"
        )
        payload: dict[str, Any] = {
            "StackName": kwargs["StackName"],
            "ChangeSetName": kwargs["ChangeSetName"],
        }
        if binding.change_set_type is not None:
            if (
                "ChangeSetType" in kwargs
                and kwargs["ChangeSetType"] != binding.change_set_type
            ):
                raise AuthorizationDenied("ChangeSetType does not match permit binding")
            payload["ChangeSetType"] = binding.change_set_type
        if binding.role_arn is not None:
            if "RoleARN" in kwargs and kwargs["RoleARN"] != binding.role_arn:
                raise AuthorizationDenied("RoleARN does not match permit binding")
            payload["RoleARN"] = binding.role_arn

        template_body = kwargs.get("TemplateBody")
        if binding.template_sha256 is not None:
            if template_body is None:
                raise AuthorizationDenied("bound TemplateBody is required")
            if _sha256_bytes(template_body) != binding.template_sha256:
                raise AuthorizationDenied("TemplateBody SHA256 does not match permit binding")
            payload["TemplateBody"] = template_body

        if self._session.is_real_explicit_session:
            if binding.change_set_type is None or binding.template_sha256 is None:
                raise AuthorizationDenied(
                    "real CreateChangeSet requires bound ChangeSetType and TemplateBody SHA256"
                )

        return self._invoke(
            "cloudformation:CreateChangeSet",
            kwargs=payload,
            mutation=True,
        )

    def execute_change_set(
        self, *, change_set_name: str, stack_name: str | None = None
    ) -> Any:
        if not change_set_name:
            raise ConfigurationError("change_set_name is required")
        binding = self._permit.resource_binding_for(
            "cloudformation:ExecuteChangeSet"
        )
        payload: dict[str, Any] = {"ChangeSetName": change_set_name}
        if binding.stack_name is not None:
            if stack_name is not None and stack_name != binding.stack_name:
                raise AuthorizationDenied("stack_name does not match permit binding")
            payload["StackName"] = binding.stack_name
        elif stack_name is not None:
            raise AuthorizationDenied(
                "stack_name is not permitted for full-ARN execute binding"
            )
        return self._invoke(
            "cloudformation:ExecuteChangeSet",
            kwargs=payload,
            mutation=True,
        )

    def create_bucket(self, **kwargs: Any) -> Any:
        if not kwargs.get("Bucket"):
            raise ConfigurationError("Bucket is required")
        payload = {"Bucket": kwargs["Bucket"]}
        return self._invoke(
            "s3:CreateBucket",
            kwargs=payload,
            mutation=True,
        )

    def put_object(self, **kwargs: Any) -> Any:
        if not kwargs.get("Bucket") or not kwargs.get("Key"):
            raise ConfigurationError("Bucket and Key are required")
        binding = self._permit.resource_binding_for("s3:PutObject")
        payload: dict[str, Any] = {
            "Bucket": kwargs["Bucket"],
            "Key": kwargs["Key"],
        }
        body = kwargs.get("Body")
        if body is not None:
            if binding.body_sha256 is not None:
                if _sha256_bytes(body) != binding.body_sha256:
                    raise AuthorizationDenied("S3 Body SHA256 does not match permit binding")
            elif self._session.is_real_explicit_session:
                raise AuthorizationDenied(
                    "real S3 PutObject requires body_sha256 in permit binding"
                )
            payload["Body"] = body
        elif self._session.is_real_explicit_session:
            raise AuthorizationDenied("real S3 PutObject requires explicit Body")

        # Caller-controlled security-sensitive headers are never forwarded.
        if binding.s3_acl is not None:
            payload["ACL"] = binding.s3_acl
        if binding.s3_server_side_encryption is not None:
            payload["ServerSideEncryption"] = binding.s3_server_side_encryption
        if binding.s3_ssekms_key_id is not None:
            payload["SSEKMSKeyId"] = binding.s3_ssekms_key_id

        return self._invoke(
            "s3:PutObject",
            kwargs=payload,
            mutation=True,
        )
