# MATRIX C2 — R8.3R6 Strong External Authority
## Authority Service Source Design

Status: **SOURCE DESIGN ONLY — NO AUTHORITY SERVICE SOURCE IMPLEMENTED**

Baseline HEAD:

`1dbf1b71c0b1146dac63ca2ada1b2fb0e2c9bc1c`

Authority-service source-design preflight report SHA-256:

`9f8255c0b327310b9f171d0125f288528097351e40de9623fa04a08afd51c751`

Authority-service source-design preflight bundle SHA-256:

`9cac6ce954fcfd60cd154c95c5aae9e7ebb7d50b531c85a64d1c1d7e361bfccf`

Architecture:

`AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1`

Reference Lambda handler:

`authority_service.handler`

Candidate future source:

`infra/aws/r8_3r6/authority_service/authority_service.py`

Candidate future offline test:

`tests/test_c2_r8_3r6_authority_service_offline.py`

Candidate future package requirements:

`infra/aws/r8_3r6/authority_service/requirements.txt`

---

## 1. Scope and non-claims

This document specifies the source contract for the signer/security-boundary Lambda
authority service. It does **not** implement the Lambda, build a deployment ZIP,
install Boto3/botocore, access AWS, use real cloud credentials, provision resources,
select Object Lock retention, or authorize CONTROLLED_LIVE.

The source gate remains downstream of the already implemented and independently
audited CloudFormation dual-stack templates. It must preserve the sealed R8.3R6
receipt protocol and the already hardened immutable archive policy.

Explicit status:

- `AUTHORITY_SERVICE_SOURCE_DESIGN_COMPLETE=TRUE` only after this document is committed
  by its gate.
- `AUTHORITY_SERVICE_SOURCE_IMPLEMENTATION_AUTHORIZED=FALSE`
- `AUTHORITY_SERVICE_SOURCE_IMPLEMENTED=FALSE`
- `DEPLOYMENT_PACKAGE_BUILD_AUTHORIZED=FALSE`
- `DEPLOYMENT_PACKAGE_BUILT=FALSE`
- `DEPENDENCY_INSTALLATION_PERFORMED=FALSE`
- `REAL_AWS_NETWORK_EXECUTION_AUTHORIZED=FALSE`
- `REAL_CLOUD_CREDENTIALS_AUTHORIZED=FALSE`
- `RESOURCE_PROVISIONING_PERFORMED=FALSE`
- `STRONGER_EXTERNAL_AUTHORITY_IMPLEMENTED=FALSE`
- `CONTROLLED_LIVE_ADMISSIBLE=FALSE`
- `MACROBLOCK_2_CLOSED=FALSE`
- `REMAINING_C2_LIVE_MACROBLOCKS=5`
- `PRODUCTION_ADMISSIBLE=FALSE`

---

## 2. Design objective

The authority service is not a generic signing API and not a generic S3 writer.
It is a narrowly scoped remote state-transition integrity authority.

For each governed receipt mutation it must:

1. validate an exact versioned MATRIX request;
2. bind the request to the one configured project/sport/root/database stream;
3. verify the caller used the governed Lambda alias/version;
4. verify the configured KMS signing identity;
5. reconstruct/validate the immutable remote predecessor;
6. construct the exact canonical unsigned receipt;
7. sign with the exact KMS Ed25519 key;
8. locally verify the returned signature;
9. assume the exact archive append role;
10. create exactly one canonical S3 receipt key with `IfNoneMatch="*"`;
11. read the object back and verify exact bytes;
12. reconcile 412/409/timeout ambiguity without silently forking;
13. return only bounded non-secret authority evidence.

It must never become a bypass around the sealed protocol.

---

## 3. Trust and fault boundaries

### 3.1 Normal MATRIX runtime

The normal runtime may invoke only the governed authority alias and read non-secret
verification/configuration metadata. It must not possess:

- raw `kms:Sign`;
- direct S3 receipt write;
- receipt delete;
- bucket policy/retention/Object Lock administration;
- KMS administration;
- account/root credentials;
- long-lived AWS access keys created by MATRIX.

### 3.2 Signer/security account

The authority Lambda executes in the signer/security account. Its base role is
limited to exact KMS sign/get-public-key/describe-key, exact STS assume-role into
the archive boundary, and exact log write.

### 3.3 Archive account

