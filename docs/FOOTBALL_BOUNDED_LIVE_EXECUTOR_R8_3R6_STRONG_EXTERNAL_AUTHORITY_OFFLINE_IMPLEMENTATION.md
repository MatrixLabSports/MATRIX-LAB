# MATRIX C2 — R8.3R6 Strong External Authority Offline Implementation

## Status

**OFFLINE COMPONENT IMPLEMENTATION ONLY**

This implementation adds the provider-neutral external-authority port and the
offline AWS S3 Object Lock / KMS Ed25519 protocol adapter selected by the hardened
R8.3R6 architecture.

It does not provision or contact AWS, load cloud credentials, load a real signing
private key, authorize a sports provider, authorize repeated polling, or make the
strong authority CONTROLLED_LIVE-admissible.

## Baseline

Implementation parent:

`0ae8db99852f28d9ded20b0e759f4ac6f21d3a28`

The parent is the one-file authority-stream semantics hardening that aligned the
strong design with the sealed R8.3R6 protocol:

- genesis remains root sequence 1;
- the immutable archive is one global root-store/database stream;
- control/run identity remains inside signed receipts rather than creating
  independent object-key sequence spaces;
- `signer_key_id` remains the Ed25519 public-key fingerprint identity while the KMS
  ARN is a separate pinned deployment identity.

## New implementation surface

### `app/application/football/strong_external_authority.py`

Provides:

- `R83R6StrongExternalAuthorityPort`
  - provider-neutral runtime-checkable receipt-store contract;
  - exposes root-store identity, read, head and compare-and-append semantics;
  - contains no AWS request types in the port contract.

- `R83R6StrongAuthorityStreamIdentity`
  - binds project domain, sport, root-store, database instance, authority profile,
    archive account/bucket/region, authority-service identity, signing account,
    KMS key ARN and key epoch;
  - derives the canonical global S3 receipt prefix;
  - genesis key is sequence 1:
    `00000000000000000001.json`.

- `R83R6AwsS3ActivationEvidence`
  - requires Versioning `Enabled`;
  - requires Object Lock enabled;
  - requires default retention mode `COMPLIANCE`;
  - requires positive retention horizon;
  - requires conditional-write enforcement;
  - rejects runtime delete, retention administration and bucket-policy
    administration capabilities.

- `R83R6AwsKmsActivationEvidence`
  - requires `ECC_NIST_EDWARDS25519`;
  - requires `SIGN_VERIFY`;
  - requires `ED25519_SHA_512`;
  - requires enabled key state;
  - rejects exportable private material and runtime KMS administration.

- `R83R6OfflineAwsKmsEd25519SigningAuthority`
  - requires an injected transport explicitly marked `offline_only`;
  - constructs KMS `Sign` requests with `MessageType=RAW`;
  - verifies returned Ed25519 signatures using pinned raw public-key material;
  - never exposes a private key;
  - preserves canonical `ed25519:{sha256(raw_public_key)}` signer identity.

- `R83R6OfflineAwsStrongAuthorityAdapter`
  - requires an injected `offline_only` transport;
  - builds S3 `PutObject` with `IfNoneMatch="*"`;
  - derives a single global sequence namespace without control/run partitioning;
  - validates receipt project/sport/root/database/predecessor bindings;
  - performs read-after-write verification;
  - treats HTTP 412 as exact-idempotency check or fork rejection;
  - bounds HTTP 409/service retries;
  - reconciles ambiguous timeouts by reading the canonical object;
  - reconstructs the authoritative head only from a contiguous immutable sequence;
  - fails closed on namespace gaps, cross-database/root substitution and
    authorization failures;
  - deliberately reports:
    `controlled_live_admissible=False`;
  - deliberately reports:
    `stronger_external_authority_implemented=False`.

No boto3, botocore, requests, socket client or environment-secret loader is added.
No dependency file is changed.

## Dedicated test surface

`tests/test_c2_r8_3r6_strong_external_authority_offline_aws.py`

The dedicated suite covers 67 tests, including:

- stream identity and global namespace;
- genesis sequence 1;
- S3 Compliance/Object Lock/Versioning/conditional-write evidence;
- KMS Ed25519/sign-verify/non-exportable evidence;
- offline-only transport enforcement;
- exact KMS request and local public-key signature verification;
- exact S3 `If-None-Match` request construction;
- cross-project/sport/root/database rejection;
- read-after-write durability checks;
- 412 idempotency vs fork;
- bounded 409 retries;
- ambiguous timeout reconciliation;
- fail-closed authorization/service errors;
- contiguous head reconstruction and gap detection;
- predecessor-chain verification;
- compatibility with the sealed R8.3R6 `build_signed_receipt` structural contract;
- static absence of AWS SDK/network/secret-environment access;
- no premature CONTROLLED_LIVE or stronger-authority claim.

## Explicit non-claims

This implementation does not prove:

- any AWS resource exists;
- a bucket is actually WORM/Compliance configured;
- IAM separation exists;
- KMS is remotely provisioned;
- remote retention cannot be weakened;
- remote credentials are least-privilege;
- real-network retry/latency behavior;
- CONTROLLED_LIVE admission;
- real-provider execution;
- repeated polling;
- profitability;
- production admission.

Synthetic/offline activation evidence is only protocol-test input. It is not remote
deployment evidence.

## Required next gate

`R8_3R6_STRONG_EXTERNAL_AUTHORITY_OFFLINE_IMPLEMENTATION_INDEPENDENT_AUDIT`

That audit must independently challenge the new port/adapter and verify that no
network, credential or CONTROLLED_LIVE authority was introduced.

After an independent audit passes, the next architecture subgate may specify the
cloud bootstrap/deployment evidence and controlled external-authority activation
path. Those remain separate from sports-provider execution authorization.

## Authorization state after this implementation

- `STRONG_AUTHORITY_OFFLINE_COMPONENTS_IMPLEMENTED=TRUE`
- `STRONGER_EXTERNAL_AUTHORITY_IMPLEMENTED=FALSE`
- `REAL_EXTERNAL_AUTHORITY_PROVISIONED=FALSE`
- `REAL_AWS_NETWORK_EXECUTION_AUTHORIZED=FALSE`
- `REAL_CLOUD_CREDENTIALS_AUTHORIZED=FALSE`
- `CONTROLLED_LIVE_ADMISSIBLE=FALSE`
- `MACROBLOCK_2_CLOSED=FALSE`
- `REMAINING_C2_LIVE_MACROBLOCKS=5`
- `REAL_PROVIDER_EXECUTION_AUTHORIZED=FALSE`
- `REPEATED_REAL_PROVIDER_EXECUTION_AUTHORIZED=FALSE`
- `REPEATED_REAL_PROVIDER_POLLING_AUTHORIZED=FALSE`
- `AUTOMATIC_PROVIDER_SWITCH=FALSE`
- `AUTOMATIC_MODEL_PROMOTION=FALSE`
- `AUTOMATIC_WAGERING=FALSE`
- `PRODUCTION_ADMISSIBLE=FALSE`
