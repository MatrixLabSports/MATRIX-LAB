# MATRIX C2 R8.3R6 — Sealed boto3 Control Plane Hardening R1

Status: **OFFLINE HARDENING ONLY**

This hardening closes the seven findings produced by the independent
adversarial audit R1 of commit
`8f1d5b195c0d1e1635523a3b9630bd297861bd65`.

The audit result was `FAIL` with five BLOCKER findings and two MAJOR findings.
No real AWS identity, credentials, network calls, provisioning, CONTROLLED_LIVE,
or production admission are authorized by this hardening.

## A01 — immutable operation allowlist

`ControlPlanePermit.allowed_operations` is normalized to `frozenset` inside the
frozen dataclass. A mutable caller-owned list can no longer expand the permit
after construction.

Mutation resource bindings are likewise normalized into an immutable tuple of
frozen `MutationResourceBinding` values.

## A02 — canonical SDK configuration

`SealedBoto3ControlPlane` no longer accepts a caller-supplied `config`
parameter. It constructs its own configuration through
`build_botocore_config()`.

The canonical configuration fixes:

- connect timeout: 3 seconds;
- read timeout: 8 seconds;
- total maximum attempts: 1;
- retry mode: `standard`;
- configured endpoint URL overrides ignored.

## A03 — endpoint override protection

The botocore configuration sets:

`ignore_configured_endpoint_urls=True`

This prevents configured AWS endpoint URL overrides from silently redirecting
the governed client boundary.

## A04 — runtime dependency version pinning

Before configuration or session creation, the implementation verifies:

- boto3 == 1.43.73
- botocore == 1.43.73

Missing or mismatched runtime versions fail closed with `ConfigurationError`.

## A05 — mutation target resource binding

Each allowlisted mutation must have exactly one immutable
`MutationResourceBinding`.

The current exact target semantics are:

- `cloudformation:CreateChangeSet` → exact `StackName` + `ChangeSetName`;
- `cloudformation:ExecuteChangeSet` → exact `ChangeSetName`;
- `s3:CreateBucket` → exact bucket;
- `s3:PutObject` → exact bucket + exact object key.

Missing, duplicate, extra, or mismatching bindings fail closed. A single permit
therefore cannot silently widen itself to a different stack, bucket, change
set, or object key.

## A06 — identity operation dependency

Any permit containing a non-STS operation must also contain
`sts:GetCallerIdentity`.

Non-STS execution still requires successful identity verification against the
same exact 12-digit account id before the operation can run.

## A07 — test credential sentinel separation

`TemporaryAwsCredentials` no longer accepts `MATRIX_TEST_ONLY`.
Only access-key identifiers beginning with `ASIA` are accepted by this
production-facing credential value object.

Test-only sentinels must remain outside the real credential path.

## Dependency source

No dependency is installed into the Windows host. Hardening verification
materializes the seven sealed pure-Python control-plane wheels ephemerally from
the already sealed wheelhouse and runs with network denied.

The approved pins remain:

- boto3 1.43.73
- botocore 1.43.73

## Verification target

The hardening regression file contains 92 tests in total, including 31 focused
A01–A07 hardening regressions.

The expected canonical suite after this replacement is:

`2510 passed, 1 skipped`

The hardening gate also performs a baseline-aware secret scan and requires the
repository to be clean after the exact hardening commit.

## Governance

`REAL_AWS_IDENTITY_PROBE_AUTHORIZED=FALSE`

`REAL_AWS_CREDENTIAL_READ_AUTHORIZED=FALSE`

`REAL_AWS_NETWORK_AUTHORIZED=FALSE`

`RESOURCE_PROVISIONING_AUTHORIZED=FALSE`

`PYTHON312_ACTUAL_RUNTIME_EXECUTION_PROVEN=FALSE`

`CONTROLLED_LIVE_ADMISSIBLE=FALSE`

`MACROBLOCK_2_CLOSED=FALSE`

`REMAINING_C2_LIVE_MACROBLOCKS=5`

`PRODUCTION_ADMISSIBLE=FALSE`

The next required gate is a new independent adversarial audit R2. No audit seal
and no real AWS authorization may occur until that audit closes the findings.
