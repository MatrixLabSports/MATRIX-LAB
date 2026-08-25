# MATRIX C2 — R8.3R6 External Immutable Integrity Root

## Design and Adversarial Specification

### Gate status

**DESIGN ONLY — NO RUNTIME IMPLEMENTATION IN THIS GATE**

This specification is bound to:

- Branch: `integration/c2-private-live-foundation`
- Sealed R8.3R5R1 HEAD: `581f69ff8c7115fac05d4a2e64c57ddbefc4589f`
- R8.3R5R1 seal report SHA-256: `23adcd55356982153f477bac4ad50d70d5195770ef4272c1a3662f2a2c39a9c6`
- R8.3R5R1 seal-document SHA-256: `e41245c1e044d43a0b01e60e3a12793a4c016e0274279e8148785856bc0ce44b`

R8.3R6 addresses the exact A19 limitation retained by the sealed R8.3R5R1 gate: a complete replacement or coherent re-authoring of the local SQLite control/journal database can preserve all local hashes and therefore cannot be detected by local evidence alone.

## 1. Objective

Introduce a cryptographically authenticated integrity root outside the mutable SQLite database trust boundary so that MATRIX can detect rollback, replacement, or coherent re-authoring of the complete local control/transition database when the external-root trust authority remains intact.

The external root must anchor the durable transition history without becoming a second mutable copy of the same trust domain.

R8.3R6 must close the following statement:

> If the local database is replaced by a different internally coherent database, but the independently maintained external integrity authority is not compromised, startup/resume validation must fail closed.

## 2. Security claim and trust boundary

The R8.3R6 security claim is intentionally scoped.

Protected boundary:

- local SQLite control/run state;
- R8.3R5/R8.3R5R1 transition-event history;
- local transition integrity chain;
- complete local-database rollback or replacement;
- coherent recomputation of local hashes after database re-authoring.

Trusted external authority:

- external receipt history;
- external receipt monotonic head;
- active signing-key continuity;
- external store identity;
- configured bootstrap trust identity.

The design does **not** claim protection if an attacker simultaneously compromises:

1. the complete local database;
2. the external immutable-root history or authoritative monotonic head; and
3. the active signing authority or an equivalent trusted root credential.

That whole-authority compromise is outside the R8.3R6 claim and must remain explicit.

## 3. Meaning of “external” and “immutable”

“External” means outside the SQLite database and outside any local integrity field that can be recomputed solely by rewriting that database.

“Immutable” means append-only and rollback-resistant within the declared root-store trust boundary. At minimum, the admissible root-store contract must provide:

- historical receipts are never updated in normal operation;
- historical receipts are never deleted by the runtime API;
- monotonic sequence advancement;
- predecessor-hash compare-and-append semantics;
- idempotent operation identity;
- deterministic readback;
- durable persistence before acknowledgement;
- rejection of divergent forks at the same sequence/predecessor;
- an authoritative latest-head mechanism that cannot silently move backward within the stated trust boundary.

A plain writable file that the same runtime can freely truncate, replace, or rewrite is **not sufficient by itself** to justify an “immutable” claim.

A filesystem-backed implementation may be used for research/testing only if its limitations are explicitly labeled. Promotion must be based on the exact trust properties demonstrated by the chosen backend, not by its filename or location.

## 4. High-level architecture

R8.3R6 consists of five logical components:

1. **Local durable transition journal** — the sealed R8.3R5R1 source of detailed transition evidence.
2. **Root coordinator** — constructs canonical root operations and reconciles cross-boundary crash states.
3. **External root store** — append-only receipt authority outside SQLite.
4. **Signing authority** — signs root receipts using a private key not stored in the SQLite database or Git repository.
5. **Verifier/recovery gate** — validates receipt chain, signatures, local/external correspondence, monotonic head, and crash recovery before resume.

The root coordinator must not bypass or weaken any existing R8.3R5R1 transition invariant.

## 5. Ledger and installation identity

Every rooted ledger must be bound to stable identities that prevent transplantation.

Required identities:

- project/domain identifier;
- sport identifier (`football`);
- C2 root protocol identifier;
- ledger/database instance ID;
- control ID;
- run ID where applicable;
- transition event ID;
- transition event SHA-256;
- external root-store ID;
- signing-key ID;
- root protocol/schema version.

