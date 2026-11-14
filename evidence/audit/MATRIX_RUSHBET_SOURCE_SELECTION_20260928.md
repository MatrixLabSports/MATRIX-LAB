# MATRIX RUSHBET SOURCE SELECTION — 2026-09-28

## Status
PREACTIVATION / CREDENTIAL_REQUIRED / NOT YET VERIFIED USED

## Objective
Add RushBet as a verifiable football odds source for MATRIX without scraping or pretending that API-Football supplies it.

## Physical facts already verified in MATRIX
- API-Football bookmaker catalog returned 33 bookmakers.
- Pinnacle was present as bookmaker id 4.
- RushBet was not present in that API-Football catalog.
- Therefore RushBet must use a separate provider path.

## Public provider research
### Selected candidate: odds-api.net
Official documentation states:
- Base URL: https://api.odds-api.net/v1
- Authentication: X-API-Key
- Colombia catalog includes 15 bookmakers.
- Canonical Colombia keys include:
  - betplay
  - betano
  - bwin
  - rushbet
  - wplay
  - and 10 additional Colombian-facing integrations.
- GET /v1/bookmakers?country_code=CO discovers the active bookmaker catalog.
- GET /v1/events discovers canonical events.
- GET /v1/events/{event_id}/odds/snapshot supports bookmaker filters and bookmaker-specific freshness.
- include_source=true exposes provenance/capture metadata.
- SSE and WebSocket streams are available for supported pre-match updates.
- Historical odds are a separate paid add-on.
- The provider states that it currently does not support in-play odds.
- Paid plans permit internal analytics, modelling, dashboards and applications subject to the data license.

### Pricing observed 2026-09-28
Starter:
- USD 30/month
- 50,000 requests/month
- 60 requests/minute
- all bookmakers
- all markets
- 150 stream-hours/month
- 1 concurrent stream

Builder:
- USD 90/month
- 2,000,000 requests/month
- 300 requests/minute
- all bookmakers
- all markets
- 1,500 stream-hours/month
- 8 concurrent streams

## MATRIX fit
Why odds-api.net is preferred for the first RushBet activation:
1. It explicitly documents RushBet Colombia.
2. The same feed also exposes BetPlay, Betano and Bwin, reducing the need for four independent integrations.
3. It uses canonical event/bookmaker/market/selection schemas.
4. It exposes freshness timestamps and optional source provenance.
5. It supports normalized pre-match snapshots and streaming.
6. It avoids an unsupported direct RushBet scraper.

## Limitations
- This is an aggregator, not an official RushBet API.
- Documentation claims are not treated as physical usage proof.
- No RushBet quote is admissible in MATRIX until a credentialed live call is performed and persisted with raw bytes + SHA-256 + timestamps.
- No live/in-play RushBet capability is assumed through odds-api.net because the provider currently documents pre-match only.
- No odds from any bookmaker may generate P_MATRIX.

## Activation gate
Before status may become VERIFIED_USED:
1. User subscribes to an odds-api.net plan.
2. API key is stored only as GitHub Actions secret ODDS_API_NET_KEY.
3. A governed one-call catalog probe to /v1/bookmakers?country_code=CO succeeds.
4. Physical response includes rushbet.
5. Physical response also records whether betplay, betano and bwin are available.
6. Raw body and SHA-256 are persisted.
7. Rate-limit metadata is persisted.
8. No key is printed or committed.
9. REAL_MONEY remains BLOCKED.

## Sources
- https://odds-api.net/colombia
- https://odds-api.net/docs
- https://odds-api.net/pricing
- https://odds-api.net/terms

REAL_MONEY = BLOCKED
AUTOMATIC_WAGERING = FALSE
