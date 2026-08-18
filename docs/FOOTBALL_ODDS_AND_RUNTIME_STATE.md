# Football Odds & Runtime State Gate

Status: **TECHNICALLY_VERIFIED foundation; not permission for real-money wagering.**

This block closes two P0 gaps required before controlled-live review:

1. **Canonical odds evidence** — provider, event, bookmaker, market, selection, decimal odds,
   provider quote time, capture time, phase, execution/reference role, source payload SHA-256,
   and source reference are persisted in an append-only hash-chained ledger.
2. **Persistent risk runtime state** — bankroll, peak/day-start bankroll, daily/open/market
   exposure, manual kill-switch and consumed human approvals survive process restarts through an
   append-only hash-chained event ledger.

## Execution vs reference odds

`EXECUTION` is the quote that could actually be submitted to the bookmaker available to the user.
`REFERENCE` is a governed market-price source used for closing-line and calibration evidence. They
must never be silently substituted for each other.

The current authorized provider boundary supports API-Football and The Odds API at the software
contract level. Provider authorization for production remains a governance/compliance decision and
must be recorded before controlled-live review.

## Closing-line rule

A closing reference quote must be pre-match, timestamped at or before kickoff, inside the governed
closing window, from an authorized provider, and pass capture-latency checks. Post-kickoff quotes
cannot be used as a closing line.

## Fail-closed runtime rules

- Runtime state cannot be rebuilt if the hash chain is altered.
- A human approval ID can be consumed once only.
- Exposure cannot be settled for more than is open.
- Daily rollover is blocked while exposure remains open.
- A manual kill-switch persists across process restarts.
- Automatic wager execution remains disabled.

## Remaining P0 gates

- Confirm a licensed/contractually authorized production odds source and credentials.
- Add scheduled capture of execution and reference quotes with provider health/quota monitoring.
- Map provider event IDs to canonical fixture IDs with ambiguity rejection.
- Persist production runtime ledgers in PostgreSQL with transactional locking and backup/restore.
- Accumulate prospective paper-trading evidence and prove calibration/CLV/edge stability.
- Complete compliance/legal review for the intended operating jurisdictions and product model.