The database-instance identity must survive ordinary reopen/restart but must not be silently regenerated when an existing database is present.

A copied receipt from another installation, sport, control, run, or database instance must not validate.

## 6. Canonical receipt schema

Every external receipt record must contain, at minimum:

- receipt ID;
- root sequence number;
- previous receipt ID;
- previous receipt SHA-256;
- receipt type;
- operation/correlation ID;
- project/domain ID;
- sport ID;
- ledger/database instance ID;
- control ID;
- run ID where applicable;
- local transition event ID where applicable;
- local transition event SHA-256 where applicable;
- local transition sequence where applicable;
- local control state version where applicable;
- local schema/user version;
- receipt protocol/schema version;
- created-at timestamp;
- signer key ID;
- canonical payload SHA-256;
- signature;
- root-store ID.

Receipt types must include at least:

- `ROOT_GENESIS`
- `ROOT_PREPARED`
- `ROOT_COMMITTED`
- `ROOT_ABORTED`
- `ROOT_KEY_ROTATION`

Additional types require explicit versioned semantics.

## 7. Canonical serialization and cryptography

The cryptographic representation must be deterministic.

Requirements:

- UTF-8 canonical encoding;
- deterministic key ordering;
- no floating-point values in signed payloads;
- no NaN/Infinity representations;
- normalized integer/string/boolean/null semantics;
- domain separation string identifying MATRIX C2 R8.3R6;
- SHA-256 for content digests unless a stronger approved digest is justified;
- Ed25519 is the preferred signing primitive for the first implementation because deterministic signing and verification are well supported by the installed cryptography stack.

The signature must cover the complete canonical payload, including predecessor binding and identity fields.

A signature over only the local event hash is insufficient.

## 8. Signing-key requirements

The private signing key:

- must not be stored in SQLite;
- must not be committed to Git;
- must not appear in logs, reports, exceptions, screenshots, or test fixtures;
- must never be printed by installers or auditors;
- must have a stable key ID/fingerprint;
- must be loadable through an explicit governed secret-provider boundary;
- must fail closed if unavailable for a transition that requires external anchoring.

Tests must use ephemeral test keys generated inside isolated test directories or memory.

Real secret material is not authorized in the design or offline implementation-preflight gates.

## 9. Root genesis and migration anchor

R8.3R6 cannot pretend that pre-R8.3R6 external receipts already existed.

At first activation, the system must create an explicit `ROOT_GENESIS` receipt that binds the current sealed local state.

The genesis payload must include a deterministic digest of the current critical ledger snapshot, including at minimum:

- database instance ID;
- relevant SQLite user version;
- ordered durable transition-event identities/hashes or an equivalent deterministic aggregate;
- current run/control durable state identities and versions;
- current R8.3R5R1 transition-head information;
- current local anchor/integrity metadata where applicable.

`ROOT_GENESIS` is a migration-time integrity baseline, not evidence that pre-genesis transitions were externally observed when they occurred.

That distinction must remain explicit in reports and audit output.

## 10. Two-phase external anchoring protocol

A transition that requires external anchoring must use a crash-safe cross-boundary protocol.

Preferred protocol:

### Phase A — external PREPARE

1. validate current local and external heads;
2. construct the proposed local transition event;
3. construct a deterministic root operation ID;
4. append `ROOT_PREPARED` externally using compare-and-append against the exact current external head;
5. durably receive the prepared receipt identity/digest.

### Phase B — local COMMIT

6. begin the existing SQLite transaction;
7. append the local R8.3R5R1 transition event;
8. apply the corresponding local state mutation or non-committed outcome evidence;
9. persist the external operation identity/prepared receipt binding;
10. commit SQLite atomically.

### Phase C — external FINALIZE

11. append `ROOT_COMMITTED` externally, referencing both the prepared receipt and exact committed local transition event hash;
12. receive the committed external receipt identity/digest.

### Phase D — local ACK

13. persist local acknowledgement of the exact committed external receipt;
14. acknowledge the transition to the caller only after reconciliation rules are satisfied.

The implementation may use an equivalent protocol only if it proves the same or stronger crash and rollback properties.

## 11. Why PREPARE occurs before local commit

If the local transaction were committed first and the machine crashed before any external evidence existed, an attacker could replace the local database during that unanchored interval.

An external PREPARE creates durable evidence that an operation was expected before the local mutation becomes authoritative.

