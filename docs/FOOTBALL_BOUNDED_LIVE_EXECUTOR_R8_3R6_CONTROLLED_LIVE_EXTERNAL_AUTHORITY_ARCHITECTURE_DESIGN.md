# MATRIX C2 — R8.3R6
## CONTROLLED_LIVE-Admissible External Authority Architecture Selection and Design

Status: **DESIGN SELECTED — IMPLEMENTATION NOT YET AUTHORIZED**

Macroblock: **2 — External Immutable Integrity Root**

The previously sealed `LOCAL_EXTERNAL_RESEARCH` profile remains valid for research,
but is not promoted or re-described as CONTROLLED_LIVE-admissible.

---

## 1. Decision

MATRIX selects the following reference architecture class for the first
CONTROLLED_LIVE-admissible external integrity authority:

`AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1`

The application-facing implementation MUST remain behind a provider-agnostic
external-authority port so a future equivalent backend can replace AWS without
changing the canonical receipt protocol.

This selection is an architecture decision only. It does not create or authorize:

- an AWS account or resource;
- network traffic;
- production credentials;
- a real signing key;
- sports-provider execution;
- repeated polling;
- automatic wagering;
- CONTROLLED_LIVE admission;
- production admission.

---

## 2. Why this architecture was selected

The local preflight rejected NTFS/local files, OneDrive sync, Git history and a
local TPM by itself as sufficient independent authorities.

The selected reference architecture combines:

1. **Remote immutable receipt authority**
   - Amazon S3 general-purpose bucket.
   - Versioning enabled.
   - S3 Object Lock enabled.
   - Time-based retention in **Compliance** mode.
   - Receipt creation by conditional `PutObject` with `If-None-Match: *`.
   - Bucket policy MUST enforce conditional writes on the protected receipt prefix.
   - Normal runtime MUST have no `DeleteObject`, retention-policy mutation,
     Object-Lock bypass, bucket-policy administration, or account-administration
     authority.

2. **Separate remote signing authority**
   - AWS KMS asymmetric Ed25519 key.
   - Key spec: `ECC_NIST_EDWARDS25519`.
   - Usage: `SIGN_VERIFY`.
   - Protocol v1 signing algorithm: `ED25519_SHA_512`, `MessageType=RAW`.
   - Private key MUST never be exportable to or persisted on the MATRIX host.
   - MATRIX stores/pins the public verification material and immutable key identity,
     never the private key.

3. **Authority service boundary**
   - The normal MATRIX runtime MUST NOT receive raw KMS administrative credentials.
   - The preferred strong profile uses a narrowly scoped remote authority service
     in a signer/security boundary that validates append semantics, invokes KMS
     signing and performs the conditional immutable write.
   - The normal MATRIX runtime receives only an invocation permission/token scoped
     to the authority protocol.
   - Infrastructure administration credentials MUST NOT be present on the MATRIX
     runtime host.

For the intended strong profile, the immutable archive boundary and signing/
authority boundary SHOULD be independently administered (preferably separate AWS
accounts or equivalently independent security boundaries). A one-account sandbox
may be used for research, but MUST NOT be labeled CONTROLLED_LIVE-admissible.

---

## 3. Official capability basis reviewed on 2026-08-25

The architecture decision is based on current official vendor documentation:

- Amazon S3 User Guide — "Locking objects with Object Lock":
  Object Lock implements WORM retention; Compliance mode prevents protected object
  versions from being overwritten or deleted during retention even by the AWS
  account root user.
  Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html

- Amazon S3 User Guide — "How to prevent object overwrites with conditional writes":
  `If-None-Match: *` permits creation only when the object key does not already
  exist; competing writes to the same key result in a precondition/conflict
  outcome.
  Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html

- Amazon S3 User Guide — "Enforce conditional writes on Amazon S3 buckets":
  bucket policy can require conditional-write headers for object creation.
  Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html

- Amazon S3 User Guide — "What is Amazon S3?":
  S3 provides strong read-after-write and list consistency. The documentation also
  warns that S3 does not itself provide a general cross-key object-locking
  transaction, therefore MATRIX MUST design fork prevention into its protocol.
  Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html

- AWS KMS Developer Guide — "Key spec reference":
  AWS KMS supports `ECC_NIST_EDWARDS25519` for signing/verification and the private
  key does not leave AWS KMS unencrypted.
  Source: https://docs.aws.amazon.com/kms/latest/developerguide/symm-asymm-choose-key-spec.html

These sources establish service capabilities only. They do not prove MATRIX's
future implementation or deployment is secure; that requires implementation,
configuration evidence and independent adversarial audit.

---

## 4. Trust model

### 4.1 Assets to protect

