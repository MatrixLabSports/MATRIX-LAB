# MATRIX Telegram SHADOW Bridge — Governance Baseline

Date: 2026-10-05/06 UTC
Mode: SHADOW
REAL_MONEY: BLOCKED
AUTO_BETTING: DISABLED

## Purpose
Connect only genuinely authorized prospective MATRIX signals to the Telegram notification lane. This bridge is fail-closed and does not place wagers.

## Mandatory gates
- `daily_p_matrix == GENERATED`.
- Candidate has numeric `p_matrix` in (0,1).
- Decimal odds strictly greater than 1.50.
- Prematch freeze timestamp exists and is before event start.
- Event has not started.
- EV is recomputed as `p_matrix * decimal_odds - 1` and must be positive.
- `NO_BET`, `WATCHLIST`, and `RESEARCH_SIGNAL` adjudications cannot be promoted.
- `REAL_MONEY` must remain `BLOCKED`.
- `automatic_wagering` must remain `false`.

## Current physical source adjudication
The 2026-10-05 football adjudication on the operational branch declares `daily_p_matrix = NOT_GENERATED`. Therefore the correct bridge result for that source is BLOCKED and zero Telegram picks. This is intentional evidence of fail-closed behavior, not a missing signal.

## Code evidence
- `tools/telegram_shadow_bridge.py`
- `tests/test_telegram_shadow_bridge.py`

No sportsbook write path exists in this bridge.
