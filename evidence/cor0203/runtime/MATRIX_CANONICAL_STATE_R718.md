# MATRIX CANONICAL STATE R718

Ancestor: R717.
Targets: COR02 / COR03 prospective conversion from Saint-Tropez semifinal + batch-workflow root-cause repair.

## Live identity progression used for admission only

On 25-SEP-2026 the Saint-Tropez quarterfinals produced two FINAL winners that fixed a future semifinal identity:
- Murphy Cassone advanced from Cassone vs Daniel Masur.
- Harold Mayot advanced from Mayot vs Jesper de Jong.
- Future semifinal identity: Harold Mayot vs Murphy Cassone.

These FINAL results were used only to establish the identity of the future semifinal.
They were NOT used to open holdout performance metrics, tune the model, rewrite prior observations, or update same-period model state.

Schedule evidence:
- 365Scores current Saint-Tropez bracket displayed the semifinal on 26-SEP-2026 at 12:00.
- Official Saint-Tropez programme confirms singles semifinals on 26-SEP-2026 and a day start from 11:30 local.

The pipeline stored:
- event_start_utc = 2026-09-26T12:00:00+00:00

Schedule-provenance limitation:
- the 365Scores rendered display did not expose an explicit timezone label in the retrieved text.
- therefore the stored timestamp is preserved append-only as the pipeline interpretation used at freeze time.
- freeze prospectivity is safe even under the plausible local/UTC interpretation gap because the freeze occurred on 25-SEP-2026 at 18:03:16 UTC, well before 26-SEP play.
- if a later official order-of-play gives a different exact timestamp, record an append-only schedule correction artifact; do not rewrite the probability or freeze timestamp.

## Strict prefeature ordering

Prefeature artifact:
- evidence/cor0203/runtime/MATRIX_COR0203_PREFEATURE_REGISTRY_R718.json

Prefeature commit:
- bfe46a8c0f780fdfdd039b5927fd6f3a9a7f51d5

At preregistration:
- starting_observation_count = 8
- features_loaded = false
- outcome = null
- metrics_opened = false
- odds_used = false

## PIT STATIC4

Artifact:
- evidence/cor0203/runtime/MATRIX_COR0203_STATIC4_R718.json

Commit:
- a9cfdd1b24266395a2d6e4caef02de0d8ed483b1

No new ranking scrape was used.
The exact 21-SEP player state already physically frozen in R707 was reused unchanged:

Harold Mayot:
- source_id M0G4
- hand R
- age 24.627
- rank 237
- rank_points 233

Murphy Cassone:
- source_id C0HT
- hand R
- age 24.099
- rank 318
- rank_points 169

## Prospective batch

Artifact:
- evidence/cor0203/runtime/MATRIX_COR0203_PROSPECTIVE_EVENTS_R718.json

Commit:
- 5f93143b32800b10431e3ed47e5696e6f7cdb9cd

Event:
- COR0203-R718-STT-MAYOT-CASSONE
- Saint-Tropez SF
- Hard
- target_period = 20260921
- starting_observation_count = 8

## First batch attempt — fail closed

Initial governed batch run:
- 36170903777
- conclusion = failure

The failure occurred BEFORE history scoring and BEFORE any freeze.

Root cause:
- the workflow wrote FREEZE_AT to GITHUB_ENV and attempted to read os.environ['FREEZE_AT'] inside the same GitHub Actions step.
- GitHub Actions does not expose a value written to GITHUB_ENV back into the current step process.
- exact failure: KeyError: 'FREEZE_AT'

Effects:
- invalid freezes written = 0
- probability rewrites = 0
- outcome reads for performance = 0
- holdout increment from failed attempt = 0

## Root-cause workflow repair

Workflow:
- .github/workflows/cor0203-batch-freeze.yml

Repair:
- export FREEZE_AT in the current shell before same-step Python validation.
- continue writing FREEZE_AT to GITHUB_ENV for subsequent steps.

Repair commit:
- ebec6eb2015d0f9d047ea75358db5e18e17585b7

Regression test:
- tests/test_r718_semifinal_freeze.py

Test commit:
- 785b0a583603a7635956c9341d7936e424e701dd

## Successful governed R718 freeze

Successful batch run:
- 36170967289
- completed / success

Workflow-repair MATRIX CI:
- 36170967489
- completed / success

Freeze commit:
- 44756809b76e14d2ff79db5e65b3860bc10ab40a

History gate:
- evidence/cor0203/runtime/MATRIX_COR0203_HISTORY_GATE_R718.json
- PASS
- annual_rows_used_preperiod = 5313
- annual_periods_used_preperiod = 38
- same_period_results_used = false
- silent_imputation = false
- Harold Mayot n_history = 184; ELO present; Glicko present
- Murphy Cassone n_history = 89; ELO present; Glicko present

Holdout artifact:
- evidence/cor0203/holdout/MATRIX_COR0203_HOLDOUT_BATCH_R718.json

Freeze:
- freeze_at_utc = 2026-09-25T18:03:16+00:00
- stored event_start_utc = 2026-09-26T12:00:00+00:00
- freeze strictly pre-start

## Observation 9

Alphabetical orientation:
- player_a = Harold Mayot
- player_b = Murphy Cassone

R218_ELO_BOTH:
- p(Harold Mayot) = 0.590324156023151
- p(Murphy Cassone) = 0.409675843976849

R223_BATCH_GLICKO_RATING_BOTH:
- p(Harold Mayot) = 0.5566867602439216
- p(Murphy Cassone) = 0.4433132397560784

Control probability window 1:
- 0.4967308051559873

Hashes:
- feature_snapshot_sha256 = 7c5c2c60e933e76d0e158581ddc561706f68a02ffb032a46dad65795cdee9ccf
- observation_sha256 = ce507864c7606c0e51f3205123ea045ce6fbe69645f9522c8251b78841e19777
- batch_sha256 = d8a33307b2975c264484ef466d1b4575440266aa7c427ba43c70049e283e51c8
- annual_2026_sha256 = d3f0e7edca273d0e1fcd4700581cf00398e46719f0aaadb62a1c97ec0ffa6ab5
- bundle_sha256 = ef5788fa4212c67880a52af85359bed1483ba1d59b1655e28390bbfaf0187ec8

At freeze:
- outcome = null
- metrics_opened = false
- odds_used = false
- historical_backfill = FORBIDDEN
- REAL_MONEY = BLOCKED

## Holdout counter after R718

- Window 1 = 9/200
- Window 2 = 0/200
- Window 3 = 0/200
- Total = 9/600
- Metrics = SEALED_UNTIL_600
- Outcomes read for performance = 0

No prior observation was removed, repurposed or rewritten.

## San Diego frontier

At the R718 check, San Diego 2 semifinal rows still contained placeholders:
- WQF1 vs WQF2
- WQF3 vs WQF4

Therefore:
- new San Diego semifinal preregistrations = 0
- placeholder inflation = 0
- retrospective conversion = 0

The next San Diego semifinal may enter only after both quarterfinal winners are FINAL and the future semifinal identity is fixed.

## Audit state

RESOLVED:
- COR01
- COR04
- COR05
- COR06
- COR07
- COR08
- COR09
- COR12

IN_PROGRESS:
- COR02
- COR03
- COR10
- COR11

COR11 remains 5/14 on local date 25-SEP-2026.
GO/NO-GO remains 4/8 YES.
External audit = NOT CLOSED.
REAL_MONEY = BLOCKED.
Ordinary sports production remains PAUSED except audit/validation evidence.
