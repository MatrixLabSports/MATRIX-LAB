# Football bounded LIVE control — R8.2R3 schema constraint and canonical evidence hardening

## Purpose

Independent audit I12 found four blockers after R8.2R2:

- durable `manifest_json` accepted non-canonical byte representations;
- empty schema-83 migration produced a schema that differed from a fresh store;
- SQLite PK/UNIQUE/FK/CHECK contracts were not independently re-derived;
- exact `(run_id, round_index, modality)` slot uniqueness depended on DDL alone.

The root architecture finding was that control-ledger integrity still depended
on unverified SQLite DDL.

## Schema 85

R8.2R3 advances the control ledger to user version 85. Fresh stores are created
from one canonical schema definition.

Empty schema-83 stores are rebuilt transactionally into that exact canonical
schema, rather than using nullable `ALTER TABLE` additions. Non-empty schema-83
stores remain fail-closed because historical manifest provenance was never
available there.

Schema-84 stores already contain durable manifest provenance. They may promote
to schema 85 only after SQLite integrity, exact schema contract, local anchor,
and full semantic control integrity all verify.

## Structural schema verification

Every integrity audit now re-derives:

- exact column names, SQLite types, NOT NULL flags, and primary-key positions;
- required primary-key and unique index column sets;
- reservation foreign key to `football_bounded_run_control(run_id)`;
- the singleton anchor CHECK constraint.

A database whose data and local anchor are internally consistent but whose DDL
has lost PK, UNIQUE, FK, NOT NULL, or anchor CHECK semantics is rejected.

## Canonical manifest evidence

`manifest_json` is not only parsed and semantically reconstructed. Its stored
bytes must equal the canonical JSON serialization of the reconstructed manifest
payload exactly. Formatting-only rewrites therefore fail integrity even if the
JSON object is semantically equivalent and the local anchor is recomputed.

## Slot uniqueness

Integrity independently tracks every
`(run_id, round_index, modality)` tuple and rejects duplicates. This duplicates
the SQLite primary-key protection intentionally: critical control invariants are
not trusted to DDL alone.

## Scope

This remains an offline control-plane hardening gate. It performs no provider
call, reads no provider secret, implements no executor loop, performs no
automatic provider switch, model promotion, wagering, or production admission.

The next gate is an independent R8.2R3 adversarial audit before any fake-provider
bounded executor loop design is admitted.
