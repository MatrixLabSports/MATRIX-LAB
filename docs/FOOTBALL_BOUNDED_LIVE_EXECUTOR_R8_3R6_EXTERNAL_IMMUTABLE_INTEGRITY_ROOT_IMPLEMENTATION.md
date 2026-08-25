# MATRIX C2 — R8.3R6 External Immutable Integrity Root Implementation

## Status

**OFFLINE IMPLEMENTATION — LOCAL_EXTERNAL_RESEARCH**

This implementation introduces an external cryptographic integrity authority for the C2 football bounded-live control transition journal. It is intentionally not a CONTROLLED_LIVE-admissible backend and does not widen any provider, wagering, or production authorization.

## Baseline

- Implementation baseline HEAD: `4d422414f02509c54f93d7336035429747019e02`
- R8.3R6 design blob SHA-256: `ecac0347b9b181d758f0df163f5e23502cd2e9fc1091a7296941191af986da22`
- R8.3R6 preflight bundle SHA-256: `77cc2bfedf68e9e9fd640e6d5f92f5e30559b790301321b68ef065653c17c095`
- R8.3R6 preflight report SHA-256: `c7a9a6a343263e9515bb3c2e18dbfc28196bff01b899f9ff333b176577c95591`

## Implemented components

### 1. Control-ledger schema v87

The bounded football live-control SQLite schema advances from user version 86 to 87 and adds:

- `football_bounded_external_root_state`
- `football_bounded_external_root_coordination`

The database obtains a stable `database_instance_id`. Existing v86 ledgers migrate deterministically without fabricating external receipts. The new local coordination metadata is covered by the existing control-ledger integrity anchor but is not treated as the external trust root.

### 2. Transition preview and exact binding

The control store exposes deterministic transition-event preview/reference functions so an external PREPARE receipt can bind the exact transition event ID, event digest, sequence, state versions, run/control identity, outcome, cause, and chronology before the local transition is committed.

The committed local event must exactly match the prepared binding. A mismatch fails closed.

### 3. Canonical receipt protocol v1

The root protocol implements these receipt types:

- `ROOT_GENESIS`
- `ROOT_PREPARED`
- `ROOT_COMMITTED`
- `ROOT_ABORTED`
- `ROOT_KEY_ROTATION`

Receipts use canonical UTF-8 JSON, deterministic ordering, SHA-256 content digests, explicit project/sport/database/root-store identity binding, predecessor ID/SHA chaining, operation idempotency, and Ed25519 signatures over the complete unsigned receipt payload.

### 4. Ephemeral Ed25519 signing authority

The implementation includes an in-memory `EphemeralEd25519SigningAuthority` for offline research and tests.

It deliberately has no persistence API for private signing material. Private-key bytes are not written to SQLite, Git, reports, receipt metadata, or root-store files by this implementation.

A persistent governed secret provider is not implemented or authorized by this gate.

### 5. LOCAL_EXTERNAL_RESEARCH root store

`LocalDirectoryExternalIntegrityRootStore` stores canonical signed receipts and independent head-marker files outside the SQLite database.

The application API is append-only:

- canonical receipt files are exclusively created;
- historical receipt replacement is not supported;
- sequence and predecessor compare-and-append semantics are enforced;
- conflicting operation replay is rejected;
- receipt/head cardinality and naming are re-derived on read;
- root-store identity is stable and verified.

This backend's trust claim assumes the external directory authority is not rolled back or coherently rewritten by an attacker. It is therefore `LOCAL_EXTERNAL_RESEARCH`, not `CONTROLLED_LIVE_ADMISSIBLE`.

### 6. Explicit ROOT_GENESIS migration boundary

First activation creates a signed `ROOT_GENESIS` binding the current local critical snapshot, including the existing R8.3R5R1 transition history.

Genesis is explicitly a migration-time baseline. It does not claim that historical pre-genesis transitions were externally witnessed when they originally occurred.

### 7. Cross-boundary anchoring protocol

The coordinator implements the required sequence:

1. external `ROOT_PREPARED`;
2. exact local R8.3R5R1 transition commit plus local coordination record;
3. external `ROOT_COMMITTED`;
4. local acknowledgement of the exact final receipt.

Failed/abandoned transition attempts can also be rooted without advancing the mutable run state.

### 8. Crash recovery

Injection points cover:

- `AFTER_EXTERNAL_PREPARE`
- `AFTER_LOCAL_COMMIT`
- `AFTER_EXTERNAL_COMMIT`
- `AFTER_LOCAL_ACK`

Recovery behavior is deterministic:

- PREPARE with no local transition becomes append-only `ROOT_ABORTED`;
- local commit without external finalization is finalized idempotently;
- external COMMIT without local acknowledgement repairs acknowledgement only;
- fully durable operations replay without duplicating transition or root history.

### 9. Key continuity and rotation

Root verification begins from an explicit bootstrap trusted Ed25519 public key.

`ROOT_KEY_ROTATION` is signed by the current trusted key and includes the new key identity, public-key fingerprint, activation sequence, and proof of possession by the new key. Silent signer substitution and forged rotation fail closed.

## EIR01–EIR34 implementation evidence

The dedicated implementation tests cover all design cases EIR01 through EIR34, including:

- coherent old-DB rollback;
- complete local DB re-authoring with recomputed local integrity;
- forged unrooted local history;
- receipt mutation/deletion/reorder/duplication/fork;
- external truncation/older-prefix rollback under the declared store-head trust assumption;
- cross-control, cross-run, cross-database and cross-project/sport transplant;
- key-ID mutation, forged and valid rotation;
- unsupported/downgraded receipt schema;
- root-store substitution;
- clock rollback;
- unavailable external store;
- PREPARE/LOCAL-COMMIT/EXTERNAL-COMMIT crash recovery;
- idempotent and conflicting PREPARE/COMMIT replay;
- deleted local coordination metadata;
- hidden FAILED/ABANDONED and terminal transitions via DB rollback;
- missing signing key;
- private-key leakage checks.

## Security boundary and non-claims

This implementation closes the prior A19 limitation only under the declared assumption that the external root-store authority and trusted bootstrap signing identity remain intact while the local SQLite database is rolled back/replaced/re-authored.

It does **not** claim resistance to simultaneous compromise of:

- the complete local SQLite database;
- the external root directory/head history; and
- the trusted signing authority/bootstrap trust configuration.

It also does not establish:

- a hardware/WORM/remote immutable authority;
- durable production private-key management;
- CONTROLLED_LIVE admissibility;
- real-provider execution safety;
- repeated polling/retry safety;
- empirical capture cadence;
- profitability or wagering readiness;
- production admissibility.

## Authorization boundary

All remain FALSE / NOT AUTHORIZED:

- real-provider execution;
- repeated real-provider execution;
- repeated real-provider polling;
- automatic provider switching;
- automatic model promotion;
- automatic wagering;
- production admissibility.

## Required next gate

After the offline implementation commits successfully, R8.3R6 requires an **independent adversarial audit**. The Macrobloque 2 must not be declared closed merely because the LOCAL_EXTERNAL_RESEARCH implementation passes its own tests. A later trust-strengthening decision is still required before CONTROLLED_LIVE admission can rely on the external root.
