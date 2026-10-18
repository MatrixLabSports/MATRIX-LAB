# MATRIX TENNIS API GLOBAL AUDIT — 2026-09-28

## Status
DOCUMENTATION_AUDIT_COMPLETE / LIVE_COMPARATIVE_PROBE_PENDING

This audit evaluates tennis data APIs specifically against MATRIX-LAB-SPORTS requirements. It does **not** assert 100% live coverage for any vendor. Vendor documentation claims must be verified with controlled live probes before purchase or promotion.

## MATRIX requirements used
1. Global breadth: ATP, WTA, Grand Slams, Challenger, ITF; singles/doubles and qualifiers where possible.
2. Point-in-time safety: timestamps, historical snapshots, as-of rankings, no future leakage.
3. Deep history for model training and calibration.
4. Player identity and stable IDs.
5. Surface, form, serve/return, break/tiebreak and point-by-point data.
6. Tournament calendar/draw/topology.
7. Pre-match/live odds and odds history where available.
8. Live transport (REST/WebSocket) and high-volume capacity.
9. Practical commercial/self-serve access.
10. Suitability for governed raw capture + SHA/provenance.

## Providers screened
- Tennis API — tennis-api.com / RapidAPI (current MATRIX provider)
- Live Tennis API — livetennisapi.com
- API-Tennis — api-tennis.com
- Sportradar Tennis v3
- Stats Perform / Opta / RunningBall
- Genius Sports / IMG-derived tennis products

## Top 3 for MATRIX

### 1. Tennis API (tennis-api.com / RapidAPI)
Role: PRIMARY ALL-AROUND MATRIX SOURCE.

Documented strengths:
- ATP + WTA datasets across supported Grand Slam, tour, Challenger and ITF levels.
- Core numeric IDs for fixtures, players and tournaments.
- Tournament calendars, seasons, results, draws, seeds and potential future matchups.
- Advanced player statistics: surface splits, serve/return, pressure/break-point metrics, H2H and recent form.
- Live scores, match statistics, point-by-point and timelines.
- Pre-match odds, live odds, odds movement and historical odds; provider docs state historical odds reach as far as 2010.
- Multiple bookmaker coverage is documented.
- Plans: Pro $29/mo, Ultra $59/mo, Mega $99/mo; Ultra exposes full REST premium data, Mega adds WebSocket.
- MATRIX already has physically verified real network use for the RapidAPI integration.

Important weaknesses:
- Core fixtures and live/odds use different ID surfaces; identity bridging must remain governed.
- "Supported levels" is not proof of 100% of every ITF/Challenger event.
- Must run a global empirical coverage audit before treating it as complete.

Official sources:
- https://docs.tennis-api.com/getting-started
- https://docs.tennis-api.com/players
- https://docs.tennis-api.com/tournaments
- https://docs.tennis-api.com/live-event-and-odds
- https://docs.tennis-api.com/results
- https://tennis-api.com/api-coverage/

### 2. Live Tennis API
Role: HISTORICAL / PIT / POINT-BY-POINT COMPLEMENT AND POSSIBLE SECOND PRIMARY.

Documented strengths:
- ATP, WTA, Challenger and ITF; singles and doubles, with qualifying coverage stated.
- Results archive: 1968–2022.
- Per-match serve statistics from 1991.
- Point-by-point tape from 2023 onward; provider publishes measured coverage and provenance classes.
- Provider states 179,578 matches with a tape and 27,381,531 archived point-state rows as of Sep 2026, with coverage flags.
- As-of-match rankings on Ultra, highly valuable for leakage-safe backtests.
- Live in-play statistics: aces, double faults, serve split, hold/break.
- Stable single match-id space is documented across match routes.
- Market price timestamps and per-point match-winner price history.
- WebSocket/webhooks on Ultra.
- Self-serve pricing: Basic $9.99/mo, Pro $29.99/mo, Ultra $99.99/mo; Ultra quota 500,000/day.

Important weaknesses:
- Market surface is primarily match-winner prices, not a broad multi-market bookmaker feed.
- No tournament draw/bracket endpoint is documented.
- Shot/rally-level coverage is much smaller than the full match corpus.
- MATRIX has not yet run a credentialed physical probe against this provider.

Official sources:
- https://livetennisapi.com/
- https://livetennisapi.com/pricing
- https://docs.livetennisapi.com/
- https://docs.livetennisapi.com/historical-results-archive.html
- https://docs.livetennisapi.com/point-by-point-history.html
- https://docs.livetennisapi.com/tennis-odds.html

### 3. API-Tennis (api-tennis.com)
Role: WORLD LIVE/ODDS/DRAW REDUNDANCY SOURCE.

Documented strengths:
- Event catalogue includes ATP, WTA, Challenger men/women, ITF, singles/doubles and junior categories.
- Fixtures and livescore payloads can include point-by-point, set scores and match statistics inline.
- Player profiles include DOB and season/surface records.
- H2H, standings/rankings, pre-match odds, live odds and tournament draws.
- Odds examples show multiple bookmakers.
- Business+ adds live odds and WebSocket.
- Quotas are large: Starter 8,000/day ($40), Premium 80,000/day ($60), Business 200,000/day ($80), Ultra 2,000,000/day ($120).

