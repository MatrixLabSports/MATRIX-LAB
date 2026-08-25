# MATRIX C2 — R8.3R6 Strong External Authority
## CloudFormation Dual-Stack Declarative Design

Status: **OFFLINE DECLARATIVE DESIGN ONLY — NO CLOUD PROVISIONING AUTHORIZED**

Macroblock: **2 — External Immutable Integrity Root**

Selected architecture:

`AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1`

This document defines the exact contract for the next CloudFormation template
implementation gate. It does not create AWS resources, contact AWS, load cloud
credentials, load a real signing key, authorize a sports provider, authorize
repeated polling, authorize wagering, or make the strong authority
CONTROLLED_LIVE-admissible.

---

## 1. Exact design baseline

Repository baseline:

- branch:
  `integration/c2-private-live-foundation`
- HEAD:
  `865692217793a8dfca0ebdd7c1fa93dd1fbc29ab`
- subject:
  `docs(football): seal R8.3R6 offline strong authority audit`

Sealed inputs:

- cloud-bootstrap design-preflight bundle SHA-256:
  `4d0465c6eaef2a2da647d1257b0f0d8508d7f6f29c26b19b1eb8be796392f459`
- cloud-bootstrap design-preflight report SHA-256:
  `0241dfd1eef2d025557f131285a3f89e3b92d46ed1f9626444bb8f419ca930f8`
- repository-native root-pattern supplement SHA-256:
  `9c5117d26a891c35613dec6123fe4a3d59444ed7b68f3fc7237bd62244880c70`
- repository-native supplement report SHA-256:
  `082582a507089f723865a402a23659aeb7937043d698985c3f1b33f2a4499129`
- hardened strong-authority architecture SHA-256:
  `cd09ff9b7a6b8f5692a047dbe63aa63a48e06f654950814d71028cd89b131d34`
- offline strong-authority implementation seal SHA-256:
  `8ed0f160f65fd076ba3c80c83817aade83e5f3773fbbb0f892a0a3e30314a89a`

The repository-native supplement found 23 relevant tracked files, including:

- 31 exact `postgres_freshness_root` matches;
- 63 Postgres freshness-class matches;
- 277 freshness-root matches;
- 11 rollback-root matches;
- 3 rollback-resistant matches;
- 2 monotonic-root matches;
- 4 freshness-authority matches.

This design therefore incorporates the existing MATRIX remote-freshness and
rollback-safety conventions rather than creating an unrelated second philosophy.

---

## 2. Critical architecture decision after repository-native review

The existing `PostgresFreshnessRoot` is **not** promoted into the R8.3R6 immutable
receipt authority and is **not** treated as a replacement for S3 Object Lock.

The two mechanisms solve related but distinct trust problems:

- `FreshnessRoot` / `PostgresFreshnessRoot`
  - provides monotonic current/pending state;
  - supports prepare/finalize/abort and compare-and-set semantics;
  - detects regression and same-sequence divergence;
  - was previously demonstrated against remote AWS RDS PostgreSQL outside the local
    Windows rollback fault domain;
  - remains a mutable remote state authority rather than an immutable historical
    receipt archive.

- R8.3R6 external immutable integrity root
  - preserves the complete signed receipt sequence;
  - provides immutable historical evidence for PREPARE, COMMIT, ABORT, terminal
    outcomes and key rotation;
  - must detect coherent replacement/re-authoring of the local database while the
    external authority remains intact;
  - requires append-only/rollback-resistant remote history.

Therefore:

**PostgreSQL freshness semantics are reused as design patterns, not as the R8.3R6
WORM trust root.**

No second authoritative receipt history is introduced in PostgreSQL.

---

## 3. Repository-native patterns that are mandatory in the cloud design

### 3.1 Explicit production-admission bit

`FreshnessRoot` exposes `production_authorized`, and the in-memory and current
PostgreSQL implementations do not silently become production roots.

R8.3R6 adopts the same admission principle:

