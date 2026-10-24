# MATRIX TENNIS SOURCE RESTORATION DECISION V1

Status: SOURCE_RESTORATION_PENDING_CREDENTIAL
Date: 2026-09-26
Authority: MATRIX_RECONCILED_BASELINE_SUPREMACY_V1

## Goal
Restore one real, governed, auditable source for prospective ATP Challenger Hard discovery and later FINAL settlement.

## Rejected as production scraper: ATP official website

Reason:
ATP public terms prohibit systematic retrieval of scores/statistics/rankings and prohibit wagering/gambling use absent prior express written permission.

Decision:
- ATP official web may be used only within allowed informational/manual bounds.
- It MUST NOT be treated as an automated production ingestion source for MATRIX without documented permission.
- Existing ATP browser/HAR evidence does not authorize systematic future scraping.

## Existing provider: API-Tennis

Current physical state:
- account trial expired/inactive according to user dashboard;
- MATRIX GitHub source status: API_TENNIS_KEY_NOT_CONFIGURED;
- verified MATRIX network calls: 0;
- current source state: NOT_CONNECTED / SOURCE_BLOCKED.

Decision:
Keep adapter code, but do not claim restoration until a real authenticated request succeeds and raw evidence is persisted.

## Candidate provider: Tennis API - ATP WTA ITF via RapidAPI

Public documentation states:
- authentication via X-RapidAPI-Key;
- ATP dataset includes Challengers and ITF;
- future fixtures endpoints;
- numeric player/match/tournament identifiers;
- tournament calendar and draws;
- results/historical endpoints;
- free and paid tiers are available.

Candidate host:
tennis-api-atp-wta-itf.p.rapidapi.com

Potential MATRIX fit:
- WORLD_DISCOVERY: fixtures by date/range
- DOMAIN FILTER: TourRank / tournament metadata / surface
- IDENTITY: numeric player IDs + matchId/tournament IDs
- DRAW TOPOLOGY: tournament draw endpoint
- SETTLEMENT: results endpoints
- provenance: request URL + headers metadata excluding secret + response SHA-256 + raw body + checkpoint

## Required proof before status can become VERIFIED_USED

1. User creates/uses a RapidAPI subscription and stores key as GitHub secret; key must never be pasted in chat or committed.
2. Governed probe executes against a bounded fixtures endpoint.
3. HTTP success is verified.
4. Raw provider body is persisted.
5. Response SHA-256 is persisted.
6. Call evidence/checkpoint is persisted.
7. network_calls > 0 is physically recorded.
8. At least one prospective Challenger event is discovered with provider IDs.
9. No metric/outcome leakage.

Until all 1-9 pass:
SOURCE_RESTORED = FALSE
PROVIDER_USAGE_VERIFIED = FALSE

## Current adjudication
- ATP official automated scrape: REJECTED_BY_RIGHTS_GATE
- API-Tennis: BLOCKED_INACTIVE/NOT_CONFIGURED
- RapidAPI Tennis API: TECHNICALLY_COMPATIBLE_CANDIDATE / CREDENTIAL_REQUIRED
