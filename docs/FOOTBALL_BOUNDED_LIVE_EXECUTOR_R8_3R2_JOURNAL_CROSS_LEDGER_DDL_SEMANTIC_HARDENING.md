# MATRIX C2 — R8.3R2 Journal Cross-Ledger and DDL Semantic Hardening

## Scope

R8.3R2 is an offline-only hardening patch for the synthetic football bounded executor introduced in R8.3. It closes the four blocking findings reported by independent audit I21 before any design work for real-provider execution is permitted.

No real provider execution, network access, secret access, polling, production admission, model promotion, provider switching, or wagering is authorized by this patch.

## I21 blocking findings closed

1. `FAKE_JOURNAL_SLOT_SEQUENCE_NOT_BOUND_TO_CONTROL_RESERVATION`
2. `FAKE_JOURNAL_SUCCESS_SOURCE_FINGERPRINT_NOT_BOUND_TO_DURABLE_EVIDENCE`
3. `FAKE_JOURNAL_CALL_TABLE_DDL_SEMANTICS_NOT_REDERIVED`
4. `FAKE_JOURNAL_RESUME_COUNT_NOT_EVENT_DERIVED`

The corresponding four architectural findings are addressed by explicit cross-ledger verification, canonical journal DDL verification, and durable resume-event provenance.

## Journal schema v2

The synthetic journal advances from `user_version=1` to `user_version=2`. R8.3R2 adds:

- `r8_3_fake_resume_event`, with one durable event per explicit resume;
- `intent_binding_sha256` and `result_binding_sha256` on `r8_3_fake_call_attempt`;
- exact DDL semantic verification for every journal table;
- a version-2 local journal anchor that covers run metadata, call attempts, and resume events.

Version 1 is rejected fail-closed. There is no operational/production R8.3 journal whose history needs promotion; R8.3 remains synthetic and operational execution remains unauthorized.

## Call provenance bindings

Each fake-call `INTENT` receives a deterministic binding over:

- run ID;
- round index;
- modality;
- attempt index;
- sequence number;
- correlation ID;
- attempted timestamp.

Each terminal fake-call result receives a second binding over the intent binding plus result state, result timestamp, source fingerprint, and error code. A local rehash that modifies only sequence or result provenance is therefore rejected by journal semantic integrity.

These local bindings are not represented as an external immutable trust root. Coordinated local tampering remains within the accepted local-anchor threat-model limitation and is additionally checked against the independent control and evidence ledgers during executor integrity gates.

## Cross-ledger integrity

`SQLiteR83FakeExecutorJournal.audit_cross_ledger_integrity(...)` verifies that:

- every durable fake-call attempt maps to an existing R8.2 reservation for the same `(run_id, round_index, modality)`;
- the journal sequence number equals the control-ledger reservation sequence number;
- every `SUCCEEDED` fake-call result maps to exactly one accepted durable normalized football observation with the same subject, provider, modality, correlation ID, sequence ID, and source-record fingerprint.

The executor's `_ensure_integrity(...)` gate now requires this cross-ledger integrity in addition to the independent control, evidence, and journal integrity checks.

## Resume telemetry provenance

`resume_count` is no longer accepted as a free-standing mutable counter. Every explicit resume inserts the next contiguous event into `r8_3_fake_resume_event`; integrity re-derives the count from those events and requires journal `updated_at` to equal the latest resume event timestamp, or `created_at` when there has been no resume.

## DDL semantic authority

R8.3R2 verifies the normalized canonical `sqlite_master.sql` definition for all journal tables. A table rebuilt with the same visible column names but different primary-key, foreign-key, or constraint semantics is rejected even if the local journal anchor is recomputed.

## Required validation

The implementation gate must prove at minimum:

- all original R8.3 dedicated tests remain green;
- I21 sequence tamper is rejected;
- I21 source-fingerprint tamper is rejected;
- I21 DDL semantic tamper is rejected;
- I21 resume-count tamper is rejected;
- legitimate resume events are contiguous and event-derived;
- coordinated local sequence/source rebinding can pass journal-local bindings only if internally recomputed, but is still rejected by cross-ledger integrity;
- crash/resume behavior remains valid;
- focused R8.3/R8.2/LIVE regressions pass;
- canonical MATRIX CI passes before and after commit;
- exact committed payload hashes are sealed;
- Git object integrity passes;
- repository ends clean.

## Non-claims and unchanged restrictions

- The journal anchor remains local, not an external immutable root.
- Complete deletion of the local journal database is not claimed detectable by the journal itself.
- Synthetic retry behavior is not evidence that a real provider is safe to retry.
- Capture interval remains empirically uncalibrated.
- Cross-process whole-platform determinism is not claimed.
- Real-provider execution remains unauthorized.
- Repeated real-provider polling remains unauthorized.
- Automatic wagering remains forbidden.
- Production admission remains false.

## Next gate

After a successful R8.3R2 implementation, an independent audit is mandatory before any R8.4 real-provider execution design preflight.