- CloudFormation template existence is not deployment evidence.
- Stack creation is not sufficient activation evidence.
- Synthetic policy validation is not remote proof.
- The application property
  `stronger_external_authority_implemented`
  MUST remain `False` until the separately governed remote evidence and independent
  audit gates pass.
- `controlled_live_admissible` MUST remain `False` throughout bootstrap and research
  sandbox phases.

No CloudFormation parameter, output, tag or environment variable may directly flip
either application admission bit.

### 3.2 Reservation-aware transition semantics

The existing MATRIX freshness lifecycle uses:

1. verify external checkpoint;
2. verify current freshness authority;
3. transactional domain validation;
4. append local lifecycle/tail evidence;
5. prepare external freshness transition;
6. commit local transaction;
7. finalize external freshness transition;
8. synchronize external checkpoint;
9. resolve failed/ambiguous transitions.

R8.3R6 keeps its already sealed protocol:

`REMOTE PREPARE -> LOCAL COMMIT -> REMOTE FINALIZE/COMMIT -> LOCAL ACK`

The cloud bootstrap MUST preserve that ordering. Infrastructure must not introduce a
shortcut that acknowledges local success before remote PREPARE or remote FINALIZE is
authoritative.

### 3.3 Fail-closed corrupted authority state

`PostgresFreshnessRoot` treats malformed or internally inconsistent authority rows
as security failures and never silently repairs them.

The strong external authority MUST similarly reject:

- malformed S3 receipt bytes;
- wrong stream identity;
- wrong sequence;
- wrong predecessor;
- wrong signer identity;
- wrong KMS key identity;
- wrong archive account/bucket/region;
- gaps in the receipt stream;
- conflicting same-sequence receipts;
- weakened retention/conditional-write evidence.

No repair-by-rebaseline is permitted.

### 3.4 Ambiguous commit outcome is a first-class state

The PostgreSQL adapter explicitly distinguishes a commit failure from proof that the
server did not commit.

The S3 authority MUST preserve the analogous R8.3R6 behavior:

- if a conditional `PutObject` response is lost or times out after the request may
  have committed, do not assume failure;
- read the canonical sequence key;
- exact byte/hash/signature equivalence => idempotent reconciliation;
- conflicting object => fork incident;
- object absent => bounded retry according to the governed retry contract;
- no unbounded retry loop.

### 3.5 Regression and same-sequence divergence are blocking

MATRIX already treats freshness regression and same-sequence divergence as explicit
security states.

The S3 authority therefore keeps:

- genesis = sequence `1`;
- next sequence = exactly predecessor + 1;
- no sequence regression;
- no same-sequence alternative receipt;
- no mutable authoritative HEAD object;
- authoritative head = highest contiguous cryptographically valid sequence from
  genesis.

### 3.6 Secret-reference, not secret-value, persistence

Existing MATRIX secret-reference governance records references/fingerprints while
declaring raw-secret persisted/logged/fingerprinted flags false.

Cloud bootstrap MUST therefore contain no:

- AWS access key;
- AWS secret access key;
- AWS session token;
- root credential;
- KMS private material;
- authority invocation secret;
- provider API credential;
- DSN/password.

CloudFormation parameter values that are credentials are forbidden for this
bootstrap. The later activation gate must use an external short-lived machine
identity mechanism or equivalent governed credential source; raw credential values
must remain outside Git/evidence.

### 3.7 Network execution remains separately authorized

Existing MATRIX provider network execution uses explicit scoped authorization,
fingerprints and one-use permits.

The future cloud-authority network gate MUST reuse that **governance pattern** but
must not reuse or overload sports-provider permits. It requires a distinct authority
network permit domain, bound to:

- authority profile;
- authority service ARN/identity;
- archive account/bucket/region;
- signing account/KMS key;
- root-store/database identity;
- request nonce/operation id;
- one-use or explicitly bounded execution scope;
- terminal network evidence.

Sports-provider execution authorization remains independent and false.

### 3.8 Remote fault-domain and least-privilege precedent

The prior remote freshness closure established a valuable MATRIX precedent:

