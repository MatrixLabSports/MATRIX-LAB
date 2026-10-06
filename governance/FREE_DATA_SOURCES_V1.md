# FREE DATA SOURCES V1

Status: ACTIVE_FOR_DISCOVERY_AND_RECONCILIATION
Date: 2026-10-06

## Permanent controls
- Paid APIs remain primary governed sources where applicable.
- Free sources are additive and independent; they never silently replace paid data.
- Every observation retains source, retrieval timestamp and source identifier.
- Missing != 0. No silent imputation.
- Conflicts are reconciled explicitly; unresolved identity/time conflicts are BLOCKED.
- Odds/market prices MUST NOT generate P_MATRIX.
- REAL_MONEY=BLOCKED.
- AUTO_BETTING=DISABLED.

## Football free layer
### football-data.org
Role: independent fixture/schedule/result/table reconciliation in competitions available to the free tier.
Authentication: FOOTBALL_DATA_ORG_TOKEN.
Status until token probe passes: CONFIGURED_NOT_VERIFIED.

### TheSportsDB v1 free
Role: secondary metadata, league/team/event identity and schedule enrichment only.
Authentication: public free development key documented by provider.
Status: FREE_SECONDARY_SOURCE.
Important: free methods are limited; never treat its absence as proof that an event does not exist.

## Tennis free layer
### Live Tennis API free tier
Role: prospective discovery/fixtures and live/result reconciliation across ATP, WTA, Challenger and ITF where the free plan exposes the endpoint.
Authentication: LIVE_TENNIS_API_KEY.
Status until key probe passes: CONFIGURED_NOT_VERIFIED.
This source does not replace API-Tennis or RapidAPI Tennis.

### TheSportsDB v1 free
Role: secondary tennis event/player/league metadata when available.
Status: FREE_SECONDARY_SOURCE_LIMITED.

### Sackmann archival/open datasets
Role: historical PIT support and audit cross-check only, subject to source snapshot date and license.
Status: HISTORICAL_SECONDARY_ONLY.
Never use an archive snapshot as a live calendar.

### Match Charting Project
Role: optional point-by-point/statistical enrichment for matches physically present in the dataset.
Status: SPARSE_ENRICHMENT_ONLY.
Absence is not missing-zero and does not block discovery by itself.

## Browser verification sources
SofaScore, Flashscore and official federation/tour pages remain independent physical verification layers. Browser-derived data must retain capture timestamp and evidence. They are not silently promoted to API truth.

## Reconciliation order
Football: paid API-Football + football-data.org + TheSportsDB + SofaScore/Flashscore -> canonical identity/time -> PIT -> model.

Tennis: paid API-Tennis + paid RapidAPI Tennis + Live Tennis API free + historical/open datasets + SofaScore/Flashscore/official sources -> deduplication -> canonical identity/time -> PIT -> R218/R223 where domain-valid.

## Activation gate
A source requiring a key is ACTIVE only after a physical probe returns a valid provider response and evidence is persisted. Merely adding a secret or adapter does not prove activation.