The archive role alone performs conditional receipt reads/writes on the canonical
prefix. The bucket policy remains deny-first and retained across stack
delete/replacement.

### 3.4 Administrative identities

Bootstrap/rotation/infrastructure administrators remain outside the MATRIX runtime
credential path. Administrative capability is never inferred from a successful
runtime invocation.

---

## 4. Source structure and dependency boundary

The future source should expose a pure service/core layer plus a thin Lambda wrapper.

Reference module:

`infra/aws/r8_3r6/authority_service/authority_service.py`

Required construction pattern:

- no AWS client creation at module import time;
- no credential/environment dump;
- no global mutable authority state;
- lazy runtime factory for real AWS clients;
- dependency injection for offline tests:
  - KMS client;
  - STS client;
  - S3 client factory;
  - clock;
  - backoff/sleeper;
  - invocation metadata/context.

The Lambda package must not silently depend on whatever Boto3 version happens to be
present in the managed runtime. The future package requirements must pin and package
Boto3 plus its transitive dependencies. If `cryptography` is used for SPKI parsing
and Ed25519 verification, it must likewise be pinned and packaged with exact build
evidence.

The root repository `requirements.txt` is not changed merely to satisfy Lambda
packaging.

---

## 5. Invocation surface

Direct Lambda invocation remains reference v1.

The CloudFormation resource permission already targets the governed alias and exact
`AuthorityInvokerPrincipalArn`; source adds defense in depth.

The handler must examine `context.invoked_function_arn` when available and reject
invocation that is not the governed alias/version. `$LATEST` is never a governed
authority surface.

The source does not treat `request_nonce`, `operation_id`, caller-supplied ARNs, or
event fields as authentication credentials.

---

## 6. Request protocol

Envelope schema:

`matrix.c2-r8-3r6-authority-request/1`

The parser is exact-key, versioned and fail-closed. Unknown top-level fields are
rejected.

Reference operations:

### 6.1 `APPEND_RECEIPT`

Mutating operation for one receipt intent. The request carries:

- schema;
- operation;
- request nonce/correlation id;
- required root-store id;
- required database-instance id;
- expected head:
  - sequence;
  - receipt id;
  - receipt SHA-256;
- receipt intent:
  - receipt type;
  - operation id;
  - control/run references when required;
  - local transition references when required;
  - local schema user version;
  - exact receipt-type metadata.

The caller does **not** authoritatively supply:

- archive destination;
- archive role ARN;
- KMS key ARN;
- signing account/region;
- signer key id;
- canonical payload SHA-256;
- signature;
- receipt id.

Those are derived/validated inside the authority.

### 6.2 `READ_HEAD`

Read-only operation. It reconstructs the authoritative head from the immutable
receipt namespace. It never creates a mutable HEAD object and never signs.

### 6.3 `READ_RECEIPT`

Read-only exact-sequence retrieval for reconciliation/evidence. It fully validates
the returned receipt before treating it as trusted.

No generic S3/KMS/STS proxy operation is exposed.

---

## 7. Stream identity

Fixed values:

- project domain: `matrix.c2`
- sport: `football`
- receipt protocol: `matrix-eir/v1`
- authority profile:
  `AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1`

Environment-pinned values:

- `MATRIX_ROOT_STORE_ID`
- `MATRIX_DATABASE_INSTANCE_ID`
- `MATRIX_ARCHIVE_ACCOUNT_ID`
- `MATRIX_ARCHIVE_REGION`
- `MATRIX_ARCHIVE_BUCKET`
- `MATRIX_ARCHIVE_APPEND_ROLE_NAME`
- `MATRIX_SIGNING_KEY_ARN`
- `MATRIX_KEY_EPOCH`

The canonical receipt prefix remains:

`matrix-eir/v1/matrix.c2/football/{root_store_id}/{database_instance_id}/receipts/`

and the object key remains:

`{sequence:020d}.json`

Genesis is sequence `1`. `control_id` and `run_id` remain signed receipt fields and
never become path partitions.

---

## 8. Receipt intent and metadata contracts

The existing canonical receipt types remain:

- `ROOT_GENESIS`
- `ROOT_PREPARED`
- `ROOT_COMMITTED`
- `ROOT_ABORTED`
- `ROOT_KEY_ROTATION`

The service must use exact metadata schemas, not arbitrary pass-through mappings.

### 8.1 Genesis