- canonical transition receipt history;
- authoritative sequence/predecessor relation;
- project/sport/database/root-store identity;
- signing authority identity;
- local transition journal binding;
- terminal/failed/abandoned outcomes;
- key-rotation history.

### 4.2 Threats this profile is designed to detect or prevent

Subject to correctly deployed independent authority boundaries:

- complete coherent replacement/rollback of local SQLite state;
- local re-authoring of an alternative history;
- deletion, reordering or mutation of historical external receipts;
- same-sequence fork attempts;
- cross-database/root-store/project/sport transplantation;
- silent replacement of a historical receipt;
- local removal of failed/abandoned outcomes;
- rollback behind an already authoritative remote receipt;
- loss/replacement of local coordination metadata;
- local theft of a non-existent plaintext private signing key.

### 4.3 Explicit non-claims

This design does NOT claim to prevent:

- simultaneous compromise of all independent cloud administrative boundaries;
- deliberate closure/destruction of the entire external provider account by an
  authority capable of doing so;
- malicious future events submitted by a fully compromised client if the remote
  authority's semantic policy legitimately permits those events;
- availability during a provider/network outage;
- correctness of sports data, models, prices or wagering decisions;
- profitability.

Availability failures MUST produce fail-closed behavior, not a silent downgrade.

---

## 5. Immutable stream identity

Every authority stream is uniquely bound to:

- `project_id`
- `sport = football`
- `protocol = matrix-eir`
- `protocol_version`
- `root_store_id`
- `database_instance_id`
- `control_id`
- optional `run_id` where applicable
- `authority_profile`
- `archive_account_id`
- `archive_bucket_arn`
- `authority_service_id`
- `signing_account_id`
- `kms_key_arn`
- `key_epoch`

No field above may be inferred from an untrusted receipt alone during admission.
Expected identities are pinned from governed configuration/evidence.

---

## 6. Immutable object namespace

Canonical receipt object key:

`matrix-eir/v1/{project_id}/football/{root_store_id}/{database_instance_id}/{control_id}/receipts/{sequence:020d}.json`

Rules:

- Genesis is sequence `00000000000000000000`.
- Every subsequent receipt is exactly predecessor sequence + 1.
- There is exactly one canonical object key per sequence.
- Receipt object creation MUST use `If-None-Match: *`.
- Bucket policy MUST reject unconditioned writes to the receipt prefix.
- A `412 Precondition Failed` is not blindly retried as success:
  MATRIX/authority reads the existing object and accepts only byte/hash-equivalent
  idempotency; otherwise it is a fork/conflict.
- A `409 Conflict` receives bounded protocol-defined retries and then fails closed.
- No mutable `HEAD` object is part of the trust root.
- Optional mutable caches/indexes may exist only as performance aids and are never
  authoritative.

The absence of a mutable authoritative head avoids making a rewriteable pointer the
root of trust.

---

## 7. Authoritative head derivation

The authoritative head is the highest **contiguous, cryptographically valid**
sequence reachable from genesis under the pinned stream identity.

Normal operation may cache the last verified sequence locally. On each append it
must verify the expected predecessor. On startup, rollback suspicion, local cache
loss, migration or audit, the implementation can reconstruct/advance the
authoritative head from the immutable stream.

A gap, unexpected object, invalid signature, wrong predecessor, wrong identity or
non-contiguous sequence is blocking evidence and MUST fail closed.

---

## 8. Receipt canonicalization and signing

The existing R8.3R6 canonical UTF-8/no-float/no-NaN/no-Infinity rules remain.

For the AWS strong profile:

1. construct canonical unsigned receipt bytes;
2. hash according to the canonical R8.3R6 receipt protocol;
3. remote authority validates identity, predecessor, sequence, operation id and
   admissible receipt type;
4. authority invokes AWS KMS Ed25519 signing using the exact governed key;
5. authority embeds signature metadata and verifies the resulting signed receipt;
6. authority conditionally creates the canonical S3 object;
7. authority re-reads/verifies the authoritative object before acknowledging.

KMS key ARN, key epoch and algorithm are part of signed/bound receipt metadata.

The normal MATRIX runtime never receives the private key.

---

## 9. Append and fork-control protocol

For append request `(stream, sequence=N, predecessor_hash=H, operation_id=O,
payload_digest=P)`:

1. remote authority resolves the pinned stream;
2. it verifies canonical predecessor `N-1` exists and is valid;
3. it verifies the predecessor hash equals `H`;
4. it rejects skipped sequence numbers;
5. it verifies operation-id/idempotency constraints;
6. it creates/signs the candidate receipt;
7. it writes only canonical key `N` with `If-None-Match: *`;
8. if write succeeds, it GETs and verifies canonical bytes/hash/signature;
9. if key already exists:
   - exact semantic/cryptographic match => idempotent success;
   - any conflict => fork rejection and incident evidence;
