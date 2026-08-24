# Football bounded LIVE control — R8.2R5 canonical DDL + result replay hardening

## Purpose

Independent audit I14 found two blockers after R8.2R4:

1. the control ledger verified columns, PK/UNIQUE/FK and the persistent object
   namespace but did not canonically re-derive the full table SQL semantics;
2. a terminal reservation result such as `COMMITTED` could be replayed after a
   run recovery only when the caller supplied a sufficiently new timestamp.
   Replaying the exact historical durable transition timestamp failed.

R8.2R5 closes the two blockers at their architectural roots without adding any
provider loop or network execution.

## Canonical table DDL authority

The module now defines the canonical stored `CREATE TABLE` SQL for all four
control-ledger tables. `_assert_schema_contract()` compares the normalized
`sqlite_master.sql` of every table with that canonical authority in addition to
the existing column, PK/UNIQUE, FK and persistent object-namespace checks.

This closes semantic DDL drift that PRAGMA metadata alone does not expose, such
as an extra `CHECK` constraint capable of vetoing a legal state transition.

The SQLite control-ledger user version remains `85`; the durable column layout
does not change.

## Durable terminal-result replay

`transition_reservation()` now resolves an already durable terminal result
(`COMMITTED` or `ABANDONED`) immediately after exact slot lookup and integrity
verification, before applying run-state or caller-timestamp guards.

This is intentionally read-only idempotency. The existing durable reservation
is returned byte-for-byte semantically unchanged. No anchor rewrite, sequence
allocation, watermark advance, state change, or timestamp change occurs.

Temporal and run-state guards still apply to an actual new transition from
`RESERVED` to `COMMITTED`/`ABANDONED`.

The rule also works after a run has become terminal. A previously committed
result may be replayed after `COMPLETED`, and an automatically abandoned result
may be replayed after `ABORTED`, because neither operation mutates durable
state.

## Scope

- No network calls.
- No API secret access.
- No provider import or provider execution.
- No fake-provider executor loop.
- No repeated polling.
- No automatic provider switch.
- No model promotion.
- No wagering.
- No production admission.

The next gate is an independent R8.2R5 audit before any R8.3 fake-provider
bounded executor loop design.
