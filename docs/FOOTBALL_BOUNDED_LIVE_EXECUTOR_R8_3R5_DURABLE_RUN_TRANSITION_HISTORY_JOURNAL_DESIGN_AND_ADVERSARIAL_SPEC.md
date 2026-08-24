# MATRIX C2 — R8.3R5 Durable Run-Transition History Journal

## Design and Adversarial Specification

### Gate status

**DESIGN ONLY — NO RUNTIME IMPLEMENTATION IN THIS GATE**

This specification is bound to:

- Branch: `integration/c2-private-live-foundation`
- Sealed R8.3R4 HEAD: `0ca520f34dd5803e659d5693eac26279994c8f64`
- R8.3R4 seal report SHA-256: `b64d4cb7d4d06289a658a1990548e37346c5b3ed5d9e2de68e35617ea5a58edd`

R8.3R5 addresses the highest-priority post-audit constraint left after R8.3R4: the R8.2 control/run layer does not yet maintain an explicit durable transition-history journal.

## 1. Objective

Introduce an append-oriented durable history of every admissible run/control state transition so that transition provenance, crash recovery, reverse reconstruction, terminal semantics, and audit evidence do not depend on inference from the final mutable state alone.

The journal must preserve the historical fact that a transition occurred, including failed or abandoned attempts where required by the state machine and audit model.

## 2. Scope

R8.3R5 covers only the durable run-transition history journal and the controls necessary to verify its integrity and completeness.

In scope:

- transition-event schema;
- deterministic event ordering;
- state-before/state-after binding;
- run/control identity binding;
- causal action binding;
- timestamps and monotonic ordering metadata;
- append semantics;
- replay/reconstruction semantics;
- forward completeness;
- reverse completeness;
- crash/restart durability;
- abandoned/failed transition-attempt evidence;
- tamper and deletion detection within the local persistence boundary;
- schema migration/versioning;
- deterministic validation;
- compatibility with existing R8.3R4 provenance/terminal semantics.

Out of scope for this gate:

- external immutable integrity root;
- real-provider execution;
- repeated real-provider polling;
- operational fake-provider loops;
- provider failover;
- model promotion;
- wagering;
- empirical capture-interval calibration.

## 3. Threat model

The implementation must be designed against, at minimum:

1. deletion of an intermediate transition while preserving final state;
2. insertion of a plausible but nonexistent transition;
3. reordering of valid transitions;
4. duplication of a valid transition;
5. mutation of state-before or state-after fields;
6. mutation of causal reason/action fields;
7. mutation of transition timestamps;
8. transition timestamp postdating a bound terminal control state;
9. replay of an old transition into a newer run;
10. cross-run transition transplantation;
11. cross-control transition transplantation;
12. erasure of a failed or abandoned transition attempt;
13. crash after reservation but before durable commit;
14. crash after durable journal append but before mutable-state update;
15. crash after mutable-state update but before acknowledgement;
16. partial write or truncated event;
17. schema downgrade or incompatible user-version rollback;
18. valid local database replacement with a different internally consistent history.

Threat 18 must be explicitly marked as **not fully detectable until the later external immutable-root gate**.

## 4. Persistence model

Preferred implementation target: the existing local SQLite control/journal persistence layer, using a schema migration with explicit `PRAGMA user_version` advancement.

The transition journal must be append-oriented. Historical transition rows must not be updated in ordinary operation.

A transition record must contain, at minimum:

- durable transition event ID;
- run ID;
- control ID or equivalent control-instance identity;
- transition sequence number scoped to the run/control lineage;
- previous durable event ID or chain predecessor;
- prior state;
- next state;
- triggering action/event code;
- causal reason code where applicable;
- transition-attempt outcome;
- durable occurred-at timestamp;
- persisted-at timestamp;
- state version before;
- state version after;
- correlation/operation identity where available;
- schema/event version;
- integrity digest over canonical event content;
- predecessor digest or equivalent local chain binding.

If an existing canonical identity or digest primitive already exists in the codebase, implementation must reuse it rather than create a competing representation without justification.

## 5. Event classes

The design must distinguish at least:

- `STATE_TRANSITION_COMMITTED`
- `STATE_TRANSITION_FAILED`
- `STATE_TRANSITION_ABANDONED`

Additional event classes may be added only when required by the existing state machine.

A failed/abandoned attempt must not falsely advance the committed state while still remaining durably auditable where the causal workflow requires evidence of the attempt.

## 6. Core invariants

### INV-01 — Append-only history

Committed historical transition events cannot be silently rewritten through normal repository APIs.

### INV-02 — Strict lineage

Every committed transition after the first must identify exactly one valid predecessor in the same run/control lineage.

### INV-03 — Sequence continuity

Committed transition sequence numbers are strictly increasing and contiguous within their defined lineage.

### INV-04 — State continuity

For adjacent committed transitions:

`next[n-1] == prior[n]`

unless an explicitly versioned recovery event type defines and proves a different admissible semantic.

### INV-05 — Version continuity

State versions must advance exactly according to the canonical state-machine contract. Final-state version inference alone is insufficient proof of historical completeness.

### INV-06 — Run/control binding

A transition belonging to one run or control instance cannot validate when transplanted into another.

### INV-07 — Causal binding

Action/reason fields are part of the integrity-bound canonical event representation.

### INV-08 — Chronology

Durable ordering metadata and timestamps cannot contradict the terminal chronology rules already closed by R8.3R4.

### INV-09 — Reverse completeness

Every durable state advancement requiring a journal event must have exactly the required transition-history evidence.

### INV-10 — Failure-history preservation

An abandoned or failed reserved transition attempt that is required by the workflow cannot be erased while leaving the local history valid.

### INV-11 — Deterministic replay

Reconstruction from an identical valid journal yields the same derived control/run state.

### INV-12 — Fail closed

Missing, duplicated, reordered, malformed, mismatched, or cryptographically inconsistent transition evidence causes validation/recovery rejection, not silent repair.

## 7. Transactional write protocol

The implementation must specify one transaction boundary that prevents durable state and durable transition history from diverging silently.

Preferred behavior:

1. validate proposed transition against current durable state;
2. construct canonical transition event;
3. begin database transaction;
4. append transition event;
5. apply corresponding durable mutable-state change;
6. persist all required causal/failure evidence;
7. commit atomically;
8. acknowledge only after commit.

If the existing architecture prevents one SQLite transaction from covering every required write, the implementation must introduce an explicit recovery protocol and prove crash consistency at every gap.

## 8. Recovery semantics

On startup/resume:

1. validate schema/user version;
2. validate local transition lineage;
3. validate state/version continuity;
4. validate local integrity chain;
5. reconcile final mutable state against journal-derived state;
6. reject unexpected forward or reverse incompleteness;
7. expose an explicit failure reason;
8. do not auto-repair destructive discrepancies without a separately governed repair path.

Recovery must never invent a transition solely because final state suggests one probably occurred.

## 9. Migration requirements

The first R8.3R5 implementation must:

- advance the relevant SQLite user version;
- create the transition-history schema deterministically;
- be idempotent when reopening an already migrated database;
- reject unsupported future schema versions;
- preserve existing valid R8.2/R8.3R4 evidence;
- define treatment of pre-R8.3R5 histories explicitly.

For legacy histories created before the transition journal existed, the system must not fabricate historical events and label them as observed facts.

If a synthetic migration anchor is necessary, it must be explicitly typed, versioned, marked as migration-derived, and excluded from claims of pre-migration observational completeness.

## 10. Required adversarial harness

The implementation gate must include independent adversarial cases for at least:

### A01 — Delete middle transition

Remove one committed transition while preserving later rows and final state.

Expected: **REJECTED**.

### A02 — Insert plausible forged transition

Insert a syntactically valid transition with allowed states and plausible timestamps.

Expected: **REJECTED**.

### A03 — Reorder two transitions

Swap historical order without changing row content.

Expected: **REJECTED**.

### A04 — Duplicate transition

Duplicate a valid committed event.

Expected: **REJECTED**.

### A05 — Mutate prior/next state

Change one side of a historical state edge.

