# Provider Temporal Truth & Revision Policy V23

## Purpose

MATRIX must preserve both **what a provider says is true about an event** and **when MATRIX first knew that information**. Provider corrections, revisions, retractions, and late-arriving changes must never rewrite historical decision evidence as though the corrected value had been known earlier.

## Core rules

1. Every provider fact version is immutable and fingerprinted with SHA-256.
2. A truth chain begins with exactly one `INITIAL` version and thereafter progresses linearly through explicit supersession.
3. `PROGRESSION` represents new event knowledge as time advances. `CORRECTION` and `RETRACTION` represent a provider revision of previously published knowledge.
4. Every correction/retraction must declare a reason and exact correction scope.
5. Undeclared correction deltas fail closed. Declared scopes with no actual delta produce review evidence rather than silent acceptance.
6. Provider identity, canonical fixture identity, competition, home/away identity, and provider fixture identity may not be silently rewritten inside a truth chain.
7. Score, event-state, and kickoff corrections are high-impact and require human review under the V23 policy.
8. Corrections that arrive materially later than their effective event time are surfaced for review; they are not silently normalized away.
9. Point-in-time queries are bitemporal: they filter by both `known_at` and `valid_from_event_time`.
10. A historical decision may only use truth that was known at or before the decision timestamp. Later provider corrections may never be injected into the frozen decision evidence.
11. Backtests and training features must be built using the truth reconstructable at the feature cutoff. Labels may be known later, but feature inputs may not use later revisions.
12. A later correction may require controlled re-analysis, but the correction alone does **not** determine that the original analysis was good or bad. That judgment must be evaluated against the evidence actually available at decision time.
13. Provider revision evidence is append-only, hash chained, cross-process locked, flushed, and fsynced. A corrupt ledger cannot accept a new append.
14. V23 does not silently backfill historical decisions, promote models, switch providers, or enable wagering.

## Bitemporal model

For each truth version MATRIX records at minimum:

- provider identity;
- canonical fixture identity;
- provider fixture identity;
- immutable provider snapshot;
- `known_at`: when MATRIX had the version available;
- `valid_from_event_time`: the event-time point from which that version applies;
- revision kind;
- explicit predecessor;
- correction scope and reason when relevant;
- SHA-256 evidence reference;
- human-review evidence when required.

This allows two distinct questions:

- **What do we currently believe happened at minute X?**
- **What did MATRIX actually know at minute X when the decision was made?**

Those questions must never be conflated.

## Safety invariants

- `future_knowledge_used = FALSE`
- `historical_backfill_allowed = FALSE`
- `automatic_provider_switch = FALSE`
- `automatic_model_promotion = FALSE`
- `automatic_wagering = FALSE`
- `production_certified = FALSE` until the consolidated package is integrated and verified in the real repository.
