# MATRIX CANONICAL STATE R712

Ancestor: R711.
Targets: COR02 / COR03 calendar separation and governed prospective inventory.

## World calendar separation

The world tennis calendar is now physically populated before COR02/COR03 filtering.

Artifact:
- `evidence/world_calendar/MATRIX_WORLD_TENNIS_CALENDAR_R712.json`

Current+next operational-week tournament denominator:
- WORLD_CALENDAR_COUNT = 16 tournaments

This universe intentionally preserves:
- ATP main-tour events,
- ATP Challenger events,
- Hard and Clay,
- events outside COR02/COR03.

It MUST NOT be renamed or interpreted as the COR02/COR03 denominator.

## COR02/COR03 derived calendar

Artifact:
- `evidence/cor0203/runtime/MATRIX_COR0203_ELIGIBLE_CALENDAR_R712.json`

Derived tournament pool:
- COR0203_ELIGIBLE_TOURNAMENT_COUNT = 6

Eligible tournament pools:
1. Saint-Tropez Open — Hard
2. San Diego 2 / Tennis Warehouse Open — Hard
3. Eupago Porto Open — Hard
4. Columbus Challenger — Indoor Hard
5. Open de Vendée / Mouilleron-le-Captif — Indoor Hard
6. Jingshan Open — Hard

Clay Challengers and ATP main-tour events remain in WORLD_CALENDAR but do not enter COR02/COR03.

## Match-level projection

Existing valid holdout observations remain:
1. Glinka–Prizmic
2. Lajal–Droguet
3. Masur–Cassone
4. Mayot–De Jong
5. Gomez–Marcondes
6. Dietrich–Searle
7. Boyer–Legout

New identity-fixed candidate discovered:
- Nishesh Basavareddy vs Andres Andrade — San Diego 2 QF

Current gate state:
- identity_fixed = true
- exact start authority = insufficiently consolidated
- preregistered = false
- features_loaded = false
- new freeze = false
- holdout increment = 0

Fail-closed reason:
Public sources confirm the quarterfinal identity and Friday quarterfinal session, but exact-match start-time evidence is not sufficiently authoritative/consistent for the prospective freeze contract. No feature acquisition is allowed before valid preregistration.

## Holdout

- Window 1 = 7/200
- Window 2 = 0/200
- Window 3 = 0/200
- Total = 7/600
- Metrics = SEALED_UNTIL_600
- Outcomes read for performance = 0

## Regression protections

Code:
- `app/research/tennis/world_calendar_registry.py`

Tests:
- `tests/test_world_calendar_registry.py`
- `tests/test_r712_calendar_derivation.py`

Protected invariants:
- world calendar is preserved before model-domain filtering
- COR02/COR03 is a derived subset
- denominators are distinct
- duplicates do not inflate counts
- placeholders do not become identity-fixed matches
- out-of-domain events stay visible in world calendar
- no holdout increment without valid prospective freeze
- no feature loading before preregistration
- no historical backfill
- no odds-to-P
- no silent imputation

## Validation

Artifact:
- `evidence/cor0203/runtime/MATRIX_R712_WORLD_CALENDAR_VALIDATION.json`

MATRIX CI:
- run 36126047078 = completed / success

## Audit status

Resolved:
COR01, COR04, COR05, COR06, COR07, COR08, COR09, COR12.

In progress:
- COR02
- COR03
- COR10
- COR11

GO/NO-GO = 4/8 YES.
External audit = NOT CLOSED.
REAL_MONEY = BLOCKED.
Ordinary sports production remains PAUSED except audit/validation evidence.

## Next admissible conversion

The next legitimate holdout increment requires one of:
- Basavareddy–Andrade obtaining sufficiently authoritative exact future start evidence before start, or
- a newly published identity-fixed future match from Porto, Columbus, Mouilleron-le-Captif or Jingshan.

Only then:
preregister -> load PIT features -> R218/R223 -> freeze -> 8/200.