Expected: **REJECTED**.

### A06 — Mutate causal action/reason

Substitute another allowed action or reason.

Expected: **REJECTED**.

### A07 — Mutate timestamp

Move transition time into an impossible causal or terminal order.

Expected: **REJECTED**.

### A08 — Cross-run transplant

Copy a valid event to another run lineage.

Expected: **REJECTED**.

### A09 — Cross-control transplant

Copy a valid event to another control lineage.

Expected: **REJECTED**.

### A10 — Erase failed/abandoned history

Delete required failure-attempt evidence.

Expected: **REJECTED**.

### A11 — Crash before journal append

Inject crash before durable append.

Expected: no phantom committed transition; restart remains valid.

### A12 — Crash after append before state update

Inject crash at the critical boundary.

Expected: atomic rollback or deterministic failure-closed recovery.

### A13 — Crash after state update before acknowledgement

Expected: durable state and journal remain mutually complete after restart.

### A14 — Partial/truncated event

Expected: **REJECTED**.

### A15 — Schema downgrade

Force a lower/unsupported user version against newer persisted structures.

Expected: **REJECTED**.

### A16 — Unsupported future schema

Expected: **REJECTED**.

### A17 — Final-state-only forged resume

Reproduce the class of attack closed in R8.3R4 but now require explicit journal evidence.

Expected: **REJECTED**.

### A18 — Terminal stop replay compatibility

Existing R8.3R4 terminal stop causality and chronology must remain durable.

Expected: **PASS** for valid history; forged history **REJECTED**.

### A19 — Complete local DB replacement

Replace the entire local journal/control database with a different internally consistent database.

Expected for R8.3R5 alone: limitation must remain **explicitly documented**. Full detection is deferred to the external immutable-root gate.

## 11. Required test layers

R8.3R5 implementation cannot be promoted on unit tests alone.

Required:

1. schema migration tests;
2. repository/persistence tests;
3. state-machine transition tests;
4. crash-injection tests;
5. replay/reconstruction tests;
6. forward completeness tests;
7. reverse completeness tests;
8. adversarial tamper tests;
9. R8.3R4 regression suite;
10. canonical full MATRIX CI;
11. independent read-only adversarial audit.

## 12. Evidence requirements

The implementation installer must seal:

- baseline HEAD and parent;
- exact payload SHA-256 values;
- migration/user-version before and after;
- dedicated test counts;
- adversarial harness outcomes;
- canonical CI outcome;
- Git diff exact file set;
- resulting commit;
- committed blob hashes;
- Git integrity result;
- authorization state;
- report SHA-256 and sidecar.

The independent audit must consume committed artifacts and sealed evidence rather than trusting installer output alone.

## 13. Promotion criteria

R8.3R5 implementation can be considered technically closed only if:

- all required invariants are executable checks where technically applicable;
- all adversarial cases A01–A18 have explicit PASS/REJECTED evidence;
- A19 remains honestly documented as a limitation pending external anchoring;
- no R8.3R4 regression occurs;
- full MATRIX CI passes;
- repository is clean;
- independent audit passes;
- all real-provider and production permissions remain closed.

## 14. Explicit non-claims

R8.3R5 does not prove:

- external immutability;
- detection of total local persistence replacement;
- real-provider retry safety;
- real-provider latency suitability;
- empirical capture cadence;
- profitability or wagering readiness;
- production admissibility.

## 15. Authorization boundary

Throughout design, implementation, and audit of R8.3R5:

- Real-provider execution: **NOT AUTHORIZED**
- Repeated real-provider execution: **NOT AUTHORIZED**
- Repeated real-provider polling: **NOT AUTHORIZED**
- Automatic provider switching: **NOT AUTHORIZED**
- Automatic model promotion: **NOT AUTHORIZED**
- Automatic wagering: **NOT AUTHORIZED**
- Production admissibility: **FALSE**

## 16. Next gate after this specification

**R8.3R5 — OFFLINE DURABLE RUN-TRANSITION HISTORY JOURNAL IMPLEMENTATION**

The implementation must be derived from this specification and the committed repository state. It must not widen operational permissions.
