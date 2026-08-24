# C2 R8.2R9 — Terminal chronology and process-guard type hardening

## Scope

This offline hardening closes the two blocking findings reproduced by the independent R8.2R8 I18 audit. It does not implement or authorize a provider executor loop, repeated polling, production execution, provider switching, model promotion, or wagering.

## Terminal chronology authority

The control ledger already required terminal transitions to occur no earlier than the latest durable reservation result at mutation time. R8.2R9 rederives that same invariant during every integrity audit.

For `COMPLETED` and `ABORTED` runs, `run.updated_at` must be greater than or equal to every durable reservation `updated_at` belonging to the run. A locally rehashed anchor cannot legitimize a reservation result whose timestamp is later than the terminal run timestamp.

This is a semantic integrity rule only. The SQLite schema remains at user version 85.

## Process-scope guard provenance type schema

The process-scope lock is now validated as a strict typed provenance record before value comparison. The declared field set remains exact. String fields must remain JSON strings, and `pid` must remain a non-boolean JSON integer. Digit strings, floats, and booleans are rejected instead of being coerced through `int(...)`.

Canonical JSON bytes, hostname, acquired-at, owner token, control path, schema, and current process identity remain bound as before.

## Preserved constraints

- local SQLite anchor is not an external immutable root;
- complete database deletion/recreation is not claimed detectable;
- whole-platform cross-process determinism is not claimed;
- capture interval remains uncalibrated;
- executor loop remains unimplemented;
- real/repeated provider execution remains unauthorized;
- production remains inadmissible.

## Next gate

Independent audit of R8.2R9 is required before any R8.3 offline fake-provider bounded executor-loop design gate can open.
