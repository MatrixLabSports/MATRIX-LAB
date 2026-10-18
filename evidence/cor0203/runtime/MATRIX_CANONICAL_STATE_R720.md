# MATRIX CANONICAL STATE R720

Ancestor: R719.
Target: maximize COR02/COR03 prospective conversion without violating preregistration ordering.

## Current holdout
- Window 1 = 9/200
- Total = 9/600
- Metrics = SEALED_UNTIL_600
- Outcomes read for performance = 0
- REAL_MONEY = BLOCKED

## San Diego 2 live frontier

A new material bracket progression occurred after R719:

### Quarterfinal complete
Igor Marcondes defeated Federico Agustin Gomez:
- 4-6, 6-4, 6-1
- status = FINAL

This FINAL is used ONLY to establish future-round identity.
It is not used as a model feature and does not open holdout metrics.

### Semifinal partial identity
Current structured bracket:
- semifinal scheduled 2026-09-26T21:00:00+00:00
- one player = Igor Marcondes
- other player = winner of Tristan Boyer vs Timo Legout

Boyer vs Legout progressed during R720:
- first structured snapshot = LIVE, 1-0
- later structured snapshot = LIVE, 1-1

Because the quarterfinal is still LIVE:
- semifinal has only one fixed identity
- preregistration = FORBIDDEN
- feature acquisition for the new semifinal = FORBIDDEN
- new freeze = FORBIDDEN

This is a temporal blocker, not a model/data blocker.

Existing sealed player state is already physically available from prior valid observations:
- Igor Marcondes: R707
- Tristan Boyer: R708
- Timo Legout: R708

Those prior states are NOT yet assembled into a new semifinal event. The new event may be constructed only after the winner is FINAL and the two-player identity is fixed.

## Next-week expansion check

Porto:
- official qualifying programme exists for 27-SEP
- public evidence currently provides entry list and court-level schedule, but no individual ATP qualifying pairings recovered
- admissible new matches = 0

Columbus:
- official schedule: matches begin 27-SEP
- entry list available
- no individual pairings recovered
- admissible new matches = 0

Mouilleron-le-Captif:
- ATP entry list visible
- no individual qualifying/main-draw pairings recovered
- admissible new matches = 0

Jingshan:
- ATP entry list visible
- no individual ATP pairings recovered
- WTA qualifying pairings are visible but OUTSIDE the governed ATP Challenger Hard domain
- admissible new ATP matches = 0

## Physical R720 frontier artifact
- evidence/cor0203/runtime/MATRIX_COR0203_FRONTIER_R720.json
- commit fbdad597632e2df06a9af008d168be1fc9e6d5be

## Next trigger

When Boyer-Legout reaches FINAL:
1. verify winner from current structured bracket plus corroborating current source when available;
2. confirm future semifinal time;
3. create physical prefeature registration for winner vs Igor Marcondes with starting_observation_count=9;
4. only AFTER preregistration bind/reuse the sealed 21-SEP STATIC4 state;
5. execute authorized preperiod history gate;
6. run R218_ELO_BOTH and R223_BATCH_GLICKO_RATING_BOTH;
7. freeze strictly before semifinal start;
8. persist observation 10 if all gates pass;
9. keep outcome=null and metrics_opened=false;
10. if any gate fails, persist the exact blocker and do not increment.

## Protections
- LIVE scores as model features = false
- same-period results in model state = false
- placeholders counted = 0
- retroactive freezes = 0
- odds-to-P = false
- silent imputation = false
- metrics opened = false
- REAL_MONEY = BLOCKED

## Audit
Resolved: COR01, COR04, COR05, COR06, COR07, COR08, COR09, COR12.
In progress: COR02, COR03, COR10, COR11.
COR11 remains 5/14 on 25-SEP-2026 America/Bogota.
GO/NO-GO remains 4/8.
External audit = NOT CLOSED.
