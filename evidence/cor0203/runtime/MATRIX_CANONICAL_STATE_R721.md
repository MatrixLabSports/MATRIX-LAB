# MATRIX CANONICAL STATE R721

Ancestor: R720.
Target: lock San Diego 2 draw topology before the next COR02/COR03 prospective freeze.

## Holdout
- Window 1 = 9/200
- Total = 9/600
- Metrics = SEALED_UNTIL_600
- Outcomes read for performance = 0
- REAL_MONEY = BLOCKED

## Verified San Diego 2 quarterfinal topology

QF1:
- Nishesh Basavareddy vs Andres Andrade

QF2:
- Dylan Dietrich vs Henry Searle

QF3:
- Tristan Boyer vs Timo Legout

QF4:
- Igor Marcondes vs Federico Agustin Gomez

Semifinal topology:
- SF1 = WINNER_QF1 vs WINNER_QF2
- SF2 = WINNER_QF3 vs WINNER_QF4

QF4 is FINAL:
- Igor Marcondes defeated Federico Agustin Gomez 4-6 6-4 6-1
- therefore SF2 partial identity = WINNER(Boyer-Legout) vs Igor Marcondes

At the latest structured live check during R721:
- Boyer vs Legout = LIVE
- latest displayed set line = Boyer 6-2, second set not terminal
- therefore two-player semifinal identity is NOT yet fixed
- preregistration remains forbidden until FINAL

## Physical topology artifact
- evidence/cor0203/runtime/MATRIX_COR0203_DRAW_TOPOLOGY_R721.json
- topology commit: 06f17fec2c870660c1415f989624f07289a5998b

## Regression protection
- tests/test_r721_draw_topology.py
- test commit: 9f40e23f48c36cd24c4fd7a3e670917cda580340

The regression gate enforces:
- QF1/QF2/QF3/QF4 mapping
- SF1 and SF2 winner mapping
- placeholders are not real identities
- preregistration requires two real players
- LIVE results cannot be model features
- same-period FINAL results may be used only for future identity progression

## Sources used for topology verification
- Canal Tenis San Diego 2 2026 draw
- SteveG Tennis San Diego 2 Challenger 2026 draw
- SweTennis San Diego 2 2026 draw
- current structured tennis tournament bracket

## Next exact conversion path

When Boyer-Legout becomes FINAL:
1. verify the winner as QF3 winner;
2. bind SF2 identity = winner vs Igor Marcondes;
3. verify the future semifinal start time;
4. create physical prefeature registry with starting_observation_count=9;
5. only after that, bind/reuse sealed 21-SEP STATIC4 state;
6. run authorized preperiod history gate;
7. execute R218_ELO_BOTH and R223_BATCH_GLICKO_RATING_BOTH;
8. freeze strictly before the semifinal start;
9. persist observation 10 if every gate passes;
10. keep outcome=null and metrics_opened=false.

For SF1:
- wait for FINAL of Basavareddy-Andrade and Dietrich-Searle;
- apply the same process for a possible observation 11.

## Audit
Resolved:
- COR01
- COR04
- COR05
- COR06
- COR07
- COR08
- COR09
- COR12

In progress:
- COR02
- COR03
- COR10
- COR11

COR11 = 5/14 on 25-SEP-2026 America/Bogota.
GO/NO-GO = 4/8 YES.
External audit = NOT CLOSED.
REAL_MONEY = BLOCKED.
