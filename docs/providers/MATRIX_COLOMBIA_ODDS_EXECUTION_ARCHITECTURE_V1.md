# MATRIX-LAB-SPORTS — Colombia Odds Execution Architecture V1

Effective date: 2026-09-28
Status: ARCHITECTURE_PREPARED / PROVIDER_CREDENTIAL_PENDING
REAL_MONEY: BLOCKED
AUTOMATIC_WAGERING: FALSE

## Purpose

Prepare the complete governed path for comparing pre-match prices across Colombia-authorized execution candidates after an independently generated P_MATRIX exists.

This architecture does not activate a bookmaker, does not authorize real-money execution and does not treat documentation or memory as proof of live provider coverage.

## Execution portfolio

MATRIX execution candidates:
- Betano
- BetPlay
- Betsson
- Bwin
- Codere
- Luckia
- MrYoker
- Rivalo
- RushBet
- Sportium
- Stake Colombia
- Wplay
- YaJuego
- Zamba

Reference-only:
- Pinnacle: market/reference only; never Colombia execution.

Quarantine:
- Unibet: provider-visible but blocked pending Colombia regulatory reconciliation.
- Bingo Casino: regulator/provider coverage inconsistency; blocked pending reconciliation.

## Provider activation candidate

Provider: odds-api.net
Credential secret: ODDS_API_NET_KEY
Activation state: REQUIRED_NOT_CONFIGURED

The provider is not VERIFIED_USED until a credentialed physical catalog call succeeds and its raw response, SHA-256, timestamp and rate-limit metadata are persisted.

## Price architecture

The provider price is never allowed to generate P_MATRIX.

Required flow:

1. P_MATRIX generated from governed sports data and frozen model binding.
2. Exact market contract is fixed:
   - sport
   - event_id
   - market_key
   - bet_type
   - metric
   - period
   - line
   - side
   - selection_key
   - market_contract where supplied
   - selection_parameters where supplied
3. Pre-match quotes are acquired.
4. Each quote passes:
   - execution-bookmaker classification
   - availability
   - freshness
   - pre-match timestamp
   - decimal-odds validity
   - permanent minimum odds rule (> 1.50)
5. Only exact comparison keys compete with each other.
6. Best valid decimal price is selected.
7. Implied probability and expected value are computed after P_MATRIX:
   EV = P_MATRIX * decimal_odds - 1
8. Non-positive EV => NO_BET.
9. Stake is computed only after calibration gate and real-money gate pass.
10. Freeze is written before event start to the append-only hash-chained ledger.

## Stake architecture

Default policy is deliberately conservative and configurable:
- fractional Kelly: 0.25
- maximum bankroll fraction: 0.02
- minimum bankroll fraction: 0.0025
- minimum expected value: 0.0
- minimum decimal odds: strictly greater than 1.50

No stake may be emitted as BET_CANDIDATE while:
- calibration gate is not PASS; or
- REAL_MONEY is BLOCKED.

The policy is an execution component, not a model-training input. It can be changed only through explicit governed change control after calibration evidence exists.

## Freeze invariants

A CONTROLLED_LIVE freeze requires:
- P_MATRIX generated before freeze;
- quote captured before freeze;
- quote and freeze before event start;
- exact probability/quote comparison-key equality;
- PRICE_CANDIDATE;
- BET_CANDIDATE;
- real-money gate open;
- automatic_wagering = false.

The ledger is append-only and hash-chained. Duplicate freeze IDs are rejected.

## odds-api.net snapshot integration

The canonical adapter persists:
- provider event ID
- bookmaker
- market key
- bet type
- metric
- period
- line
- side
- selection key
- odds
- availability
- event/snapshot freshness timestamp
- source payload SHA-256
- resume/cursor metadata where supplied

When bookmaker-specific freshness is missing, snapshot time may be used only with the explicit label:
SNAPSHOT_AS_OF_FALLBACK.

When the provider selection_key is missing, a local exact-snapshot identity may be derived, but it is marked:
DERIVED_LOCAL_EXACT_SNAPSHOT_ONLY
and is not treated as provider-history eligible.

## Activation procedure after payment

1. Store ODDS_API_NET_KEY only as GitHub Actions secret.
2. Run the governed Colombia catalog probe.
3. Persist raw bytes, SHA-256, timestamp and rate metadata.
4. Promote only physically present execution targets.
5. Run one event snapshot in football and one in tennis.
6. Verify exact-line normalization and freshness.
7. Run shadow comparisons with REAL_MONEY still BLOCKED.
8. Validate freeze ledger end to end.
9. Only after calibration and external-audit gates pass may controlled-live execution be considered.

## Truthfulness rule

The system must never say a bookmaker is integrated, verified, live, or usable through odds-api.net unless the current physical evidence proves it.

Architecture-ready is not provider-active.
Provider-visible is not execution-authorized.
Best price is not a bet unless all downstream gates pass.
