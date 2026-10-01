# MATRIX-LAB-SPORTS — CALIBRATION V2 STATUS — 01-OCT-2026

## Scope
Research-only calibration improvement for tennis and football. This lane does not alter the active production probabilities, does not open the A22 tennis holdout, does not reuse the protected football final holdout, and does not authorize real money.

## Tennis

Active production remains unchanged:
- Holdout: `A22_POST_AUDIT_VIRGIN_HOLDOUT_V1`.
- Active binding: R218 ELO + R223 batch Glicko.
- Physical count at research start: 102/600.
- Active metrics: sealed until 600.
- Outcomes read for calibration-v2 development from the active holdout: 0.

Historical development used the exact 2022-2025 Challenger source files whose SHA-256 hashes are already bound in the canonical project. A bounded regularization search produced one research lead:
- candidate: `TENNIS_BASE12_ELO_REG_C0P01_20261001`
- family: BASE12 + overall/surface ELO, logistic C=0.01
- prospective inference: observed features required; no missing-value imputation
- future-only cutoff: 2026-10-02T00:00:00Z
- promotion: forbidden without fresh prospective evidence

The historical development replay shows useful 75-90% confidence populations, but the candidate is NOT promoted because 2024 maximum calibration error and the close-rank band remain unstable.

A separate audit also found that older R238/R251 research used an orientation derived from a hash whose input contained winner/loser-labelled ordering. That exact orientation cannot be reproduced prospectively before the result is known. Therefore those old results must not be used as direct promotion evidence without re-expression under an outcome-independent orientation.

## Football

The declared gate-100 prefix remains evaluation-only. New diagnostics show:
- 1X2 BSS vs Poisson: about +3.18%; ECE about 9.25%.
- Over 2.5 BSS vs Poisson: about +1.26%; ECE about 7.01%.
- BTTS v2 BSS vs Poisson: about +1.57%; ECE about 3.06%.

The project then tested simple calibration-v2 candidates only on historical development data while permanently excluding the original final 357 and without using the prospective gate100 for tuning.

Adjudication:
- richer 1X2 standardized softmax: rejected; worse Brier and log-loss than current challenger on internal chronological validation.
- richer Over 2.5 logistic: rejected; worse Brier and log-loss.
- 1X2 temperature scaling: rejected; worsened Brier and log-loss.
- Over 2.5 Platt layer: rejected; worsened Brier and log-loss.

Therefore the current football challenger remains unchanged. Calibration improvement must come from genuinely new information/architecture and fresh validation, not from forcing probabilities upward.

## CI / resilience correction

The historical regression test that required `build_freeze(...).frozen_event_count > 0` was time-dependent and could fail on a healthy cycle with no newly eligible fixtures. The research branch changes that assertion to allow zero while preserving every safety invariant: future-only, unseen-only, original-357 exclusion, prematch freeze, no outcome at freeze, no P_MATRIX, and REAL_MONEY=BLOCKED.

## Governance
- Active production branch is untouched.
- `P_MATRIX=NOT_GENERATED`.
- `AUTOMATIC_WAGERING=false`.
- `REAL_MONEY=BLOCKED`.
- Draft PR #2 exists only for CI/review; do not merge as model promotion.
