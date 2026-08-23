# Football Repeatable LIVE Ingestion Foundation — R7

Status: **offline foundation only**.

This block closes the twelve structural gaps identified by R6/R6.1 without
authorizing repeated provider execution.

Implemented:

- explicit `ingested_at` and `normalized_at`;
- deterministic `correlation_id` and positive `sequence_id`;
- stage-by-stage latency evidence;
- football modality-specific freshness policies;
- explicit freshness reason codes;
- cross-modal alignment object and reason codes;
- configurable cross-modal skew policy;
- fail-closed stale-data behavior;
- out-of-order quarantine;
- idempotent duplicate handling;
- append-only SQLite evidence with integrity checks;
- admission states that never auto-run a model or wager.

Important governance constraints:

- No production freshness threshold is inferred from the first fixture.
- All default thresholds remain uncalibrated.
- A policy with explicit numeric thresholds is a test/configuration surface,
  not a production SLO.
- Sequential multimodal evidence must not be described as a synchronous
  snapshot.
- Late/out-of-order evidence cannot retroactively promote a past LIVE state.
- Automatic provider switching, model promotion, and wagering remain disabled.
- No provider network executor or repeated polling loop is introduced here.

Next gate: independent audit of the R7 foundation, followed by a separate
decision on wiring it into a bounded repeated-ingestion executor.
