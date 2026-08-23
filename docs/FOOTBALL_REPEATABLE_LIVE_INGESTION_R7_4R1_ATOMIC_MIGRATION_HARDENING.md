# Football Repeatable LIVE Ingestion — R7.4R1 Atomic Migration Hardening

Status: **offline foundation only**.

R7.4R1 closes the independent I3 finding `FAILED_R73_TO_R74_MIGRATION_IS_NOT_ATOMIC`.

## Atomic migration contract

- Store initialization now opens an explicit SQLite `BEGIN IMMEDIATE` transaction before any schema, index, backfill, stream-state, ledger-anchor, or `PRAGMA user_version` mutation.
- The existing R7.3→R7.4 table rebuild remains isolated by its nested savepoint, but release of that savepoint no longer commits the outer migration.
- `COMMIT` occurs only after bootstrap/re-derivation and the full ledger integrity assertion succeed.
- Any exception executes guarded rollback of the outer transaction and re-raises the original failure.
- A rejected migration must preserve the exact pre-migration observation table DDL, indexes, stream state, ledger anchor, and `user_version`, with no leaked `football_live_observation_r73` table.
- A valid R7.3 ledger must still migrate to R7.4 and pass integrity.

## Scope retained from R7.4

- Quarantined rows remain durable evidence.
- Only accepted rows advance sequence and `observed_at` watermarks.
- Provider-aware table/index uniqueness remains in force.
- Ledger `user_version` remains 74; no new schema version is invented because this change hardens transaction boundaries, not stored semantics.

## Governance

- No network or provider call is introduced.
- No provider key is required or read.
- No repeated polling or provider executor is introduced.
- No automatic provider switch, model promotion, or wagering is enabled.
- Production admissibility remains false.
- The intermittent identity supersession concurrency finding reproduced by I3 remains open and must be independently resolved before any bounded repeatable executor is authorized.

Next gate: `INDEPENDENT_AUDIT_R7_4R1_ATOMIC_MIGRATION_AND_CONCURRENCY`.
