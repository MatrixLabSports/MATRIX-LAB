# FOOTBALL BOUNDED LIVE EXECUTOR R8.3R4 — Provenance and terminal semantic hardening

## Scope

R8.3R4 is an offline, fake-provider-only hardening block. It closes the four
blocking findings raised by independent audit I23 without authorizing any real
provider execution, repeated real-provider polling, production use, automatic
provider switching, automatic model promotion, or wagering.

## I23 closures

1. Resume-event provenance is constrained by the deterministic control-state
   transition span consumed by each resume. Resume spans may not overlap, may
   not exceed the durable control state version, and may not consume the
   terminal transition.
2. Durable terminal stop reasons are cross-bound to the durable terminal run
   state. COMPLETED accepts only completion causes; ABORTED cannot claim a
   completion cause. Capture-round-limit completion additionally requires the
   complete planned slot set to be committed.
3. Durable stop timestamps may not postdate the terminal control timestamp.
4. A scripted-failure ABORTED run with ABANDONED reservations requires exactly
   one durable FAILED attempt for each abandoned slot, with matching sequence
   number and scripted failure error code.

## Retained limitations

The fake journal anchor remains local and is not an external immutable root.
Complete database deletion is not claimed detectable. The R8.2 control ledger
still does not provide a general run-transition-history journal; R8.3R4 uses
bounded fake-executor state-machine transition-span semantics for resume
provenance. Capture interval remains empirically uncalibrated. Fake-provider
retry safety is not evidence of real-provider retry safety.

## Authorization

Synthetic fake-provider tests are authorized only for this offline hardening
and its independent audit. Operational fake-provider execution, real-provider
execution, repeated real-provider polling, production admission, and automatic
wagering remain false.
