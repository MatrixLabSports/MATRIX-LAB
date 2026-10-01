# MATRIX-LAB-SPORTS — CALIBRATION V2 RESEARCH PLAN — 01-OCT-2026

## Purpose
Improve probability calibration in tennis and football without contaminating any protected holdout, without changing frozen probabilities after freeze, and without enabling real-money execution.

## Non-negotiable governance
- Physical repository evidence > memory > chat summaries.
- Tennis and football remain separate lanes.
- PIT and anti-leakage are mandatory.
- Missing != 0; no silent imputation.
- Odds never generate P_MATRIX.
- Freeze probabilities are immutable.
- Settlement is FINAL-only.
- REAL_MONEY=BLOCKED.
- AUTOMATIC_WAGERING=false.

## Tennis lane
Current protected holdout:
- A22_POST_AUDIT_VIRGIN_HOLDOUT_V1.
- 3 non-overlapping windows x 200 = 600.
- R218_ELO_BOTH and R223_BATCH_GLICKO_RATING_BOTH remain frozen candidates.
- No holdout outcomes may be read for model development.
- No tuning inside the 600-case holdout.

Development work must use only historical/pre-holdout evidence whose target outcome was available before the relevant training cut. Candidate families to test outside the protected holdout:
1. Surface-aware ELO.
2. Recency-weighted ELO with fixed predeclared decay.
3. Service/return strength decomposition when PIT-safe source fields exist.
4. Glicko/ELO logit ensemble.
5. Post-model probability calibration: logistic/Platt first; isotonic only with sufficient independent development n.
6. Stability by rank-difference bands and chronological folds.

Promotion contract after an independent OOS test:
- Brier lower than frozen champion/reference.
- BSS >= 3% where contract requires it.
- ECE and maximum calibration error within predeclared limits.
- No segment collapse.
- No use of the active 600 observations for fitting or hyperparameter selection.

## Football lane
Protected evidence:
- Original final historical holdout n=357 is permanently excluded from new tuning.
- Existing prospective gate-100 prefix is evaluation-only and must not be used for parameter tuning.
- Existing frozen probabilities remain immutable.

Market-specific development:
### 1X2
- Multinomial calibration independent of binary goal markets.
- Compare log-pool champion against regularized multinomial/logistic calibrators trained only on historical development+validation data.
- Evaluate reliability of top-pick confidence and class-specific calibration.

### Over 2.5
- Independent binary calibration.
- Compare current logit pool with regularized logistic and beta-calibration candidates.
- Preserve Poisson as reference baseline.

### BTTS
- Keep BTTS separate from Over 2.5.
- Continue BTTS v2 development only on data excluding the original 357 final holdout.
- Require a fresh prospective unseen holdout for any promotion.

## New diagnostic added in research branch
Tool:
- tools/api_football_calibration_diagnostics_v2.py

Test:
- tests/test_api_football_calibration_diagnostics_v2.py

Purpose:
- Evaluate the already-declared gate-100 prefix only.
- Report calibration bins, ECE, powered-bin MCE, and Brier Skill Score vs Poisson.
- Explicitly forbid using gate100 as a tuning sample.
- Highlight 70-75, 75-80, 80-85, 85-90, 90-95 and 95%+ confidence regions when sample exists.
- This diagnostic does not create selection rules and does not generate P_MATRIX.

## Next implementation order
1. Run/verify football calibration diagnostics V2 on the gate-100 prefix.
2. Add football historical-development challenger V2 per market with the original 357 excluded.
3. Add a fresh prospective evaluation contract for the new football challenger.
4. Build tennis pre-holdout challenger dataset audit; prove every row is outside the active 600 and PIT-safe.
5. Implement tennis challenger models only after that audit passes.
6. Keep autonomous tennis 102->200->400->600 production untouched.
7. Continue COR11 real-calendar cadence independently.
