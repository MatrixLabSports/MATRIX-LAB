# MATRIX CANONICAL STATE R713

Ancestor: R712.
Targets: COR02 / COR03 prospective ELO/Glicko holdout.

## New admissible observation

Event:
- Nishesh Basavareddy vs Andres Andrade
- ATP Challenger San Diego 2
- Quarterfinal
- Hard
- Scheduled start: 2026-09-26T01:30:00+00:00
- Local schedule authority: Friday 25-SEP-2026 18:30 PDT, Stadium Court

Discovery and preregistration:
- Identity/time resolved before feature acquisition.
- Prefeature registry commit: 35e7bfd75d198dfac9e4d8d6aa88bb6245c4603a
- features_loaded=false at preregistration
- outcome=null
- metrics_opened=false

STATIC4 acquired only after preregistration:
- Nishesh Basavareddy: rank 167, 344 points, DOB 2005-05-02, hand R
- Andres Andrade: rank 206, 269 points, DOB 1998-12-14, hand R

## Authorized history gate

Artifact:
- evidence/cor0203/runtime/MATRIX_COR0203_HISTORY_GATE_R713.json

Result: PASS.

Pre-period state:
- target_period = 20260921
- same-period results used = false
- annual pre-period rows used = 5313
- annual pre-period periods used = 38

Player state:
- Nishesh Basavareddy: n_history=89; ELO present; Glicko present
- Andres Andrade: n_history=74; ELO present; Glicko present

No neutral-history substitution.
No silent imputation.
Missing != 0 preserved.

## Freeze

Workflow:
- COR02-03 prospective holdout freeze
- run 36127553405 = completed / success

Freeze commit:
- 68d029192e4cc3a6f843b41dfde1e5d5f969240a

Freeze timestamp:
- 2026-09-25T11:06:11+00:00

Event start:
- 2026-09-26T01:30:00+00:00

Freeze is strictly pre-start.

## Observation 8

Artifact:
- evidence/cor0203/holdout/MATRIX_COR0203_HOLDOUT_BATCH_R713.json

Observation index = 8.

Alphabetical orientation:
- player_a = Andres Andrade
- player_b = Nishesh Basavareddy

R218_ELO_BOTH:
- p(Andres Andrade) = 0.2756055161896191
- p(Nishesh Basavareddy) = 0.7243944838103809

R223_BATCH_GLICKO_RATING_BOTH:
- p(Andres Andrade) = 0.3393261713165514
- p(Nishesh Basavareddy) = 0.6606738286834486

Control probability window 1:
- 0.4967308051559873

Odds used = false.
Outcome = null.
Metrics opened = false.

Hashes:
- feature_snapshot_sha256 = 7c9f410eec4dafcc5f02e0e1b2dfa3e9b18faac547384d5168640133a757e64f
- observation_sha256 = 096339db7b7fd06ef1a310eacf9815313318f7345be2c4541719ee252ecaf5c8
- batch_sha256 = f99067607c2fb744fe0f569e052bc3f2118a3cb3168ad4bdc21425c108ace1c1
- annual_2026_sha256 = d3f0e7edca273d0e1fcd4700581cf00398e46719f0aaadb62a1c97ec0ffa6ab5
- bundle_sha256 = ef5788fa4212c67880a52af85359bed1483ba1d59b1655e28390bbfaf0187ec8

## Holdout counter

- Window 1 = 8/200
- Window 2 = 0/200
- Window 3 = 0/200
- Total = 8/600
- Metrics = SEALED_UNTIL_600
- Outcomes read for performance = 0

R706 remains quarantined.
R709 Basavareddy-Hance remains blocked and is not repurposed as observation 8.
Observation 8 is a new event with its own prospective preregistration and freeze.

## Audit state

Resolved:
COR01, COR04, COR05, COR06, COR07, COR08, COR09, COR12.

In progress:
COR02, COR03, COR10, COR11.

COR02/COR03 current prospective holdout = 8/600.
Performance metrics remain sealed until >=600.

GO/NO-GO remains 4/8 YES.
External audit = NOT CLOSED.
REAL_MONEY = BLOCKED.
Ordinary sports production remains PAUSED except audit/validation evidence.
