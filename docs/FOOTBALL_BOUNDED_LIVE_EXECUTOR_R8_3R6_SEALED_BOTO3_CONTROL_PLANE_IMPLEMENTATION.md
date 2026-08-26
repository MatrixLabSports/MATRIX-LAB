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

When a value is bound, caller input must match the binding exactly. After the
R3 composition hardening, every execution mode (real or explicitly offline test)
requires a bound change-set type and exact TemplateBody SHA-256 before dispatch.

## B05 — S3 PutObject content digest binding

`MutationResourceBinding` now exposes `body_sha256`.

The exact bytes/string payload are hashed before dispatch and a mismatch fails
closed. After the R3 composition hardening, every `PutObject` execution mode
requires a content digest binding and an explicit Body. Offline test doubles no
longer receive a weaker mutation contract.

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

## R3 composition hardening — C01–C09

The independent R3 audit confirmed A01–A07 and B01–B08 remained closed but
identified nine composition findings. The C01–C09 hardening changes the
boundary model rather than adding special-case bypasses.

### C01 — real versus offline-test session authority separation

Raw session injection is rejected. `SealedBoto3ControlPlane` accepts only a
sealed boundary minted by an approved factory. A real boundary can pair only
with `aws_network_authorized=True`; an offline-test boundary can pair only with
`offline_test_authorized=True` and `aws_network_authorized=False`. The two
authority modes are mutually exclusive.

### C02 — no digest bypass through test doubles

`S3 PutObject` requires `body_sha256` and an explicit Body in both real and
offline-test execution modes. Test-double provenance cannot weaken the content
integrity contract.

### C03 — immutable CreateChangeSet contract in every mode

`CreateChangeSet` requires a permit-bound `ChangeSetType` and exact
`TemplateBody` SHA-256 for both real and offline-test execution. A test double
cannot dispatch a minimally bound change set.

### C04 — caller-forgeable real-provenance globals removed

The legacy module-level `_SESSION_SEAL` and `_REAL_SESSION_PROVENANCE` tokens
are removed. Session-boundary minting uses closure-held capabilities, and direct
construction without the capability fails closed. Real session creation remains
available only through `create_explicit_boto3_session`.

### C05 — STS principal session name is non-empty

Verified STS assumed-role ARNs must match a strict assumed-role grammar with a
non-empty role-session-name. Prefix matching no longer accepts an ARN ending in
`assumed-role/<role>/`.

### C06 — ExecuteChangeSet ARN scope

A full CloudFormation change-set ARN is validated against the permit account and
region. Cross-account or cross-region full ARNs fail at permit construction.

### C07 — CreateChangeSet RoleARN account scope

A bound CloudFormation `RoleARN` must be a syntactically valid IAM role ARN in
the same account as the permit. Cross-account pass-role expansion is rejected.

### C08 — SSE-KMS key account and region scope

A bound `SSEKMSKeyId` must be a full KMS key ARN and must match the permit
account and region. Cross-account or cross-region encryption-key widening is
rejected.

### C09 — strict secret/token types

`TemporaryAwsCredentials` requires `access_key_id`, `secret_access_key`, and
`session_token` to be non-empty strings. Truthy non-string values are rejected.

## R4 partition hardening — D03–D06

The independent R4 audit confirmed A01–A07, B01–B08, and C01–C09 remained
closed but identified four AWS-partition findings. The D03–D06 hardening makes
the permit region the authoritative source for the ARN partition.

The admitted partition mapping is:

- standard commercial regions → `aws`;
- `us-gov-*` → `aws-us-gov`;
- `cn-*` → `aws-cn`.

Specialized ISO/ISOB/ISOE/ISOF partitions are not silently treated as
commercial. They fail closed until explicitly governed by a future reviewed
extension.

### D03 — ExecuteChangeSet ARN partition scope

A full CloudFormation change-set ARN must match the permit account, region, and
AWS partition. A GovCloud or China ARN cannot be used with a commercial-region
permit even if its account and textual region fields otherwise satisfy the
existing checks.

### D04 — CreateChangeSet RoleARN partition scope

A bound CloudFormation `RoleARN` must match both the permit account and the AWS
partition implied by the permit region. Commercial, GovCloud, and China IAM
role ARNs cannot be interchanged.

### D05 — SSE-KMS key ARN partition scope

A bound `SSEKMSKeyId` must match the permit account, region, and AWS partition.
This prevents cross-partition KMS widening even when account and region strings
are otherwise valid.

### D06 — STS principal partition follows the permit region

The canonical default expected STS principal now uses the region-derived
partition:

- `arn:aws:sts::...` for commercial regions;
- `arn:aws-us-gov:sts::...` for GovCloud;
- `arn:aws-cn:sts::...` for China.

Caller-supplied expected principals are validated against the same partition,
so a cross-partition STS principal cannot be bound to a permit.

## Verification contract

The hardening gate must run under the already sealed dependency wheelhouse and
a Python socket-deny guard.

Expected focused D03–D06 partition regressions:

`14 passed`

Expected dedicated control-plane suite:

`141 passed`

Expected canonical MATRIX suite after replacing the prior 114-test file with
the 141-test partition-hardened file:

