# MATRIX TENNIS SOURCE RESTORATION — PRE-ACTIVATION STATE

Date: 2026-09-26
Authority: MATRIX_TOTAL_RECONCILIATION_AUDIT_20260926 + MATRIX_TRUTHFULNESS_AND_PHYSICAL_EVIDENCE_CONSTITUTION_V1
Status: PREPARED_NOT_ACTIVATED

## Baseline
The reconciled baseline remains authoritative.
Current COR02/COR03 holdout:
- total observations: 10/600
- Window 1: 10/200
- metrics: SEALED_UNTIL_600
- current persisted settlements: 0
- real money: BLOCKED

## Existing provider
API-Tennis:
- account plan known inactive from user-side evidence
- MATRIX GitHub secret/API credential not configured
- verified MATRIX provider network calls: 0
- current production status: SOURCE_BLOCKED

## Alternate provider prepared
Provider key: rapidapi_tennis
Product: Tennis API - ATP WTA ITF
Host: tennis-api-atp-wta-itf.p.rapidapi.com

Repository implementation now includes:
- tools/cor0203_rapidapi_tennis_discovery.py
- tools/cor0203_rapidapi_durable_discovery.py
- provider-aware preregistration
- provider-aware historical identity crosswalk support
- provider-preserving settlement queue
- FINAL-only RapidAPI settlement converter
- mixed-provider settlement dispatcher
- explicit MATRIX_TENNIS_PROVIDER selector
- workflow inputs for RAPIDAPI_TENNIS_KEY
- scheduler input for RAPIDAPI_TENNIS_KEY
- regression tests for identity, missing credential, domain, pagination, queue, and FINAL-only settlement

Governed eligibility:
- ATP only
- singles only
- future event required
- numeric match/player IDs required
- TourRank=1 discovery is NOT sufficient by itself
- tournament tier must explicitly prove Challenger
- court/surface must be Hard
- ranking snapshot cut = 2026-09-21
- no missing ranking substitution
- no odds-to-P
- real money remains BLOCKED

## CI verification
Physical head verified before this report:
377f14af9f2a4ca9e745070097fff50eed1ba9da

MATRIX CI push:
- run 36282975515
- completed / success

MATRIX CI pull_request:
- run 36282977815
- completed / success

## Activation gate
RAPIDAPI_TENNIS_USED = FALSE
VERIFIED_NETWORK_CALLS = 0

The provider MUST NOT be described as connected, active, restored, or used until ALL are physically true:
1. a valid RapidAPI subscription for the exact product exists;
2. RAPIDAPI_TENNIS_KEY is stored as a GitHub Actions secret, never committed;
3. provider selection is explicitly changed to rapidapi_tennis;
4. a governed workflow run performs network_calls > 0;
5. raw provider evidence is persisted in the durable acquisition store;
6. source readiness = READY;
7. checkpoint/provenance links the request to persisted evidence.

## Manual dependency
The available GitHub connector cannot write repository Secrets/Variables.
The Opera connector was checked and is currently unavailable/not connected.
Therefore provider subscription/credential entry requires user interaction.

No API key should ever be pasted into ChatGPT or committed to the repository.
