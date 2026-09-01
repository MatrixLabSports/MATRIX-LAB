# MATRIX FÚTBOL — Prospective Shadow V1

Status: `PRE_FREEZE_RESEARCH_ONLY`.

Purpose: run the already-existing MATRIX football operational baseline on genuinely future
fixtures and freeze its diagnostic probabilities before kickoff so calibration errors can be
measured later without hindsight.

This lane is intentionally separate from official PAPER_TRADING and from the odds-aware
`FootballProspectiveEvidenceLedger`.

## Guarantees

- Uses `build_football_operational_analysis`; it does not replace the existing MATRIX model.
- Refuses to freeze a prediction at or after kickoff.
- Refuses insufficient-data evaluations.
- Binds every prediction to exact repository HEAD and model input SHA-256.
- Append-only hash-chained JSONL ledger.
- Outcomes are separate append-only events and cannot rewrite frozen predictions.
- Supports post-settlement multiclass Brier/log-loss plus Brier for O1.5/O2.5/O3.5/BTTS.
- No bookmaker integration is implied.
- No EV/CLV claim is made without authorized timestamped odds.
- No model promotion, official paper trading, CONTROLLED_LIVE, production, or wagering.

This lane is for empirical error discovery while the formal Scope/Selection/Freeze governance
chain continues independently.
