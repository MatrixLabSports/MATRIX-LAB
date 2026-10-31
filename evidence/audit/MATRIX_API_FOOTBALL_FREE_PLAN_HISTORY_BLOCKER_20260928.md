# MATRIX API-FOOTBALL FREE-PLAN HISTORY BLOCKER — 2026-09-28

Status: PHYSICALLY VERIFIED PROVIDER PLAN BLOCKER
Scope: football prematch historical acquisition for the 83 future fixtures captured for 2026-09-28 America/Bogota.

## What succeeded

API-Football connectivity and future fixture discovery remain verified.

The future fixture acquisition produced:
- 84 provider fixtures received
- 83 strictly future eligible fixtures
- 166 unique teams
- 36 competitions
- 25 countries
- RAW response persisted
- SHA-256 persisted
- REAL_MONEY = BLOCKED

## What failed

The historical acquisition route was tested against the real provider.

### Season-wide route

Request pattern:
- /fixtures?league=<league_id>&season=<target season>

Provider result for all 37 requested league-season groups:
- HTTP 200 envelope
- provider data error
- no historical rows returned

Exact provider message:
- `Free plans do not have access to this season, try from 2022 to 2024.`

Observed target seasons include 2025, 2026 and 2027.

### Team-last fallback probe

Request pattern:
- /fixtures?team=1&last=20

Provider result:
- HTTP 200 envelope
- provider data error
- no historical rows returned

Exact provider message:
- `Free plans do not have access to the Last parameter.`

## Physical workflow evidence

Workflow:
- API-Football governed group history capture
- original run id: 36380202821

Attempt 1:
- failed on the first provider plan error before persistence.

Attempt 2:
- rerun with fail-closed per-group quarantine.
- 37 league-season groups requested.
- 37 provider-error groups.
- 37 network request attempts.
- 0 targets with minimum history.
- 83 targets blocked.

Attempt 3:
- rerun after free-plan range detection and bounded team-last fallback.
- 1 season-wide probe.
- 1 team-last probe.
- free_plan_season_range_blocked = true
- team_last_probe_status = PROVIDER_ERROR_BLOCKED
- 0 targets with minimum history.
- 83 targets blocked.
- status of the acquisition controller = PASS because it persisted and quarantined provider blockers instead of fabricating history.

Latest physical evidence:
- `evidence/api_football/history/history_capture_manifest.json`
- `evidence/api_football/history/history_readiness.json`
- `evidence/api_football/history/benchmark_with_history.json`
- raw provider envelopes under `evidence/api_football/history/raw/`

## Adjudication

`API_FOOTBALL_CONNECTIVITY = VERIFIED`

`API_FOOTBALL_FUTURE_FIXTURE_DISCOVERY = VERIFIED`

`API_FOOTBALL_FREE_PLAN_CURRENT_HISTORY_ROUTE = BLOCKED_BY_PLAN`

`API_FOOTBALL_FREE_PLAN_TEAM_LAST_ROUTE = BLOCKED_BY_PLAN`

`FOOTBALL_HISTORY_READY_TARGETS = 0/83`

`REAL_MONEY = BLOCKED`

No missing history is converted to zero.
No provider error is treated as data.
No 2022-2024 season is silently substituted for a 2025-2027 target as if it were recent form.
No model probability is generated from these blocked histories.

## Anti-repeat guard

The manual group-history workflow is now guarded against repeating these already-proven blocked free-plan routes. If the same physical blocker evidence is present, a new run terminates before making a provider request.

## External provider documentation

API-Football's current pricing page states:
- Free: 100 requests/day
- Pro: 7,500 requests/day
- all plans include all endpoints and competitions
- Free plans are limited in available seasons

The exact season and `last` restrictions above are taken from the real provider responses received by MATRIX, which are the authoritative evidence for this account.

## Next governed paths

There are now only two legitimate paths for recent prematch history:

1. change API-Football subscription/data entitlement and re-verify the previously blocked routes with a bounded probe; or
2. keep the Free subscription for current/future discovery and acquire recent historical form from a separate governed source with stable identity, PIT timestamps, raw persistence and anti-leakage.

Until one of those paths is physically verified, the 83 fixtures remain discovery inventory only and must not be presented as model-ready.