Existing canonical genesis metadata includes:

- `backend_profile`
- `controlled_live_admissible`
- `local_snapshot_sha256`
- `genesis_transition_events`
- `genesis_run_state`
- `bootstrap_public_key_b64`
- `bootstrap_public_key_fingerprint`
- `bootstrap_signer_key_id`

Genesis has no local transition reference and requires expected head `(0, null, null)`.

### 8.2 Prepared

Prepared requires the control/run/event references already enforced by R8.3R6.
Metadata is exactly:

- `expected_outcome`
- `expected_prior_state`
- `expected_next_state`
- `expected_state_version_before`
- `expected_state_version_after`

### 8.3 Committed / Aborted

Terminal metadata is exactly:

- `prepared_receipt_id`
- `prepared_receipt_sha256`

`ROOT_COMMITTED` must bind the same local transition as its prepare.
`ROOT_ABORTED` must not fabricate a committed local transition reference.

### 8.4 Key rotation

The receipt protocol already defines `ROOT_KEY_ROTATION`, including:

- `new_key_id`
- `new_public_key_b64`
- `new_public_key_fingerprint`
- `new_key_proof_signature_b64`
- `activation_sequence`
- `proof_core`

However, ordinary runtime invocation must not be able to nominate and activate an
arbitrary new key. The first source implementation must fail closed for key rotation
unless its implementation gate also proves a separately governed new-KMS-key
identity/permission workflow. A later rotation subgate may enable it without changing
the receipt schema.

CloudFormation replacement is never a valid rotation event by itself.

---

## 9. Canonicalization and signing

The authoritative canonical JSON contract remains the existing MATRIX contract:

- UTF-8;
- keys sorted;
- separators `(",", ":")`;
- `ensure_ascii=False`;
- `allow_nan=False`;
- one terminal newline.

The service constructs the unsigned receipt payload, canonicalizes it, and computes
its SHA-256.

KMS requirements:

- exact configured key ARN;
- key spec `ECC_NIST_EDWARDS25519`;
- usage `SIGN_VERIFY`;
- signing algorithm includes `ED25519_SHA_512`;
- key state enabled at activation/runtime evidence;
- `Sign` uses:
  - `SigningAlgorithm="ED25519_SHA_512"`
  - `MessageType="RAW"`
  - exact canonical unsigned receipt bytes.

### 9.1 Critical DER-to-raw public-key bridge

AWS KMS `GetPublicKey` returns DER-encoded X.509 SubjectPublicKeyInfo (SPKI), not
the 32 raw Ed25519 bytes used by the sealed MATRIX signer identity.

Therefore the source must:

1. call `GetPublicKey` on the exact configured KMS ARN;
2. validate returned key ARN/spec/usage/signing algorithms;
3. parse DER SPKI as an Ed25519 public key;
4. export exactly 32 raw Ed25519 public bytes;
5. compute:
   `public_key_fingerprint = sha256(raw_public_key)`;
6. derive:
   `signer_key_id = "ed25519:" + public_key_fingerprint`;
7. use that raw public key to verify every returned KMS signature before S3 publish.

Fingerprinting the DER SPKI bytes would be a protocol incompatibility and must fail
tests.

The service then derives:

- `canonical_payload_sha256`;
- base64 signature;
- `receipt_id` using existing
  `matrix.c2-r8-3r6-receipt-id/1`;
- exact storage receipt bytes.

It reparses/validates the constructed receipt before remote publication.

No ephemeral/local private signer fallback is allowed.

---

## 10. Archive role assumption

After receipt/key validation, the service assumes exactly:

`arn:aws:iam::{ArchiveAccountId}:role/{ArchiveAppendRoleName}`

The role ARN is built from pinned configuration, never event input.

Returned assumed-role identity evidence must match the expected archive
account/role before an S3 client is accepted.

Temporary credentials exist only in memory inside the Lambda invocation and must
never appear in logs, responses, receipt metadata, reports or evidence bundles.

---

## 11. S3 mutation protocol

Canonical `PutObject`:

- configured archive bucket only;
- canonical sequence key only;
- body = exact canonical receipt bytes;
- `ContentType = application/json`;
- `IfNoneMatch = "*"`.

The existing archive bucket policy enforces the conditional-write header and denies
receipt deletion/retention mutation.

On success the service re-reads the canonical object and requires exact byte
equivalence before reporting success.

