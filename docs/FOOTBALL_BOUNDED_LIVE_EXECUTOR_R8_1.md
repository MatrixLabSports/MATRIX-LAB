# Football bounded live executor — R8.1

## Scope

R8.1 implements only the offline domain and durable planning layer for the
single-process bounded repeatable LIVE executor.

It does **not** call a provider, read a provider secret, schedule polling, run
a repeated capture, switch providers, promote a model, or place a wager.

## Implemented

- immutable, finite executor configuration;
- explicit football fixture subject binding;
- explicit allowed modality set: fixture status, statistics, events;
- odds disabled;
- no automatic retry;
- exact finite capture-slot plan;
- maximum capture rounds, maximum total provider calls, and maximum runtime;
- capture interval intentionally unset until empirical calibration;
- single-process scope with cross-process execution forbidden;
- deterministic governance-bound planned-run manifest;
- durable SQLite run-manifest ledger with exact replay idempotency;
- payload/fingerprint rederivation;
- anchor-based detection of row/payload changes;
- I5R1 and R8 design SHA binding;
- execution, repeated provider calls, production, provider switching, model
  promotion, and wagering all fixed to false.

## Explicit limitations

The local SQLite anchor detects row or payload changes while the anchor remains
present. It is not an external immutable root and R8.1 does not claim that a
complete deletion of both the ledger and its local anchor is detectable.

R8.1 does not implement the persistent per-stream sequence allocator, process
scope guard, crash recovery execution protocol, fake-provider executor loop, or
real provider execution. Those remain later gates.

Cross-process determinism is not proven. Any future executor must fail closed
for multiprocess launch until a process-safe serialization contract is
implemented and independently audited.

## Next gate

R8.1 must pass independent offline audit before R8.2 can add the durable
per-stream sequence allocator and run recovery controls.
