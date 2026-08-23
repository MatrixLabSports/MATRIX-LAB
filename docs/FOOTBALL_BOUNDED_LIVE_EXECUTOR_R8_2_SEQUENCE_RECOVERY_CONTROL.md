# Football bounded LIVE executor — R8.2 durable sequence and recovery control

## Scope

R8.2 is an offline control-plane implementation. It does not call a provider,
read a provider secret, poll, execute a bounded LIVE loop, switch providers,
promote a model, place a wager, or admit production.

Independent I9 authorized construction of this block after R8.1R3 closed the
canonical identity chain with zero blocking or architecture findings.

## Process-scope guard

Every control-plane mutation requires a path-bound process-scope lease.

The guard uses atomic exclusive lock-file creation. A second process or a stale
lock causes a fail-closed rejection. Stale locks are never removed
automatically; recovery requires explicit human investigation and remediation.

This guard prevents cooperating executor instances from sharing the same
control path concurrently. It does not claim global cross-process determinism
for the whole platform.

## Durable sequence allocator

The allocator key is derived from:

- sport (`football`);
- canonical fixture subject key;
- canonical provider key;
- modality.

A reservation is created inside one SQLite `BEGIN IMMEDIATE` transaction that
also advances the stream watermark and rewrites the local integrity anchor.

The exact run/round/modality slot is idempotent. Sequence numbers are strictly
monotonic per stream. `ABANDONED` reservations are retained and never reused,
so gaps are explicit evidence instead of being silently repaired.

Reservation states are:

- `RESERVED`;
- `COMMITTED`;
- `ABANDONED`.

R8.2 does not yet bind `COMMITTED` to a real provider capture or normalized
evidence row. That integration belongs to a later fake-provider executor gate.

## Crash recovery state machine

Run-control states are durable and compare-and-swap versioned:

`PLANNED -> IN_PROGRESS -> RECOVERY_REQUIRED -> IN_PROGRESS`

An in-progress run may also become `COMPLETED` or `ABORTED`. `PLANNED` may be
aborted. `COMPLETED` and `ABORTED` are terminal.

The state machine is control evidence only; changing state does not authorize a
provider call.

## Resource safety

R8.2 defines engineering safety ceilings, not calibrated operational SLOs:

- maximum 10,000 capture rounds;
- maximum 30,000 total provider-call slots;
- maximum 24 hours declared runtime.

A lazy capture-slot iterator is provided so future executor code need not
materialize the entire plan in memory.

Capture interval and production freshness/SLO thresholds remain uncalibrated.

## Integrity model

The control SQLite database uses a local SHA-256 anchor over run-control,
stream-watermark, and reservation rows plus SQLite `integrity_check`.

As before, this is not an external immutable root. Deletion of the complete
database is not claimed detectable by this local mechanism alone.

## Next gate

R8.2 must pass an independent offline adversarial audit before any fake-provider
bounded executor loop can be implemented. Real repeated provider execution
remains unauthorized.
