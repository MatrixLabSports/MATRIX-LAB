# MATRIX-LAB-SPORTS — Permanent Football Scheduler Resilience Mandate V1

Effective date: 2026-09-28
Mode: PERMANENT + ADDITIVE
Status: ACTIVE
Scope: API-Football prospective settlement and calibration scheduling.

## Root-cause classification

On 2026-09-28, expected hourly GitHub Actions schedule deliveries for the football
FINAL-only settlement and subsequent calibration were not physically observed at
the expected times, while:
- the repository default branch was main;
- both workflow files existed on main;
- the same workflows executed successfully when triggered by push;
- settlement and calibration code passed their governed tests.

GitHub documents that scheduled workflow events may be delayed during periods of
high load and that queued jobs may be dropped. MATRIX therefore must not rely on
one hourly schedule delivery as the sole trigger for prospective settlement.

## Permanent correction

The active architecture is:

1. Legacy settlement workflow:
   - manual/push recovery only;
   - no schedule trigger;
   - shared settlement-calibration concurrency lock.

2. Legacy calibration workflow:
   - manual/push recovery only;
   - no schedule trigger;
   - shared settlement-calibration concurrency lock.

3. Primary supervisor workflow:
   - four staggered schedule opportunities per hour at UTC minute 07, 22, 37, 52;
   - workflow_run fallback after completion of:
     - COR02-03 repo-native hourly scheduler;
     - API-Football daily prospective production;
   - shared concurrency lock;
   - fail-closed provider credential preflight;
   - settlement and calibration executed in the same governed cycle.

4. Due gate:
   - no API poll if no frozen events exist;
   - no API poll if all frozen events are settled;
   - no API poll if no unresolved event is at least 120 minutes beyond kickoff;
   - no API poll if the last physical settlement sync is less than 45 minutes old;
   - poll only when eligible unresolved events exist and settlement state is stale.

## Hard invariants

- settlement remains FINAL-only;
- nonstandard terminal states remain blocked/adjudication-required;
- settlement outcomes do not automatically open metrics;
- calibration thresholds remain 30 / 50 / 100;
- parameter tuning remains forbidden by this supervisor;
- original 357 holdout reuse remains forbidden;
- P_MATRIX remains NOT_GENERATED until separately governed;
- automatic wagering remains false;
- REAL_MONEY remains BLOCKED;
- settlement and calibration evidence must remain hash/provenance governed;
- multiple delayed supervisor triggers must not multiply provider calls inside the 45-minute freshness window.

## Failure behavior

If one scheduled supervisor delivery is delayed or dropped, later staggered
schedule opportunities or the workflow_run fallback must re-evaluate the same
physical state. The due gate prevents unnecessary duplicate provider polling.

A missing scheduled event must never be represented as a successful execution.
Only a physical GitHub workflow run and persisted evidence count as execution.

## Change control

This mandate is permanent until the user explicitly REPLACES, MODIFIES,
SUSPENDS or REVOKES it.