- remote authority outside the local Windows host;
- verified TLS/server identity;
- separate migrator/admin role;
- runtime role not owner of the authority table;
- real concurrency allowed exactly one prepare winner;
- local snapshot rollback failed closed while remote root remained ahead.

The dual-stack design adopts the same separation principle, strengthened for
immutable receipts by independent archive and signer/security boundaries.

---

## 4. Current AWS capability basis verified for this design

Official AWS documentation reviewed on 2026-08-25 supports the following design
assumptions:

1. `AWS::S3::Bucket`
   - supports `ObjectLockEnabled`;
   - supports `ObjectLockConfiguration`;
   - supports Versioning configuration;
   - Object Lock default retention can use mode `COMPLIANCE` with a period in days or
     years.

2. Amazon S3 conditional writes
   - `If-None-Match: *` prevents creation when the current key already exists;
   - S3 can return `412 Precondition Failed` for a conflicting existing key;
   - concurrent/request-race paths can produce `409 Conflict`;
   - bucket policy can enforce conditional-write headers using
     `s3:if-none-match`;
   - enforcing conditional writes on the protected prefix also makes copy-style
     creation unsuitable, which matches MATRIX's requirement to forbid copy or
     unconditioned alternate write paths.

3. `AWS::KMS::Key`
   - supports `ECC_NIST_EDWARDS25519`;
   - asymmetric Ed25519 uses `SIGN_VERIFY`;
   - `ED25519_SHA_512` requires `MessageType=RAW`.

4. KMS rotation
   - automatic and on-demand key-material rotation are not supported for asymmetric
     KMS keys;
   - R8.3R6 key rotation must therefore be **manual logical rotation**:
     create a new KMS key / key epoch, bind the new public key, and authorize the
     transition through signed `ROOT_KEY_ROTATION` evidence.

5. `AWS::Lambda::Function`
   - can use a versioned S3 deployment package via S3 bucket, key and object version.

6. `AWS::Lambda::Permission`
   - can restrict invocation to a specified AWS account, IAM user or IAM role.

Official references:

- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3-bucket.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-s3-bucket-objectlockconfiguration.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-s3-bucket-defaultretention.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-kms-key.html
- https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-lambda-function.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-lambda-permission.html

These are capability references only. They do not prove a future MATRIX deployment.

---

## 5. Declarative artifact format

The next implementation gate will create **JSON CloudFormation templates**, not
YAML.

Reason:

- deterministic UTF-8 representation;
- Python standard-library parsing without PyYAML;
- no dependency on AWS CLI, Terraform, OpenTofu, `cfn-lint`, Docker, Node or npm;
- exact SHA-256 sealing of template bytes;
- straightforward adversarial structural validation offline.

The template pair will be:

1. `infra/aws/r8_3r6/matrix-c2-eir-signer-stack.json`
2. `infra/aws/r8_3r6/matrix-c2-eir-archive-stack.json`

A separate policy/test document will validate the pair before any network gate.

---

## 6. Two-stack trust topology

### Stack S — Signer/Security boundary

Deployment account:

`SIGNING_ACCOUNT_ID`

Deployment region:

`SIGNING_REGION`

Purpose:

- hold the asymmetric Ed25519 signing key;
- run the narrowly scoped authority service;
- expose only an exact governed invocation surface;
- assume the archive-account append role for immutable receipt access.

The signing account SHOULD be independently administered from the archive account.
For any future CONTROLLED_LIVE consideration, the two account IDs MUST differ.

### Stack A — Immutable Archive boundary

Deployment account:

`ARCHIVE_ACCOUNT_ID`

Deployment region:

`ARCHIVE_REGION`

Purpose:

- own the dedicated S3 receipt bucket;
- enforce Versioning + Object Lock + Compliance retention;
- enforce conditional creation on the canonical receipt prefix;
- expose only a least-privilege role assumable by the exact signer authority role.

The archive account must not contain the KMS private signing authority.

---

## 7. Shared pinned deployment identity

