# MATRIX C2 — R8.3R5R1 Event-Outcome Semantic Hardening

## Gate status

**OFFLINE HARDENING — NO REAL-PROVIDER OR PRODUCTION AUTHORIZATION**

Baseline implementation commit:

`13fc66ef01ecbcbe59c7e2f2f469e0da7102d05e`

## Blocking finding

The R8.3R5 design requires durable transition-event outcomes for at least:

- `STATE_TRANSITION_COMMITTED`
- `STATE_TRANSITION_FAILED`
- `STATE_TRANSITION_ABANDONED`

The first R8.3R5 implementation declared all three outcome constants, but its
transition-history validator admitted only `STATE_TRANSITION_COMMITTED` and it
had no repository API for durably recording failed/abandoned run-state
transition attempts.

R8.3R5R1 closes that semantic gap before independent audit and seal.

## Hardening

The control store now:

1. uses one canonical transition-event append primitive for all three outcomes;
2. maintains one contiguous event sequence and predecessor digest chain across
   committed, failed, and abandoned events;
3. advances durable run state/version only for committed events;
4. preserves failed/abandoned attempts without falsely advancing state/version;
5. binds every event to run ID, control ID, attempted state edge, action,
   causal reason, chronology, correlation ID, predecessor and event digest;
6. permits `PLANNED.updated_at` to move beyond registration only when the
   journal proves a non-committed transition attempt at that exact timestamp;
7. derives reverse completeness from committed-event count versus durable state
   version while still validating every non-committed event;
8. keeps the existing SQLite schema and `PRAGMA user_version = 86`; no
   fabricated legacy history is introduced.

## Adversarial coverage added

The dedicated R8.3R5 test layer adds executable evidence that:

- failed attempts persist with unchanged state/version;
- abandoned attempts persist with unchanged state/version;
- deletion of required non-committed history before a later committed event is
  rejected even after the local aggregate anchor is recomputed;
- mutation of a non-committed outcome is rejected after local rehash;
- committed transition and idempotent replay remain valid after preceding
  failed/abandoned attempts.

These tests complement the existing A01–A19 R8.3R5 harness and the existing
R8.3R4 regression suite.

## Explicit limitation

A fully coherent replacement or coordinated reauthoring of every local
persistence structure remains outside the proof boundary of R8.3R5R1. Full
detection of complete local persistence replacement requires the later
**External Immutable Integrity Root** macrobloque.

## Authorization boundary

Throughout this hardening:

- operational fake-provider loop execution: **NOT AUTHORIZED**
- real-provider execution: **NOT AUTHORIZED**
- repeated real-provider execution: **NOT AUTHORIZED**
- repeated real-provider polling: **NOT AUTHORIZED**
- automatic provider switching: **NOT AUTHORIZED**
- automatic model promotion: **NOT AUTHORIZED**
- automatic wagering: **NOT AUTHORIZED**
- production admissibility: **FALSE**

## Promotion requirement

R8.3R5R1 is not sealed by implementation alone. It must pass:

1. dedicated hardening tests;
2. bounded-control regression;
3. R8.3R4 fake-provider regression;
4. canonical MATRIX CI;
5. exact committed-blob verification;
6. clean-repository and Git-integrity checks;
7. independent read-only adversarial audit;
8. final seal.

Only after independent audit and seal may the R8.3R5 macrobloque be closed.