A PREPARE that never becomes a local commit must never be deleted. It must be resolved by a durable `ROOT_ABORTED` record or equivalent append-only terminal evidence.

## 12. Crash/restart recovery state machine

Recovery must deterministically handle at least:

### Crash before external PREPARE

No external or local transition exists.

Expected: normal prior state.

### Crash after PREPARE before local transaction commit

External PREPARE exists; local transition does not.

Expected: append `ROOT_ABORTED` after proving absence of the matching local transition. No phantom local transition may be invented.

### Crash after local commit before external COMMIT

External PREPARE exists; matching local transition exists; final external receipt is absent.

Expected: fail normal resume until deterministic idempotent finalization appends the matching `ROOT_COMMITTED`.

### Crash after external COMMIT before local ACK

External COMMIT and local transition both exist; local acknowledgement is stale/missing.

Expected: verify exact correspondence and idempotently repair only the acknowledgement metadata. Historical receipts/events are never rewritten.

### Crash after local ACK before caller acknowledgement

All durable evidence is complete.

Expected: retry returns the same committed result without duplicating the transition or external root operation.

## 13. Startup/resume admission

Before any resume or new rooted transition, the verifier must:

1. validate supported local schema;
2. validate R8.3R5R1 local transition integrity;
3. validate external receipt schema;
4. validate receipt signatures and key continuity;
5. validate receipt sequence/predecessor chain;
6. validate root-store ID and ledger/database identity;
7. determine the authoritative external head;
8. reconcile unresolved PREPARE operations;
9. compare finalized external root evidence with the local transition history;
10. reject local rollback, replacement, missing rooted history, or unexplained extra history;
11. reject external rollback/truncation when the backend trust contract exposes it;
12. admit resume only when local and external histories are mutually complete.

No “best effort” resume is allowed after integrity uncertainty.

## 14. Local coordination metadata

The SQLite side may maintain a root-coordination/outbox table, but that table is not itself the trust root.

It may contain:

- operation ID;
- transition event ID/hash;
- prepared external receipt ID/hash;
- committed external receipt ID/hash;
- coordination status;
- retry count;
- timestamps;
- schema version.

Deleting or rewriting this local coordination table must not be enough to make external evidence disappear.

External receipts remain authoritative for proving that an anchoring operation existed.

## 15. Idempotency and fork prevention

The external store must enforce deterministic idempotency.

For the same operation ID:

- same canonical payload -> idempotent replay is allowed;
- different canonical payload -> **REJECTED**.

For the same predecessor/root sequence:

- only one admissible successor may become authoritative;
- a competing successor is a fork and must be **REJECTED**.

Concurrent transition attempts must serialize through a compare-and-append/CAS boundary or equivalent mutually exclusive root coordinator.

## 16. Key rotation

Key rotation is part of the integrity chain, not an out-of-band silent configuration change.

A valid `ROOT_KEY_ROTATION` receipt must:

- be signed by the currently trusted key;
- identify the current key ID;
- identify the new public-key fingerprint/key ID;
- identify the activation sequence;
- be bound to the exact prior external receipt;
- preferably be co-signed by the new key as proof of possession.

After activation, receipts signed by an untrusted or retired key are rejected unless a versioned recovery policy explicitly permits them.

A forged rotation or silent key substitution is **REJECTED**.

## 17. Backend trust profiles

The implementation must label the active backend profile.

### TEST_ONLY

Examples: in-memory root store, temporary directory, unrestricted local file.

May prove protocol semantics but does not justify a durable immutability claim.

### LOCAL_EXTERNAL_RESEARCH

External to SQLite and signed, with append-only application API and explicit local-machine trust assumptions.

May close A19 against database-only replacement while the external store/signing authority remains intact.

Must not claim resistance to full-machine/root-authority compromise.

### CONTROLLED_LIVE_ADMISSIBLE

Must demonstrate stronger rollback/deletion resistance suitable for the later CONTROLLED_LIVE admission gate, such as an independently protected append-only/WORM authority, remote immutable log, hardware-backed monotonic authority, or another reviewed equivalent.

R8.3R6 must record which profile has actually been implemented and tested.

## 18. External-store unavailability

If the external root authority is unavailable:

- startup may perform read-only diagnostics when safe;
- no transition requiring a new root may be acknowledged as fully committed;
- no unresolved integrity discrepancy may be ignored;
- repeated blind retries are not authorized by this gate;
- real-provider execution remains disabled.

