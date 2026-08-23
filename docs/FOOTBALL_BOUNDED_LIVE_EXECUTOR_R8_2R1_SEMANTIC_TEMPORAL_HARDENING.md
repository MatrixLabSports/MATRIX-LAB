# Football bounded LIVE control — R8.2R1 semantic and temporal hardening

## Why R8.2R1 exists

Independent audit I10 found seven blocking defects in R8.2 before any fake
provider executor loop was allowed:

- run-control timestamps could move backwards;
- sequence reservation timestamps could move backwards;
- run-control rows were not independently re-derived as valid executor configs;
- reservation stream keys were not re-derived from run identity;
- reservation round/modality membership was not re-derived;
- deletion of a middle durable sequence could be hidden by re-hashing the
  local anchor;
- a terminal run could be made internally consistent with an open reservation.

I10 also identified one root architecture issue: the control ledger had not
bound run authority to a re-derivable config contract.

## Schema 83

R8.2R1 advances the control-ledger schema from 82 to 83 and stores the exact
`config_fingerprint` beside each run. Existing schema-82 control databases are
migrated transactionally after their old local anchor and SQLite integrity are
verified. Every migrated run has its config reconstructed and validated before
the new fingerprint is written.

## Semantic integrity

Every integrity audit now reconstructs `BoundedFootballLiveExecutorConfig` from
the durable run row and requires canonical provider, canonical fixture subject,
allowed/unique modalities, finite resource bounds, and exact config fingerprint.

Every reservation is re-bound to its parent run:

- modality must belong to the run;
- round must remain within the run bound;
- stream key must equal SHA-256 of sport + canonical subject + provider +
  modality;
- per-run reservation count cannot exceed the provider-call budget;
- reservation creation cannot precede run registration.

Because every allocated sequence is retained, including `ABANDONED` entries,
each stream must contain a contiguous sequence `1..last_reserved_sequence`.
A missing middle number is therefore detected rather than silently accepted.

`PLANNED` runs cannot contain reservations. `COMPLETED` and `ABORTED` runs
cannot contain open `RESERVED` entries.

## Temporal monotonicity

Run state changes must occur at or after the current run timestamp and at or
after the latest reservation timestamp for that run.

New reservations must occur at or after the current run-state timestamp.
Reservation state transitions must occur at or after both the reservation's
current timestamp and the run-state timestamp.

Registration cannot predate the manifest creation timestamp.

## Scope unchanged

The local SHA anchor remains local rather than externally immutable. Complete
database deletion is still not claimed detectable by this mechanism alone.

No provider call, repeated polling, fake-provider loop, real-provider loop,
automatic provider switch, model promotion, wagering, or production admission
is authorized. The next gate is an independent R8.2R1 adversarial audit.
