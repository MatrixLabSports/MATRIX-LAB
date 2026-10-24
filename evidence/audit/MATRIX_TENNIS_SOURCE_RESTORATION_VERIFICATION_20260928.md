# MATRIX Tennis Source Restoration Verification — 2026-09-28

## Scope

This record verifies the first governed live restoration of the COR02/COR03 tennis discovery source using the explicit provider selector `rapidapi_tennis`.

## Physical evidence

- Scheduler run: `COR02-03 repo-native hourly scheduler #17`
- GitHub Actions run id: `36372527482`
- Triggered operational HEAD: `ec028ecf663382e15628f7ac26bc422737a1bcaf`
- Runtime evidence commit produced by the scheduler: `7caa9a02495f090542afd54abbd5ff8f74eb1511`
- Workflow conclusion: `SUCCESS`
- Provider: `rapidapi_tennis`
- Provider network calls: `9`
- Durable discovery status: `PASS`
- Durable raw records: `1`
- Durable checkpoints: `1`
- Durable store integrity: `true`
- Source readiness: `READY / DISCOVERY_COMPLETED`
- Automatic provider switch: `false`
- Automatic wagering: `false`
- REAL_MONEY: `BLOCKED`

## Prospective inventory

The governed discovery registered 18 future ATP Challenger Hard events under revision `R723`, before feature acquisition and without outcomes or odds entering P_MATRIX.

Protections persisted in the preregistration record:
- historical backfill: false
- metrics opened: false
- odds used: false
- outcome read for performance: false
- feature acquisition before preregistration: false

Identity crosswalk result:
- passed events: 2
- blocked events: 16
- silent identity join: false

Staging result:
- staged events: 0
- blocked events: 18
- current bottleneck: `ALL_PREREGISTERED_EVENTS_BLOCKED_AT_STAGING`
- principal blocker class: sealed/static feature coverage plus historical identity requirements

## Holdout and settlement remain unchanged

- holdout: `10/600`
- Window 1: `10/200`
- metrics: `SEALED_UNTIL_600`
- outcomes read for performance: `0`
- settlements: `0`
- REAL_MONEY: `BLOCKED`

## Governance interpretation

The physical source-restoration evidence required by the reconciled baseline is now present:
1. governed authorization/credential path;
2. successful real provider requests;
3. durable raw evidence;
4. SHA/provenance-linked evidence;
5. attributable provider;
6. checkpoint tied to durable evidence;
7. network_calls > 0;
8. future eligible Challenger Hard events discovered;
9. no leakage observed in the preregistration protections.

This file does not declare the wider COR02/COR03 calibration program closed and does not open sealed metrics.

Canonical close gate for this restoration verification: a terminal successful MATRIX CI on a commit containing this evidence.
