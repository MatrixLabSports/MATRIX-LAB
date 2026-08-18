# MATRIX FÚTBOL — Prospective Evidence Ledger

## Purpose

This module prevents hindsight from being counted as evidence for live-money promotion. A prediction only counts when it is frozen **before kickoff**, tied to a timestamped authorized odds snapshot, and written to an append-only SHA-256 hash chain. The result is recorded later as a separate settlement event.

## Evidence lifecycle

1. `DECISION_FROZEN` — model version, probability, market, selection, entry odds, source, input hashes and kickoff are frozen before the match.
2. `CLOSING_ODDS_RECORDED` — a reference price is captured after the decision but still before kickoff, allowing closing-line-value (CLV) measurement.
3. `SETTLEMENT_RECORDED` — result is attached only after kickoff with its own source hash.
4. Every event contains the previous event digest. Editing, removing or reordering an event invalidates the ledger.
5. The ledger is summarized per `market_key + model_version`; evidence from one market or model version cannot promote another.

## Promotion safeguards

Controlled-live review now additionally requires:

- sufficient closing-odds observations;
- verified closing-odds timestamp/source integrity;
- prospective paper-trading performance within policy limits;
- positive CLV confirmed by a deterministic block-bootstrap confidence interval;
- all existing protected-test, calibration, baseline, walk-forward, governance, risk, compliance and human-approval gates.

The module **never transmits or places a wager**. `automatic_wager_execution_enabled` remains permanently false in this gate. A future controlled-live decision still requires explicit human approval.

## Why this is necessary

Backtests and retrospective analyses are not enough for real-money readiness because they can hide timestamp leakage, selection bias, stale prices and overfitting. Prospective freezing plus closing-line comparison provides a harder-to-game record of what the system actually knew, when it knew it, and whether its quoted edge survived market movement.