Both templates must bind the same governed identity parameters:

- `DeploymentId`
- `RootStoreId` — lowercase SHA-256 hex, no default
- `DatabaseInstanceId` — lowercase SHA-256 hex, no default
- project domain — hard-coded `matrix.c2`
- sport — hard-coded `football`
- authority profile — hard-coded
  `AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1`
- receipt protocol — hard-coded `matrix-eir/v1`

Canonical receipt prefix:

`matrix-eir/v1/matrix.c2/football/{root_store_id}/{database_instance_id}/receipts/`

Canonical receipt key:

`{prefix}{sequence:020d}.json`

Genesis:

`00000000000000000001.json`

`control_id` and `run_id` remain signed receipt fields and MUST NOT appear in the S3
namespace structure.

---

## 8. Signer stack contract

Proposed template:

`infra/aws/r8_3r6/matrix-c2-eir-signer-stack.json`

### 8.1 Parameters — all security-sensitive deployment identities have no default

Mandatory parameters:

- `DeploymentId`
- `ArchiveAccountId`
- `ArchiveRegion`
- `ArchiveBucketName`
- `ArchiveAppendRoleName`
- `RootStoreId`
- `DatabaseInstanceId`
- `KeyEpoch`
- `SignerAdminPrincipalArn`
- `AuthorityInvokerPrincipalArn`
- `AuthorityCodeBucket`
- `AuthorityCodeKey`
- `AuthorityCodeObjectVersion`
- `AuthorityCodeSha256`

Rules/validation requirements:

- `ArchiveAccountId` is 12 digits.
- `RootStoreId` and `DatabaseInstanceId` are 64 lowercase hex characters.
- `KeyEpoch` is a positive integer.
- no credential parameter exists;
- no secret parameter exists;
- no retention parameter exists in the signer stack;
- for a future strong-profile deployment, offline/remote evidence must prove
  `ArchiveAccountId != SigningAccountId`.

### 8.2 KMS signing key

Resource class:

`AWS::KMS::Key`

Required properties:

- `KeySpec = ECC_NIST_EDWARDS25519`
- `KeyUsage = SIGN_VERIFY`
- description bound to deployment id/profile/key epoch
- explicit key policy
- no automatic rotation property
- no imported private key
- no grant to MATRIX runtime

Lifecycle:

- `DeletionPolicy: Retain`
- `UpdateReplacePolicy: Retain`

The authority execution role may receive only:

- `kms:Sign`
- `kms:GetPublicKey`
- `kms:DescribeKey`

against the exact signing key.

It MUST NOT receive:

- `kms:PutKeyPolicy`
- `kms:CreateGrant` unless a later independently reviewed requirement proves it is
  necessary;
- `kms:DisableKey`
- `kms:ScheduleKeyDeletion`
- `kms:EnableKeyRotation`
- `kms:RotateKeyOnDemand`
- `kms:*`.

### 8.3 Manual key rotation

Because asymmetric automatic/on-demand rotation is not available, a key epoch
transition is:

1. create a distinct new Ed25519 KMS key;
2. obtain/pin its raw public verification material;
3. derive canonical
   `ed25519:{sha256(raw_public_key)}`;
4. emit signed `ROOT_KEY_ROTATION` evidence under the current key;
5. preferably obtain a new-key co-signature/activation proof;
6. switch governed deployment identity only after independent validation;
7. keep historical public keys/verifiers available;
8. do not silently disable/delete a key that remains inside the evidence horizon.

CloudFormation replacement alone is **not** a valid MATRIX key rotation event.

### 8.4 Authority execution role

Resource class:

`AWS::IAM::Role`

Trust:

- only `lambda.amazonaws.com`.

Inline permissions:

- exact KMS sign/get-public-key/describe-key on the governed key;
- exact `sts:AssumeRole` on:
  `arn:aws:iam::{ArchiveAccountId}:role/{ArchiveAppendRoleName}`;
- CloudWatch Logs write only for the exact authority log group.

Forbidden:

