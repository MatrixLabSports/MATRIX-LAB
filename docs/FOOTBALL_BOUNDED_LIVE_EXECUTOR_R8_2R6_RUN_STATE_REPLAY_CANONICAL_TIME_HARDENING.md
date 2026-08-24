# R8.2R6 — Run-State Replay + Canonical Time Hardening

## Scope

R8.2R6 closes the two blocking findings sealed by independent audit I15 before any fake-provider bounded executor loop is designed or executed.

This increment remains offline control-plane hardening only. It does not implement a provider executor, polling loop, automatic provider switching, model promotion, wagering, or production admission.

## I15 blockers closed

1. `RUN_STATE_TRANSITION_IDEMPOTENT_REPLAY_NOT_SUPPORTED`
   - An exact replay of the immediately durable run-state command is resolved read-only when `(new_state, expected_version + 1, changed_at)` exactly matches the current durable run state.
   - A replay with a different timestamp or different command does not bypass compare-and-swap.

2. `RUN_TRANSITION_RESERVATION_TIME_ORDERING_NOT_INSTANT_SAFE`
   - All durable run/reservation timestamps must use the exact canonical UTC representation produced by timezone-aware Python `datetime.isoformat()` after UTC normalization.
   - Equivalent offset aliases (for example `-12:00` for the same instant) are rejected by integrity audit even if the local anchor is recomputed.
   - Run-state temporal admission no longer uses SQLite textual `MAX(updated_at)`; reservation timestamps are parsed as canonical instants and the true maximum is computed in Python.

## Invariants retained

- Control schema remains `user_version = 85`; no DDL change is required.
- Existing canonical table-SQL, namespace, PK/UNIQUE/FK, manifest provenance, sequence continuity, terminal reservation, and local-anchor checks remain active.
- Exact slot replay and terminal reservation-result replay remain read-only and idempotent.
- New reservations and new reservation-result transitions retain their temporal monotonicity guards.
- The local SQLite anchor is not claimed to be an external immutable trust root.
- Whole-platform cross-process determinism is not claimed.
- Capture interval remains uncalibrated.
- Real provider execution remains unauthorized.

## Next gate

`INDEPENDENT_AUDIT_R8_2R6_BEFORE_FAKE_PROVIDER_BOUNDED_EXECUTOR_LOOP`
