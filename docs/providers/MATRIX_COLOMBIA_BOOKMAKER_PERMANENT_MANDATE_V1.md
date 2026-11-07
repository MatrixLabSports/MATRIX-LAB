# MATRIX-LAB-SPORTS — Permanent Colombia Bookmaker & Price Architecture Mandate V1

Effective date: 2026-09-28
Mode: PERMANENT + ADDITIVE
Status: ACTIVE
Scope: football + tennis price comparison, execution-candidate selection, EV, stake and prematch price freeze.

## Permanent mandate

The Colombia bookmaker and price-comparison architecture prepared on 2026-09-28 is a permanent, additive component of MATRIX-LAB-SPORTS.

It must not be silently omitted, downgraded, replaced, bypassed or forgotten in future revisions, prompts, handoffs, automations or model changes.

It may only be REPLACED, MODIFIED, SUSPENDED or REVOKED by an explicit user instruction.

## Permanent Colombia execution-candidate portfolio

The governed execution-candidate portfolio is:

1. Betano
2. BetPlay
3. Betsson
4. Bwin
5. Codere
6. Luckia
7. MrYoker
8. Rivalo
9. RushBet
10. Sportium
11. Stake Colombia
12. Wplay
13. YaJuego
14. Zamba

These are execution candidates only after current regulatory eligibility and physical provider visibility are verified.

## Permanent non-execution classifications

- Pinnacle: REFERENCE_ONLY_NOT_COLOMBIA_EXECUTION.
- Unibet: QUARANTINED pending Colombia regulatory reconciliation.
- Bingo Casino: QUARANTINED pending regulator/provider reconciliation.

No future workflow may silently promote any reference-only or quarantined book to execution status.

## Permanent price path

The required order is:

P_MATRIX
→ exact canonical market identity
→ bookmaker quotes
→ freshness + availability + prematch gates
→ exact-line comparison
→ best valid price
→ implied probability
→ expected value
→ calibration/risk-adjusted stake
→ prematch freeze
→ append-only ledger

## Hard invariants

- Odds must never generate P_MATRIX.
- P_MATRIX must exist before price/EV selection.
- Only exactly equivalent market contracts may compete:
  sport + event + market + canonical market version + bet type + metric + period + line + side + selection + provider contract parameters where applicable.
- Different lines must never be compared as the same wager.
- Permanent minimum decimal odds rule remains strictly > 1.50.
- Stale, unavailable, post-start or non-execution quotes are rejected.
- Unmapped provider markets are fail-closed for execution.
- Best price is selected only among valid execution candidates.
- Expected value is computed only after P_MATRIX.
- Non-positive EV remains NO_BET.
- Stake is not fixed and must remain risk/calibration aware.
- Stake requires calibration gate PASS and REAL_MONEY gate OPEN.
- REAL_MONEY remains BLOCKED until separately and explicitly governed open conditions are met.
- Automatic wagering remains FALSE unless separately and explicitly authorized under future governance.
- Prematch freeze is mandatory.
- Price freezes are append-only and hash-chained.
- Duplicate freezes are rejected.
- Architecture-ready does not mean provider-active.
- Provider-visible does not mean regulator-authorized.
- Documentation does not equal physical provider usage.
- A bookmaker cannot be called VERIFIED_USED without current physical network evidence and persisted provenance.

## Activation timing

No odds-api.net subscription is required now.

Activation is intentionally deferred until price comparison is operationally useful, near controlled-live readiness.

Future activation procedure:
1. Purchase/enable provider only when justified.
2. Store ODDS_API_NET_KEY only as a GitHub Actions secret.
3. Perform a governed physical Colombia catalog probe.
4. Persist raw bytes, SHA-256, timestamps and rate metadata.
5. Promote only regulator-eligible books physically present in the feed.
6. Verify at least one football snapshot and one tennis snapshot.
7. Run shadow price comparison with REAL_MONEY still BLOCKED.
8. Validate end-to-end freeze/ledger behavior.
9. Controlled-live eligibility remains dependent on calibration and audit gates.

## Regression rule

CI must fail if the permanent portfolio or hard invariants are silently weakened.

At minimum CI must protect:
- the 14 execution-candidate keys;
- Pinnacle reference-only classification;
- Unibet/Bingo quarantine;
- odds-to-P_MATRIX prohibition;
- >1.50 minimum odds;
- exact-line/canonical-market matching;
- calibration and real-money stake gates;
- automatic_wagering = false;
- provider-not-activated state until physical credentialed evidence exists.

## Truthfulness rule

If physical repository state conflicts with memory, chat, a prompt or a summary, the physical governed artifacts win.

## Change control

This mandate is permanent until the user explicitly REPLACES, MODIFIES, SUSPENDS or REVOKES it.