- direct S3 receipt permission in its base signer-account identity;
- IAM administration;
- KMS administration;
- account administration;
- Secrets Manager administrative access;
- wildcard `Action: "*"`;
- wildcard `Resource: "*"` for KMS/STS authority actions.

The archive operation must happen only after assuming the archive-account role so the
fault boundary remains explicit in evidence.

### 8.5 Authority Lambda function

Resource class:

`AWS::Lambda::Function`

Purpose:

- validate pinned stream identity;
- verify expected predecessor/sequence;
- construct canonical unsigned receipt;
- invoke exact KMS `Sign`;
- verify the produced signature/public key binding;
- assume the archive append role;
- perform exact conditional S3 creation;
- re-read and verify the authoritative object;
- reconcile ambiguous outcomes;
- return an authority result only after the remote receipt is authoritative.

Code input:

- versioned S3 deployment package;
- exact S3 bucket/key/object-version parameters;
- independently sealed `AuthorityCodeSha256`.

CloudFormation does not by itself prove the user-supplied SHA matches the object
bytes. The later provisioning gate MUST verify package bytes/hash before stack
creation and bind that evidence to the stack parameters.

Environment variables/configuration may contain only non-secret identities:

- project domain;
- sport;
- authority profile;
- root-store id;
- database-instance id;
- archive account;
- archive region;
- archive bucket;
- archive role ARN/name;
- signing key ARN;
- key epoch.

No AWS secret key, session token, authority secret or provider secret is permitted.

### 8.6 Authority invocation

Direct Lambda invocation is the reference v1 invocation surface.

Resource class:

`AWS::Lambda::Permission`

Required:

- `Action = lambda:InvokeFunction`
- principal = exact governed `AuthorityInvokerPrincipalArn`
- invocation targets a governed alias/version, not an unconstrained wildcard.

The normal MATRIX runtime must receive only the ability to invoke the exact governed
authority function/alias plus read non-secret verification metadata.

The bootstrap templates do not create long-lived local access keys. Credential
delivery for that invocation is a later activation/security gate.

---

## 9. Archive stack contract

Proposed template:

`infra/aws/r8_3r6/matrix-c2-eir-archive-stack.json`

### 9.1 Parameters — no unsafe defaults

Mandatory:

- `DeploymentId`
- `SignerAccountId`
- `SignerAuthorityExecutionRoleName`
- `ArchiveBucketName`
- `RetentionDays`
- `RootStoreId`
- `DatabaseInstanceId`

Rules/validation:

- signer account id is 12 digits;
- root/database ids are lowercase 64-hex;
- `RetentionDays` has **no Default**;
- `RetentionDays >= 1`;
- first real deployment requires explicit human approval of the selected value;
- future strong-profile evidence must prove
  `SignerAccountId != ArchiveAccountId`.

The template MUST NOT invent a retention duration.

### 9.2 Receipt bucket

Resource class:

`AWS::S3::Bucket`

Required:

- dedicated general-purpose bucket;
- `VersioningConfiguration.Status = Enabled`;
- `ObjectLockEnabled = true`;
- `ObjectLockConfiguration.ObjectLockEnabled = Enabled`;
- default retention:
  - `Mode = COMPLIANCE`;
  - `Days = RetentionDays`;
- Public Access Block:
  - block public ACLs;
  - ignore public ACLs;
  - block public policy;
  - restrict public buckets;
- Object Ownership:
  - `BucketOwnerEnforced`;
- explicit server-side encryption at rest;
- no website hosting;
- no public access.

Lifecycle:

- `DeletionPolicy: Retain`;
- `UpdateReplacePolicy: Retain`.

The receipt bucket is never treated as ephemeral test output once real Compliance
retention is activated.

### 9.3 Canonical receipt prefix only

Protected object ARN:

`arn:aws:s3:::${ArchiveBucketName}/matrix-eir/v1/matrix.c2/football/${RootStoreId}/${DatabaseInstanceId}/receipts/*`

The archive append role receives only:

- `s3:GetObject`
- `s3:GetObjectVersion`
- `s3:PutObject`

