# MATRIX C2 — R8.3 Offline Fake-Provider Bounded Executor Loop

## Status

Implementation gate for an **offline, deterministic, single-process fake-provider executor**. This block does not authorize or perform real-provider execution, repeated real-provider polling, odds capture, production admission, model promotion, or wagering.

Approved baseline: `1fbb9ba97a2ffeb33c158382d0bf0c0e877e340c`.

Independent I20 authority: `b6ad7c453440fd59b2b35c08706989e20995c9569be1652e6a7fe9422ba85dc4`.

R8.3 design manifest: `112b28a24d7e992576824959652a471a3e10ee7948d8dccee4d1703d2a010791`.

R8.3 gap audit: `7101a406d895c715e25224cf2af11f7b9b47ca193b502c8da944ed4cee468e3d`.

## Scope and invariants

The R8.3 executor is deliberately bounded and synthetic:

- Football only.
- Provider key is exactly `fake:football:deterministic`.
- No network client and no provider adapter import.
- No secret read.
- No sleep or real-time polling loop.
- Finite plan derived from the existing `BoundedFootballLiveExecutorConfig` contract.
- Existing R8.2 process-scope guard, run state machine, persistent sequence allocator and terminal replay semantics are reused unchanged.
- Existing `SQLiteFootballLiveObservationStore` is the durable normalized temporal evidence boundary.
- A separate R8.3 SQLite fake-call journal records durable call intent/result telemetry without changing the R8.2 control schema (`user_version=85`).
- One deterministic correlation id is derived per run/round and shared only by modalities in that round.
- A sequence reservation is durable before any fake call.
- Durable normalized observation evidence is written before a reservation may become `COMMITTED`.
- A scripted fake-provider failure results in `ABANDONED` slot evidence and an aborted run.
- A committed slot is never called again on resume.
- A reserved slot whose normalized evidence already exists is committed on resume without another fake call.
- A fake call whose result is uncertain because of an injected crash may be retried only if the durable fake-call budget still has headroom.
- Sequence numbers are never reused, including after abandoned reservations.

## Synthetic execution authority

`R83OfflineFakeExecutionAuthorityPlan` is a separate synthetic-only authority boundary. It binds the exact approved baseline, I20 report, R8.3 design manifest, R8.3 gap audit, fake provider key, subject key and immutable run manifest fingerprint into a plan fingerprint.

This authority does **not** alter the R8.1/R8.2 real-provider flags. `execution_authorized`, `repeated_provider_execution_authorized` and `production_admissible` in the durable run manifest remain false. A fake-provider PASS is therefore not evidence of authorization or retry safety against API-Football or any other real provider.

## Deterministic fake provider

`DeterministicFakeFootballLiveProvider` supports the three currently approved modalities:

- `fixture_status`
- `fixture_statistics`
- `fixture_events`

For a fixed `(run_id, subject_key, round_index, modality, sequence_number, reservation_created_at)` the provider deterministically re-derives the same normalized synthetic record, source fingerprint and temporal observation. The provider can also script a failure for an exact slot or a terminal fixture status for a selected round.

Raw provider response retention is not introduced. Synthetic normalized payloads are used only to derive the source-record fingerprint and the existing temporal evidence record.

## Durable fake-call journal

`SQLiteR83FakeExecutorJournal` records call intent before a fake call and result after a successful or failed fake call. It records:

- run/manifest/plan identity,
- provider and subject identity,
- canonical modality set,
- round and total fake-call limits,
- resume count,
- slot identity,
- attempt index,
- sequence number,
- round correlation id,
- `INTENT`, `SUCCEEDED`, or `FAILED` state,
- attempt/result timestamps,
- source-record fingerprint or failure code.

The journal has a local content anchor and performs semantic re-derivation of provider identity, fixture subject grammar, canonical modality bytes, slot bounds, correlation provenance, attempt-index contiguity, sequence immutability inside a slot, timestamp monotonicity, result-state fields and total fake-call budget. It also fails closed on unexpected SQLite namespace objects or column-contract drift.

The journal anchor is local SQLite evidence, not an external immutable root. Complete database deletion is not claimed detectable.

## Crash injection and resume

The implementation exposes the following test-only crash injection points:

1. `AFTER_RUN_REGISTERED`
2. `AFTER_RUN_IN_PROGRESS`
3. `AFTER_SLOT_RESERVED_BEFORE_FAKE_CALL`
4. `AFTER_FAKE_CALL_BEFORE_NORMALIZED_PERSIST`
5. `AFTER_NORMALIZED_PERSIST_BEFORE_SLOT_COMMIT`
6. `AFTER_SLOT_COMMIT_BEFORE_NEXT_SLOT`
7. `BEFORE_RUN_COMPLETED`

Resume is explicit. An `IN_PROGRESS` run is first moved through `RECOVERY_REQUIRED` and back to `IN_PROGRESS`; a durable `RECOVERY_REQUIRED` run resumes directly to `IN_PROGRESS`. A `COMPLETED` run resolves idempotently without another fake call. An `ABORTED` run is not resumable.

R8.3 does not implement a durable historical run-transition journal; the accepted R8.2 constraint remains immediate durable command replay plus current-state recovery semantics.

## Stop conditions

The fake loop emits explicit stop reasons for bounded round completion, total fake-call budget, runtime, process-scope guard loss, provider/subject mutation, clock regression, evidence/control integrity failure, unexpected fake response, scripted fake-provider failure, terminal fixture status and manual stop.

`capture_interval_ms` remains uncalibrated. There is no `sleep`-based polling loop.

## Telemetry

The returned `FakeProviderBoundedRunTelemetry` includes run/plan identity, planned and touched rounds/slots, reservation/commit/abandon counts, durable fake-call attempt/success/failure/uncertain counts, calls by modality, sequence numbers per slot, round correlation ids, duplicate/quarantine counts, integrity failures, resume count, stop reasons and attempt runtime.

The telemetry is validation evidence for the synthetic executor only. It is not a production SLO.

## Required independent audit before any next promotion

R8.3 implementation must be independently audited before any real-provider design or execution gate. The independent audit must challenge, at minimum:

- fake-only authority isolation,
- no network/secret/provider imports,
- deterministic same-slot replay,
- durable call-intent budget across crash/resume,
- fake-call journal schema and semantic tamper resistance,
- sequence no-reuse,
- evidence-before-commit ordering,
- committed-slot no-recall,
- all seven crash injection points,
- terminal/manual/failure stop behavior,
- correlation boundaries,
- control/evidence/journal integrity fail-closed behavior,
- no hidden production, model-promotion, provider-switch or wagering path.

No real provider execution is authorized by this document.
