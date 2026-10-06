# PINNACLE CLOSING LINE REFERENCE V1

Status: GOVERNANCE_ACTIVE
Scope: football research and SHADOW evaluation only

## Purpose
Use Pinnacle only as an independent market-reference source for line movement and closing-line-value (CLV) measurement.

## Separation rule
1. P_MATRIX is generated and frozen before any market-reference comparison.
2. Pinnacle prices MUST NOT be used to generate, tune, calibrate, backfill, or modify P_MATRIX.
3. Bookmaker/reference data are downstream evaluation data only.
4. REAL_MONEY remains BLOCKED.
5. AUTO_BETTING remains DISABLED.

## Observation fields
For each eligible frozen prospective event, the downstream reference ledger may record:
- event_id
- market
- selection
- p_matrix_frozen
- p_matrix_freeze_utc
- observed_bookmaker
- observed_decimal_price
- observed_price_utc
- pinnacle_reference_decimal_price
- pinnacle_reference_utc
- pinnacle_close_decimal_price
- pinnacle_close_utc
- kickoff_utc
- source_evidence
- clv_status

Missing reference data MUST remain MISSING. No silent imputation is allowed.

## Closing protocol
PINNACLE_CLOSE is the last physically verified Pinnacle prematch price captured before kickoff for the identical event, market, selection and line. A post-kickoff price is invalid for closing-line evaluation.

If no valid prematch Pinnacle observation exists, set CLV status to MISSING_REFERENCE_CLOSE. Do not substitute another source silently.

## CLV measurement
For decimal prices, price-ratio CLV is recorded as:
CLV_PRICE_RATIO = observed_decimal_price / pinnacle_close_decimal_price - 1

The ledger must retain the raw prices and timestamps so alternative vig-adjusted CLV calculations can be audited later. No CLV result feeds back into the already frozen probability for that event.

## Notification boundary
Telegram may report research/SHADOW status and reference-line information. It MUST NOT place wagers, interact with a betting account, or trigger automatic wagering.

Permanent controls:
- MATRIX_MODE=SHADOW
- REAL_MONEY=BLOCKED
- AUTO_BETTING=DISABLED
- NO_ODDS_TO_P=true
- NO_SILENT_IMPUTATION=true