on the exact protected object prefix, plus only the minimum bucket-level reads needed
to list/reconstruct and validate configuration.

Required bucket-level reads may include:

- `s3:ListBucket` constrained to the exact prefix;
- `s3:GetBucketVersioning`;
- `s3:GetBucketObjectLockConfiguration`;
- `s3:GetBucketPolicy`;
- `s3:GetBucketLocation`.

No delete or policy/retention mutation permission is granted.

### 9.4 Archive append role

Resource class:

`AWS::IAM::Role`

Trust principal:

`arn:aws:iam::{SignerAccountId}:role/{SignerAuthorityExecutionRoleName}`

No other runtime principal may assume the role.

The role must not grant:

- `s3:DeleteObject`;
- `s3:DeleteObjectVersion`;
- `s3:PutBucketPolicy`;
- `s3:PutBucketVersioning`;
- `s3:PutBucketOwnershipControls`;
- `s3:PutBucketPublicAccessBlock`;
- `s3:PutObjectRetention`;
- `s3:BypassGovernanceRetention`;
- `s3:PutObjectLegalHold`;
- IAM administration;
- account administration.

### 9.5 Bucket policy

The template must implement explicit defense-in-depth statements for the protected
receipt prefix.

At minimum:

1. **Deny non-TLS access**
   - `Principal: "*"`
   - deny applicable S3 actions when `aws:SecureTransport = false`.

2. **Deny unconditioned receipt creation**
   - deny `s3:PutObject` on the protected receipt prefix when
     `s3:if-none-match` is absent;
   - the application request must use `If-None-Match: *`.

3. **Deny delete-marker/object deletion on receipt keys**
   - deny `s3:DeleteObject`;
   - deny `s3:DeleteObjectVersion`;
   - applies to the protected receipt prefix.

4. **Deny retention/lock mutation by the append path**
   - the append role must not be able to change object retention/legal hold.

5. **No copy/multipart alternate creation path**
   - the v1 authority uses single-object `PutObject`;
   - no copy-based receipt creation is authorized;
   - template/policy validation must reject a policy that opens an alternate
     unconditioned receipt-creation path.

Only the archive administrative boundary may alter bucket policy/infrastructure, and
those credentials never appear on the MATRIX runtime host.

---

## 10. Deployment order without circular authority

The exact declarative order is:

1. prepare and independently hash the authority Lambda code artifact;
2. deploy **Signer stack** first;
3. obtain/pin:
   - signer account id;
   - authority execution-role ARN;
   - KMS key ARN;
   - key epoch;
   - authority function/version/alias ARN;
4. deploy **Archive stack** second, trusting the exact signer authority execution
   role;
5. verify archive stack outputs/evidence;
6. update/confirm signer configuration only if a pinned archive role ARN needs an
   exact final binding;
7. perform no governed transition until remote activation evidence passes.

The signer role may contain the deterministic archive role ARN before the archive
role exists; lack of the remote role merely causes assume-role failure and cannot
grant authority.

No automatic fallback to local research authority is allowed.

---

## 11. Stack outputs — public identities only

Permitted signer outputs:

- signing account id;
- signing region;
- KMS key ARN;
- KMS public-key identity metadata/fingerprint when produced by later evidence;
- key epoch;
- authority execution-role ARN;
- authority function/version/alias ARN;
- deployment id.

Permitted archive outputs:

- archive account id;
- archive region;
- bucket ARN/name;
- archive append-role ARN;
- canonical receipt prefix;
- retention mode;
- approved retention days;
- root-store id;
- database-instance id.

Forbidden outputs:

- access key;
- secret key;
- session token;
- private key;
- credential material;
- provider API key;
- DSN/password;
- authority bearer secret.

---

## 12. Human approval gates before any real provisioning

The seven preflight gates remain mandatory:

