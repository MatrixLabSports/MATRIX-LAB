# MATRIX-LAB-SPORTS — Permanent Paid API Mandate V1

Effective date: 2026-09-28
Mode: PERMANENT + ADDITIVE
Status: ACTIVE

## Mandate

MATRIX-LAB-SPORTS must use the two currently paid production APIs as mandatory primary acquisition providers for their corresponding sports matrices:

1. FOOTBALL
   - Provider: API-Football
   - Paid tier: Pro
   - Role: PRIMARY_PAID_API_FOOTBALL
   - Required domains: governed football discovery, fixture identity, schedules/results, statistics and other supported football data used by MATRIX.
   - Pinnacle odds obtained through API-Football remain market/reference data and must never be converted into P_MATRIX.

2. TENNIS
   - Provider: Tennis API - ATP WTA ITF via RapidAPI
   - Paid tier: Ultra
   - Role: PRIMARY_PAID_API_TENNIS
   - Required domains: governed tennis discovery and supported ATP/WTA/Challenger/ITF acquisition, including the Ultra capabilities that are explicitly allowed by the provider and the MATRIX pipeline.

## Permanent operating rules

- Both paid APIs must be attempted and physically evidenced whenever their corresponding governed MATRIX pipeline requires provider data.
- A chat statement, memory, prior run or subscription receipt is not evidence of current API consumption.
- Every claimed API use must be backed by run evidence: provider identity, timestamp, endpoint/request evidence or provider call count, and persisted output/provenance where applicable.
- If a paid API is unavailable, quota-limited, unauthorized, stale, out of coverage or otherwise fails a hard gate, MATRIX must fail closed for that provider role or use an independently approved fallback. It must never silently pretend the paid API was used.
- Paid API data does not override PIT, identity, domain, anti-leakage, Missing != 0, no silent imputation, freeze-before-kickoff/start, FINAL-only settlement, or any existing audit rule.
- Odds/market prices may be used for price/EV/reference after model probability exists; they are prohibited as a source for generating P_MATRIX.
- The paid-API mandate does not authorize model promotion, automatic wagering or real-money execution.
- Existing independent/history/reference sources remain valid for corroboration, historical features, fallback and adversarial checks under their own governance.
- This mandate is additive to PROVIDER_PORTFOLIO_GOVERNANCE_POLICY_V20 and does not weaken V20 hard gates.

## Truthfulness invariant

The system may state "API-Football Pro used" or "Tennis API Ultra used" only when the specific run being described contains verifiable physical evidence of that provider's use.

## Change control

This mandate is permanent until the user explicitly REPLACES, MODIFIES, SUSPENDS or REVOKES it.
