# MATRIX CANONICAL STATE R724

## Purpose

Reconcile the COR02/COR03 tennis production state after real RapidAPI source restoration, R723 prospective conversion, and the post-restoration regression repairs.

This state supersedes older summaries where they conflict with physically persisted evidence.

## Ancestors and physical heads

- Last prior canonical narrative state: R721.
- Prospective evidence revision produced after source restoration: R723.
- Source-restoration evidence commit: `7caa9a02495f090542afd54abbd5ff8f74eb1511`.
- Source-restoration audit commit: `6e1c9a9422bac5187e2eba9725ce4732fcc17a4b`.
- Event-level identity/staging repair commit: `61adeb5d801ebcdc341dc3b1b35b4f91b2ff9c34`.
- R723 governed production evidence commit: `ecb760f7b368acf015f9cec8973eacc9acdcb1e3`.
- Current regression-repair head before this state: `932c9cf5852200701bde5c69bfb2c5770c0500b8`.

## Source restoration: physically verified

GitHub Actions scheduler run #17:
- run id: `36372527482`
- conclusion: SUCCESS
- provider: `rapidapi_tennis`
- provider network calls: 9
- source readiness: `READY / DISCOVERY_COMPLETED`
- durable discovery: PASS
- durable store integrity: true
- durable raw records: 1
- durable checkpoints: 1
- automatic provider switch: false
- automatic wagering: false
- REAL_MONEY: BLOCKED

MATRIX CI #489 on the persisted restoration audit completed SUCCESS.

Therefore the prior state in which RapidAPI use was not physically demonstrated is no longer current. The tennis discovery source is restored and physically evidenced.

## Current prospective holdout

- Window 1: **11/200**
- Total: **11/600**
- Total remaining: **589**
- Metrics: `SEALED_UNTIL_600`
- Outcomes read for performance: 0
- Failed audited observations: 0
- REAL_MONEY: BLOCKED

R723 added exactly one admissible frozen observation:
- event: `COR0203-RAPIDAPI-TENNIS-1499`
- canonical provider event: `rapidapi-tennis:match:1499`
- match: Daniel Rincon vs Dino Prizmic
- competition: Porto Challenger
- surface: Hard
- freeze: `2026-09-28T03:12:54+00:00`
- event start: `2026-09-28T09:00:00+00:00`
- outcome: null
- metrics_opened: false

R723 holdout integrity:
- admissible revisions: 707, 708, 713, 718, 722, 723
- admissible observations: 11
- audited observations: 11
- passed observations: 11
- failed observations: 0
- result: PASS

## R723 conversion funnel

The restored provider discovered and preregistered 18 future ATP Challenger Hard events.

Identity crosswalk:
- 2 events PASS
- 16 events BLOCKED
- silent identity join: false

A staging defect was identified and repaired: a revision-level `PASS_WITH_BLOCKERS` may no longer block an event whose own two provider identities have complete PASS mappings.

After the repair:
- staged events: 2
- blocked at identity/staging stage: 16

Preflight/history gate:
- valid events: 1
- blocked events: 1

The blocked staged event is:
- Hugo Grenier vs Grigor Dimitrov
- blocker class:
  - `SURFACE_HISTORY_MISSING:Grigor Dimitrov`
  - `ELO_SURFACE_MISSING:Grigor Dimitrov`
  - `GLICKO_SURFACE_MISSING:Grigor Dimitrov`

This blocker is retained. Missing surface history is not imputed and does not become zero.

## Static-cut and identity governance

The R723 staging repair may use the exact sealed 21-SEP static cut through a provider-to-canonical identity crosswalk only when all required static fields are present and the mapping is PASS.

Required fields remain:
- canonical source id
- hand
- age
- rank
- rank points
- ranking cut = 20260921

Provenance distinguishes:
- `FROZEN_SEALED_PLAYER_REGISTRY`
- `SEALED_STATIC_CUT_IDENTITY_CROSSWALK`

No name-only silent join was introduced.

## Regression and CI

The production-count regression tests were changed from hard-coded 10-observation expectations to invariant-based checks so that legitimate holdout growth does not make the quality gate stale.

MATRIX CI #499 completed SUCCESS after that repair.

The no-op persistence boundary was also repaired:
- mutable `*_LAST` summaries no longer define material production;
- a zero-progress cycle exits before committing mutable summary churn.

Physical proof:
- governed batch freeze run #61
- source ready
- starting physical count: 11
- ending physical count: 11
- new freezes: 0
- emitted: `COR0203_CYCLE_NO_MATERIAL_CHANGE`
- no spurious production evidence commit was created.

The strengthened no-op regression test was repaired after an intermediate syntax defect.

Current terminal quality gate:
- MATRIX CI #511
- conclusion: SUCCESS
- tests: **3047 passed**
- `MATRIX CI QUALITY GATE: PASS`

## Discovery throughput improvement

The RapidAPI discovery implementation now reuses tournament metadata already embedded in the fixture response when tier, rank id, and court are complete.

Only tournaments lacking sufficient embedded metadata consume the bounded tournament-info fallback.

This removes the former effective 12-tournament truncation from the normal embedded-metadata path while retaining bounded fallback and fail-closed validation.

Status:
- implementation committed;
- unit/regression tests added;
- canonical quality gate PASS;
- **fresh-hour live-network exercise of this optimization is still pending**.

Do not claim the new breadth optimization has increased the physical holdout until a fresh provider bucket proves it.

## Current operational state

At the latest physically persisted no-new-event cycle:
- source_ready: true
- source_status: DISCOVERY_COMPLETED
- holdout: 11/600
- operational state: `IDLE_VALID`
- bottleneck stage: `INVENTORY`
- bottleneck cause: `SOURCE_READY_NO_NEW_ELIGIBLE_EVENTS`

The repository-native scheduler remains configured for hourly execution at minute 17 UTC and does not depend on chat or Opera to run.

## Permanent protections retained

- no historical backfill into the prospective holdout
- point-in-time chronology
- no same-period outcomes as model features
- no outcome read for performance before settlement rules permit it
- no odds-to-P
- no silent imputation
- Missing != 0
- identity must be fixed
- freeze strictly before event start
- metrics remain sealed until 600
- automatic wagering = false
- REAL_MONEY = BLOCKED

## Immediate next conversion objective

1. Allow the next fresh hourly RapidAPI bucket to exercise the expanded embedded-tournament discovery path.
2. Persist only genuinely new future eligible events.
3. Increase identity-crosswalk conversion without weakening identity proof.
4. Preserve legitimate history blockers; do not impute absent Hard history.
5. Freeze every event that passes preregistration, identity, static, preperiod history, model and chronology gates.
6. Do not report a count above 11/600 until the corresponding holdout batch exists physically.