Important weaknesses:
- Public documentation does not state historical depth or historical point-in-time ranking snapshots as precisely as Live Tennis API.
- No public evidence found comparable to Live Tennis API's measured historical completeness.
- MATRIX has not yet performed a real authenticated call in the reconciled evidence baseline.
- Previous MATRIX state for this provider was NOT_CONNECTED after the trial expired; that is not a quality judgment, only an integration state.

Official sources:
- https://api-tennis.com/
- https://api-tennis.com/documentation
- https://api-tennis.com/documentation_websocket

## Enterprise providers not selected in the practical top 3

### Sportradar Tennis v3
Very strong enterprise-grade data:
- >4,000 competitions in one package.
- Schedules, live scores, point-by-point, match stats, profiles, rankings, brackets, historical results and probabilities.
- Official ATP data; official ATP/Challenger rights.
- Trial access exists.

Why not practical top 3 for MATRIX global coverage:
- Sportradar announced that ITF World Tennis Tour coverage was removed starting in 2025.
- Production pricing is commercial/custom rather than transparent self-serve.
- Excellent ATP/Challenger verification source, but weaker fit for the project's all-level global requirement.

Sources:
- https://developer.sportradar.com/tennis/reference/overview
- https://developer.sportradar.com/tennis/docs/tennis-ig-data-coverage-tiers
- https://developer.sportradar.com/sportradar-updates/changelog/tennis-api-coverage-updates
- https://investors.sportradar.com/news-releases/news-release-details/sportradar-wins-major-bid-atp-rights

### Stats Perform / Opta
Very deep enterprise product:
- Exclusive official WTA umpire data and shot-by-shot feed.
- Point-level prediction APIs, stable fixture UUIDs, timestamps, tournament/draw metadata.
- Live, deep stats and enterprise historical products.

Why not practical top 3:
- Public docs do not establish comparable worldwide ITF/Challenger breadth for one self-serve tennis package.
- Commercial access/pricing is enterprise/contact-sales.
- Best used as a premium authoritative source if budget/licensing later justify it.

Sources:
- https://www.statsperform.com/wta/
- https://www.statsperform.com/products/official-wta-data-streaming/
- https://developers.statsperform.com/feed-ma21-tennis-predictions
- https://developers.statsperform.com/historical-sports-data-for-pricing-models

## MATRIX-oriented scoring
These scores are an internal fit assessment, not an industry ranking.

| Provider | Global breadth | History/PIT | Stats/PBP | Odds | Identity | Draw | Live | Cost/volume | Current MATRIX fit | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Tennis API (RapidAPI) | 19/20 | 18/20 | 15/15 | 15/15 | 8/10 | 5/5 | 5/5 | 5/5 | 5/5 | **95/100** |
| Live Tennis API | 20/20 | 20/20 | 14/15 | 8/15 | 10/10 | 0/5 | 5/5 | 4/5 | 2/5 | **83/100** |
| API-Tennis | 20/20 | 10/20 | 13/15 | 13/15 | 8/10 | 5/5 | 5/5 | 4/5 | 1/5 | **79/100** |
| Sportradar | 14/20 | 14/20 | 15/15 | 5/15 | 10/10 | 5/5 | 5/5 | 1/5 | 0/5 | 69/100 |

Scoring caveat: current live completeness, latency and actual missingness cannot be scored conclusively from public documentation. Those must be measured under a common probe.

## Recommended architecture
Do not rely on one provider as the entire truth source.

- PRIMARY: Tennis API (RapidAPI) for worldwide discovery, advanced pre-match stats, draws and broad odds/history.
- SECONDARY/PIT: Live Tennis API for deep historical results, point-by-point history, as-of rankings and independent cross-check.
- REDUNDANCY/LIVE: API-Tennis for broad event discovery, live/PBP/odds and draw redundancy.

No provider should be promoted solely from documentation.

## Next required audit before paying
Run the same governed 48-hour benchmark on all three:
1. Same calendar window and same target universe.
2. Count unique ATP/WTA/Challenger/ITF events and tournaments.
3. Identity match rate and collision rate.
4. Scheduled-time consistency and reschedule updates.
5. Pre-target historical recovery: 5/10/20/50 windows.
6. Ranking/rank-points availability at the correct PIT.
7. DOB/hand/surface completeness.
8. Serve/return/break/tiebreak completeness.
9. PBP completeness and timestamp provenance.
10. Pre-match odds coverage by market/bookmaker.
11. Live odds/PBP latency on a controlled sample.
12. Error/rate-limit behavior.
13. Raw body/SHA/provenance reproducibility.
14. No leakage / no silent imputation.

Only after this comparative live probe should MATRIX purchase or promote a provider.

REAL_MONEY = BLOCKED
AUTOMATIC_WAGERING = FALSE