A successful SDK response without exact read-back is not authority success.

---

## 12. Idempotency, conflicts and ambiguous outcomes

### 12.1 412

`412 PreconditionFailed` means the service must read the exact sequence key.

- exact existing receipt/intended operation => idempotent success;
- conflicting receipt => fork/security incident;
- unreadable/malformed existing receipt => fail closed.

### 12.2 409

`409 ConditionalRequestConflict` / `OperationAborted` is bounded-retry eligible.
The retry cannot change operation id, expected predecessor or sequence.

### 12.3 Timeout / connection loss

When a write may have committed:

1. do not assume failure;
2. read the canonical sequence key;
3. exact matching receipt => reconciled success;
4. conflicting receipt => fork;
5. absent receipt => only bounded retry.

No unbounded loop is allowed.

### 12.4 Authorization errors

AccessDenied, expired/invalid credentials and signing failures are blocking and are
not treated as ordinary transient retries.

---

## 13. SDK retry ownership

MATRIX must be able to account for every AWS attempt.

Future Boto3/botocore clients therefore use explicit configuration equivalent to:

`Config(retries={"total_max_attempts": 1, "mode": "standard"})`

so an SDK call performs one total request and does not silently multiply
application-level retry budgets.

MATRIX-owned retry/reconciliation code supplies the bounded retry policy and records
attempt counts.

Backoff/jitter is injectable in offline tests and is not yet claimed operationally
calibrated. Latency/capture calibration remains a later macroblock.

---

## 14. Lambda time-budget discipline

The CloudFormation timeout is finite. The source must check
`context.get_remaining_time_in_millis()`.

Before starting a mutating remote call it must preserve a configured reconciliation
reserve. If that reserve cannot be preserved, it fails before the mutation.

After a potentially committed write, the remaining budget is used first for
canonical read-back/reconciliation.

The source-design gate intentionally does not choose a CONTROLLED_LIVE latency
threshold; empirical calibration remains required.

---

## 15. Immutable head reconstruction

No mutable authoritative HEAD object is introduced.

`READ_HEAD` reconstructs from the immutable namespace and requires:

- sequence starts at 1;
- contiguous sequence;
- no malformed key;
- exact stream identity;
- exact receipt canonical bytes;
- exact receipt id/hash;
- correct predecessor id/SHA;
- valid active signer history;
- no same-sequence alternative receipt.

The authoritative head is the highest contiguous cryptographically valid receipt
from genesis.

Warm Lambda caches may only accelerate non-authoritative data. Cache loss must not
change the authority result.

---

## 16. Response protocol

Response schema:

`matrix.c2-r8-3r6-authority-response/1`

Allowed response classes include:

- `APPENDED`
- `IDEMPOTENT_EXISTING`
- `IDEMPOTENT_AFTER_AMBIGUOUS_OUTCOME`
- `HEAD`
- `RECEIPT`
- bounded fail-closed error status/code.

Permitted evidence includes:

- request nonce/correlation id;
- operation id;
- root/database identity;
- authority profile;
- signer key id/public fingerprint/key epoch;
- receipt/head public fields;
- canonical receipt SHA-256;
- archive bucket/key identity;
- bounded attempt counters;
- reconciliation boolean/status.

Forbidden:

- AWS access/secret/session credentials;
- private key material;
- environment dump;
- arbitrary exception text;
- provider credentials;
- DSN/password;
- bearer secrets.

The response itself cannot set application admission booleans true.

---

## 17. Logging and error hygiene

The handler never logs the raw event.

Loggable fields are explicit allowlisted hashes/ids/status codes only.

Domain errors use stable constant codes, e.g.:

- request schema mismatch;
- stream identity mismatch;
- governed alias required;
- KMS identity/spec/usage mismatch;
- KMS signature verification failed;
- archive assume-role identity mismatch;
- predecessor/sequence mismatch;
- 412 fork;
- 409 retry exhausted;
- ambiguous timeout exhausted;
- read-back divergence;
- sequence gap;
- unsupported rotation;
- insufficient reconciliation budget.

Unexpected exceptions map to a generic fail-closed code. User-controlled values are
not interpolated into the public error.

---

## 18. Offline-test architecture

Offline tests must not require Boto3 to contact AWS and must not read real
credentials.

The implementation should support injected fake clients/factories. Tests cover:

