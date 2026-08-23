# Football Repeatable LIVE Ingestion — R7.1 Critical Hardening

Status: **offline hardening only**.

This patch closes critical findings found during independent review of R7 before
any repeated provider executor is allowed.

## Findings closed

1. Ledger integrity now re-derives `status` and `reason_codes` from the actual
   insertion history instead of merely checking that values belong to an
   allowed set.
2. SQLite identity columns (`subject_key`, `modality`, `correlation_id`,
   `sequence_id`, `source_record_fingerprint`, `observed_at`) are cross-checked
   against the hashed observation payload during integrity audit.
3. A newer ingestion sequence carrying an older `observed_at` is quarantined as
   `QUARANTINED_LATE_OBSERVATION`.
4. A repeated stable `source_record_fingerprint` is idempotent even when it
   arrives under a different sequence id, preventing double counting.
5. The source-record uniqueness rule is enforced durably with a scoped SQLite
   unique index.
6. Transaction rollback no longer masks the original error if transaction
   acquisition itself fails.
7. Concurrency tests verify that duplicate source observations cannot create
   multiple durable rows.

## Governance remains unchanged

- no provider calls;
- no repeated polling;
- no production SLO;
- no inferred freshness/alignment thresholds;
- no automatic provider switching;
- no automatic model promotion;
- no automatic wagering;
- no retroactive LIVE promotion.

Next gate:
`INDEPENDENT_AUDIT_R7_1_REPEATABLE_LIVE_INGESTION_HARDENING`.
