# C2 R8.2R10 — Quiescent state timestamp semantics hardening

## Scope

Offline-only hardening of the durable football bounded-LIVE control ledger. This
gate closes the two I19 findings without implementing or authorizing any
provider executor loop, repeated provider execution, polling, production use,
automatic provider switching, model promotion, or wagering.

## I19 blockers closed

1. `PLANNED_RUN_UPDATED_AT_STATE_SEMANTICS_NOT_REDERIVED`
   - A `PLANNED` run has not undergone any run-state transition.
   - Its durable `updated_at` therefore must equal `created_at`.
   - `audit_integrity()` now rederives and enforces that equality.

2. `RESERVED_RESERVATION_UPDATED_AT_STATE_SEMANTICS_NOT_REDERIVED`
   - A `RESERVED` slot has not undergone any result transition.
   - Its durable `updated_at` therefore must equal `created_at`.
   - `audit_integrity()` now rederives and enforces that equality.

## Preserved semantics

- `COMMITTED` and `ABANDONED` reservation result timestamps may legitimately
  advance beyond allocation time.
- Existing terminal-run chronology, canonical timestamp, canonical DDL,
  replay-idempotency, slot recovery, manifest authority, and process-guard
  controls remain intact.
- Control schema remains `user_version = 85`; no table layout change is made.
- The SQLite anchor remains local rather than an external immutable trust root.
- Real-provider execution and the bounded executor loop remain unauthorized.

## Required next gate

`INDEPENDENT_AUDIT_R8_2R10_BEFORE_FAKE_PROVIDER_BOUNDED_EXECUTOR_LOOP`
