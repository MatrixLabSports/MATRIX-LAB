# MATRIX V23 — Provider Corrections, Revisions & Temporal Truth Governance

V23 adds bitemporal provider truth, immutable correction chains, point-in-time reconstruction, decision-evidence freeze validation, training/backtest leakage protection, post-decision correction impact assessment, and an append-only provider revision ledger.

The core rule is simple: **MATRIX may learn that an old value was wrong, but it may never pretend that the corrected value was known before it actually arrived.**

V23 distinguishes normal event progression from provider correction/retraction, requires explicit correction scope, blocks identity rewrites, requires human review for critical score/state/kickoff corrections, and preserves the evidence that was actually available when a LIVE or pre-match decision was made.

A later provider correction may trigger controlled re-analysis, but V23 deliberately refuses to infer from that correction alone whether the original analysis was good or bad.

Automatic model promotion, provider switching, historical backfill, and wagering remain disabled.
