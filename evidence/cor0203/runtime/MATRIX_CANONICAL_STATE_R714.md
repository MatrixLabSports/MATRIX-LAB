# MATRIX CANONICAL STATE R714

Ancestor: R713.
Targets: COR02 / COR03 volume conversion and anti-stagnation.

## Physical holdout state

- Window 1 = 8/200
- Window 2 = 0/200
- Window 3 = 0/200
- Total = 8/600
- Metrics = SEALED_UNTIL_600
- Outcomes read for performance = 0
- REAL_MONEY = BLOCKED

No observation was removed or reclassified.

## Worldwide conversion sweep

Artifact:
- evidence/cor0203/runtime/MATRIX_COR0203_WORLD_SWEEP_R714.json

Current ATP Challenger Hard reconciliation:

### Saint-Tropez
All four identity-fixed quarterfinals are already represented by valid holdout observations 1-4.
No new non-duplicate identity-fixed future match exists until quarterfinal FINAL results determine semifinal identities.

### San Diego 2
All four identity-fixed quarterfinals are already represented by valid holdout observations 5-8.
Observation 8 is Basavareddy-Andrade from R713.
No new non-duplicate identity-fixed future match exists until quarterfinal FINAL results determine semifinal identities.

### Next eligible tournaments
- Eupago Porto Open — Hard — 28 Sep to 4 Oct — no identity-fixed ATP singles draw recovered at this sweep.
- Columbus Challenger — Indoor Hard — 28 Sep to 4 Oct — current public evidence exposes an entry list, not a draw.
- Open de Vendée — Indoor Hard — qualifying scheduled from 27 Sep; current public schedule exposes no individual matches yet.
- Jingshan Open — Hard — qualifying event 28-29 Sep exists; no identity-fixed qualifying/main-draw match recovered yet.

R714 therefore adds:
- new identity-fixed rows = 0
- new preregistrations = 0
- new freezes = 0
- holdout increment = 0

This is a fail-closed inventory result, not a production failure.

## Root-cause scale repair

The prior R713 workflow was valid but event-specific. R714 adds reusable batch infrastructure so future conversion does not require one bespoke workflow per match.

New reusable gate:
- tools/cor0203_batch_linkage_gate.py

New regression tests:
- tests/test_cor0203_batch_linkage_gate.py

New reusable workflow:
- .github/workflows/cor0203-batch-freeze.yml

The batch path enforces:
1. newest prospective manifest is resolved deterministically;
2. already-frozen revision is a no-op, preventing duplicates;
3. physical current holdout count must equal manifest starting count;
4. every event must have a physically prior prefeature registration;
5. prefeature row must have features_loaded=false, outcome=null, metrics_opened=false;
6. placeholders and duplicate event ids are forbidden;
7. freeze must be strictly before start;
8. only ATP Challenger Hard enters;
9. every player must have authorized pre-period history, ELO state and Glicko state;
10. same-period results are excluded;
11. R218_ELO_BOTH and R223_BATCH_GLICKO_RATING_BOTH are used;
12. outcomes remain null and metrics remain sealed;
13. one future batch may contain multiple events and may advance 8 -> 9,10,11... in one governed run.

The existing producer tools/cor0203_prospective_producer.py already supports multiple events per batch; R714 closes the missing admission/linkage and orchestration controls.

## Validation

World-sweep commit:
- dd70707df0a934699987e392a6588402024062f5
- MATRIX CI push and PR runs = success.

Batch-linkage implementation commit:
- 63c16650d6c20966a2ccca8a18d57b149dd868a6
- MATRIX CI = success.

Batch-linkage tests commit:
- 20ae429be9234fec8203c0a2a40900e1533033da
- push CI = success; PR CI pending/completing at canonicalization time.

Reusable batch workflow commit:
- 9f3ca5b7f377b71500faa56ecc149e2bf6fbad0a
- governed batch-freeze self-check run 36132354485 = completed / success.
- The self-check correctly detected that R713 was already frozen and skipped all duplicate freeze/commit steps.

## Next legitimate conversion triggers

The next observation(s) can be created immediately when one of these becomes physically true before start:
- a San Diego 2 semifinal identity is fixed after a quarterfinal reaches FINAL and a future exact start exists;
- a Saint-Tropez semifinal identity is fixed after a quarterfinal reaches FINAL and a future exact start exists;
- Porto, Columbus, Mouilleron-le-Captif or Jingshan publishes qualifying/main-draw matches with two real identities and future exact start times.

At that point the next batch is:
prefeature registry -> STATIC4/PIT -> prospective events manifest -> reusable R714 batch workflow -> R218/R223 -> sealed freeze batch.

## Audit state

Resolved:
COR01, COR04, COR05, COR06, COR07, COR08, COR09, COR12.

In progress:
COR02, COR03, COR10, COR11.

GO/NO-GO remains 4/8 YES.
External audit = NOT CLOSED.
Ordinary sports production remains PAUSED except audit/validation evidence.
