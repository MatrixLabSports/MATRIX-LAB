from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable, Mapping
from weakref import WeakKeyDictionary
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
        "cloudformation:DescribeChangeSet",
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
    "cloudformation:DescribeChangeSet": ("cloudformation", "describe_change_set"),
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
    r"^arn:(?P<partition>aws(?:-[a-z0-9-]+)?):cloudformation:(?P<region>[a-z0-9-]+):(?P<account>\d{12}):changeSet/(?P<name>[^/]+)/(?P<identifier>[A-Za-z0-9-]+)$"
)
_ROLE_ARN_RE = re.compile(
    r"^arn:(?P<partition>aws(?:-[a-z0-9-]+)?):iam::(?P<account>\d{12}):role/(?P<role>[A-Za-z0-9+=,.@_/-]+)$"
)
_KMS_KEY_ARN_RE = re.compile(
    r"^arn:(?P<partition>aws(?:-[a-z0-9-]+)?):kms:(?P<region>[a-z0-9-]+):(?P<account>\d{12}):key/(?P<key>[A-Za-z0-9-]+)$"
)
_ASSUMED_ROLE_ARN_RE = re.compile(
    r"^arn:(?P<partition>aws(?:-[a-z0-9-]+)?):sts::(?P<account>\d{12}):assumed-role/(?P<role>[^/]+(?:/[^/]+)*)/(?P<session>[^/]+)$"
)


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


def _partition_for_region(region: str) -> str:
    if not isinstance(region, str) or not _REGION_RE.fullmatch(region):
        raise ConfigurationError("region is not an admissible AWS region identifier")
    if region.startswith("us-gov-"):
        return "aws-us-gov"
    if region.startswith("cn-"):
        return "aws-cn"
    # MATRIX R8.3R6 intentionally supports the standard commercial, GovCloud,
    # and China partitions only. Specialized ISO/ISOB/ISOE partitions must be
    # introduced explicitly rather than silently inheriting commercial ARN rules.
    if (
        region.startswith("us-iso-")
        or region.startswith("us-isob-")
        or region.startswith("eu-isoe-")
        or region.startswith("us-isof-")
    ):
        raise ConfigurationError("AWS region partition is not admitted by this control plane")
    return "aws"


def _canonical_expected_principal(account_id: str, partition: str) -> str:
    return f"arn:{partition}:sts::{account_id}:assumed-role/matrix-deployer/*"


def _principal_matches(expected: str, actual: str) -> bool:
    if not isinstance(actual, str) or not _ASSUMED_ROLE_ARN_RE.fullmatch(actual):
        return False
    if expected.endswith("/*"):
        prefix = expected[:-1]
        return actual.startswith(prefix) and len(actual) > len(prefix)
    return actual == expected


def _expected_principal_is_valid(
    account_id: str,
    partition: str,
    value: str,
) -> bool:
    if value.endswith("/*"):
        prefix = value[:-2]
        marker = f"arn:{partition}:sts::{account_id}:assumed-role/"
        if not prefix.startswith(marker):
            return False
        role = prefix[len(marker):]
        return bool(role) and not role.endswith("/") and "//" not in role
    match = _ASSUMED_ROLE_ARN_RE.fullmatch(value)
    return bool(
        match
        and match.group("account") == account_id
        and match.group("partition") == partition
    )


@dataclass(frozen=True)
class TemporaryAwsCredentials:
    access_key_id: str
    secret_access_key: str = field(repr=False)
    session_token: str = field(repr=False)
    expiration: datetime | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for name, value in (
            ("access_key_id", self.access_key_id),
            ("secret_access_key", self.secret_access_key),
            ("session_token", self.session_token),
        ):
            if not isinstance(value, str) or not value:
                raise ConfigurationError(f"{name} must be a non-empty string")
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
            if self.s3_ssekms_key_id is not None and not _KMS_KEY_ARN_RE.fullmatch(
                self.s3_ssekms_key_id
            ):
                raise ConfigurationError(
                    "s3_ssekms_key_id must be a full KMS key ARN"
                )