The exact timeout/retry policy belongs to later execution-safety gates unless required for deterministic single-operation recovery.

## 19. Required adversarial harness

The R8.3R6 implementation and independent audit must cover at least the following.

### EIR01 — Old coherent DB rollback

Restore an older internally valid database while retaining the newer external root history.

Expected: **REJECTED**.

### EIR02 — Coherently re-authored DB

Rewrite the complete database and recompute all local hashes so local validation passes.

Expected: external-root mismatch -> **REJECTED**.

### EIR03 — Forged new local history without receipt

Create a coherent new local transition sequence with no matching external receipt.

Expected: **REJECTED**.

### EIR04 — Mutate external receipt payload

Change one signed receipt field.

Expected: signature/digest validation -> **REJECTED**.

### EIR05 — Delete middle external receipt

Remove one receipt from the external chain.

Expected: sequence/predecessor gap -> **REJECTED**.

### EIR06 — Reorder external receipts

Swap two receipts.

Expected: **REJECTED**.

### EIR07 — Duplicate external receipt

Duplicate a valid receipt.

Expected: exact idempotent read semantics only; duplicated historical position -> **REJECTED**.

### EIR08 — Fork same predecessor

Create two different successors from one predecessor/root sequence.

Expected: **REJECTED**.

### EIR09 — Truncate external history

Remove the newest receipts.

Expected: backend anti-rollback/head validation -> **REJECTED** within the declared backend trust profile.

### EIR10 — Replace external history with older valid signed prefix

Present an older cryptographically valid receipt prefix.

Expected: authoritative-head rollback detection -> **REJECTED** for a backend claiming rollback resistance.

### EIR11 — Cross-control receipt transplant

Copy a valid receipt to another control identity.

Expected: **REJECTED**.

### EIR12 — Cross-run receipt transplant

Copy a valid run-bound receipt to another run.

Expected: **REJECTED**.

### EIR13 — Cross-database-instance transplant

Copy a valid receipt to a different ledger/database instance.

Expected: **REJECTED**.

### EIR14 — Cross-project/sport transplant

Reuse a valid receipt outside MATRIX C2 football.

Expected: **REJECTED**.

### EIR15 — Signing-key ID mutation

Change the key identifier or public-key fingerprint binding.

Expected: **REJECTED**.

### EIR16 — Forged key rotation

Attempt to activate a new key without valid continuity from the trusted key.

Expected: **REJECTED**.

### EIR17 — Valid key rotation

Perform the governed signed rotation.

Expected: **PASS**.

### EIR18 — Unsupported receipt schema

Use a future/unknown receipt protocol version.

Expected: **REJECTED**.

### EIR19 — Receipt schema downgrade

Present old semantics against a newer rooted history.

Expected: **REJECTED**.

### EIR20 — Root-store identity substitution

Point the verifier at another valid external store.

Expected: **REJECTED**.

### EIR21 — Clock rollback

Move system time backward while sequences and signed predecessor bindings remain authoritative.

Expected: clock manipulation cannot create a valid history fork; invalid chronology -> **REJECTED** where applicable.

### EIR22 — External store unavailable before PREPARE

No PREPARE can be durably created.

Expected: local transition is not admitted as externally anchored; fail closed.

### EIR23 — Crash after PREPARE before local commit

Expected: no phantom local transition; append-only ABORT recovery.

### EIR24 — Crash after local commit before external COMMIT

Expected: normal resume blocked until deterministic matching finalization succeeds.

### EIR25 — Crash after external COMMIT before local ACK

Expected: idempotent local acknowledgement reconciliation.

### EIR26 — Duplicate PREPARE replay

Replay identical PREPARE with the same operation ID.

Expected: idempotent same receipt/result; no duplicate root history.

### EIR27 — Conflicting PREPARE replay

Same operation ID with different payload.

Expected: **REJECTED**.

### EIR28 — Duplicate COMMIT replay

Retry identical finalization.

Expected: idempotent same committed receipt/result.

### EIR29 — Conflicting COMMIT replay

Same operation ID but different transition hash/final payload.

Expected: **REJECTED**.

### EIR30 — Delete local root-coordination metadata

Erase the local outbox/ack record while external PREPARE/COMMIT evidence remains.

Expected: external reconciliation exposes discrepancy; no silent acceptance.

