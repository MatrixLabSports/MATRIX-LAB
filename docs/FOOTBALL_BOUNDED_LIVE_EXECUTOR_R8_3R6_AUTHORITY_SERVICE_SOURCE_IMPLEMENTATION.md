# MATRIX C2 — R8.3R6 Strong External Authority
## Authority Service Source Implementation

Status: **SOURCE IMPLEMENTATION ONLY — NO DEPLOYMENT PACKAGE / NO AWS EXECUTION**

Baseline design commit: `2ac5848c75f0d9362d2dd7f1d1eaaf48a2df383b`

Architecture:
`AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1`

Reference handler:
`authority_service.handler`

Lambda runtime contract: `python3.12`

## Implemented source boundary

The source implementation is confined to:
- `infra/aws/r8_3r6/authority_service/authority_service.py`
- `infra/aws/r8_3r6/authority_service/requirements.txt`
- `tests/test_c2_r8_3r6_authority_service_offline.py`
- this implementation document.

No `app/application` refactor is authorized or performed. The authority serializer is self-contained and is checked byte-for-byte against the six canonical R8.3R6 golden vectors produced by the implementation preflight.

## Dependency boundary

Direct deployment-package dependencies are pinned:
- `boto3==1.43.73`
- `botocore==1.43.73`
- `cryptography==50.0.0`

The source does not import Boto3/botocore at module import time. Real AWS client creation is lazy inside `build_real_service`. No dependency installation is performed by the source gate.

The later deployment-package gate must create the transitive hash lock, build in the Python 3.12 target runtime, inventory every file/version, produce SBOM-style evidence, scan secrets, and verify the final ZIP SHA-256 against `AuthorityCodeSha256`.

## Safety properties

The source:
- accepts only versioned `APPEND_RECEIPT`, `READ_HEAD`, and `READ_RECEIPT`;
- requires the `governed` Lambda alias and binds signing account/region to the configured KMS ARN;
- derives archive/KMS destinations only from pinned non-secret configuration;
- validates KMS Ed25519 identity and DER-SPKI→raw-32 fingerprint parity;
- signs only canonical UTF-8 unsigned receipt bytes with `ED25519_SHA_512`, `MessageType=RAW`;
- locally verifies every KMS-returned signature before S3 publication;
- assumes only the exact archive append role;
- writes only the canonical receipt sequence key with `IfNoneMatch="*"`;
- re-reads successful writes;
- reconciles 412/409/timeout/5xx ambiguity conservatively;
- uses application-owned bounded retries while real botocore clients are configured with `total_max_attempts=1`;
- re-checks the 5-second mutation/reconciliation reserve before **every** S3 `put_object` retry so a retry cannot begin after the Lambda time budget has fallen below the fail-closed reconciliation floor;
- reconstructs the head from a complete paginated immutable listing or fails closed;
- bounds receipt bodies and request/metadata JSON;
- derives genesis authority profile, `controlled_live_admissible=False`, and bootstrap public-key fields internally;
- derives `created_at` from the authority clock and rejects time regression;
- validates complete chain signature/predecessor/operation semantics before append;
- rejects ordinary runtime `ROOT_KEY_ROTATION`;
- `KEY_ROTATION_RUNTIME_ENABLEMENT=FALSE`;
- never logs the raw event, credentials, session tokens, raw exception text, or environment dumps;
- does not import or reuse sports-provider network permits or provider-secret surfaces.

Authority networking remains a separate future authority permit domain from all sports-provider networking.

## Test floor

The dedicated offline suite contains:
- 84 direct ASD-marker tests;
- 40 additional adversarial/hardening tests;
- total dedicated tests after independent-audit hardening: 124.

Independent Audit R1 exposed one real source defect: the mutation reconciliation reserve was checked before `_put_receipt()` entered its retry loop but was not re-checked before each subsequent mutating S3 attempt. Hardening moves a `mutation=True` time-budget guard inside every retry iteration and adds permanent regression tests for the structural placement plus 409, 5xx, and timeout retry paths. The R1 audit also contained three auditor-only defects (test-name counting plus two mutation-detector multiplicity errors); those belong to the corrected independent audit and are not source defects.

The implementation gate must also preserve:
- CloudFormation regression: 69 PASS;
- strong-authority focused regression: 264 PASS;
- native freshness/PostgreSQL focused regression: 83 PASS;
- canonical full MATRIX CI.

## Explicit non-claims

`AUTHORITY_SERVICE_SOURCE_IMPLEMENTATION_AUTHORIZED=TRUE`
`AUTHORITY_SERVICE_SOURCE_IMPLEMENTED=TRUE`
`DEPLOYMENT_PACKAGE_BUILD_AUTHORIZED=FALSE`
`DEPLOYMENT_PACKAGE_BUILT=FALSE`
`DEPENDENCY_INSTALLATION_PERFORMED=FALSE`
`REAL_AWS_NETWORK_EXECUTION_AUTHORIZED=FALSE`
`REAL_CLOUD_CREDENTIALS_AUTHORIZED=FALSE`
`RESOURCE_PROVISIONING_PERFORMED=FALSE`
`STRONGER_EXTERNAL_AUTHORITY_IMPLEMENTED=FALSE`
`CONTROLLED_LIVE_ADMISSIBLE=FALSE`
`MACROBLOCK_2_CLOSED=FALSE`
`REMAINING_C2_LIVE_MACROBLOCKS=5`
`PRODUCTION_ADMISSIBLE=FALSE`

Python 3.12 actual runtime execution remains unproven at this source-only gate and is mandatory at the later deployment-package gate.