10. only then may the authority acknowledge the external receipt as authoritative.

S3's cross-key atomicity is NOT assumed.

---

## 10. R8.3R6 transition protocol mapping

The existing protocol remains:

`PREPARE -> LOCAL COMMIT -> EXTERNAL COMMIT -> LOCAL ACK`

### PREPARE
No local state transition may occur until authoritative remote
`ROOT_PREPARED` evidence exists.

### LOCAL COMMIT
The local journal transaction commits only after PREPARE is durable.

### EXTERNAL COMMIT
`ROOT_COMMITTED` binds the exact local event id/hash and the PREPARE receipt.

### LOCAL ACK
Local acknowledgement records the exact externally authoritative committed receipt.

Crash reconciliation semantics from the sealed research implementation remain
mandatory:

- crash after PREPARE / before local commit => authoritative abort reconciliation;
- local commit / before external COMMIT => further transitions blocked until
  finalize/reconcile;
- external COMMIT / before local ACK => ACK repaired from authoritative receipt.

---

## 11. No-silent-downgrade invariant

If the configured required profile is
`AWS_DUAL_BOUNDARY_S3_OBJECT_LOCK_COMPLIANCE_KMS_ED25519_V1`:

- failure to reach/verify the remote authority is blocking;
- missing credentials are blocking;
- wrong bucket/account/key identity is blocking;
- Object Lock policy not verified as required is blocking;
- conditional-write policy not verified is blocking;
- key/signing identity mismatch is blocking;
- the runtime MUST NOT fall back to `LOCAL_EXTERNAL_RESEARCH`;
- the runtime MUST NOT replace remote signing with an ephemeral/local key;
- the runtime MUST NOT continue new governed transitions offline.

Research-only operation may be separately launched under an explicit research
profile, but that is a different admission state and cannot inherit a
CONTROLLED_LIVE claim.

---

## 12. IAM / authority separation requirements

### MATRIX runtime identity

May receive only the minimum authority needed to invoke the remote authority
service and read non-secret public verification/configuration metadata.

It MUST NOT receive:

- AWS account/root credentials;
- IAM administration;
- KMS key administration;
- raw `kms:Sign` in the preferred strong profile;
- S3 bucket policy administration;
- S3 Object Lock configuration administration;
- delete rights over immutable receipts;
- retention-shortening/bypass rights.

### Authority service identity

May receive only:

- exact KMS sign permission for the governed key;
- exact read/conditional-create permissions for the governed immutable prefix;
- required metadata reads.

### Human/cloud administrator

Administrative bootstrap credentials are kept outside MATRIX runtime configuration
and are never committed to Git or evidence.

A deployment where one ordinary runtime credential can both rewrite infrastructure
policy and sign/write receipts is inadmissible.

---

## 13. Object Lock requirements

Activation evidence MUST prove:

- general-purpose S3 bucket;
- Versioning enabled;
- Object Lock enabled;
- time-based retention configured;
- retention mode = `COMPLIANCE`;
- retention policy is effective for every canonical receipt object;
- runtime cannot shorten/remove retention;
- runtime cannot delete protected receipts;
- conditional create is enforced for the canonical prefix;
- expected bucket ARN/account/region are pinned.

Retention duration is a governed deployment parameter and MUST cover the required
audit/rollback-detection horizon. The first real activation must explicitly approve
the duration; it is not silently chosen by application code.

---

## 14. Signing-key lifecycle

Mandatory lifecycle states:

`PROVISIONED -> ACTIVE -> ROTATING -> RETIRED -> VERIFY_ONLY`

Rules:

- private material never leaves KMS;
- public verification material is pinned and versioned;
- rotation requires signed `ROOT_KEY_ROTATION` evidence;
- current key authorizes transition to the new key;
- new key SHOULD co-sign activation proof;
- historical keys remain verifiable;
- key disable/deletion schedules are governed and cannot silently invalidate the
  evidence horizon;
- unexpected key state blocks new transitions;
- key recovery/change is an audited incident, not an automatic fallback.

---

## 15. Availability and retry contract

Network calls are bounded and measured.

Required classes:

- DNS/connect/TLS failure;
- authentication/authorization failure;
- throttling;
- `409` conditional conflict;
- `412` precondition/fork result;
- timeout after request may have committed;
- response loss after immutable write;
- KMS unavailable;
- S3 unavailable;
- partial authority-service failure.

Retries MUST be idempotent and bounded. An ambiguous timeout requires
read-after-write reconciliation using operation id, sequence and expected digest.

No unbounded retry loop is admissible.

---

## 16. Latency boundary

Remote authority adds latency to governed transitions. This design does not claim
that the latency is operationally acceptable for live decision timing.

