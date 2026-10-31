# MATRIX HANDOFF — 27-OCT-2026

## Freeze reference
- Branch: `repair/cor09-world-pipeline`
- Handoff base HEAD: `f46bae6470a2224b1420dba123407621c20e4e1b`
- This marker is a continuity pointer. Re-fetch the current HEAD before making current-state claims.

## Current verified facts at handoff freeze
- Football prospective sync: 4,796 observations / settlements, synced 2026-10-27T14:18:05Z, parameters_mutated=false.
- Telegram bankroll: COP 4,859,500; 187 effective settlements; 106 wins; 81 losses; -COP 140,500; -5.62u.
- Telegram quote telemetry: 94 real revalidations; READY_FOR_CAUSAL_RECOMMENDATION; Betano exact O2.5 40; BetPlay 0; Rushbet 0.
- Telegram blocker audit: 50 waiting final window, 5 no valid exact authorized Over2.5 quote, 2 historical monitoring breaches, 1 nonpositive EV.
- Elite committee: ROOT_CAUSES_IDENTIFIED_RELIABILITY_REPAIR_VERIFIED.
- Latest canonical Truth Guard at package freeze: FAIL_CLOSED because football_current_settlement, tennis_three_blocks, and telegram_daily_bankroll were stale.
- Over 2.5 is the only explicitly promoted football market for Telegram signals under the current market-scoped promotion artifact.
- 1X2 is NOT_PROMOTED_BY_THIS_GATE; BTTS is NO_GO in that artifact.
- Telegram football engine is currently wired to Goles totales Más/Menos -> Más de 2.5.

## Permanent source order
SofaScore -> Flashscore -> APIs / official providers -> identity reconciliation -> P_MATRIX -> prematch freeze -> odds/EV -> Telegram.

## Safety
- REAL_MONEY=BLOCKED
- automatic_wagering=false
- SHADOW/PAPER only
- odds >1.50
- EV positive
- P_MATRIX before odds
- no post-kickoff backfill
- 1u = COP 25,000; temporary flat 1u cap
- Telegram supervisor 15m

## Highest-priority next actions
1. Refresh/fix the 3 stale Truth Guard sources without weakening freshness gates.
2. Continue physical multi-market audit: 1X2, Under2.5, Double Chance, BTTS, corners, team/player shots, fouls, saves, cards, period goals.
3. Do not promote a market merely because a lane/state file exists. Require explicit reproducible governance.
4. Audit the 28-OCT paid API transition before any post-expiry paid consumption.
5. Preserve all Telegram reliability fixes, final-window readiness, dynamic waiting count, and append-only quote telemetry.

## Important repair commits from this conversation
- 0b656398644fbdc5dab3c63e83eaff8eb3a779b3
- 64a666622f2e27dc2d41f415e7dafcca176987e7
- 8efeaa12dc6d3a3c4a73a1e1fd1cf5e6f17c9eca
- 16f5ab8325ffd22dd30110dbb04ecd355b0d6af1
- 2ad7c5896cfbd6612bf67b376f7f32b349917784
- aa29577e893675cb03a6d790e419c2a2496ca562
- 4029c7f29e184b841840d32afdca03279f75f8db
- d9edb99b50c104d3c0bfd1879d483c01fc17c0ec
- 30d83448d436bcc2bf27b8086720ce2f45e3fd50
- 882e7036fd215399dfb510827885c5fc74c05d61
- 30936db612d799da645b51b2f1f01a21042c4be6
- bd9745adb3d388f007f8f407d35f3651bb265cd9

## Certified runs
- Football settlement #103 — SUCCESS
- Tennis Three-Block #48 — SUCCESS
- Live Tennis #655 — SUCCESS
- Supervisor #116 / #117 / #123 — SUCCESS
- Green Signals #1265 / #1341 / #1342 — SUCCESS
- Historical Truth Guard #795 was SUCCESS at that moment; do not confuse it with the newer FAIL_CLOSED stale-source state.