@dataclass(frozen=True)
class ControlPlanePermit:
    account_id: str
    region: str
    credential_mode: str
    allowed_operations: frozenset[str] | Iterable[str]
    aws_network_authorized: bool
    offline_test_authorized: bool = False
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
        partition = _partition_for_region(self.region)
        if self.credential_mode != "STS_SESSION":
            raise ConfigurationError("only STS_SESSION credential mode is admissible")

        expected_principal = self.expected_principal_arn
        if expected_principal is None:
            expected_principal = _canonical_expected_principal(self.account_id, partition)
        if not isinstance(expected_principal, str) or not expected_principal:
            raise ConfigurationError("expected_principal_arn must be a non-empty string")
        if not _expected_principal_is_valid(
            self.account_id,
            partition,
            expected_principal,
        ):
            raise ConfigurationError(
                "expected_principal_arn must bind an STS assumed-role principal with a non-empty session in the permit account and AWS partition"
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
        if self.aws_network_authorized and self.offline_test_authorized:
            raise ConfigurationError(
                "AWS network authorization and offline-test authorization are mutually exclusive"
            )
        if operations and not (self.aws_network_authorized or self.offline_test_authorized):
            raise ConfigurationError(
                "allowed operations require explicit AWS network authorization or explicit offline-test authorization"
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

        for binding in bindings:
            if binding.operation == "cloudformation:ExecuteChangeSet":
                match = _CHANGE_SET_ARN_RE.fullmatch(binding.change_set_name or "")
                if match is not None and (
                    match.group("account") != self.account_id
                    or match.group("region") != self.region
                    or match.group("partition") != partition
                ):
                    raise ConfigurationError(
                        "ExecuteChangeSet full ARN must match permit account, region, and AWS partition"
                    )
            elif binding.operation == "cloudformation:CreateChangeSet" and binding.role_arn is not None:
                role_match = _ROLE_ARN_RE.fullmatch(binding.role_arn)
                if (
                    role_match is None
                    or role_match.group("account") != self.account_id
                    or role_match.group("partition") != partition
                ):
                    raise ConfigurationError(
                        "CreateChangeSet RoleARN must match permit account and AWS partition"
                    )
            elif binding.operation == "s3:PutObject" and binding.s3_ssekms_key_id is not None:
                kms_match = _KMS_KEY_ARN_RE.fullmatch(binding.s3_ssekms_key_id)
                if kms_match is None:
                    raise ConfigurationError(
                        "SSE-KMS key id must be a full KMS key ARN"
                    )
                if (
                    kms_match.group("account") != self.account_id
                    or kms_match.group("region") != self.region
                    or kms_match.group("partition") != partition
                ):
                    raise ConfigurationError(
                        "SSE-KMS key ARN must match permit account, region, and AWS partition"
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


def _clone_offline_value(value: Any, *, _depth: int = 0) -> Any:
    """Clone only inert values admissible in the deterministic offline recorder."""
    if _depth > 12:
        raise ConfigurationError("offline test scenario nesting is too deep")
    if value is None or type(value) in {bool, int, float, str, bytes}:
        return value
    if type(value) is list:
        return [_clone_offline_value(v, _depth=_depth + 1) for v in value]
    if type(value) is tuple:
        return tuple(_clone_offline_value(v, _depth=_depth + 1) for v in value)
    if type(value) is dict:
        cloned: dict[str, Any] = {}
        for key, nested in value.items():
            if type(key) is not str or not key:
                raise ConfigurationError(
                    "offline test scenario mappings require nonempty string keys"
                )
            cloned[key] = _clone_offline_value(nested, _depth=_depth + 1)
        return cloned
    raise ConfigurationError(
        "offline test scenarios may contain inert built-in data only"
    )


class _OfflineRecordingClient:
    __slots__ = ("service", "_responses", "calls")

    def __init__(self, service: str, responses: Mapping[str, Any]) -> None:
        self.service = service
        self._responses = dict(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        allowed = {
            api
            for service, api in _OPERATION_BINDINGS.values()
            if service == self.service
        }
        if name not in allowed:
            raise AttributeError(name)

        def call(**kwargs: Any) -> Any:
            self.calls.append((name, dict(kwargs)))
            if name in self._responses:
                return _clone_offline_value(self._responses[name])
            return {
                "service": self.service,
                "method": name,
                "kwargs": dict(kwargs),
            }

        return call


class _OfflineRecordingSession:
    __slots__ = ("_clients", "client_calls")

    def __init__(self, scenario: Mapping[str, Mapping[str, Any]]) -> None:
        clients: dict[str, _OfflineRecordingClient] = {}
        allowed_services = {service for service, _ in _OPERATION_BINDINGS.values()}
        for service, responses in scenario.items():
            if type(service) is not str or service not in allowed_services:
                raise ConfigurationError(
                    f"offline test scenario service is not governed: {service!r}"
                )
            if type(responses) is not dict:
                raise ConfigurationError(
                    "offline test scenario service responses must be exact dict values"
                )
            allowed_methods = {
                api
                for bound_service, api in _OPERATION_BINDINGS.values()
                if bound_service == service
            }
            safe_responses: dict[str, Any] = {}
            for method, response in responses.items():
                if type(method) is not str or method not in allowed_methods:
                    raise ConfigurationError(
                        f"offline test scenario method is not governed: {service}.{method}"
                    )
                safe_responses[method] = _clone_offline_value(response)
            clients[service] = _OfflineRecordingClient(service, safe_responses)
        for service in allowed_services:
            clients.setdefault(service, _OfflineRecordingClient(service, {}))
        self._clients = clients
        self.client_calls: list[tuple[str, dict[str, Any]]] = []

    def client(self, service: str, **kwargs: Any) -> Any:
        if service not in self._clients:
            raise ConfigurationError(
                f"offline test service is not governed: {service}"
            )
        self.client_calls.append((service, dict(kwargs)))
        return self._clients[service]

    def calls_for(self, service: str) -> tuple[tuple[str, dict[str, Any]], ...]:
        if service not in self._clients:
            raise ConfigurationError(
                f"offline test service is not governed: {service}"
            )
        return tuple((name, dict(kwargs)) for name, kwargs in self._clients[service].calls)


_ISSUED_SESSION_BOUNDARIES = WeakKeyDictionary()


class SealedSessionBoundary:
    """Factory-issued boundary around a real boto3 session or inert offline recorder.

    Direct construction and subclassing are forbidden.  Factory issuance is recorded
    in a weak identity registry that binds the exact delegate identity, region,
    provenance, and real/offline mode.  Revalidation therefore rejects objects
    fabricated with ``object.__new__`` as well as post-issuance slot replacement.

    Python same-process introspection is not claimed to be a cryptographic security
    boundary; this object is a fail-closed control-plane contract against unsupported
    construction/injection paths inside the governed application runtime.
    """

    __slots__ = ("_delegate", "region", "provenance", "_real", "__weakref__")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise ConfigurationError(
            "session boundaries can only be issued by an approved factory"
        )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("SealedSessionBoundary cannot be subclassed")

    def __setattr__(self, name: str, value: Any) -> None:
        raise ConfigurationError("session boundary state is immutable after issuance")

    def _validate_integrity(self) -> None:
        try:
            issuance = _ISSUED_SESSION_BOUNDARIES.get(self)
        except Exception as exc:
            raise ConfigurationError("session boundary issuance cannot be verified") from exc
        if issuance is None:
            raise ConfigurationError(
                "session boundary was not issued by an approved factory"
            )
        try:
            delegate = object.__getattribute__(self, "_delegate")
            region = object.__getattribute__(self, "region")
            provenance = object.__getattribute__(self, "provenance")
            real = object.__getattribute__(self, "_real")
        except (AttributeError, TypeError) as exc:
            raise ConfigurationError("session boundary is incomplete") from exc
        expected = (id(delegate), region, provenance, real)
        if issuance != expected:
            raise ConfigurationError(
                "session boundary state no longer matches its factory issuance record"
            )
        if type(real) is not bool:
            raise ConfigurationError("session boundary mode is malformed")
        if type(region) is not str or not _REGION_RE.fullmatch(region):
            raise ConfigurationError("session boundary region is not admissible")
        _partition_for_region(region)
        if real:
            if provenance != "EXPLICIT_TEMPORARY_STS_SESSION":
                raise ConfigurationError("real session provenance mismatch")
            _require_runtime_versions()
            import boto3

            if not isinstance(delegate, boto3.Session):
                raise ConfigurationError(
                    "real session boundary delegate must be a boto3.Session"
                )
        else:
            if provenance != "EXPLICIT_OFFLINE_TEST_RECORDER":
                raise ConfigurationError("offline-test session provenance mismatch")
            if type(delegate) is not _OfflineRecordingSession:
                raise ConfigurationError(
                    "offline-test boundary must use the module-owned inert recorder"
                )

    @property
    def is_real_explicit_session(self) -> bool:
        self._validate_integrity()
        return bool(object.__getattribute__(self, "_real"))

    @property
    def is_offline_test_session(self) -> bool:
        self._validate_integrity()
        return not bool(object.__getattribute__(self, "_real"))

    @property
    def offline_client_calls(self) -> tuple[tuple[str, dict[str, Any]], ...]:
        self._validate_integrity()
        if self.is_real_explicit_session:
            raise ConfigurationError("offline call evidence is unavailable for real sessions")
        recorder = object.__getattribute__(self, "_delegate")
        return tuple((service, dict(kwargs)) for service, kwargs in recorder.client_calls)

    def offline_calls_for(
        self, service: str
    ) -> tuple[tuple[str, dict[str, Any]], ...]:
        self._validate_integrity()
        if self.is_real_explicit_session:
            raise ConfigurationError("offline call evidence is unavailable for real sessions")
        recorder = object.__getattribute__(self, "_delegate")
        return recorder.calls_for(service)

    def client(self, service: str, **kwargs: Any) -> Any:
        self._validate_integrity()
        if service not in {value[0] for value in _OPERATION_BINDINGS.values()}:
            raise ConfigurationError(
                f"service is not bound to the sealed control plane: {service}"
            )
        if "endpoint_url" in kwargs:
            raise ConfigurationError("endpoint_url override is forbidden")
        requested_region = kwargs.get("region_name")
        if requested_region != self.region:
            raise ConfigurationError("client region must match sealed session boundary")
        if "config" not in kwargs:
            raise ConfigurationError("canonical botocore config is required")
        return self._delegate.client(service, **kwargs)


def create_offline_test_session_boundary(
    scenario: Any,
    *,
    region: str,
) -> SealedSessionBoundary:
    if type(scenario) is not dict:
        raise ConfigurationError(
            "offline test boundary accepts an exact dict scenario only; arbitrary session/delegate objects are forbidden"
        )
    if not _REGION_RE.fullmatch(region):
        raise ConfigurationError("session boundary region is not admissible")
    _partition_for_region(region)
    recorder = _OfflineRecordingSession(scenario)
    boundary = object.__new__(SealedSessionBoundary)
    object.__setattr__(boundary, "_delegate", recorder)
    object.__setattr__(boundary, "region", region)
    object.__setattr__(boundary, "provenance", "EXPLICIT_OFFLINE_TEST_RECORDER")
    object.__setattr__(boundary, "_real", False)
    record = (
        id(recorder),
        region,
        "EXPLICIT_OFFLINE_TEST_RECORDER",
        False,
    )
    _ISSUED_SESSION_BOUNDARIES[boundary] = record
    try:
        boundary._validate_integrity()
    except Exception:
        _ISSUED_SESSION_BOUNDARIES.pop(boundary, None)
        raise
    return boundary


def create_explicit_boto3_session(
    *,
    credentials: TemporaryAwsCredentials,
    region: str,
) -> SealedSessionBoundary:
    if not isinstance(credentials, TemporaryAwsCredentials):
        raise ConfigurationError(
            "credentials must be a TemporaryAwsCredentials instance"
        )
    if not _REGION_RE.fullmatch(region):
        raise ConfigurationError("region is not an admissible AWS region identifier")
    _partition_for_region(region)
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
    if not isinstance(raw, boto3.Session):
        raise ConfigurationError(
            "boto3 session factory did not return a boto3.Session instance"
        )
    boundary = object.__new__(SealedSessionBoundary)
    object.__setattr__(boundary, "_delegate", raw)
    object.__setattr__(boundary, "region", region)
    object.__setattr__(boundary, "provenance", "EXPLICIT_TEMPORARY_STS_SESSION")
    object.__setattr__(boundary, "_real", True)
    record = (
        id(raw),
        region,
        "EXPLICIT_TEMPORARY_STS_SESSION",
        True,
    )
    _ISSUED_SESSION_BOUNDARIES[boundary] = record
    try:
        boundary._validate_integrity()
    except Exception:
        _ISSUED_SESSION_BOUNDARIES.pop(boundary, None)
        raise
    return boundary


class SealedBoto3ControlPlane:
    def __init__(
        self,
        *,
        session: Any,
        permit: ControlPlanePermit,
    ) -> None:
        if session is None:
            raise ConfigurationError("an explicitly minted sealed session boundary is required")
        if type(session) is not SealedSessionBoundary:
            raise ConfigurationError(
                "raw session injection is forbidden; use an approved session-boundary factory"
            )
        session._validate_integrity()
        if session.region != permit.region:
            raise ConfigurationError("session boundary region does not match permit region")
        if session.is_real_explicit_session:
            if not permit.aws_network_authorized or permit.offline_test_authorized:
                raise ConfigurationError(
                    "real session boundary requires AWS network authorization only"
                )
        else:
            if permit.aws_network_authorized or not permit.offline_test_authorized:
                raise ConfigurationError(
                    "offline test boundary requires offline_test_authorized with AWS network authorization false"
                )
        boundary = session
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
        if self._session.is_real_explicit_session:
            if not self._permit.aws_network_authorized or self._permit.offline_test_authorized:
                raise AuthorizationDenied("real AWS execution is not authorized by this permit")
        else:
            if self._permit.aws_network_authorized or not self._permit.offline_test_authorized:
                raise AuthorizationDenied("offline test execution is not explicitly authorized")
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


    def describe_change_set(self, *, stack_name: str, change_set_name) -> Any:
        if not isinstance(change_set_name, str) or not change_set_name.strip():
            raise ControlPlaneError('change_set_name must be a non-empty string')
        if not stack_name:
            raise ConfigurationError('stack_name is required')
        return self._invoke('cloudformation:DescribeChangeSet', kwargs={'StackName': stack_name, 'ChangeSetName': change_set_name})

    def wait_create_change_set_ready(
        self,
        *,
        stack_name,
        change_set_name,
        expected_logical_resource_ids,
        max_attempts=60,
        poll_interval_seconds=2.0,
        sleep_fn=None,
    ):
        max_attempts, poll_interval_seconds = _validate_lifecycle_wait_bounds(
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval_seconds,
            max_attempts_limit=120,
        )
        if sleep_fn is None:
            import time
            sleep_fn = time.sleep
        if not callable(sleep_fn):
            raise ControlPlaneError("sleep_fn must be callable")

        for attempt in range(max_attempts):
            response = self.describe_change_set(
                stack_name=stack_name,
                change_set_name=change_set_name,
            )
            status = response.get("Status") if isinstance(response, dict) else None
            if status in {"CREATE_PENDING", "CREATE_IN_PROGRESS"}:
                if attempt + 1 >= max_attempts:
                    break
                sleep_fn(poll_interval_seconds)
                continue
            return validate_create_change_set_ready_for_execution(
                response,
                expected_stack_name=stack_name,
                expected_change_set_name=change_set_name,
                expected_logical_resource_ids=expected_logical_resource_ids,
            )

        raise ControlPlaneError(
            "change set did not become CREATE_COMPLETE/AVAILABLE within max_attempts"
        )

    def wait_stack_create_complete(
        self,
        *,
        stack_name,
        max_attempts=180,
        poll_interval_seconds=2.0,
        sleep_fn=None,
    ):
        max_attempts, poll_interval_seconds = _validate_lifecycle_wait_bounds(
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval_seconds,
            max_attempts_limit=300,
        )
        if sleep_fn is None:
            import time
            sleep_fn = time.sleep
        if not callable(sleep_fn):
            raise ControlPlaneError("sleep_fn must be callable")

        for attempt in range(max_attempts):
            response = self.describe_stack(stack_name=stack_name)
            if not isinstance(response, dict):
                raise ControlPlaneError("describe_stack response must be a dict")
            stacks = response.get("Stacks")
            if not isinstance(stacks, list) or len(stacks) != 1:
                raise ControlPlaneError("describe_stack must return exactly one stack")
            stack = stacks[0]
            if not isinstance(stack, dict):
                raise ControlPlaneError("stack record must be a dict")
            if stack.get("StackName") != stack_name:
                raise ControlPlaneError("stack identity mismatch")
            status = stack.get("StackStatus")
            if status == "CREATE_COMPLETE":
                return response
            if status in {"REVIEW_IN_PROGRESS", "CREATE_IN_PROGRESS"}:
                if attempt + 1 >= max_attempts:
                    break
                sleep_fn(poll_interval_seconds)
                continue
            raise ControlPlaneError(f"stack entered non-success status: {status!r}")

        raise ControlPlaneError(
            "stack did not become CREATE_COMPLETE within max_attempts"
        )

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

        if binding.change_set_type is None or binding.template_sha256 is None:
            raise AuthorizationDenied(
                "CreateChangeSet requires bound ChangeSetType and TemplateBody SHA256 in every execution mode"
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
            else:
                raise AuthorizationDenied(
                    "S3 PutObject requires body_sha256 in permit binding in every execution mode"
                )
            payload["Body"] = body
        else:
            raise AuthorizationDenied("S3 PutObject requires explicit Body")

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

def _validate_lifecycle_wait_bounds(
    *,
    max_attempts,
    poll_interval_seconds,
    max_attempts_limit,
):
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
        raise ControlPlaneError("max_attempts must be an integer")
    if max_attempts < 1 or max_attempts > max_attempts_limit:
        raise ControlPlaneError("max_attempts is outside the permitted bound")
    if isinstance(poll_interval_seconds, bool) or not isinstance(
        poll_interval_seconds, (int, float)
    ):
        raise ControlPlaneError("poll_interval_seconds must be numeric")
    poll_interval_seconds = float(poll_interval_seconds)
    if poll_interval_seconds < 0.0 or poll_interval_seconds > 10.0:
        raise ControlPlaneError("poll_interval_seconds is outside the permitted bound")
    return max_attempts, poll_interval_seconds


def validate_create_change_set_ready_for_execution(
    response,
    *,
    expected_stack_name,
    expected_change_set_name,
    expected_logical_resource_ids,
):
    if not isinstance(response, dict):
        raise ControlPlaneError("describe_change_set response must be a dict")
    if not isinstance(expected_stack_name, str) or not expected_stack_name.strip():
        raise ControlPlaneError("expected_stack_name must be a non-empty string")
    if not isinstance(expected_change_set_name, str) or not expected_change_set_name.strip():
        raise ControlPlaneError("expected_change_set_name must be a non-empty string")

    try:
        expected_ids = tuple(expected_logical_resource_ids)
    except TypeError as exc:
        raise ControlPlaneError(
            "expected_logical_resource_ids must be an iterable of identifiers"
        ) from exc

    if not expected_ids:
        raise ControlPlaneError("expected_logical_resource_ids must not be empty")
    if any(not isinstance(x, str) or not x.strip() for x in expected_ids):
        raise ControlPlaneError("expected logical resource identifiers must be non-empty strings")
    if len(set(expected_ids)) != len(expected_ids):
        raise ControlPlaneError("expected logical resource identifiers contain duplicates")

    if response.get("StackName") != expected_stack_name:
        raise ControlPlaneError("change-set stack identity mismatch")

    observed_change_set_name = response.get("ChangeSetName")
    observed_change_set_id = response.get("ChangeSetId")
    if (
        observed_change_set_name != expected_change_set_name
        and observed_change_set_id != expected_change_set_name
    ):
        raise ControlPlaneError("change-set identity mismatch")

    if response.get("ChangeSetType") != "CREATE":
        raise ControlPlaneError("change-set type must be CREATE")
    if response.get("Status") != "CREATE_COMPLETE":
        raise ControlPlaneError("change-set status must be CREATE_COMPLETE")
    if response.get("ExecutionStatus") != "AVAILABLE":
        raise ControlPlaneError("change-set execution status must be AVAILABLE")

    changes = response.get("Changes")
    if not isinstance(changes, list) or not changes:
        raise ControlPlaneError("change set must contain at least one resource change")

    observed_ids = []
    for change in changes:
        if not isinstance(change, dict) or change.get("Type") != "Resource":
            raise ControlPlaneError("every change must be a Resource change")
        resource_change = change.get("ResourceChange")
        if not isinstance(resource_change, dict):
            raise ControlPlaneError("ResourceChange must be a dict")
        if resource_change.get("Action") != "Add":
            raise ControlPlaneError("first-tranche resource changes must all be Add")
        logical_id = resource_change.get("LogicalResourceId")
        if not isinstance(logical_id, str) or not logical_id.strip():
            raise ControlPlaneError("LogicalResourceId must be a non-empty string")
        observed_ids.append(logical_id)

    if len(set(observed_ids)) != len(observed_ids):
        raise ControlPlaneError("observed logical resource identifiers contain duplicates")
    if set(observed_ids) != set(expected_ids):
        raise ControlPlaneError("logical resource identifier set mismatch")

    return response