- exact request parsing;
- unknown-key rejection;
- stream mismatch;
- alias/version mismatch;
- KMS DER SPKI parsing;
- raw-32 fingerprint compatibility with existing MATRIX key id;
- exact `Sign` request;
- bad returned signature;
- STS exact-role assumption;
- wrong assumed-role identity;
- exact S3 conditional put;
- read-after-write;
- 412 idempotent/fork split;
- 409 bounded retry;
- timeout reconciliation;
- auth fail-closed;
- service retry exhaustion;
- sequence/gap/predecessor validation;
- secret/error/log hygiene;
- warm-cache non-authority;
- unsupported key rotation fail-closed;
- existing EIR/CloudFormation/full-CI regression.

No real AWS call is needed for source implementation tests.

---

## 19. Package build contract — future gate only

The source-design gate does not build a ZIP.

Future package gate must:

1. pin package dependencies;
2. build in an isolated directory;
3. include the authority source and required third-party libraries;
4. record exact dependency versions;
5. produce an inventory/SBOM-style manifest;
6. scan secrets;
7. reject credentials/private material;
8. produce deterministic or otherwise reproducibly inventoried ZIP evidence;
9. compute final ZIP SHA-256;
10. verify the ZIP hash equals the future `AuthorityCodeSha256` parameter value;
11. upload nothing until separately authorized.

---

## 20. Partition compatibility

The current application-side strong-authority identity accepts commercial partition
S3 bucket ARN form `arn:aws:s3:::`.

Therefore this source remains commercial-AWS-partition-only for any future
admission candidate. GovCloud/China are not silently accepted; extending that
contract requires a separate application + source + template audit.

---

## 21. Network-authorization separation

Authority networking is distinct from sports-provider networking.

A future authority permit domain must bind at least:

- authority profile;
- governed authority service identity;
- archive account/bucket/region;
- signing account/KMS key;
- root-store/database;
- request nonce/operation id;
- one-use or explicitly bounded scope;
- terminal network evidence.

Sports-provider execution authorization remains false and independent.

---

## 22. Key rotation boundary

The sealed protocol supports `ROOT_KEY_ROTATION`, but safe real rotation needs more
than source support.

A future governed rotation must prove:

- distinct new KMS key;
- exact signing account/region;
- Ed25519 spec/usage/algorithm;
- new raw public-key fingerprint;
- new-key proof;
- current-key authorization of the transition;
- activation sequence;
- historical verifier retention;
- no silent old-key deletion/disable inside evidence horizon;
- independent audit.

Until that workflow is implemented and audited, source must reject rotation requests
rather than accept caller-chosen replacement key material.

---

## 23. AWS capability facts used by this design

The following official AWS behavior is relied upon and must be revalidated at any
real activation/provisioning gate:

- KMS `GetPublicKey` returns DER-encoded X.509 SubjectPublicKeyInfo.
- KMS Ed25519 `ED25519_SHA_512` uses `MessageType=RAW`.
- S3 `If-None-Match: *` is a conditional create and can produce 412 on an existing
  current object and 409 on a conflicting operation.
- Boto3 `Config.retries.total_max_attempts` counts the initial request, so `1`
  disables hidden retries after that initial request.
- Lambda context exposes `invoked_function_arn`, indicating the invoked
  function/version/alias.

Capability references:

- https://docs.aws.amazon.com/kms/latest/developerguide/download-public-key.html
- https://docs.aws.amazon.com/kms/latest/APIReference/API_Sign.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
- https://docs.aws.amazon.com/boto3/latest/guide/retries.html
- https://docs.aws.amazon.com/lambda/latest/dg/python-context.html

These facts do not prove a MATRIX deployment.

---

## 24. Minimum source-design acceptance matrix

The next source implementation preflight must validate at least the following
design requirements. Count: **84**.

