# MATRIX — RapidAPI Tennis: verified historical harvest, producer and Telegram trace

## Verified physical evidence
- GitHub Actions run 40444316229, job 121991818521, completed success on 2026-10-27 UTC.
- Job log includes provider response status PASS, 2 network calls, provider_channel_errors {}, provider_inventory_complete true, 204 events (ATP 49, ITF 125, WTA 30).
- Canonical reconciliation status PASS_CANONICAL_INVENTORY_FAIL_CLOSED, 512 rows, 24 COR02/COR03 preregistration candidates.
- Canonical source receipt `evidence/tennis/paid_window_harvest/2026-10-27/MATRIX_RAPIDAPI_TENNIS_HARVEST_RECEIPT_LAST.json` records paid-through 2026-10-28, inventory hash, 204 unique events and source order SofaScore, Flashscore, RapidAPI Tennis.
- Historical subscription evidence `evidence/governance/MATRIX_RAPIDAPI_TENNIS_SUBSCRIPTION_CONFIRMED_20261101.json` records previously confirmed ULTRA plan and payment Oct 28; NOT a new API response.
- `.github/workflows/tennis-world-rolling-horizon.yml` installed in main commit 876a58640025fdb354011e04c934e7c8053b6645; cron `17 */2 * * *`, checks out operational branch and requires daily browser crosscheck and source counts.

## Exact limits
- A successful harvest is not a governed model probability, a signal candidate, or a Telegram send receipt.
- No current 2026-11-01 provider response was executed in this investigation.
- No new rolling-horizon execution after default-branch restoration certified in this investigation.
- Do not classify the provider as historically unverified; do not infer current quota or entitlement from past success.
- No changes to paid authorization, source gates, calibrated probabilities, real-money block or automatic wagering.

## Next certification
1. Observe next Tennis World Rolling Horizon scheduled run; record job and exact first failed step.
2. Confirm daily SofaScore/Flashscore crosscheck and baseline counts; never substitute old dates.
3. Check current RapidAPI entitlement using account/provider-authorized proof and capture response receipt without exposing secrets.
4. Trace generated tennis candidate artifacts to `tools/telegram_green_signal_alerts.py`; require governed P_MATRIX and exact fresh quote, then Telegram message_id; 0 BET is valid if no eligible candidate.
