# Football bounded LIVE control — R8.2R2 durable manifest provenance hardening

## Why R8.2R2 exists

Independent audit I11 kept the I10 repairs closed but found four blockers
before a fake-provider executor loop could be designed:

- the control ledger stored a manifest fingerprint without enough durable
  manifest evidence to re-derive it;
- the run ID was not re-derivable from control-ledger evidence;
- reservation creation time could move backwards within one sequence stream;
- impossible run-state/state-version combinations could be hidden by re-hashing
  the local control anchor.

The common architecture issue was that control-ledger run identity was not
bound to durable manifest authority.

## Schema 84 and durable manifest authority

Schema 84 stores the complete canonical R8.1 bounded-run manifest payload as
`manifest_json` beside the duplicated control columns.

Every integrity audit parses that payload with the canonical R8.1 manifest
validator. This independently re-derives:

- canonical executor config and config fingerprint;
- approved design/audit governance hashes;
- run nonce provenance;
- run ID;
- manifest fingerprint;
- all fail-closed authorization and production flags.

The re-derived manifest must agree exactly with the run-control row. Re-hashing
the local control anchor is therefore insufficient to legitimize a forged
manifest fingerprint or run ID.

## Legacy migration policy

Schema 82 and 83 predate durable run nonce / manifest provenance in the control
ledger. That missing cryptographic provenance cannot be reconstructed safely.

Empty legacy databases migrate transactionally to schema 84.

A non-empty schema-83 database fails closed with
`R8_2R2_NONEMPTY_V83_MANIFEST_PROVENANCE_UNAVAILABLE`; it is not silently
promoted, guessed, or rewritten. If a schema-82 database is non-empty, its
82→83 work is inside the same outer transaction and is rolled back when the
84 provenance gate fails.

This is acceptable for C2 because repeated/provider executor execution has
never been authorized, so no legitimate real execution history depends on an
automatic legacy promotion.

## Stream chronology

Within each `(football, subject, provider, modality)` stream, reservation
creation timestamps must be nondecreasing with sequence number.

The allocator checks the latest durable stream reservation before allocating a
new sequence, and integrity audit re-derives the same ordering independently.

## Run state-version semantics

The durable state/version pair is now independently constrained:

- `PLANNED` only version `0`;
- `IN_PROGRESS` positive odd versions;
- `RECOVERY_REQUIRED` positive even versions starting at `2`;
- `COMPLETED` positive even versions starting at `2`;
- `ABORTED` any positive version.

These rules follow the only transitions permitted by the existing recovery
state machine and make impossible re-hashed state/version pairs detectable.

## Scope unchanged

The SQLite anchor remains local, not an external immutable authority. Complete
database deletion is not claimed detectable by this mechanism alone.

No provider call, fake-provider loop, real-provider loop, repeated polling,
automatic provider switch, model promotion, wagering, or production admission
is authorized. R8.2R2 must pass an independent audit before R8.3.
