# MATRIX C2 — R8.3R5 Durable Run-Transition History Journal Implementation

## Scope

This implementation remains offline and local-only. It adds durable run-state transition history to the existing SQLite bounded-live control ledger without authorizing real-provider execution, repeated polling, automatic wagering, or production use.

## Schema migration

- Control-ledger `PRAGMA user_version` advances from 85 to 86.
- New table: `football_bounded_run_transition_event`.
- Fresh databases create the v86 schema directly.
- Legacy v82/v83 empty-history migration paths remain supported.
- v84/v85 histories are promoted only when every existing run is still `PLANNED` at state version 0 and no reservation history exists.
- Non-genesis pre-R8.3R5 histories are rejected rather than backfilled with invented transition events.

## Transition semantics

Every committed run-state transition is appended in the same SQLite transaction as the mutable run-state update. Each event binds:

- run and deterministic control identity;
- contiguous transition sequence;
- predecessor event ID and SHA-256;
- prior/next state;
- deterministic action and causal-reason semantics;
- occurred/persisted timestamps;
- before/after state versions;
- deterministic correlation identity;
- event schema version;
- canonical event SHA-256 and deterministic event ID.

The existing run `state_version` is the independent local completeness counter: for a valid run, committed transition-event count must equal state version, and replay of the journal must deterministically reconstruct the final run state/version.

## Crash consistency

The implementation exposes offline-only crash-injection points for tests around the transaction boundary:

1. before event append;
2. after event append before state update;
3. after state update before commit;
4. after commit before acknowledgement.

The first three must roll back atomically. The fourth must preserve the already committed state and transition history so an exact retry can resolve idempotently.

## Adversarial coverage

The dedicated R8.3R5 harness covers deletion, insertion, reorder, duplication, state mutation, causal mutation, timestamp mutation, cross-run/control transplantation, crash boundaries, truncated event evidence, schema downgrade, future schema rejection, and truthful migration. Existing R8.3R4 tests continue to cover erased failed-attempt history, forged resume provenance, and terminal stop causality/chronology.

## Explicit limitation — A19

A complete replacement of the entire local control database with a different internally consistent database is not claimed detectable by R8.3R5. Closing that trust-boundary gap remains assigned to the next External Immutable Integrity Root macroblock.

## Authorization boundary

- Operational fake-provider loop execution: **NOT AUTHORIZED**
- Real-provider execution: **NOT AUTHORIZED**
- Repeated real-provider execution: **NOT AUTHORIZED**
- Repeated real-provider polling: **NOT AUTHORIZED**
- Automatic provider switching: **NOT AUTHORIZED**
- Automatic model promotion: **NOT AUTHORIZED**
- Automatic wagering: **NOT AUTHORIZED**
- Production admissibility: **FALSE**

## Next gate

After implementation evidence passes, the next gate is an independent read-only adversarial audit of the committed R8.3R5 implementation.