1. `HUMAN_APPROVE_ARCHIVE_ACCOUNT_AND_REGION`
2. `HUMAN_APPROVE_SIGNING_ACCOUNT_AND_REGION`
3. `HUMAN_APPROVE_RETENTION_DURATION`
4. `HUMAN_APPROVE_RESOURCE_NAMES_AND_EXPECTED_COST`
5. `HUMAN_ACKNOWLEDGE_COMPLIANCE_RETENTION_IRREVERSIBILITY`
6. `HUMAN_AUTHORIZE_FIRST_AWS_NETWORK_CALL`
7. `HUMAN_AUTHORIZE_FIRST_RESOURCE_CREATION`

CloudFormation template implementation and offline validation do not satisfy these
approvals.

No real resource creation is authorized by this design.

---

## 13. Research sandbox versus CONTROLLED_LIVE boundary

A single-account sandbox may be useful only for protocol research and cost/latency
measurement.

It MUST report:

- `RESEARCH_SANDBOX_ONLY=TRUE`
- `STRONGER_EXTERNAL_AUTHORITY_IMPLEMENTED=FALSE`
- `CONTROLLED_LIVE_ADMISSIBLE=FALSE`

For a future strong-profile admission candidate:

- archive and signer/security administrative boundaries must be independent;
- exact deployed identities must be pinned;
- actual IAM effective permissions must be tested;
- Object Lock Compliance must be verified remotely;
- conditional-write enforcement must be verified remotely;
- signer separation must be verified remotely;
- real recovery/retry/fork/rollback tests must pass;
- independent remote audit must pass.

---

## 14. Template implementation gate — mandatory offline tests

The next gate must create the two JSON templates and test them without AWS network.

Minimum structural/adversarial validation:

### Archive template

1. JSON parses deterministically.
2. `RetentionDays` exists with no Default.
3. S3 bucket Versioning = Enabled.
4. Object Lock enabled.
5. Default retention mode = COMPLIANCE.
6. Default retention days references `RetentionDays`.
7. bucket DeletionPolicy = Retain.
8. bucket UpdateReplacePolicy = Retain.
9. Public Access Block fully enabled.
10. BucketOwnerEnforced.
11. canonical receipt prefix contains project/sport/root/database and not control/run.
12. append role trust is exact signer authority role.
13. append role has no delete permission.
14. append role has no bucket-policy administration.
15. append role has no retention administration.
16. bucket policy denies non-TLS.
17. bucket policy requires `s3:if-none-match` for receipt PutObject.
18. bucket policy denies receipt delete/delete-version.
19. no wildcard principal grants write authority.
20. no copy/multipart alternate write path is opened.

### Signer template

21. JSON parses deterministically.
22. KMS key spec = ECC_NIST_EDWARDS25519.
23. KMS key usage = SIGN_VERIFY.
24. KMS key retained on delete/replacement.
25. no automatic/on-demand rotation action is granted.
26. authority role may Sign/GetPublicKey/DescribeKey only on exact key.
27. authority role may AssumeRole only on exact archive role.
28. authority role has no direct S3 receipt permission.
29. authority role has no IAM/KMS administration.
30. Lambda uses exact authority execution role.
31. function code requires S3 bucket/key/object-version parameters.
32. `AuthorityCodeSha256` has no default and is evidence-bound.
33. Lambda environment contains no secret-value parameter.
34. Lambda permission is not public/wildcard.
35. runtime invoker is exact governed principal.
36. no AWS access-key resource/secret is created.

### Cross-stack and MATRIX-native invariants

37. signing/archive account identities are explicit.
38. root-store id is shared exactly.
39. database-instance id is shared exactly.
40. project/sport/protocol are fixed.
41. genesis remains sequence 1.
42. control/run do not partition S3 keys.
43. no template can set application admission booleans true.
44. no raw secret value appears in templates/tests/docs.
45. ambiguous S3 write outcome remains a runtime reconciliation responsibility.
46. manual key rotation is documented and requires ROOT_KEY_ROTATION.
47. CloudFormation replacement cannot silently count as key rotation.
48. one-account deployment cannot claim CONTROLLED_LIVE.
49. full tracked-secret scanner passes.
50. sealed R8.3R6 focused suite passes.
51. repository-native freshness/PostgreSQL regression family passes.
52. canonical full MATRIX CI passes.
53. repository remains clean and Git integrity passes.
54. no AWS network call occurs during template implementation/validation.

