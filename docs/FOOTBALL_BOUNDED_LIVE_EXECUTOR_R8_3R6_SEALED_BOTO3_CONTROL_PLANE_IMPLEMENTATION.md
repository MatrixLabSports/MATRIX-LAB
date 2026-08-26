# MATRIX C2 R8.3R6 — Sealed boto3 Control Plane Post-Audit R2 Hardening B01–B08

Status: **OFFLINE HARDENING ONLY — NO REAL AWS AUTHORIZATION**

Baseline: `f201b42faf521c089fe06f98db346969c3ecf249`

This hardening responds to independent adversarial audit R2, which returned
`FAIL` with five BLOCKER findings and three MAJOR findings. The prior A01–A07
findings remain closed. No real AWS identity probe, credential read, network
execution, resource provisioning, CONTROLLED_LIVE admission, or production
admission is authorized by this hardening.

## Preserved A01–A07 controls

The implementation retains the previously hardened invariants:

- immutable `frozenset` operation allowlists and immutable resource bindings;
- canonical botocore configuration owned by the control-plane boundary;
- configured endpoint URL overrides disabled;
- exact boto3/botocore runtime pins (`1.43.73`);
- explicit mutation target bindings;
- mandatory `sts:GetCallerIdentity` dependency for non-STS operations;
- rejection of the `MATRIX_TEST_ONLY` credential sentinel.

## B01 — sealed session provenance boundary

`SealedBoto3ControlPlane` no longer stores an arbitrary injected session object
directly. All sessions are mediated by `SealedSessionBoundary`.

Two provenance modes are distinguished:

- `EXPLICIT_TEMPORARY_STS_SESSION`, minted only by
  `create_explicit_boto3_session()` through a private module seal; and
- `INJECTED_OFFLINE_TEST_DOUBLE`, retained only so deterministic offline tests
  can exercise dispatch without contacting AWS.

Direct boto3/botocore session injection is rejected; the real runtime path must
use the explicit temporary-session factory. The boundary also enforces the
permit region, canonical botocore configuration, service allowlist, and no
caller endpoint override.

## B02 — expected STS principal binding

`ControlPlanePermit` now contains `expected_principal_arn`.

When the caller does not provide a narrower value, the canonical default is the
MATRIX deployer assumed-role family for the permit account:

`arn:aws:sts::<account-id>:assumed-role/matrix-deployer/*`

`verify_identity()` now validates both the exact 12-digit account and the STS
principal ARN. A same-account but unexpected IAM user or role session fails
closed and clears the sticky identity state.

## B03 — ExecuteChangeSet stack scope

An `ExecuteChangeSet` mutation binding must contain either:

- `stack_name` plus `change_set_name`; or
- a full CloudFormation change-set ARN.

A bare change-set name without stack scope is rejected. Dispatch includes the
bound stack name when name-based addressing is used.

## B04 — immutable CreateChangeSet request contract

Caller-supplied security-sensitive `CreateChangeSet` fields are never forwarded
merely because they were present in `**kwargs`.

The permit binding can independently bind:

- `change_set_type`;
- `role_arn`;
- `template_sha256`.

When a value is bound, caller input must match the binding exactly. A real
explicit session additionally requires a bound change-set type and exact
TemplateBody SHA-256 before dispatch.

## B05 — S3 PutObject content digest binding

`MutationResourceBinding` now exposes `body_sha256`.

When a digest is bound, the exact bytes/string payload are hashed before
dispatch and a mismatch fails closed. The real explicit-session path requires a
content digest binding for non-empty `PutObject` writes. Offline injected test
doubles may omit it only to support deterministic adversarial harnesses; that
provenance is not an admissible real boto3 session path.

## B06 — exact temporary access-key shape

Temporary access-key identifiers must match:

`ASIA[0-9A-Z]{16}`

Short, long, lowercase, malformed, `AKIA`, and test-sentinel identifiers are
rejected.

## B07 — temporary credential expiration

`TemporaryAwsCredentials` now contains a non-repr `expiration` field.

When supplied, expiration must be timezone-aware and in the future. The real
boto3 session factory requires expiration to be present and unexpired before it
can mint a sealed real-session boundary.

## B08 — S3 security-sensitive header binding

Caller-controlled S3 security-sensitive headers are not forwarded directly.

The permit may bind:

- `ACL`, restricted to `private`;
- server-side encryption, restricted to `aws:kms`;
- an SSE-KMS key id only when KMS encryption is bound.

A caller request such as `ACL="public-read"` cannot widen the permit. If the
permit has no ACL binding, the ACL is omitted; if the permit binds `private`,
that exact value is dispatched.

## Verification contract

The hardening gate must run under the already sealed dependency wheelhouse and
a Python socket-deny guard.

Expected focused B01–B08 regressions:

`22 passed`

Expected dedicated control-plane suite:

`114 passed`

Expected canonical MATRIX suite after replacing the prior 92-test file with the
114-test hardened file:

`2532 passed, 1 skipped`

The gate also requires:

- exact baseline and audit-evidence SHA-256 checks;
- exact three-file mutation scope;
- payload SHA-256 checks before testing;
- baseline-aware secret scanning;
- `git diff --check`;
- exact three-file commit;
- clean post-commit repository;
- `git fsck --full`.

## Governance

`REAL_AWS_IDENTITY_PROBE_AUTHORIZED=FALSE`

`REAL_AWS_CREDENTIAL_READ_AUTHORIZED=FALSE`

`REAL_AWS_NETWORK_AUTHORIZED=FALSE`

`RESOURCE_PROVISIONING_AUTHORIZED=FALSE`

`RESOURCE_PROVISIONING_PERFORMED=FALSE`

`PYTHON312_ACTUAL_RUNTIME_EXECUTION_PROVEN=FALSE`

`CONTROLLED_LIVE_ADMISSIBLE=FALSE`

`MACROBLOCK_2_CLOSED=FALSE`

`REMAINING_C2_LIVE_MACROBLOCKS=5`

`PRODUCTION_ADMISSIBLE=FALSE`

The next required gate after a successful hardening commit is
`R8_3R6_SEALED_BOTO3_CONTROL_PLANE_INDEPENDENT_AUDIT_R3`.
