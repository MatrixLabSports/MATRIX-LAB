# MATRIX C2 — R8.3R6 Strong External Authority
## CloudFormation Dual-Stack Template Implementation

Status: **OFFLINE TEMPLATE IMPLEMENTATION — NO AWS PROVISIONING AUTHORIZED**

Baseline HEAD:

`b9f410f4d4e29d67b1195963c1de2b1a4abb58ca`

Declarative design SHA-256:

`7168437b827c17a9c37cae611059ac0a4beaf16ac26b6a61276525fd57922d3a`

Template implementation preflight bundle SHA-256:

`3c9c2bc33388c0ffa0b4200ea415ebcf6ebf45e3c4cb6fdab0684dfa9562a3e1`

Selected architecture:

`AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1`

---

## 1. Implemented artifacts

This gate installs exactly four offline source artifacts:

1. `infra/aws/r8_3r6/matrix-c2-eir-signer-stack.json`
2. `infra/aws/r8_3r6/matrix-c2-eir-archive-stack.json`
3. `tests/test_c2_r8_3r6_cloudformation_dual_stack.py`
4. this implementation document.

The templates are deterministic JSON and require no AWS CLI, Terraform, OpenTofu,
SAM, Docker, Node, npm or external YAML parser for offline validation.

No authority Lambda source code is implemented in this gate. The signer template
only defines the future deployment boundary and requires a versioned, externally
prepared S3 code artifact plus an independently governed SHA-256 parameter.

---

## 2. Critical compatibility finding retained

The current application-side
`R83R6StrongAuthorityStreamIdentity.archive_bucket_arn` contract accepts the
commercial partition form `arn:aws:s3:::`.

The templates use `${AWS::Partition}` for CloudFormation portability but explicitly
record:

`CommercialAwsPartitionRequiredForCurrentApplicationAdapter=true`

and output the actual partition.

Therefore this implementation **does not claim activation compatibility with
aws-us-gov or aws-cn**. Before activation, the remote provisioning preflight must
require `AWS::Partition=aws` unless the application adapter is separately extended,
tested and audited.

This restriction does not affect the offline protocol implementation or the current
commercial-AWS reference architecture.

---

## 3. Signer/security stack

The signer template defines:

- explicit signing account and region expectations;
- explicit archive account, region, bucket and append-role identity;
- `AWS::KMS::Key` with:
  - `ECC_NIST_EDWARDS25519`;
  - `SIGN_VERIFY`;
  - retained deletion/replacement lifecycle;
  - exact authority-service signing principal;
  - separate signer administration principal;
- Lambda execution role with:
  - only `sts:AssumeRole` on the exact archive append role;
  - exact CloudWatch log-stream write permission;
  - no direct S3 receipt permission;
  - no IAM or KMS administration;
- a separate `AWS::IAM::Policy` attached to that exact role after key creation with
  only `kms:Sign`, `kms:GetPublicKey`, `kms:DescribeKey` on the exact key;
- a future authority Lambda deployment boundary with:
  - versioned S3 code object;
  - independently supplied `AuthorityCodeSha256`;
  - non-secret identity configuration only;
  - reserved concurrency `1`;
  - governed published Lambda version and `governed` alias;
- resource-side Lambda invocation permission for the exact
  `AuthorityInvokerPrincipalArn`.

The external invoker still requires its own identity-side permission and governed
credential path. This template does not create an access key or other long-lived
credential.

The KMS key policy contains one signer-admin statement and one exact authority
service signing statement whose principal is the exact `AuthorityExecutionRole`
resource ARN. The KMS identity policy is attached as a separate
`AWS::IAM::Policy`; this deliberately breaks the otherwise circular dependency
between role creation and key creation. The `kms:*` administration grant belongs
only to the explicit signer administration principal; it is never granted to the
authority execution role or MATRIX runtime.

---

## 4. Archive stack

The archive template defines:

- explicit archive account and region expectations;
- exact signer account and signer authority role identity;
- an explicit archive append-role name;
- explicit `RetentionDays` with:
  - no default;
  - minimum one day;
  - no value chosen by MATRIX;
- S3 receipt bucket with:
  - Versioning `Enabled`;
  - Object Lock enabled;
  - default Object Lock `COMPLIANCE`;
  - retention days bound to the explicit human-approved parameter;
  - full Public Access Block;
  - `BucketOwnerEnforced`;
  - explicit AES-256 server-side encryption;
  - `DeletionPolicy: Retain`;
  - `UpdateReplacePolicy: Retain`;
- exact archive append role with:
  - conditional `s3:PutObject`;
  - receipt reads;
  - exact-prefix listing;
  - read-only archive configuration evidence;
  - no delete, policy, versioning or retention administration;
- bucket policy defense in depth:
  - deny non-TLS;
  - deny receipt `PutObject` when `s3:if-none-match` is absent;
  - deny receipt delete/delete-version;
  - deny receipt retention/legal-hold mutation.

The v1 role opens no copy or multipart-specific alternate creation permission.
The protected namespace is:

`matrix-eir/v1/matrix.c2/football/{root_store_id}/{database_instance_id}/receipts/`

Genesis remains sequence `1`:

`00000000000000000001.json`

`control_id` and `run_id` remain signed receipt fields and do not partition the S3
stream.

---

## 5. Conditional-write semantics

The application-side offline adapter already constructs receipt writes with:

`IfNoneMatch = "*"`

The bucket policy requires the `s3:if-none-match` condition to be present for
protected `PutObject` requests. S3 validates the header; the application protocol
requires the `*` value.

An ambiguous S3 write outcome remains a runtime reconciliation responsibility:

1. do not assume a timeout proves failure;
2. read the canonical sequence key;
3. exact receipt equivalence is idempotent success/reconciliation;
4. conflicting receipt is a fork incident;
5. absent receipt permits only bounded retry;
6. no unbounded retry is permitted.

The templates do not create a mutable authoritative HEAD object.

---

## 6. Manual asymmetric key rotation

Automatic/on-demand KMS material rotation is not used for this asymmetric signing
key.

A MATRIX signing transition requires a new KMS key/key epoch and signed
`ROOT_KEY_ROTATION` protocol evidence.

**CloudFormation replacement is not a valid key rotation event.**

Historical verification material must remain available for every receipt inside the
governed evidence horizon.

---

## 7. Parameter versus deployed-environment evidence

CloudFormation parameter values such as `SigningAccountId`, `SigningRegion`,
`ArchiveAccountId` and `ArchiveRegion` are expected identities, not proof.

The templates separately output actual:

- `AWS::AccountId`;
- `AWS::Region`;
- `AWS::Partition`.

Before any remote activation, an external evidence gate must reject mismatches
between expected parameters and actual deployed identities.

Likewise, `AuthorityCodeSha256` binds the intended code artifact to stack
configuration but CloudFormation alone does not prove the bytes in the referenced
S3 object have that digest. The future package/provisioning gate must hash the
actual code artifact before stack creation and later verify deployed code identity.

---

## 8. One-account sandbox boundary

Both templates hard-code outputs:

- `ResearchSandboxOnly = TRUE`
- `ControlledLiveAdmissible = FALSE`
- `ProductionAdmissible = FALSE`

No parameter can turn those values true.

A one-account deployment, if ever separately authorized, is research-only and
cannot claim CONTROLLED_LIVE admission.

A future admission candidate must independently prove archive/signing
administrative separation.

---

## 9. Human approvals remain mandatory

Template implementation does not satisfy any of:

1. `HUMAN_APPROVE_ARCHIVE_ACCOUNT_AND_REGION`
2. `HUMAN_APPROVE_SIGNING_ACCOUNT_AND_REGION`
3. `HUMAN_APPROVE_RETENTION_DURATION`
4. `HUMAN_APPROVE_RESOURCE_NAMES_AND_EXPECTED_COST`
5. `HUMAN_ACKNOWLEDGE_COMPLIANCE_RETENTION_IRREVERSIBILITY`
6. `HUMAN_AUTHORIZE_FIRST_AWS_NETWORK_CALL`
7. `HUMAN_AUTHORIZE_FIRST_RESOURCE_CREATION`

No retention period is selected by this implementation.

---

## 10. Offline validation scope

Dedicated validation covers at least the original 54 design requirements plus
additional checks for:

- exact authority role/log/KMS boundaries;
- no direct S3 permission in the signer runtime;
- exact alias-qualified invocation;
- no credential-producing resources;
- actual-versus-expected account/region evidence outputs;
- current commercial-partition activation restriction;
- deny-only bucket resource policy;
- no wildcard authority actions;
- manual key-rotation semantics;
- human approval gates;
- closed admission state.

Independent audit is still required after implementation.

---

## 11. Explicit non-claims

These JSON templates do not prove:

- CloudFormation accepts them in a real account;
- required service quotas are available;
- resource names are unused;
- the selected retention duration is appropriate;
- the account/region parameters equal the real deployment context;
- the two administrative boundaries are truly independent;
- the future Lambda package is safe or even implemented;
- the supplied Lambda package SHA equals remote bytes;
- Object Lock/Versioning/Compliance are actually active remotely;
- effective IAM permissions match intended policy;
- conditional writes work against a real S3 bucket;
- KMS signing works against a real key;
- real retries, timeouts or latency are acceptable;
- remote rollback/policy downgrade attacks are defeated;
- real authority activation;
- CONTROLLED_LIVE admission;
- provider execution;
- repeated polling;
- automated wagering;
- production admission.

Those claims require later explicit human authorization, remote evidence and
independent adversarial audit.

---

## 12. Authorization invariant

`CLOUDFORMATION_TEMPLATES_IMPLEMENTED=TRUE`
`CLOUDFORMATION_TEMPLATES_OFFLINE_VALIDATED=TRUE`
`AUTHORITY_LAMBDA_SOURCE_IMPLEMENTATION_AUTHORIZED=FALSE`
`AUTHORITY_LAMBDA_SOURCE_IMPLEMENTED=FALSE`
`CLOUD_BOOTSTRAP_RESOURCE_PROVISIONING_AUTHORIZED=FALSE`
`REAL_AWS_NETWORK_EXECUTION_AUTHORIZED=FALSE`
`REAL_CLOUD_CREDENTIALS_AUTHORIZED=FALSE`
`RESOURCE_PROVISIONING_PERFORMED=FALSE`
`COST_INCURRING_ACTION_AUTHORIZED=FALSE`
`STRONGER_EXTERNAL_AUTHORITY_IMPLEMENTED=FALSE`
`REAL_EXTERNAL_AUTHORITY_PROVISIONED=FALSE`
`CONTROLLED_LIVE_ADMISSIBLE=FALSE`
`REAL_PROVIDER_EXECUTION_AUTHORIZED=FALSE`
`REPEATED_REAL_PROVIDER_EXECUTION_AUTHORIZED=FALSE`
`REPEATED_REAL_PROVIDER_POLLING_AUTHORIZED=FALSE`
`AUTOMATIC_PROVIDER_SWITCH=FALSE`
`AUTOMATIC_MODEL_PROMOTION=FALSE`
`AUTOMATIC_WAGERING=FALSE`
`PRODUCTION_ADMISSIBLE=FALSE`
`MACROBLOCK_2_CLOSED=FALSE`
`REMAINING_C2_LIVE_MACROBLOCKS=5`

---

## 13. Next gate after independent implementation audit

The immediate next step after this implementation is an **offline independent
adversarial audit of the CloudFormation template pair**.

No AWS provisioning or cloud credential use is authorized until that independent
audit closes and the later human-approved provisioning preflight is explicitly
opened.
