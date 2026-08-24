# Football bounded LIVE control — R8.2R4 trigger namespace and recovery idempotency

## Purpose

Independent audit I13 found two blockers after R8.2R3:

1. the verified SQLite DDL surface did not close the persistent
   `sqlite_master` trigger/object namespace; and
2. exact-slot replay after a recovery cycle depended on the caller supplying a
   timestamp newer than the resumed run state.

Both are critical before any fake-provider executor loop can be designed.

## Closed SQLite mutation authority

`_assert_schema_contract()` now derives the complete persistent user schema
namespace from `sqlite_master`, excluding SQLite-reserved `sqlite_%` internal
objects.

The only permitted user objects are the four canonical control tables. No
persistent trigger, view, explicit index, or extra table is accepted. Existing
PK/UNIQUE autoindexes remain SQLite-reserved objects and continue to be
validated separately through the index contract.

This means a trigger cannot silently become an alternative mutation authority
between the pre-mutation integrity check and the post-mutation anchor rewrite.

## Exact-slot replay after recovery

`reserve_next_sequence()` now resolves an already-durable
`(run_id, round_index, modality)` slot before applying the temporal checks that
belong only to a new reservation allocation.

For exact replay:

- no new sequence is allocated;
- no watermark advances;
- no timestamp is rewritten;
- the original durable reservation is returned exactly;
- both its historical `created_at` and a newer caller timestamp resolve to the
  same durable object.

Temporal monotonicity remains mandatory for every *new* sequence allocation.

## Scope

Control schema stays at user version 85 because R8.2R4 changes integrity
semantics rather than the durable column layout.

No provider execution, polling, network access, API secret, automatic provider
switch, model promotion, wagering, or production admission is added.

The next gate is an independent R8.2R4 audit before any R8.3 fake-provider
bounded executor loop design.