The later empirical capture-interval / latency macroblock MUST measure:

- PREPARE p50/p95/p99;
- COMMIT p50/p95/p99;
- timeout/retry rate;
- reconciliation time;
- blocked-transition duration;
- effect on live decision windows.

Safety is not traded away to reduce latency. If measured latency is unacceptable,
architecture must be optimized without weakening external-authority guarantees.

---

## 17. Credential and secret rules

Forbidden in Git, SQLite, logs, reports, screenshots, test fixtures and generated
evidence:

- AWS secret access keys;
- session tokens;
- root credentials;
- KMS private key material;
- authority-service secrets.

Tests use fakes, emulators or ephemeral non-production credentials only.
No real cloud credential is authorized by this design commit.

---

## 18. Required implementation layers

Implementation is split into auditable subgates inside Macrobloque 2:

### A. Provider-neutral authority port
Contract/types/errors, canonical append request/result, reconciliation API.

### B. Offline AWS protocol adapter
Request construction, SigV4 boundary interface, S3/KMS response parsing and
policy/evidence validation, tested without network.

### C. Independent adversarial simulator
Concurrency, 409/412, rollback, truncation, fork, transplant, response loss,
credential loss, key rotation, policy downgrade.

### D. Cloud bootstrap specification
Infrastructure-as-code or equivalent declarative configuration for dual-boundary
archive/signer resources. No secrets in source.

### E. Controlled external-authority activation
Only after explicit human approval, real account preparation, least-privilege
credentials and a separate network gate. This activation concerns integrity
authority only; it does not authorize sports-provider execution.

### F. Independent remote audit
Must prove deployed immutability, key separation, conditional append behavior,
recovery, downgrade rejection and evidence preservation.

Macrobloque 2 closes only after the stronger profile is implemented and
independently audited to the required admission standard.

---

## 19. Minimum adversarial requirements for the strong profile

At minimum, independent tests/evidence must cover:

1. local DB rollback while remote history intact;
2. coherent local re-authoring;
3. protected remote receipt overwrite attempt;
4. protected remote receipt deletion attempt;
5. middle-receipt deletion/truncation attempt;
6. same-sequence concurrent writers;
7. conflicting `If-None-Match` result;
8. identical idempotent retry;
9. conflicting operation-id retry;
10. cross-database transplant;
11. cross-root-store transplant;
12. wrong archive account/bucket;
13. wrong signing account/key;
14. signer unavailable before PREPARE;
15. S3 unavailable before PREPARE;
16. local commit before external COMMIT;
17. external COMMIT before local ACK;
18. ambiguous timeout after successful remote write;
19. expired/denied invocation credential;
20. KMS key disabled;
21. valid key rotation;
22. forged key rotation;
23. attempted silent downgrade to local research profile;
24. retention-policy downgrade detection;
25. conditional-write-policy downgrade detection;
26. runtime credential cannot delete receipt;
27. runtime credential cannot change bucket policy/retention;
28. runtime credential cannot administer KMS;
29. secret scanner finds zero real credentials/private material;
30. network retry bound respected;
31. restart with lost local cache reconstructs remote authority;
32. full CI/regression preservation.

---

## 20. Promotion criteria

The strong profile may be considered for CONTROLLED_LIVE admission only when:

- provider-neutral port implemented;
- selected AWS strong adapter implemented;
- declarative cloud configuration reviewed;
- real external authority provisioned with explicit human approval;
- exact bucket/account/key/authority identities pinned;
- Object Lock Compliance verified;
- conditional writes verified/enforced;
- signer separation verified;
- no secret leakage;
- all strong-profile adversarial cases PASS;
- crash/retry/reconciliation evidence PASS;
- independent remote audit PASS;
- repository clean and canonical CI PASS;
- no broader authorization was implicitly granted.

Even then, this closes only the External Immutable Integrity Root macroblock.
Provider execution, repeated polling, empirical cadence/latency, risk admission and
automatic wagering remain separately governed.

---

## 21. Current authorization state

At this design stage:

- `R8_3R6_LOCAL_EXTERNAL_RESEARCH_SEALED=TRUE`
- `STRONGER_EXTERNAL_AUTHORITY_ARCHITECTURE_SELECTED=TRUE`
- `STRONGER_EXTERNAL_AUTHORITY_IMPLEMENTED=FALSE`
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

---

## 22. Next gate

`R8_3R6_STRONG_EXTERNAL_AUTHORITY_PROVIDER_NEUTRAL_PORT_AND_OFFLINE_AWS_ADAPTER_IMPLEMENTATION_PREFLIGHT`

This remains a subgate of Macrobloque 2. It does not increase the remaining
macrobloque count.
