# Football bounded LIVE control R8.2R7 — replay command provenance and terminal-slot hardening

## Scope

R8.2R7 is an offline control-ledger hardening gate. It closes the two blocking findings from independent audit I16 before any fake-provider bounded executor loop may be designed or executed.

No provider call, polling loop, secret access, automatic provider switch, model promotion, wagering, or production admission is introduced by this gate.

## I16 blockers closed

### 1. Run-state replay predecessor provenance

R8.2R6 made the immediately durable run-state command idempotently replayable. I16 demonstrated that result-state equality alone was insufficient: an impossible predecessor alias such as `RECOVERY_REQUIRED/version 0 -> IN_PROGRESS/version 1` could satisfy the durable result tuple.

R8.2R7 binds replay to the semantic reachability of both the caller-supplied predecessor `(expected_state, expected_state_version)` and the resulting `(new_state, expected_state_version + 1)`. Exact replay is returned only after those state/version semantics are valid. Normal compare-and-swap behavior and historical error ordering for genuinely new transitions remain unchanged.

### 2. Exact-slot replay after terminal or recovery states

An already durable `(run_id, round_index, modality)` slot is evidence lookup, not a new allocation request. R8.2R7 resolves an existing exact slot before checking whether the current run is `IN_PROGRESS`.

This keeps exact-slot replay available while the run is `RECOVERY_REQUIRED` and after terminal `COMPLETED` or `ABORTED` states. A nonexistent slot still requires an `IN_PROGRESS` run, so terminal runs cannot allocate new sequence numbers.

## Preserved controls

- control schema remains `user_version = 85`;
- canonical table DDL verification remains active;
- canonical UTC durable timestamp bytes remain required;
- reservation-time ordering remains instant-safe;
- exact result replay remains read-only;
- process-scope guard remains mandatory for mutating APIs;
- local SQLite anchor is not claimed to be an external immutable root;
- complete database deletion/recreation is not claimed locally detectable;
- whole-platform cross-process determinism is not claimed;
- capture interval remains uncalibrated;
- executor loop remains unimplemented and unauthorized;
- real provider execution remains unauthorized;
- production remains inadmissible.

## Gate outcome required

R8.2R7 may be considered implementation-gate PASS only after dedicated tests, independent blocker-closure harness, focused regressions, canonical MATRIX CI before and after commit, exact committed blob verification, sealed evidence outside the repository, and a clean final repository state all pass.

A separate independent audit is still required before R8.3.
