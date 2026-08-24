# MATRIX C2 — R8.3R3 Cross-Ledger Completeness, Recovery and Telemetry Hardening

## Scope

R8.3R3 is an offline-only hardening patch for the synthetic football bounded executor. It closes the four blocking findings produced by independent audit I22 before any design gate for real-provider execution can be opened.

No real provider execution, network access, secret access, repeated real polling, production admission, automatic provider switching, automatic model promotion, odds execution, or wagering is authorized by this patch.

## I22 blocking findings targeted

1. `COMMITTED_CONTROL_EVIDENCE_NOT_REVERSE_BOUND_TO_FAKE_CALL_JOURNAL`
2. `KNOWN_FAILED_ATTEMPT_CAN_RETRY_FROM_RESERVED_SLOT_DESPITE_AUTOMATIC_RETRY_FALSE`
3. `RESUME_EVENT_PROVENANCE_NOT_CROSS_BOUND_TO_CONTROL_LIFECYCLE`
4. `COMPLETED_REPLAY_STOP_TELEMETRY_NOT_DURABLY_RECONSTRUCTED`

The corresponding architecture findings are addressed by bidirectional cross-ledger completeness, recovery-state reconciliation, lifecycle-bound resume provenance, and durable stop events.

## Journal schema v3

The synthetic fake-call journal advances from `user_version=2` to `user_version=3`.

R8.3R3 extends `r8_3_fake_resume_event` with the control state and control state version observed immediately before each explicit resume request. It also adds `r8_3_fake_stop_event`, which stores unique, ordered stop reasons with canonical UTC timestamps.

The local journal anchor now covers run metadata, fake-call attempts, lifecycle-bound resume events, and stop events. Version 2 journals are rejected fail-closed. R8.3 remains synthetic-only, so no production journal migration is claimed or authorized.

## Bidirectional cross-ledger completeness

R8.3R2 proved the forward direction: every journal attempt had to map to its control reservation and every successful journal result had to map to durable normalized evidence.

R8.3R3 adds the reverse direction for committed slots. Every `COMMITTED` control reservation for a run represented in the fake journal must have exactly one `SUCCEEDED` journal attempt with the same sequence number. The successful attempt must still map to exactly one accepted normalized evidence record.

Therefore deleting the entire fake-call history and recomputing only the local journal anchor no longer produces a cross-ledger-valid completed run.

## Known-failure recovery

A durable `FAILED` fake-call result with a still-`RESERVED` control slot represents an interrupted reconciliation window: the provider failure is already known, but the control reservation has not yet been abandoned.

On resume, R8.3R3 does not issue another fake-provider call. It deterministically transitions the existing reservation to `ABANDONED`, records the durable scripted-failure stop reason, and aborts the run fail-closed.

A durable `SUCCEEDED` attempt whose normalized evidence was not yet persisted is also recovered without another fake-provider call: the deterministic fake response is reconstructed with `peek`, its source fingerprint is matched against the durable success record, and the normalized observation is persisted before the reservation can be committed.

This behavior applies only to the deterministic synthetic provider and is not evidence that retry/reconstruction is safe for a real provider.

## Resume lifecycle provenance

Every explicit resume event now records:

- `control_state_before`;
- `control_state_version_before`;
- canonical `resumed_at`.

Local journal integrity validates the state/version shape and event ordering. Cross-ledger integrity then verifies that the current durable control lifecycle is sufficiently advanced to make every recorded resume event possible.

For terminal runs, a resume requested from `IN_PROGRESS/v` requires a terminal control version of at least `v+3`; a resume requested from `RECOVERY_REQUIRED/v` requires at least `v+2`. This rejects a forged resume-event bundle attached to a control run that completed without the corresponding recovery transitions.

The R8.2 control ledger still does not expose a complete transition-history journal. R8.3R3 therefore binds resume events to durable state-version lifecycle evidence, not to a nonexistent historical transition table.

## Durable stop telemetry

Stop reasons are no longer represented only in an ephemeral function return value. `r8_3_fake_stop_event` persists unique ordered stop reasons before terminal control closure whenever the executor can do so.

Completed replay reconstructs its stop reasons from the durable journal. Started/closed rounds, slot states, sequence numbers, and per-round correlation IDs are reconstructed from durable control reservations rather than reset to zero on replay.

A terminal control run without at least one durable stop reason is rejected by cross-ledger integrity.

## Replay telemetry

Terminal replay now derives:

- started rounds;
- fully closed rounds;
- reserved/committed/abandoned slot counts;
- sequence numbers by slot;
- correlation IDs by started round;
- fake-call totals by state and modality;
- resume count;
- durable stop reasons;
- run timestamps from the durable control run record.

This makes terminal replay a reconstruction of durable execution state rather than a new synthetic telemetry object with generic defaults.

## Required validation

The implementation gate must prove at minimum:

- all prior R8.3/R8.3R2 dedicated tests remain green;
- all four I22 findings reproduce against the sealed R8.3R2 baseline before mutation;
- erased fake-call history is rejected by reverse cross-ledger completeness;
- a known failed reserved slot is reconciled without any additional fake-provider call;
- a forged resume-event bundle is rejected against the control lifecycle;
- terminal stop telemetry survives completed replay;
- deleting durable stop telemetry makes a terminal run fail cross-ledger integrity;
- prior I21 sequence/source/DDL/resume protections remain closed;
- focused R8.3/R8.2/repeatable-LIVE regressions pass;
- canonical MATRIX CI passes before and after commit;
- exact committed payload hashes are sealed;
- Git object integrity passes;
- the repository ends clean.

## Non-claims and unchanged restrictions

- The journal anchor remains local, not an external immutable trust root.
- Complete deletion of all local control/evidence/journal databases is not claimed detectable without an external root.
- The R8.2 run transition-history journal remains unimplemented.
- Synthetic retry/reconstruction behavior is not evidence of real-provider retry safety.
- Capture interval remains empirically uncalibrated.
- Whole-platform cross-process determinism is not claimed.
- Real-provider execution remains unauthorized.
- Repeated real-provider polling remains unauthorized.
- Automatic wagering remains forbidden.
- Production admission remains false.

## Next gate

After successful R8.3R3 implementation, an independent audit is mandatory. Only an independent audit with zero blocking findings may authorize an R8.4 real-provider execution design preflight.
