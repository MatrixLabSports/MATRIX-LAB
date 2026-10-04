# MATRIX CANONICAL STATE R726

## Purpose

Advance the reconciled COR02/COR03 tennis state from R724 after governed identity-authority recovery converted eight previously preregistered R723 events into new prospective freezes.

This state is descriptive of physically persisted evidence only. It does not open sealed metrics and it does not authorize real-money wagering.

## Physical heads

- R724 reconciled narrative: source restored, holdout 11/600.
- R725 recovery preregistration projection commit: `454b4a4c9ff6eb8bc9f674a01c63363f4a44f8f0`.
- Governed R725 production evidence commit: `9a3cf4ab460cc8961a3a06e40de40e3d73f5d288`.
- Governed batch-freeze workflow: run #64, SUCCESS.
- Quality gate on the R725 trigger state: MATRIX CI #528, SUCCESS.
- Quality-gate tests: 3051 passed.
- `MATRIX CI QUALITY GATE: PASS`.

## Current holdout

- Window 1: **19/200**
- Total: **19/600**
- Total remaining: **581**
- Metrics: `SEALED_UNTIL_600`
- Outcomes read for performance: 0
- Failed audited observations: 0
- REAL_MONEY: BLOCKED

Holdout integrity after R725:
- admissible revisions: 707, 708, 713, 718, 722, 723, 725
- admissible observations: 19
- audited observations: 19
- passed observations: 19
- failed observations: 0
- result: PASS

## R725 recovery conversion

R723 originally preregistered 18 future provider events before feature acquisition.

The first governed crosswalk admitted 2/18. After a fail-closed biographical identity authority was added:
- R723 crosswalk PASS events: 10
- R723 crosswalk blocked events: 8
- join_by_name_only: false
- silent identity join: false

The two events already staged under R723 were not rewritten.

A recovery projection R725 was created only from the eight additional R723 events that:
1. already existed in the original prospective R723 preregistration;
2. had event-level identity crosswalk PASS;
3. were not already staged or frozen.

The recovery projection preserves:
- original preregistration reference: `MATRIX_COR0203_RAPIDAPI_TENNIS_PREFEATURE_REGISTRY_R723_V1`
- original starting observation count
- original event identity, schedule, competition, round, surface and provider ids
- outcome = null
- metrics unopened
- odds unused
- historical backfill forbidden

R725 crosswalk:
- passed events: 8
- blocked events: 0
- result: PASS

R725 staging:
- staged events: 8
- blocked events: 0
- result: PASS

R725 preflight/history:
- input events: 8
- valid events: 8
- blocked events: 0
- result: PASS

R725 production:
- starting physical count: 11
- new freezes: 8
- ending physical count: 19
- freeze timestamp: `2026-09-28T03:41:23+00:00`

## New R725 observations

12. Jerome Kym vs Tiago Torres — Porto Challenger — start 15:00 UTC.
13. Laslo Djere vs Michael Mmoh — Porto Challenger — start 14:30 UTC.
14. Max Basing vs Mili Poljicak — Porto Challenger — start 13:00 UTC.
15. August Holmgren vs Benjamin Bonzi — Porto Challenger — start 11:30 UTC.
16. Anton Matusevich vs Robin Bertrand — Porto Challenger — start 11:30 UTC.
17. Aleksandar Vukic vs Ryan Seggerman — Jingshan Challenger — start 08:00 UTC.
18. Adam Walton vs Hikaru Shiraishi — Jingshan Challenger — start 05:00 UTC.
19. Dominik Palan vs Terence Atmane — Jingshan Challenger — start 05:00 UTC.

Every R725 observation:
- was frozen before event start;
- has outcome = null;
- has metrics_opened = false;
- points back to the original R723 preregistration authority;
- uses the frozen R218/R223 governed model binding;
- retains REAL_MONEY = BLOCKED.

## Governed identity authority

The new authority is bounded to the R723 recovery population.

Physical input:
- `evidence/cor0203/identity/MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R725.json`

Source classes:
1. provider numeric player id and dated 21-SEP ranking snapshot;
2. unique pre-cut local historical identity/source id and observed hand;
3. fixed biographical data from a pinned public ATP player-master snapshot.

Required fallback proof:
- provider id fixed;
- provider display name confirmed;
- provider IOC confirmed with only explicit code normalization such as POR -> PRT;
- unique canonical pre-cut source id;
- fixed observed hand;
- unique biography;
- valid date of birth;
- exact 21-SEP age derived deterministically from DOB;
- dated provider rank and rank points from the 21-SEP snapshot.

Fallback rejects ambiguity, missing DOB, missing source id, hand conflict and IOC conflict.

No name-only join was introduced.

## Remaining R723 identity blockers

Eight R723 events remain blocked at identity authority. Principal blocker classes are:
- no unique pre-cut local source id;
- non-unique biography;
- missing DOB;
- historical/current IOC transition not yet adjudicated;
- hand not fixed.

They remain blocked. No missing value is converted to zero and no ambiguous identity is silently accepted.

## Discovery throughput

The RapidAPI discovery path has also been changed to reuse complete tournament metadata embedded in fixtures before spending tournament-info requests.

This removes the former normal-path effective 12-tournament truncation while keeping a bounded fail-closed fallback.

Regression coverage is green, but the optimization still requires a **fresh hourly provider bucket** before live breadth improvement can be claimed.

## Scheduler

The repository-native scheduler on the default branch remains:
- cron: minute 17 of every UTC hour
- target operational branch: `repair/cor09-world-pipeline`
- independent of chat and Opera
- real provider secret supplied through GitHub Actions
- REAL_MONEY = BLOCKED

## Current operational state

Immediately after R725:
- source_ready: true
- source_status: DISCOVERY_COMPLETED
- new_freezes: 8
- ending physical count: 19
- holdout integrity: PASS
- bottleneck: `NEW_VALID_FREEZES_PRODUCED`
- operational state: `PRODUCING`

## Permanent protections retained

- point-in-time chronology
- preregistration before feature acquisition
- identity fixed before model execution
- historical backfill forbidden
- no same-period results as model features
- no outcome read for performance
- no odds-to-P
- Missing != 0
- no silent imputation
- freeze strictly before event start
- metrics sealed until 600
- automatic wagering false
- REAL_MONEY blocked

## Next exact objective

1. Preserve 19/600 as the only physically proven count until another holdout file exists.
2. Let the next fresh hourly RapidAPI bucket exercise the expanded tournament-discovery implementation.
3. Preregister genuinely new future ATP Challenger Hard events.
4. Continue identity conversion with bounded, auditable authority only.
5. Do not relax remaining identity or history blockers merely to raise throughput.
6. Convert every new event that passes identity, static, preperiod-history, model and chronology gates.
