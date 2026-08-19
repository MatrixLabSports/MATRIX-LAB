# Decision Replay, Error Attribution & Learning Integrity Policy V24

## Purpose

MATRIX must learn from good and bad outcomes without hindsight contamination, false blame, or accidental training-data poisoning. V24 uses the V23 bitemporal truth chain to replay the exact provider evidence that was available when a decision was made, then separates outcome, execution, data quality, coverage, timing, provider revisions, and signal/model hypotheses.

## Core rules

1. Every retrospective review begins from the immutable `DecisionEvidenceFreeze` and reconstructs the latest provider truth that was actually known at `decision_at`.
2. Later provider corrections may be considered for impact analysis but may never be injected into the decision-time replay.
3. A loss is **not** automatically classified as bad analysis. With clean, complete, on-time evidence and no material post-decision correction, a loss becomes only a `SIGNAL_ERROR_CANDIDATE` pending independent review.
4. A win is not automatic proof of high-quality analysis. V24 records the outcome but does not declare analysis quality from the result alone.
5. PUSH/VOID outcomes produce no performance judgment.
6. Wrong market identity, execution mismatch, unverified settlement, future context evidence, or invalid frozen evidence fail closed.
7. Partial/missing coverage, failed decision-time data-quality gates, late/missed entry, and material provider corrections remain separate candidate causes; they must not be mislabeled as model error.
8. Model-error labels require an independent human review bound to the exact accountability-assessment fingerprint.
9. A reviewer may not independently approve their own decision.
10. A confirmed process/data/timing/provider-revision issue may enter a process-improvement dataset but may not be relabeled as a model/signal error.
11. An inconclusive review emits no learning label.
12. Learning results are append-only, hash chained, cross-process locked, flushed, and fsynced. A corrupt ledger cannot accept a new append.
13. V24 does not promote models, switch providers, enable wagering, or retroactively rewrite historical decisions.

## Safety invariants

- `future_knowledge_used = FALSE` for an accepted replay.
- `analysis_quality_determined = FALSE` in automatic attribution.
- `learning_label_allowed = FALSE` before independent review.
- `automatic_model_promotion = FALSE`.
- `automatic_wagering = FALSE`.
- `production_certified = FALSE` until consolidated integration and verification on the real repository.