### EIR31 — Hide FAILED/ABANDONED transition via DB replacement

Restore/re-author a database that omits a previously externally rooted `STATE_TRANSITION_FAILED` or `STATE_TRANSITION_ABANDONED` event.

Expected: **REJECTED**.

### EIR32 — Hide committed terminal stop via DB rollback

Restore a database from before an externally rooted terminal transition.

Expected: **REJECTED**.

### EIR33 — Signing key unavailable

Required signing authority cannot be loaded.

Expected: new rooted transition fails closed; secret value is never printed/read into audit evidence.

### EIR34 — Secret-leak audit

Search reports, logs, committed files, exceptions, and test artifacts for private-key material or secret values.

Expected: zero secret-value exposure.

## 20. Required test layers

R8.3R6 cannot be closed on unit tests alone.

Required:

1. canonical serialization tests;
2. receipt signature tests;
3. receipt-chain tests;
4. root-store CAS/fork tests;
5. genesis/migration tests;
6. local/external reconciliation tests;
7. database replacement/rollback tests;
8. two-phase crash-injection tests;
9. idempotency tests;
10. concurrency tests;
11. key-rotation tests;
12. store-identity/transplant tests;
13. schema version/downgrade tests;
14. R8.3R5R1 regression;
15. R8.3R4 regression;
16. canonical full MATRIX CI;
17. independent read-only adversarial audit.

## 21. Evidence requirements

The implementation gate must seal:

- exact design/preflight baseline HEAD;
- exact root protocol version;
- exact receipt schema;
- backend trust profile;
- external store identity rules;
- signing algorithm and public-key fingerprint semantics;
- proof that private-key bytes are absent from committed/evidence artifacts;
- local schema/user-version before and after;
- exact payload SHA-256 values;
- EIR01–EIR34 outcomes;
- crash-boundary outcomes;
- test counts;
- canonical CI;
- network-attempt count;
- resulting commit;
- committed blob hashes;
- Git integrity;
- repository cleanliness;
- authorization state;
- report SHA-256 + sidecar.

## 22. Promotion criteria

R8.3R6 can be technically closed only if:

- the chosen backend trust profile is explicitly declared;
- `ROOT_GENESIS` is deterministic and does not fabricate pre-genesis observation;
- every transition class required by R8.3R5R1 is externally anchorable;
- receipt signatures and chain validation are executable, not documentary;
- complete local DB rollback/replacement is rejected under the declared external-root trust assumption;
- crash recovery is deterministic at PREPARE/LOCAL COMMIT/EXTERNAL COMMIT/ACK boundaries;
- forks and conflicting idempotent retries are rejected;
- private signing material is absent from Git/evidence;
- EIR01–EIR34 have explicit evidence;
- R8.3R5R1 remains regression-clean;
- full MATRIX CI passes;
- independent audit passes;
- repository is clean;
- no real-provider or wagering permission is widened.

## 23. Explicit non-claims

R8.3R6 does not by itself prove:

- resistance to simultaneous compromise of database + root authority + signing authority;
- real-provider execution safety;
- repeated polling safety;
- retry/backoff production behavior;
- empirical capture cadence;
- live latency suitability;
- profitability;
- wagering readiness;
- CONTROLLED_LIVE admission;
- production admissibility.

A weaker research backend must never be described as CONTROLLED_LIVE-admissible merely because protocol tests pass.

## 24. Authorization boundary

Throughout design, preflight, implementation, and audit:

- Real-provider execution: **NOT AUTHORIZED**
- Repeated real-provider execution: **NOT AUTHORIZED**
- Repeated real-provider polling: **NOT AUTHORIZED**
- Automatic provider switching: **NOT AUTHORIZED**
- Automatic model promotion: **NOT AUTHORIZED**
- Automatic wagering: **NOT AUTHORIZED**
- Production admissibility: **FALSE**

No real provider key is required or read by this design gate.

## 25. Next gate after this specification

**R8.3R6 — READ-ONLY EXTERNAL IMMUTABLE INTEGRITY ROOT IMPLEMENTATION PREFLIGHT**

The preflight must inspect the committed control/journal architecture, cryptography availability, schema migration surface, candidate trust-store boundaries, and exact implementation touch points without modifying runtime code or databases.

Only after preflight evidence is sealed may an implementation payload be constructed.