`2559 passed, 1 skipped`

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
`R8_3R6_SEALED_BOTO3_CONTROL_PLANE_INDEPENDENT_AUDIT_R5`.

## R5 provenance-boundary hardening — E01–E02

The independent R5 seal-candidate audit confirmed A01–A07, B01–B08, C01–C09, and D03–D06 remain closed, but identified two remaining provenance-boundary blockers. This hardening changes the offline path from an arbitrary caller-supplied session/delegate abstraction to a module-owned deterministic recorder driven only by inert exact-dict scenario data.

### E01 — offline boundary cannot smuggle a boto delegate

`create_offline_test_session_boundary(...)` no longer accepts any object exposing `client()`. It accepts only an exact built-in `dict` scenario whose service names and API method names are already governed by the sealed operation map. Scenario responses are recursively limited to inert built-in data. The module constructs its own `_OfflineRecordingSession` and `_OfflineRecordingClient` instances; the control-plane boundary revalidates that exact recorder type before every use. Therefore transparent proxies, boto3/botocore sessions, custom callables, and arbitrary executable delegates cannot become an offline execution authority.

### E02 — no closure-extractable session capability

`SealedSessionBoundary.__init__` is now an unconditional rejection path and has no token-bearing closure or factory capability. Approved factories allocate the boundary internally and the control plane calls `_validate_integrity()` before accepting it. The real path must retain explicit temporary STS provenance and a genuine `boto3.Session`; the offline path must retain the module-owned inert recorder and explicit offline-recorder provenance. An incomplete or manually allocated boundary fails closed.

### Verification contract

The hardening gate must run under the sealed dependency wheelhouse and the Python socket-deny guard.

Expected focused E01–E02 regressions:

`7 passed`

Expected dedicated control-plane suite:

`148 passed`

Expected canonical MATRIX suite after replacing the prior 141-test file with the 148-test boundary-hardened file:

`2566 passed, 1 skipped`

The gate also requires exact R5 failed-audit evidence binding, exact three-file mutation scope, payload SHA-256 checks, baseline-aware secret scanning, `git diff --check`, exact three-file commit, a clean post-commit repository, and `git fsck --full`.

## Governance after R5 hardening

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

A successful hardening commit does not seal the control plane. The required next gate is an independent post-hardening re-audit before any audit seal may be issued.

## R6 issuance-boundary hardening — F01–F02

The independent R6 seal-candidate audit confirmed A01–A07, B01–B08, C01–C09, D03–D06, and E01–E02 remain closed, but reproduced two final session-boundary issuance blockers. The remediation removes the reusable internal mint helper and adds a factory-issuance integrity record so a manually allocated Python object cannot masquerade as a real-session authority.

### F01 — reusable internal mint helper removed

`_mint_session_boundary` no longer exists. The approved offline and real factories perform their issuance steps directly. There is therefore no module helper that accepts a caller-supplied delegate, provenance string, and real/offline flag and converts those inputs into an admitted boundary.

The real factory still requires `TemporaryAwsCredentials`, a governed region, non-expired timezone-aware temporary credentials, the pinned boto3/botocore runtime, and a genuine `boto3.Session` result. The offline factory still accepts only inert exact-dict scenario data and creates the module-owned recorder itself.

### F02 — object.__new__ and post-issuance slot replacement fail closed

Each approved boundary issuance is recorded in a weak identity registry that binds:

- the exact delegate object identity;
- region;
- provenance label;
- real/offline mode.

`SealedSessionBoundary._validate_integrity()` first requires a matching factory-issuance record and then verifies that the current slots still equal that record. A boundary fabricated with `object.__new__` has no issuance record and is rejected even if all slots are populated with syntactically valid values. A legitimate issued boundary whose delegate or other bound state is later replaced with `object.__setattr__` also fails closed.

Normal attribute assignment is rejected after issuance, subclassing `SealedSessionBoundary` is forbidden, and `SealedBoto3ControlPlane` requires the exact boundary type rather than accepting subclasses that could override integrity behavior.

This is an application-runtime integrity contract, not a claim that arbitrary malicious code executing in the same Python interpreter is cryptographically isolated from all module state. Same-process arbitrary introspection and monkeypatching remain outside the capability-isolation claim and must be governed by the repository/runtime trust boundary.

### Verification contract

The hardening gate must run under the sealed dependency wheelhouse and Python socket-deny guard.

Expected focused F01–F02 regressions:

`6 passed`

Expected dedicated control-plane suite:

`154 passed`

Expected canonical MATRIX suite after replacing the prior 148-test file with the 154-test issuance-hardened file:

`2572 passed, 1 skipped`

The gate also requires exact R6 failed-audit evidence binding, exact three-file mutation scope, payload SHA-256 checks, baseline-aware secret scanning, `git diff --check`, exact three-file commit, a clean post-commit repository, and `git fsck --full`.

## Governance after R6 hardening

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

A successful hardening commit does not itself seal the control plane. The required next gate is an independent post-hardening re-audit (`R8_3R6_SEALED_BOTO3_CONTROL_PLANE_INDEPENDENT_AUDIT_R7`) before any audit seal may be issued.
