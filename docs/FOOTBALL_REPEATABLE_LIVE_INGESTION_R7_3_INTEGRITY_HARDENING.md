# Football Repeatable LIVE Ingestion — R7.3 Integrity Hardening

Status: **offline foundation only**.

R7.3 closes the five blocking findings reproduced by the independent I1 audit
against R7.2R1.

## Closed findings

1. Decision-time staleness
   - `evaluated_at` is now explicit for freshness and admission.
   - Decision-age limits are modality-specific and default to `None`.
   - Uncalibrated decision-age thresholds remain `OBSERVE_ONLY`.
   - Exceeded decision age is `BLOCKED_STALE`.

2. Duplicate modality bundles
   - A decision bundle may contain each modality at most once.
   - Duplicate modalities fail closed with `DUPLICATE_MODALITY_IN_BUNDLE`.

3. Correlation-ID ordering reset
   - Ordering is now a stream property of
     `(subject_key, provider_key, modality)`.
   - `correlation_id` remains lineage/capture evidence and cannot reset
     sequence or observed-time monotonicity.

4. Corrupted-history write bypass
   - Every write and every fusion verification first validates durable ledger
     integrity.
   - A corrupted historical stream blocks subsequent writes/admission.

5. Deleted-history reset
   - Each stream has durable state binding count, high-water marks and
     membership fingerprint.
   - A global ledger anchor binds total row count, stream count, observation
     membership and stream-state membership.
   - Row/state/anchor deletion is fail-closed.

## Governance

- No decision-time threshold is inferred from one fixture.
- No production SLO is established.
- No repeated polling executor is introduced.
- No provider execution is authorized.
- No automatic provider switch, model promotion or wagering is enabled.
- Production admissibility remains false.

Next gate:
`INDEPENDENT_AUDIT_R7_3_THEN_DESIGN_BOUNDED_REPEATABLE_EXECUTOR`.