1. **ASD01** — Handler contract is exactly `authority_service.handler`; source implementation must not change the CloudFormation handler without a separately audited template change.
2. **ASD02** — The source package exposes a pure/testable service object and a thin Lambda `handler(event, context)` wrapper.
3. **ASD03** — Offline unit tests can inject KMS, STS, S3 clients/factories, clock, sleeper/backoff policy, and invocation metadata without importing credentials or opening network connections.
4. **ASD04** — The module does not create AWS clients at import time; client construction is lazy and occurs only inside the real handler/runtime factory.
5. **ASD05** — Request envelope schema is exactly `matrix.c2-r8-3r6-authority-request/1` and unknown top-level keys are rejected.
6. **ASD06** — Supported v1 operations are an explicit allowlist; unknown operations fail closed.
7. **ASD07** — `APPEND_RECEIPT` is the only v1 mutating authority operation.
8. **ASD08** — `READ_HEAD` is read-only and cannot sign or write.
9. **ASD09** — `READ_RECEIPT` is read-only and requires one positive sequence.
10. **ASD10** — Every request carries a non-empty request nonce/correlation id with a bounded canonical representation; it is never treated as authorization by itself.
11. **ASD11** — The request may name the expected root-store and database identities only for equality checking; it cannot select archive/signing infrastructure.
12. **ASD12** — Project domain is fixed to `matrix.c2` and cannot be supplied as an alternate value.
13. **ASD13** — Sport is fixed to `football` and cannot be supplied as an alternate value.
14. **ASD14** — Authority profile is fixed to `AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1`.
15. **ASD15** — Root-store id is lowercase 64-hex and must equal `MATRIX_ROOT_STORE_ID`.
16. **ASD16** — Database-instance id is lowercase 64-hex and must equal `MATRIX_DATABASE_INSTANCE_ID`.
17. **ASD17** — The service derives archive account, region, bucket and append-role name from non-secret environment configuration, not from request-controlled destinations.
18. **ASD18** — The service derives the signing key ARN and key epoch from non-secret environment configuration, not from request-controlled key selection.
19. **ASD19** — The runtime invocation must use the governed Lambda alias/version; direct `$LATEST` or unconstrained invocation is rejected by defense-in-depth source checks.
20. **ASD20** — `context.invoked_function_arn` is checked when available and must identify the governed invocation surface.
21. **ASD21** — Signing-account identity and region are checked against the KMS ARN, Lambda invocation ARN/region, and pinned configuration; mismatch fails closed.
22. **ASD22** — Archive role assumption uses one deterministic exact role ARN in the configured archive account and never a request-provided ARN.
23. **ASD23** — STS assumed-role evidence is checked for the expected archive account/role identity before S3 use.
24. **ASD24** — Normal MATRIX runtime credentials never receive raw `kms:Sign`, direct receipt-bucket write, bucket-policy administration, retention administration, or receipt delete authority.
25. **ASD25** — Source v1 does not accept AWS access keys, secret keys, session tokens, passwords, bearer tokens, DSNs, API keys, or private-key material in request fields.
26. **ASD26** — Source v1 does not read credential values from arbitrary application environment variables; AWS SDK credential resolution is external to the protocol and later activation governance.
27. **ASD27** — Request logging never serializes the full event, metadata, AWS responses, credentials, session tokens, signatures as secrets, or exception objects containing sensitive values.
28. **ASD28** — Expected/domain errors use constant error codes; user-controlled values are not interpolated into exception messages.
29. **ASD29** — Unexpected exceptions are converted to a generic fail-closed error response while logs contain only bounded correlation identifiers and safe error classes.
30. **ASD30** — Canonical request-size and metadata-size ceilings are explicit, tested, and fail closed; no unbounded recursive or oversized JSON structures are accepted.
31. **ASD31** — `APPEND_RECEIPT` requires an exact `expected_head` tuple of sequence, receipt id and receipt SHA-256 with genesis represented only as `(0, null, null)`.
32. **ASD32** — Next sequence is exactly `expected_head.sequence + 1`; sequence is never chosen independently by the caller.
33. **ASD33** — Canonical receipt namespace is global per project/sport/root/database and uses a 20-digit sequence key; control/run never partition S3 keys.
34. **ASD34** — Genesis is sequence `1` and is the only receipt allowed with a null predecessor.
35. **ASD35** — Receipt types remain exactly `ROOT_GENESIS`, `ROOT_PREPARED`, `ROOT_COMMITTED`, `ROOT_ABORTED`, and `ROOT_KEY_ROTATION` at protocol level.
36. **ASD36** — Initial source implementation may expose only the receipt types proven safe by its tests; any unsupported receipt type, including key rotation until its governed workflow exists, must fail closed rather than downgrade semantics.
37. **ASD37** — `ROOT_GENESIS` metadata is schema-checked against the existing canonical genesis contract, including local snapshot hash, transition/run snapshots, and bootstrap public-key identity.
38. **ASD38** — `ROOT_PREPARED` requires control/run/event references and exact metadata for expected outcome/prior state/next state/state-version bounds.
39. **ASD39** — `ROOT_COMMITTED` requires the same local transition reference as its prior prepare and exact binding to prepared receipt id/SHA-256.
40. **ASD40** — `ROOT_ABORTED` requires exact prepared-receipt binding and forbids a committed local transition reference.
41. **ASD41** — `ROOT_KEY_ROTATION` can be enabled only by a separately governed rotation workflow that proves the new KMS key identity and new-key proof; ordinary runtime invocation cannot rotate to an arbitrary caller-supplied key.
42. **ASD42** — CloudFormation replacement alone never counts as a `ROOT_KEY_ROTATION` event.
43. **ASD43** — Receipt metadata uses per-receipt-type exact key sets; unknown metadata keys fail closed to prevent hidden/unreviewed immutable payloads.
44. **ASD44** — Caller does not supply `signer_key_id`, `canonical_payload_sha256`, `signature_b64`, or `receipt_id` as authoritative values; the authority derives them.
45. **ASD45** — The authority obtains the KMS public key using `GetPublicKey` and validates exact key ARN/spec/usage/signing algorithm before use.
46. **ASD46** — KMS `GetPublicKey` DER X.509 SubjectPublicKeyInfo is parsed to an Ed25519 public key and exported as exactly 32 raw bytes before MATRIX fingerprint derivation.
47. **ASD47** — `signer_key_id` is exactly `ed25519:{sha256(raw_32_byte_public_key)}` and key epoch is separately evidenced.
48. **ASD48** — KMS signing uses the exact configured key ARN, `SigningAlgorithm=ED25519_SHA_512`, and `MessageType=RAW`.
49. **ASD49** — The signed message is the exact canonical UTF-8 unsigned receipt bytes with newline and existing MATRIX serialization semantics; no SDK/base64 representation is signed accidentally.
50. **ASD50** — KMS-returned signature is verified locally with the derived Ed25519 public key over the exact signed bytes before any S3 publication.
51. **ASD51** — `canonical_payload_sha256` is recomputed from exact canonical unsigned receipt bytes.
52. **ASD52** — `receipt_id` is recomputed using the existing `matrix.c2-r8-3r6-receipt-id/1` derivation from payload hash plus signature base64.
53. **ASD53** — The full storage receipt is serialized with the existing deterministic UTF-8 JSON contract and reparsed/validated before S3 write.
54. **ASD54** — The service never uses an ephemeral/local private signing key as fallback when KMS is unavailable.
55. **ASD55** — The service assumes the exact archive append role only after successful identity/key validation and receipt construction.
56. **ASD56** — S3 writes use only the canonical configured bucket and key and set `IfNoneMatch='*'`.
57. **ASD57** — S3 write body is exactly the canonical receipt bytes and content type is `application/json`.
58. **ASD58** — S3 object metadata contains only bounded non-secret receipt identifiers/hashes already permitted by the protocol.
59. **ASD59** — On successful `PutObject`, the service performs read-after-write and requires exact canonical byte equivalence before returning success.
60. **ASD60** — On HTTP 412 / `PreconditionFailed`, the service reads the canonical sequence key: exact matching receipt/request intent is idempotent success; divergence is a fork incident.
61. **ASD61** — On HTTP 409 / `ConditionalRequestConflict` or `OperationAborted`, retry is bounded and never changes sequence or operation identity.
62. **ASD62** — On timeout/connection loss after a write may have committed, the service first reads the canonical sequence key before any retry.
63. **ASD63** — Ambiguous timeout with an exact existing receipt is reconciled as idempotent success; a conflicting receipt is a fork; an absent receipt may be retried only within the bounded budget.
64. **ASD64** — Authorization failures (401/403, AccessDenied, ExpiredToken, signature/credential errors) fail closed and are not retried as ordinary service transients.
65. **ASD65** — Service/throttling failures have an explicit bounded application retry budget; no unbounded loop is permitted.
66. **ASD66** — Boto3/botocore clients are configured with explicit `total_max_attempts=1` so hidden SDK retries cannot multiply MATRIX retry bounds; MATRIX-owned retry logic counts each AWS call.
67. **ASD67** — Backoff/jitter policy is injectable for offline tests and later empirically calibrated; source design does not claim current latency is CONTROLLED_LIVE acceptable.
68. **ASD68** — Before initiating a mutating call the handler checks remaining Lambda time and refuses to start when the governed reconciliation reserve cannot be preserved.
69. **ASD69** — After a potentially committed write, remaining time is preferentially spent on read-after-write reconciliation rather than starting an unrelated new mutation.
70. **ASD70** — `READ_HEAD` reconstructs from the immutable receipt namespace; no mutable authoritative HEAD object is introduced.
71. **ASD71** — Head is the highest contiguous cryptographically valid sequence beginning at genesis; gaps, duplicates, malformed keys, wrong predecessor, wrong store/database identity, or invalid signatures fail closed.
72. **ASD72** — `READ_RECEIPT` validates canonical bytes, receipt id/hash, stream identity, predecessor fields where context is available, and signer/key history before returning trusted data.
73. **ASD73** — Warm Lambda memory/cache may accelerate non-authoritative metadata only; it can never become the source of truth for head, sequence, idempotency, key state, or admission.
74. **ASD74** — Response schema is exactly versioned and allowlisted; it returns public identities, receipt/head evidence and bounded attempt/reconciliation metadata only.
75. **ASD75** — Responses never contain AWS credentials, STS session tokens, private key material, raw environment dumps, arbitrary exception text, or provider credentials.
76. **ASD76** — Source/package requirements are isolated under `infra/aws/r8_3r6/authority_service/requirements.txt`; root application requirements are not silently changed by the source-design gate.
77. **ASD77** — Future deployment package pins and packages Boto3 plus transitive dependencies rather than relying silently on Lambda runtime-bundled SDK versions.
78. **ASD78** — `cryptography` is explicitly pinned/packaged if used for DER SPKI parsing and local Ed25519 verification; package evidence records exact versions and hashes.
79. **ASD79** — Future package build produces deterministic inventory/SBOM-style evidence and verifies `AuthorityCodeSha256` against final ZIP bytes before any stack creation.
80. **ASD80** — Commercial AWS partition remains the only admissible partition for the current application-side bucket-ARN contract; GovCloud/China remain blocked until that contract is separately extended and audited.
81. **ASD81** — Authority-service network authorization uses a distinct authority permit domain and never reuses sports-provider execution permits.
82. **ASD82** — Source implementation and offline tests cannot set `CONTROLLED_LIVE_ADMISSIBLE`, `STRONGER_EXTERNAL_AUTHORITY_IMPLEMENTED`, or `PRODUCTION_ADMISSIBLE` true.
83. **ASD83** — First real AWS network call, credential use, package upload, stack validation/provisioning, retention selection, and resource creation remain separate human/governance gates.
84. **ASD84** — Macrobloque 2 remains open until real stronger authority is provisioned, remotely evidenced, integrated, and independently audited; this source design alone cannot close it.

