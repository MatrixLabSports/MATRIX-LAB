# MATRIX EXTERNAL API INVENTORY — PHYSICAL USAGE AUDIT V1

Date: 2026-09-26
Scope: MATRIX-LAB-SPORTS external APIs/providers present in the repository.
Authority rule: physical evidence wins over prior conversation claims.

## Classification vocabulary
- VERIFIED_USED: real provider network call + persisted provider evidence + execution linkage.
- CONNECTED_NOT_USED: credential/runtime connected but no verified real call in audited evidence.
- SHADOW_OR_OFFLINE_ONLY: provider integration exists, but audited execution explicitly performs no real provider network call.
- NOT_CONNECTED: code/adapter may exist, but no production wiring/credential/runtime evidence.
- UNKNOWN: evidence insufficient to decide.

## API-Tennis
Status: NOT_CONNECTED
Verified real network calls: 0
Physical evidence:
- production observability: SOURCE_BLOCKED
- cause: PROVIDER_CREDENTIAL_NOT_CONFIGURED
- source status: API_TENNIS_KEY_NOT_CONFIGURED
- durable discovery: SOURCE_NOT_CONFIGURED
- provider_network_calls: 0
Production workflow now references API_TENNIS_KEY, but the GitHub secret is not configured.
Adjudication: NOT USED by verified MATRIX evidence.

## API-Football / API-Sports
Status: SHADOW_OR_OFFLINE_ONLY / NOT_CONNECTED_FOR_REAL_PROVIDER_EXECUTION
Verified real API-Football network calls: 0
Physical evidence:
- .env.example contains API_FOOTBALL_KEY= with no value.
- no current production workflow references API_FOOTBALL_KEY, v3.football.api-sports.io, x-apisports-key, or app.providers.api_football.
- shadow runtime explicitly records:
  - network_call_performed=false
  - network_permit_issued=false
  - secret_resolved=false
  - real_provider_execution_authorized=false
- offline ingest certification explicitly records zero_network_calls=true and real_provider_execution_authorized=false.
- persisted COR06 football HTTP capture is UEFA official via curl, not API-Football.
Adjudication: NOT USED by verified MATRIX evidence.

## Sportradar
Status: NOT_CONNECTED
Verified real provider network calls: 0 found
Physical evidence:
- provider implementation exists under app/providers/sportradar.
- governed production client requires production authority + network certification + activation readiness + activation rehearsal.
- no current workflow references Sportradar.
- no persisted provider-specific runtime evidence was found in the audited tree.
Adjudication: usage NOT demonstrated; must be reported as NOT_CONNECTED / NOT_USED unless new evidence appears.

## The Odds API
Status: NOT_CONNECTED
Verified real provider network calls: 0 found
Physical evidence:
- repository contains adapter only under app/providers/the_odds_api/adapter.py plus tests.
- no provider client/config/workflow was found in the audited tree.
- no current workflow references The Odds API.
Adjudication: usage NOT demonstrated; adapter existence is not API usage.

## Real external football source physically verified
UEFA official HTTP capture:
- source = UEFA official
- request URL = uefa.com
- transport = curl browser-independent HTTP client
- raw body + headers + SHA-256 persisted.
This proves real UEFA HTTP retrieval only. It does NOT prove API-Football, Sportradar or The Odds API usage.

## Global adjudication
At this audit point:
- API-Tennis: 0 verified calls / not connected
- API-Football: 0 verified real provider calls / shadow-offline only
- Sportradar: 0 verified calls found / not connected
- The Odds API: 0 verified calls found / not connected
- UEFA web HTTP: VERIFIED_USED as a web source, not as an API provider

## Governance consequence
Any previous claim that MATRIX was actively using API-Tennis, API-Football, Sportradar or The Odds API is invalid unless it can be tied to new physical evidence satisfying MATRIX_API_USAGE_CLAIM_GATE_V1.

No API may be reported as USED merely because code, adapters, mocks, tests, sample payloads, shadow runtimes, offline replays or account credentials exist.