The implementation gate may add more cases but may not weaken these.

---

## 15. Template implementation artifacts expected next

The next gate is authorized to design/install only offline source artifacts such as:

- `infra/aws/r8_3r6/matrix-c2-eir-signer-stack.json`
- `infra/aws/r8_3r6/matrix-c2-eir-archive-stack.json`
- `tests/test_c2_r8_3r6_cloudformation_dual_stack.py`
- an implementation/evidence document

It is **not** authorized to:

- call AWS;
- install/use credentials;
- create a bucket;
- create a KMS key;
- create a Lambda;
- create IAM roles;
- incur cloud cost;
- choose retention days on the user's behalf.

---

## 16. Explicit non-claims after this design

This design does not prove:

- AWS accounts exist;
- the archive/signing accounts are actually independent;
- any S3 bucket exists;
- any KMS key exists;
- any Lambda exists;
- Object Lock Compliance is remotely active;
- conditional writes are remotely enforced;
- IAM least privilege is actually effective;
- a real machine invocation identity exists;
- authority-service code is implemented/deployed;
- real AWS latency is acceptable;
- real AWS outage/retry behavior is safe;
- remote policy downgrade attacks are blocked;
- deployed evidence survives administrative compromise;
- CONTROLLED_LIVE admission;
- provider execution;
- repeated polling;
- automatic wagering;
- production admission.

---

## 17. Authorization invariant after this design

- `CLOUD_BOOTSTRAP_DESIGN_AUTHORIZED=TRUE`
- `CLOUDFORMATION_DUAL_STACK_DECLARATIVE_DESIGN_COMPLETE=TRUE`
- `CLOUDFORMATION_TEMPLATES_IMPLEMENTED=FALSE`
- `CLOUD_BOOTSTRAP_RESOURCE_PROVISIONING_AUTHORIZED=FALSE`
- `REAL_AWS_NETWORK_EXECUTION_AUTHORIZED=FALSE`
- `REAL_CLOUD_CREDENTIALS_AUTHORIZED=FALSE`
- `RESOURCE_PROVISIONING_PERFORMED=FALSE`
- `COST_INCURRING_ACTION_AUTHORIZED=FALSE`
- `STRONG_AUTHORITY_OFFLINE_COMPONENTS_IMPLEMENTED=TRUE`
- `OFFLINE_IMPLEMENTATION_TECHNICALLY_AUDITED=TRUE`
- `STRONGER_EXTERNAL_AUTHORITY_IMPLEMENTED=FALSE`
- `REAL_EXTERNAL_AUTHORITY_PROVISIONED=FALSE`
- `CONTROLLED_LIVE_ADMISSIBLE=FALSE`
- `REAL_PROVIDER_EXECUTION_AUTHORIZED=FALSE`
- `REPEATED_REAL_PROVIDER_EXECUTION_AUTHORIZED=FALSE`
- `REPEATED_REAL_PROVIDER_POLLING_AUTHORIZED=FALSE`
- `AUTOMATIC_PROVIDER_SWITCH=FALSE`
- `AUTOMATIC_MODEL_PROMOTION=FALSE`
- `AUTOMATIC_WAGERING=FALSE`
- `PRODUCTION_ADMISSIBLE=FALSE`
- `MACROBLOCK_2_CLOSED=FALSE`
- `REMAINING_C2_LIVE_MACROBLOCKS=5`

---

## 18. Next gate

`R8_3R6_STRONG_EXTERNAL_AUTHORITY_CLOUDFORMATION_DUAL_STACK_TEMPLATE_IMPLEMENTATION_PREFLIGHT`

That next gate remains offline. It may validate source/tooling and prepare the exact
two-template implementation payload, but it may not provision AWS resources or read
cloud credential values.