---

## 25. Required future implementation artifacts

The source implementation gate is expected to create at minimum:

1. `infra/aws/r8_3r6/authority_service/authority_service.py`
2. `infra/aws/r8_3r6/authority_service/requirements.txt`
3. `tests/test_c2_r8_3r6_authority_service_offline.py`
4. an implementation document/evidence artifact.

If parity with the canonical receipt serializer cannot be proven without extracting
a smaller shared pure protocol module, that refactor must be proposed and audited
before implementation; byte-level protocol compatibility must not be traded for
convenience.

---

## 26. Source implementation promotion criteria

Source implementation may be authorized only after an implementation preflight
confirms:

- exact baseline and this design blob;
- all 84 ASD requirements are machine-checkable or explicitly test-mapped;
- no planned real network call;
- no real credentials;
- no dependency installation during the source gate unless separately approved;
- exact packaging/dependency plan;
- canonical receipt parity strategy;
- DER-SPKI-to-raw-key parity test;
- explicit SDK retry ownership;
- full existing R8.3R6 regression preservation.

Source implementation alone still cannot authorize AWS network execution or close
Macrobloque 2.

---

## 27. Next gate

After this source design is committed and audited for exact content, the next gate is:

`R8_3R6_STRONG_EXTERNAL_AUTHORITY_AUTHORITY_SERVICE_SOURCE_IMPLEMENTATION_PREFLIGHT`

That gate remains offline/read-only.
