# MATRIX C2 R8.2R8 — Canonical Duplicate Run Evidence + Process Guard Provenance Hardening

## Scope

Offline hardening only. This gate closes the two independent I17 blockers found against R8.2R7 before any fake-provider bounded executor loop is allowed.

No provider call, polling loop, secret read, provider switch, model promotion, wagering, or production admission is introduced by this change.

## I17 findings closed

1. `RUN_MODALITIES_JSON_CANONICAL_BYTES_NOT_ENFORCED`
2. `PROCESS_SCOPE_GUARD_LOCK_PROVENANCE_FIELDS_NOT_BOUND`

Architecture findings closed:

1. `DURABLE_DUPLICATE_RUN_CONFIG_EVIDENCE_NOT_BYTE_CANONICAL`
2. `PROCESS_SCOPE_GUARD_LOCK_EVIDENCE_HAS_UNVERIFIED_DECLARED_PROVENANCE`

## Durable duplicate run evidence

`modalities_json` is a duplicated durable representation of the canonical manifest/config modalities. R8.2R8 uses one canonical serializer for both write and integrity verification and requires exact byte equality after semantic rederivation.

Equivalent JSON with different whitespace or formatting is no longer accepted even if the local anchor is recomputed.

## Process-scope guard provenance

The process-scope lock is now treated as canonical provenance evidence. The authoritative lock payload must have exactly the declared fields and exact canonical JSON bytes.

`assert_active()` binds the lock payload to the active lease for:

- schema;
- control path;
- owner token SHA-256;
- PID;
- hostname;
- acquired-at timestamp;
- exact declared field set.

Tampering with hostname, acquired-at, extra fields, or serialization bytes fails closed.

This does not claim the lock is an external immutable root. It remains a cooperating-process, local-filesystem control.

## Retained constraints

- control schema user version remains `85`;
- local SQLite anchor is not an external immutable root;
- complete control DB deletion/recreation is not claimed detectable;
- whole-platform cross-process determinism is not claimed;
- capture interval remains uncalibrated;
- executor loop remains unimplemented;
- repeated provider execution remains unauthorized;
- production remains inadmissible.

## Gate

R8.2R8 must pass dedicated tests, an independent closure harness, focused regressions, canonical MATRIX CI pre/postcommit, exact committed blob verification, and final clean repository verification.

Even after this implementation gate passes, the next gate is an independent R8.2R8 audit before R8.3 fake-provider bounded executor loop design is opened.
