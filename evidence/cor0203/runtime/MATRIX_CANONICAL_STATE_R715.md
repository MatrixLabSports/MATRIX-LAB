# MATRIX CANONICAL STATE R715

Ancestor: R714.
Targets: COR02 / COR03 continuous prospective conversion.

## R714 final validation

Canonical R714 head before this state:
- 87a8178045a744d37e2f4ac2dd5dc4a04951440d

MATRIX CI:
- push run 36132409012 = completed / success
- pull_request run 36132412947 = completed / success

Governed batch self-check:
- run 36132354485 = completed / success
- existing R713 batch correctly detected as already frozen
- duplicate freeze = 0

## Current holdout

- Window 1 = 8/200
- Window 2 = 0/200
- Window 3 = 0/200
- Total = 8/600
- Metrics = SEALED_UNTIL_600
- Outcomes read for performance = 0
- REAL_MONEY = BLOCKED

## Current world conversion state

Current Saint-Tropez quarterfinal schedule remains the live conversion frontier:
- Murphy Cassone vs Daniel Masur — 25-SEP-2026 09:00 UTC
- Harold Mayot vs Jesper De Jong — 25-SEP-2026 10:30 UTC
- Dino Prizmic vs Daniil Glinka — 25-SEP-2026 11:00 UTC
- Titouan Droguet vs Mark Lajal — 25-SEP-2026 15:30 UTC

All four are already represented by holdout observations 1-4. They do not create new observations.

San Diego 2 current quarterfinals are already represented by observations 5-8. Semifinal identities are not valid until relevant quarterfinals reach FINAL.

Next-week eligible tournament pools:
- Porto — Hard — current public evidence remains entry-list level.
- Columbus — Indoor Hard — official daily schedule confirms matches begin 27-SEP-2026, but no individual identity-fixed draw is yet available.
- Mouilleron-le-Captif — Indoor Hard — qualifying 27-28 SEP; current public evidence exposes qualifying entrants, not pairings.
- Jingshan — Hard — qualifying 28-29 SEP; current public evidence exposes entrants/event authority, not identity-fixed pairings.

## Continuous conversion control

A recurring hourly condition watch is enabled outside the repository orchestration layer.

Its governed trigger is:
A new ATP Challenger Hard/Indoor-Hard match becomes identity-fixed with two real players and a sufficiently verifiable future start time.

On trigger, required execution remains:
1. determine newest physical canonical head;
2. reject duplicates and already-frozen rows;
3. preregister before feature acquisition;
4. persist outcome=null, metrics_opened=false, features_loaded=false;
5. acquire STATIC4 and authorized pre-period PIT history;
6. require Missing != 0 and zero silent imputation;
7. forbid odds-to-P;
8. execute R218_ELO_BOTH + R223_BATCH_GLICKO_RATING_BOTH using reusable R714 batch path;
9. freeze strictly before event start;
10. persist valid freezes or exact blockers;
11. keep SEALED_UNTIL_600 and REAL_MONEY BLOCKED;
12. report only material conversion or blocker changes.

The condition watch does not change the holdout by itself and does not authorize retrospective conversion.

## Audit state

Resolved:
COR01, COR04, COR05, COR06, COR07, COR08, COR09, COR12.

In progress:
COR02, COR03, COR10, COR11.

GO/NO-GO = 4/8 YES.
External audit = NOT CLOSED.
Ordinary sports production remains PAUSED except audit/validation evidence.
